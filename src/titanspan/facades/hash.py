"""Expose password hashing through the active application service graph.

The facade retains explicit methods so static tools can discover each
operation without dynamic forwarding.
"""

from __future__ import annotations

from titanspan.contracts.hashing import (
    Hasher,
    HashMetadata,
    HashVerification,
)
from titanspan.facades.base import Facade


class Hash(Facade[Hasher]):
    """Provide context-bound synchronous and asynchronous hash operations.

    Each call resolves the active application's canonical ``Hasher`` service.
    """

    service_contract = Hasher

    @classmethod
    def make(cls, password: str) -> str:
        """Generate an encoded password hash for the active application.

        Args:
            password: Exact password text without caller-visible coercion.

        Returns:
            Encoded hash with dependency-generated salt.
        """
        return cls.resolve_service().make(password)

    @classmethod
    async def make_async(cls, password: str) -> str:
        """Generate a password hash without blocking the event loop.

        Args:
            password: Exact password text.

        Returns:
            Encoded hash with dependency-generated salt.
        """
        return await cls.resolve_service().make_async(password)

    @classmethod
    def check(cls, password: str, hashed_password: str) -> bool:
        """Check one candidate password against a supported stored hash.

        Args:
            password: Candidate password text.
            hashed_password: Stored encoded hash.

        Returns:
            Whether the exact password matches.
        """
        return cls.resolve_service().check(password, hashed_password)

    @classmethod
    async def check_async(
        cls,
        password: str,
        hashed_password: str,
    ) -> bool:
        """Check a password without blocking the event loop.

        Args:
            password: Candidate password text.
            hashed_password: Stored encoded hash.

        Returns:
            Whether the exact password matches.
        """
        return await cls.resolve_service().check_async(
            password,
            hashed_password,
        )

    @classmethod
    def needs_rehash(cls, hashed_password: str) -> bool:
        """Check whether a recognized hash uses current work factors.

        Args:
            hashed_password: Stored encoded hash.

        Returns:
            Whether the hash needs replacement after successful verification.
        """
        return cls.resolve_service().needs_rehash(hashed_password)

    @classmethod
    def inspect(cls, hashed_password: str) -> HashMetadata | None:
        """Read supported algorithm metadata without verifying a password.

        Args:
            hashed_password: Stored encoded hash.

        Returns:
            Algorithm and work-factor metadata or ``None``.
        """
        return cls.resolve_service().inspect(hashed_password)

    @classmethod
    def verify_and_rehash(
        cls,
        password: str,
        hashed_password: str,
    ) -> HashVerification:
        """Verify a password and return any stronger replacement hash.

        Args:
            password: Candidate password text.
            hashed_password: Stored encoded hash.

        Returns:
            Verification state and an optional replacement to persist.
        """
        return cls.resolve_service().verify_and_rehash(
            password,
            hashed_password,
        )

    @classmethod
    async def verify_and_rehash_async(
        cls,
        password: str,
        hashed_password: str,
    ) -> HashVerification:
        """Verify and upgrade a hash without blocking the event loop.

        Args:
            password: Candidate password text.
            hashed_password: Stored encoded hash.

        Returns:
            Verification state and an optional replacement to persist.
        """
        return await cls.resolve_service().verify_and_rehash_async(
            password,
            hashed_password,
        )


__all__ = ["Hash"]
