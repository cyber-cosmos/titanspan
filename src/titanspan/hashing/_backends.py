"""Adapt established password hashing libraries to the native contract.

Argon2-CFFI and PyCA Bcrypt own password hashing and verification. This
adapter adds safe errors, metadata, and explicit asynchronous offloading.
"""

from __future__ import annotations

import re
from functools import partial
from typing import TYPE_CHECKING, TypeGuard

import anyio
import bcrypt
from argon2 import PasswordHasher, Type, extract_parameters
from argon2.exceptions import Argon2Error

from titanspan.contracts.hashing import (
    Hasher,
    HashMetadata,
    HashVerification,
)
from titanspan.hashing.configuration import Argon2Configuration
from titanspan.hashing.exceptions import (
    HashGenerationError,
    HashInspectionError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from titanspan.hashing.configuration import (
        BcryptConfiguration,
        HashingConfiguration,
    )

_STRING_INPUT_ERROR = "Password values must be strings."
_GENERATION_ERROR = "The password hash could not be generated."
_INSPECTION_ERROR = "The password hash is malformed or unsupported."
# Version 19 is the current Argon2 format used by the locked backend.
_ARGON2_CURRENT_VERSION = 19
_ARGON2_PREVIOUS_VERSION = 16
_ARGON2_PHC_PART_COUNT = 6
_ARGON2_MIN_TIME_COST = 1
_ARGON2_MIN_PARALLELISM = 1
_ARGON2_MIN_MEMORY_PER_LANE = 8
_ARGON2_MIN_HASH_LENGTH = 4
_ARGON2_MIN_SALT_LENGTH = 8
_BCRYPT_MAX_BYTES = 72
_BCRYPT_MIN_ROUNDS = 4
_BCRYPT_MAX_ROUNDS = 31
_BCRYPT_PATTERN = re.compile(
    r"\$(?P<prefix>2[aby])\$(?P<rounds>\d{2})\$"
    r"[./A-Za-z0-9]{53}\Z",
    re.ASCII,
)
_ARGON2_ALGORITHMS = {
    Type.ID: "argon2id",
    Type.I: "argon2i",
    Type.D: "argon2d",
}


def _is_string(value: object) -> TypeGuard[str]:
    """Confirm untrusted runtime values are strings.

    Args:
        value: Value supplied to a public hashing operation.

    Returns:
        Whether the value is a string.
    """
    return isinstance(value, str)


async def _run_in_worker[ResultT](operation: Callable[[], ResultT]) -> ResultT:
    """Run password work in a bounded thread and then observe cancellation.

    Args:
        operation: Synchronous backend operation with captured arguments.

    Returns:
        The operation result after its worker has completed.
    """
    result = await anyio.to_thread.run_sync(
        operation,
        abandon_on_cancel=False,
    )
    # Hashing cannot be forcibly stopped; deliver cancellation after the
    # bounded worker completes instead of silently returning a late result.
    await anyio.lowlevel.checkpoint()
    return result


def _argon2_metadata(hashed_password: str) -> HashMetadata | None:
    """Read standard Argon2 PHC parameters through its public parser.

    Args:
        hashed_password: Encoded value supplied for inspection.

    Returns:
        Supported algorithm and work factors, or ``None`` for malformed
        parameter text.
    """
    parts = hashed_password.split("$")
    if (
        len(parts) != _ARGON2_PHC_PART_COUNT
        or parts[0]
        or not parts[2].startswith("v=")
    ):
        return None
    parameter_items = parts[3].split(",")
    parameter_names: list[str] = []
    for item in parameter_items:
        name, separator, _ = item.partition("=")
        if not separator or not name:
            return None
        parameter_names.append(name)
    if len(parameter_names) != len(set(parameter_names)) or set(
        parameter_names
    ) != {"m", "t", "p"}:
        return None
    try:
        parameters = extract_parameters(hashed_password)
    except (Argon2Error, TypeError, ValueError):
        return None
    if (
        parameters.version
        not in (_ARGON2_PREVIOUS_VERSION, _ARGON2_CURRENT_VERSION)
        or parameters.time_cost < _ARGON2_MIN_TIME_COST
        or parameters.parallelism < _ARGON2_MIN_PARALLELISM
        or parameters.memory_cost
        < _ARGON2_MIN_MEMORY_PER_LANE * parameters.parallelism
        or parameters.hash_len < _ARGON2_MIN_HASH_LENGTH
        or parameters.salt_len < _ARGON2_MIN_SALT_LENGTH
    ):
        return None
    algorithm = _ARGON2_ALGORITHMS.get(parameters.type)
    if algorithm is None:
        return None
    return HashMetadata(
        algorithm=algorithm,
        parameters={
            "version": parameters.version,
            "memory_cost_kib": parameters.memory_cost,
            "time_cost": parameters.time_cost,
            "parallelism": parameters.parallelism,
            "hash_length": parameters.hash_len,
            "salt_length": parameters.salt_len,
        },
    )


def _bcrypt_metadata(hashed_password: str) -> HashMetadata | None:
    """Read Bcrypt prefix and cost from its standard encoded form.

    Args:
        hashed_password: Encoded value supplied for inspection.

    Returns:
        Supported Bcrypt metadata, or ``None`` for malformed encodings.
    """
    match = _BCRYPT_PATTERN.fullmatch(hashed_password)
    if match is None:
        return None
    rounds = int(match.group("rounds"))
    if not _BCRYPT_MIN_ROUNDS <= rounds <= _BCRYPT_MAX_ROUNDS:
        return None
    return HashMetadata(
        algorithm="bcrypt",
        parameters={
            "prefix": match.group("prefix"),
            "rounds": rounds,
        },
    )


def _argon2_hasher(configuration: Argon2Configuration) -> PasswordHasher:
    """Create a high-level Argon2 hasher for validated settings.

    Args:
        configuration: Work factors for newly created Argon2id hashes.

    Returns:
        A configured high-level password hasher.
    """
    return PasswordHasher(
        time_cost=configuration.time_cost,
        memory_cost=configuration.memory_cost,
        parallelism=configuration.parallelism,
        hash_len=configuration.hash_length,
        salt_len=configuration.salt_length,
        type=Type.ID,
    )


def _generate_argon2_hash(
    password: str,
    hasher: PasswordHasher,
) -> str:
    """Generate an Argon2 hash with the native password error boundary.

    Args:
        password: Exact password text supplied by the caller.
        hasher: Configured high-level Argon2 hasher.

    Returns:
        Backend-encoded hash with a random salt.

    Raises:
        HashGenerationError: If encoding or backend hashing fails.
    """
    try:
        return hasher.hash(password)
    except (Argon2Error, TypeError, ValueError, UnicodeError):
        raise HashGenerationError(_GENERATION_ERROR) from None


class _NativeHasher(Hasher):
    """Use direct algorithm APIs and normalize native service behavior.

    Backend classes and exceptions remain private to Hashing.
    """

    def __init__(self, configuration: HashingConfiguration) -> None:
        """Create hashers with validated algorithm and work-factor settings.

        Args:
            configuration: Validated algorithms and work-factor settings.
        """
        self._argon2_settings = configuration.argon2id
        self._argon2_hasher = _argon2_hasher(self._argon2_settings)
        self._algorithm = configuration.driver
        self._bcrypt_settings = configuration.bcrypt

    @property
    def algorithm(self) -> str:
        """Return the algorithm used for new password hashes.

        Verification may also recognize supported legacy encodings.
        """
        return self._algorithm

    def make(self, password: str) -> str:
        """Generate a hash without altering or truncating password text.

        Args:
            password: Exact password value supplied by the caller.

        Returns:
            An encoded hash with a backend-generated random salt.

        Raises:
            HashGenerationError: If the dependency rejects the input or work.
        """
        if not _is_string(password):
            raise HashGenerationError(_STRING_INPUT_ERROR)
        try:
            if self._algorithm == "argon2id":
                return _generate_argon2_hash(
                    password,
                    self._argon2_hasher,
                )
            encoded = password.encode("utf-8")
            salt = bcrypt.gensalt(
                rounds=self._bcrypt_settings.rounds,
                prefix=self._bcrypt_settings.prefix.encode("ascii"),
            )
            return bcrypt.hashpw(encoded, salt).decode("ascii")
        except (Argon2Error, TypeError, ValueError, UnicodeError):
            raise HashGenerationError(_GENERATION_ERROR) from None

    async def make_async(self, password: str) -> str:
        """Generate a hash in AnyIO's bounded worker thread pool.

        Args:
            password: Exact password value supplied by the caller.

        Returns:
            An encoded hash with backend-generated random salt.
        """
        return await _run_in_worker(partial(self.make, password))

    def check(self, password: str, hashed_password: str) -> bool:
        """Check a candidate against supported Argon2 or Bcrypt hashes.

        Args:
            password: Candidate password value.
            hashed_password: Stored encoded hash.

        Returns:
            Whether the password matches. Malformed and unknown hashes fail
            closed as ``False``.
        """
        if not _is_string(password) or not _is_string(hashed_password):
            return False
        metadata = self.inspect(hashed_password)
        if metadata is None:
            return False
        try:
            if metadata.algorithm == "bcrypt":
                encoded = password.encode("utf-8")
                if len(encoded) > _BCRYPT_MAX_BYTES:
                    return False
                return bcrypt.checkpw(
                    encoded,
                    hashed_password.encode("ascii"),
                )
            return self._argon2_hasher.verify(hashed_password, password)
        except (Argon2Error, TypeError, ValueError, UnicodeError):
            return False

    async def check_async(
        self,
        password: str,
        hashed_password: str,
    ) -> bool:
        """Check a password in AnyIO's bounded worker thread pool.

        Args:
            password: Candidate password value.
            hashed_password: Stored encoded hash.

        Returns:
            Whether the password matches.
        """
        return await _run_in_worker(
            partial(self.check, password, hashed_password),
        )

    def needs_rehash(self, hashed_password: str) -> bool:
        """Compare a recognized hash with the current driver settings.

        Args:
            hashed_password: Stored encoded hash.

        Returns:
            Whether the algorithm changed or a work factor is below policy.

        Raises:
            HashInspectionError: If the encoding is malformed or unsupported.
        """
        metadata = self.inspect(hashed_password)
        if metadata is None:
            raise HashInspectionError(_INSPECTION_ERROR)
        if metadata.algorithm != self._algorithm:
            return True
        if metadata.algorithm == "bcrypt":
            return (
                int(metadata.parameters["rounds"])
                < self._bcrypt_settings.rounds
            )
        try:
            backend_requires_rehash = bool(
                self._argon2_hasher.check_needs_rehash(
                    hashed_password,
                )
            )
        except (Argon2Error, TypeError, ValueError):
            raise HashInspectionError(_INSPECTION_ERROR) from None
        if not backend_requires_rehash:
            return False
        settings = self._argon2_settings
        parameters = metadata.parameters
        return (
            int(parameters["version"]) < _ARGON2_CURRENT_VERSION
            or int(parameters["time_cost"]) < settings.time_cost
            or int(parameters["memory_cost_kib"]) < settings.memory_cost
            or int(parameters["parallelism"]) < settings.parallelism
            or int(parameters["hash_length"]) < settings.hash_length
            or int(parameters["salt_length"]) < settings.salt_length
        )

    def inspect(self, hashed_password: str) -> HashMetadata | None:
        """Parse supported algorithm and cost fields from an encoded hash.

        Args:
            hashed_password: Stored encoded hash.

        Returns:
            Immutable metadata, or ``None`` for malformed or unsupported
            encodings.
        """
        if not _is_string(hashed_password):
            return None
        if hashed_password.startswith("$argon2"):
            return _argon2_metadata(hashed_password)
        return _bcrypt_metadata(hashed_password)

    def verify_and_rehash(
        self,
        password: str,
        hashed_password: str,
    ) -> HashVerification:
        """Verify a password and upgrade supported legacy hashes.

        Args:
            password: Candidate password value.
            hashed_password: Stored encoded hash.

        Returns:
            Verification result and optional replacement hash.

        Raises:
            HashGenerationError: If a replacement hash cannot be generated.
        """
        if not self.check(password, hashed_password):
            return HashVerification(verified=False)
        if self.needs_rehash(hashed_password):
            metadata = self.inspect(hashed_password)
            if (
                self._algorithm == "argon2id"
                and metadata is not None
                and metadata.algorithm.startswith("argon2")
            ):
                settings = self._settings_at_least(metadata)
                replacement = _generate_argon2_hash(
                    password,
                    _argon2_hasher(settings),
                )
                return HashVerification(
                    verified=True,
                    replacement_hash=replacement,
                )
            return HashVerification(
                verified=True,
                replacement_hash=self.make(password),
            )
        return HashVerification(verified=True)

    async def verify_and_rehash_async(
        self,
        password: str,
        hashed_password: str,
    ) -> HashVerification:
        """Verify and upgrade a hash in AnyIO's bounded worker pool.

        Args:
            password: Candidate password value.
            hashed_password: Stored encoded hash.

        Returns:
            Verification result and optional replacement hash.
        """
        return await _run_in_worker(
            partial(
                self.verify_and_rehash,
                password,
                hashed_password,
            ),
        )

    def _settings_at_least(
        self,
        metadata: HashMetadata,
    ) -> Argon2Configuration:
        """Preserve stronger stored costs when raising another factor.

        Args:
            metadata: Verified Argon2 cost values to preserve.

        Returns:
            Settings no lower than either the current policy or stored hash.
        """
        configured = self._argon2_settings
        parameters = metadata.parameters
        return Argon2Configuration(
            time_cost=max(
                configured.time_cost,
                int(parameters["time_cost"]),
            ),
            memory_cost=max(
                configured.memory_cost,
                int(parameters["memory_cost_kib"]),
            ),
            parallelism=max(
                configured.parallelism,
                int(parameters["parallelism"]),
            ),
            hash_length=max(
                configured.hash_length,
                int(parameters["hash_length"]),
            ),
            salt_length=max(
                configured.salt_length,
                int(parameters["salt_length"]),
            ),
        )

    _algorithm: str
    _argon2_settings: Argon2Configuration
    _argon2_hasher: PasswordHasher
    _bcrypt_settings: BcryptConfiguration


__all__ = ["_NativeHasher"]
