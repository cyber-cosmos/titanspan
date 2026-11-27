"""Define optional backend operations for atomic owner-token locks.
"""  # fmt: skip

from typing import Protocol, runtime_checkable


@runtime_checkable
class LockStore(Protocol):
    """Describe stores that provide atomic lease acquisition and release.
    """  # fmt: skip

    def acquire_lock(self, key: str, owner: str, ttl: float) -> bool:
        """Acquire a lease only when it is absent or expired.
        """  # fmt: skip
        ...

    async def acquire_lock_async(
        self,
        key: str,
        owner: str,
        ttl: float,
    ) -> bool:
        """Asynchronously acquire one lease.
        """  # fmt: skip
        ...

    def release_lock(self, key: str, owner: str) -> bool:
        """Release a lease only when the owner token matches.
        """  # fmt: skip
        ...

    async def release_lock_async(self, key: str, owner: str) -> bool:
        """Asynchronously owner-check and release a lease.
        """  # fmt: skip
        ...

    def lock_owner(self, key: str) -> str | None:
        """Return the current owner token for an unexpired lease.
        """  # fmt: skip
        ...

    async def lock_owner_async(self, key: str) -> str | None:
        """Asynchronously inspect the current lease owner.
        """  # fmt: skip
        ...

    def force_release_lock(self, key: str) -> bool:
        """Administratively remove one lease without owner checking.
        """  # fmt: skip
        ...

    async def force_release_lock_async(self, key: str) -> bool:
        """Asynchronously administratively remove one lease.
        """  # fmt: skip
        ...


__all__ = ["LockStore"]
