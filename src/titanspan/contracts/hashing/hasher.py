"""Define dependency-independent password hashing service contracts.

Concrete algorithms and their encoded formats remain owned by the Hashing
component and its selected password-hashing dependency.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, runtime_checkable

_ALGORITHM_REQUIRED_ERROR = "A hash algorithm identifier is required."
_REPLACEMENT_INVARIANT_ERROR = (
    "A failed verification cannot replace its stored hash."
)


@dataclass(frozen=True, slots=True)
class HashMetadata:
    """Describe one recognized encoded password hash.

    Attributes:
        algorithm: Algorithm identifier parsed from the encoded hash.
        parameters: Immutable work-factor values supported by its format.
    """

    algorithm: str
    parameters: Mapping[str, int | str]

    def __post_init__(self) -> None:
        """Freeze parameter values supplied by the backend adapter.

        Copying prevents later mutation from changing inspection results.
        """
        if not self.algorithm or not self.algorithm.strip():
            raise ValueError(_ALGORITHM_REQUIRED_ERROR)
        object.__setattr__(
            self,
            "parameters",
            MappingProxyType(dict(self.parameters)),
        )


@dataclass(frozen=True, slots=True)
class HashVerification:
    """Report password verification and an optional replacement hash.

    Attributes:
        verified: Whether the supplied password matched the stored hash.
        replacement_hash: A stronger hash to persist after successful verify.
    """

    verified: bool
    replacement_hash: str | None = None

    def __post_init__(self) -> None:
        """Keep failed verification from carrying a replacement hash.

        Callers may persist a replacement only after a successful check.
        """
        if not self.verified and self.replacement_hash is not None:
            raise ValueError(_REPLACEMENT_INVARIANT_ERROR)


@runtime_checkable
class Hasher(Protocol):
    """Hash and verify passwords through an application-owned service.

    Synchronous calls perform blocking password work. Async calls offload that
    work through the backend's bounded worker mechanism.
    """

    @property
    def algorithm(self) -> str:
        """Return the algorithm used for newly generated hashes.

        The value names the format used by ``make`` and upgrade operations.
        """
        ...

    def make(self, password: str) -> str:
        """Generate an encoded password hash using a secure random salt.

        Args:
            password: Exact password text; the implementation does not trim
                or truncate it.

        Returns:
            Encoded hash containing the salt and work parameters.
        """
        ...

    async def make_async(self, password: str) -> str:
        """Generate a hash without blocking the event loop.

        Args:
            password: Exact password text.

        Returns:
            Encoded hash containing the salt and work parameters.
        """
        ...

    def check(self, password: str, hashed_password: str) -> bool:
        """Check a password against a recognized encoded hash.

        Args:
            password: Candidate password text.
            hashed_password: Stored encoded hash.

        Returns:
            Whether the exact candidate matches. Malformed or unsupported
            hashes return ``False``.
        """
        ...

    async def check_async(
        self,
        password: str,
        hashed_password: str,
    ) -> bool:
        """Check a password without blocking the event loop.

        Args:
            password: Candidate password text.
            hashed_password: Stored encoded hash.

        Returns:
            Whether the exact candidate matches.
        """
        ...

    def needs_rehash(self, hashed_password: str) -> bool:
        """Report whether a recognized hash uses older settings.

        Args:
            hashed_password: Stored encoded hash.

        Returns:
            Whether it uses a different algorithm or weaker parameters.

        Raises:
            HashInspectionError: If the hash is malformed or unsupported.
        """
        ...

    def inspect(self, hashed_password: str) -> HashMetadata | None:
        """Return supported algorithm and work-factor metadata.

        Args:
            hashed_password: Stored encoded hash.

        Returns:
            Immutable metadata, or ``None`` for malformed or unsupported
            encodings.
        """
        ...

    def verify_and_rehash(
        self,
        password: str,
        hashed_password: str,
    ) -> HashVerification:
        """Verify a password and upgrade its hash when settings changed.

        Args:
            password: Candidate password text.
            hashed_password: Stored encoded hash.

        Returns:
            Verification status and an optional replacement hash. Callers
            must persist a replacement after successful verification.
        """
        ...

    async def verify_and_rehash_async(
        self,
        password: str,
        hashed_password: str,
    ) -> HashVerification:
        """Verify and optionally rehash without blocking the event loop.

        Args:
            password: Candidate password text.
            hashed_password: Stored encoded hash.

        Returns:
            Verification status and an optional replacement hash.
        """
        ...


__all__ = ["HashMetadata", "HashVerification", "Hasher"]
