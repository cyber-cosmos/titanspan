"""Define owner-aware cache locking contracts.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager, AbstractContextManager


@runtime_checkable
class CacheLock(Protocol):
    """Describe one leased lock with explicit sync and async operations.
    """  # fmt: skip

    @property
    def owner(self) -> str:
        """Return this lock handle's private ownership token.
        """  # fmt: skip
        ...

    @property
    def acquired(self) -> bool:
        """Return whether this owner holds a live backend lease.
        """  # fmt: skip
        ...

    async def acquired_async(self) -> bool:
        """Asynchronously inspect whether this handle owns its lease.
        """  # fmt: skip
        ...

    def acquire(self) -> bool:
        """Attempt atomic acquisition without waiting.
        """  # fmt: skip
        ...

    async def acquire_async(self) -> bool:
        """Asynchronously attempt atomic acquisition.
        """  # fmt: skip
        ...

    def release(self) -> bool:
        """Release only if this handle still owns the live lease.
        """  # fmt: skip
        ...

    def force_release(self) -> bool:
        """Administratively remove a scoped lease without owner checking.
        """  # fmt: skip
        ...

    async def release_async(self) -> bool:
        """Asynchronously release only this live ownership token.
        """  # fmt: skip
        ...

    async def force_release_async(self) -> bool:
        """Asynchronously administratively remove a scoped lease.
        """  # fmt: skip
        ...

    def block(self, wait: float) -> AbstractContextManager[CacheLock]:
        """Return a context manager that waits for a bounded duration.
        """  # fmt: skip
        ...

    def block_async(
        self,
        wait: float,
    ) -> AbstractAsyncContextManager[CacheLock]:
        """Return an async context manager with bounded acquisition.
        """  # fmt: skip
        ...


__all__ = ["CacheLock"]
