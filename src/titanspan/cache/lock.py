"""Provide cancellation-safe owner-checked cache locks.
"""  # fmt: skip

from __future__ import annotations

from inspect import isawaitable
from math import isfinite
from time import monotonic, sleep
from typing import TYPE_CHECKING, Self, TypeVar, cast
from uuid import uuid4

import anyio

from titanspan.cache.exceptions import (
    CacheBackendError,
    CacheCapabilityError,
    CacheLockTimeoutError,
)
from titanspan.contracts.cache import LockStore

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from titanspan.cache.manager import CacheManager

ResultT = TypeVar("ResultT")
_POLL_SECONDS = 0.05
_MAX_WAIT_SECONDS = 30.0


class Lock:
    """Represent one owner token and lease on an application cache key.

    A lease prevents competing acquisition only while the backend's stored
    lease remains live. Work continuing after expiry may overlap a new owner.
    """

    def __init__(
        self,
        manager: CacheManager,
        store: str,
        key: str,
        ttl: float,
        *,
        owner: str | None = None,
    ) -> None:
        """Bind a lock handle to one named store and safe key.

        Args:
            manager: Application-owned cache manager.
            store: Configured store identifier.
            key: Validated logical key.
            ttl: Positive lease duration in seconds.
            owner: Existing token for explicit ownership restoration.

        Raises:
            ValueError: If the lease is not positive or finite.
        """
        if type(ttl) not in (int, float) or not isfinite(ttl) or ttl <= 0:
            msg = "Cache lock lease must be finite and positive."
            raise ValueError(msg)
        self._manager = manager
        self._store = store
        self._key = key
        self._ttl = float(ttl)
        self._owner = owner or uuid4().hex
        self._wait = 0.0

    @property
    def owner(self) -> str:
        """Return this handle's ownership token for transfer or restoration.
        """  # fmt: skip
        return self._owner

    @property
    def store_name(self) -> str:
        """Return the configured store owning this lock handle.
        """  # fmt: skip
        return self._store

    @property
    def lease_seconds(self) -> float:
        """Return the lease duration selected for future acquisition.
        """  # fmt: skip
        return self._ttl

    @property
    def acquired(self) -> bool:
        """Return whether the backend currently recognizes this owner token.
        """  # fmt: skip
        try:
            acquired = (
                self._lock_store().lock_owner(self.backend_key) == self._owner
            )
        except CacheCapabilityError:
            raise
        except Exception:
            self._emit("lock_inspect", success=False)
            raise _lock_backend_error() from None
        self._emit("lock_inspect", success=True)
        return acquired

    async def acquired_async(self) -> bool:
        """Asynchronously inspect whether this owner holds a live lease.
        """  # fmt: skip
        try:
            acquired = (
                await self._lock_store().lock_owner_async(self.backend_key)
                == self._owner
            )
        except CacheCapabilityError:
            raise
        except Exception:
            await self._emit_async("lock_inspect", success=False)
            raise _lock_backend_error() from None
        await self._emit_async("lock_inspect", success=True)
        return acquired

    def acquire(self) -> bool:
        """Try acquiring immediately without blocking.

        Returns:
            Whether this token acquired the lease.

        Raises:
            CacheCapabilityError: If the selected backend lacks locks.
            CacheBackendError: If the backend operation fails.
        """
        try:
            acquired = self._lock_store().acquire_lock(
                self.backend_key,
                self._owner,
                self._ttl,
            )
        except CacheCapabilityError:
            raise
        except Exception:
            self._emit("lock_acquire", success=False)
            raise _lock_backend_error() from None
        self._emit("lock_acquire", success=acquired)
        return acquired

    async def acquire_async(self) -> bool:
        """Asynchronously try acquiring the lease immediately.
        """  # fmt: skip
        try:
            acquired = await self._lock_store().acquire_lock_async(
                self.backend_key,
                self._owner,
                self._ttl,
            )
        except CacheCapabilityError:
            raise
        except Exception:
            await self._emit_async("lock_acquire", success=False)
            raise _lock_backend_error() from None
        await self._emit_async("lock_acquire", success=acquired)
        return acquired

    def release(self) -> bool:
        """Release this lease only while the backend still stores its token.
        """  # fmt: skip
        try:
            released = self._lock_store().release_lock(
                self.backend_key,
                self._owner,
            )
        except CacheCapabilityError:
            raise
        except Exception:
            self._emit("lock_release", success=False)
            raise _lock_backend_error() from None
        self._emit("lock_release", success=released)
        return released

    async def release_async(self) -> bool:
        """Asynchronously release only the lease owned by this handle.
        """  # fmt: skip
        try:
            released = await self._lock_store().release_lock_async(
                self.backend_key,
                self._owner,
            )
        except CacheCapabilityError:
            raise
        except Exception:
            await self._emit_async("lock_release", success=False)
            raise _lock_backend_error() from None
        await self._emit_async("lock_release", success=released)
        return released

    def force_release(self) -> bool:
        """Administratively remove this key's lease without owner checking.

        This operation can admit overlapping work when another owner is
        active. Use it only for explicit recovery after verifying ownership.
        """
        try:
            released = self._lock_store().force_release_lock(
                self.backend_key,
            )
        except CacheCapabilityError:
            raise
        except Exception:
            self._emit("lock_force_release", success=False)
            raise _lock_backend_error() from None
        self._emit("lock_force_release", success=released)
        return released

    async def force_release_async(self) -> bool:
        """Asynchronously administratively remove one scoped lease.
        """  # fmt: skip
        try:
            released = await self._lock_store().force_release_lock_async(
                self.backend_key,
            )
        except CacheCapabilityError:
            raise
        except Exception:
            await self._emit_async("lock_force_release", success=False)
            raise _lock_backend_error() from None
        await self._emit_async("lock_force_release", success=released)
        return released

    def block(self, wait: float) -> Self:
        """Set a bounded wait duration for the next sync context entry.

        Args:
            wait: Maximum seconds to wait before raising timeout.

        Returns:
            This lock handle, for fluent ``with lock.block(...)`` usage.
        """
        self._wait = _validate_wait(wait)
        return self

    def block_async(self, wait: float) -> Self:
        """Set a bounded async wait for the next async context entry.
        """  # fmt: skip
        self._wait = _validate_wait(wait)
        return self

    def __enter__(self) -> Self:
        """Acquire before entering and release after the managed block.
        """  # fmt: skip
        if not self._acquire_until(self._wait):
            msg = "Cache lock wait expired."
            raise CacheLockTimeoutError(msg)
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Release this owner token even when managed work raises.
        """  # fmt: skip
        del exc_info
        self.release()

    async def __aenter__(self) -> Self:
        """Acquire asynchronously before entering the managed block.
        """  # fmt: skip
        if not await self._acquire_until_async(self._wait):
            msg = "Cache lock wait expired."
            raise CacheLockTimeoutError(msg)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Shield lease cleanup from cancellation during async work.
        """  # fmt: skip
        del exc_info
        with anyio.CancelScope(shield=True):
            await self.release_async()

    def run[ResultT](self, callback: Callable[[], ResultT]) -> ResultT:
        """Acquire for one callback and always release after its result.

        Args:
            callback: Synchronous work performed while holding the lease.

        Returns:
            The callback result.
        """
        with self:
            return callback()

    async def run_async[ResultT](
        self,
        callback: Callable[[], ResultT | Awaitable[ResultT]],
    ) -> ResultT:
        """Acquire asynchronously for one sync or async callback.
        """  # fmt: skip
        async with self:
            result = callback()
            if isawaitable(result):
                return await cast("Awaitable[ResultT]", result)
            return cast("ResultT", result)

    def transfer(self) -> str:
        """Return the token required to restore this owner elsewhere.

        The token is a coordination secret and must travel only through a
        trusted application channel.
        """
        return self._owner

    def _acquire_until(self, wait: float) -> bool:
        """Poll sync acquisition until success or a monotonic deadline.
        """  # fmt: skip
        deadline = monotonic() + wait
        while True:
            if self.acquire():
                return True
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            sleep(min(_POLL_SECONDS, remaining))

    async def _acquire_until_async(self, wait: float) -> bool:
        """Poll async acquisition without blocking the event loop.
        """  # fmt: skip
        deadline = monotonic() + wait
        while True:
            if await self.acquire_async():
                return True
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            await anyio.sleep(min(_POLL_SECONDS, remaining))

    @property
    def backend_key(self) -> str:
        """Return key scoped to application namespace and configured store.
        """  # fmt: skip
        return self._manager.key_prefix(self._store) + f"lock:{self._key}"

    def _lock_store(self) -> LockStore:
        """Resolve explicit owner-lock support from the selected backend.
        """  # fmt: skip
        backend = self._manager.resolve_backend(self._store)
        if not backend.capabilities.locks or not isinstance(backend, LockStore):
            msg = f"Store [{self._store}] does not support cache locks."
            raise CacheCapabilityError(msg)
        return backend

    def _emit(self, action: str, *, success: bool) -> None:
        """Send a metadata-only event without changing lock outcomes.
        """  # fmt: skip
        self._manager.record_fake(
            self._store,
            action,
            self._key,
            success,
        )
        try:
            self._manager.emit(action, self._store, success=success)
        except Exception:
            # A listener failure must not strand a successfully acquired
            # lease by turning its acquisition into an apparent failure.
            return

    async def _emit_async(self, action: str, *, success: bool) -> None:
        """Asynchronously send lock metadata without masking backend errors.
        """  # fmt: skip
        self._manager.record_fake(
            self._store,
            action,
            self._key,
            success,
        )
        try:
            await self._manager.emit_async(
                action,
                self._store,
                success=success,
            )
        except Exception:
            return

    _manager: CacheManager
    _store: str
    _key: str
    _ttl: float
    _owner: str
    _wait: float


def _validate_wait(wait: float) -> float:
    """Validate bounded lock wait input before any polling begins.
    """  # fmt: skip
    if (
        type(wait) not in (int, float)
        or not isfinite(wait)
        or wait < 0
        or wait > _MAX_WAIT_SECONDS
    ):
        msg = "Cache lock wait must be between 0 and 30 seconds."
        raise ValueError(msg)
    return float(wait)


def _lock_backend_error() -> CacheBackendError:
    """Create a lock failure that omits private backend error text.
    """  # fmt: skip
    return CacheBackendError("Cache lock backend operation failed.")


__all__ = ["Lock"]
