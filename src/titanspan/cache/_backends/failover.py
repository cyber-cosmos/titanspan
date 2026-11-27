"""Compose ordered stores with explicit non-atomic failover semantics.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.cache.exceptions import (
    CacheBackendError,
    CacheCapabilityError,
)
from titanspan.contracts.cache import CacheCapabilities

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from titanspan.contracts.cache import CacheStore, PrefixClearStore

_ALL_FAILED = "Every configured cache failover store failed."
_UNSUPPORTED = "Failover stores do not support this atomic operation."
_MINIMUM_CHILD_STORES = 2


class FailoverStore:
    """Route portable cache operations through a configured priority list.

    Reads continue after misses so values written during a primary outage
    remain visible after that primary recovers. Writes go to the first
    accepting store only. This is not replication or a consistency protocol.
    """

    capabilities = CacheCapabilities(
        atomic_add=False,
        atomic_increment=False,
        atomic_pull=False,
        tags=False,
        tag_invalidation_atomic=False,
        scoped_clear=False,
        locks=False,
        distributed_locks=False,
        lock_scoped_clear=False,
    )

    def __init__(
        self,
        stores: tuple[CacheStore, ...],
        clear_stores: tuple[PrefixClearStore, ...],
        prefix: str,
        on_fallback: Callable[[], None],
        on_fallback_async: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Bind child stores and the exact namespace reserved for this view.
        """  # fmt: skip
        if len(stores) < _MINIMUM_CHILD_STORES or len(clear_stores) != len(
            stores
        ):
            msg = "A cache failover store requires at least two children."
            raise ValueError(msg)
        self._stores = stores
        self._clear_stores = clear_stores
        self._prefix = prefix
        self._on_fallback = on_fallback
        self._on_fallback_async = on_fallback_async

    def get(self, key: str) -> bytes | None:
        """Read by priority, skipping backend errors and continuing misses.
        """  # fmt: skip
        failures: list[Exception] = []
        responses = 0
        for index, store in enumerate(self._stores):
            try:
                value = store.get(key)
            except Exception as error:
                failures.append(error)
                continue
            responses += 1
            if value is not None:
                if index:
                    self._on_fallback()
                return value
        if failures and responses:
            self._on_fallback()
        self._raise_if_all_failed(failures, responses)
        return None

    async def get_async(self, key: str) -> bytes | None:
        """Asynchronously read by priority through configured stores.
        """  # fmt: skip
        failures: list[Exception] = []
        responses = 0
        for index, store in enumerate(self._stores):
            try:
                value = await store.get_async(key)
            except Exception as error:
                failures.append(error)
                continue
            responses += 1
            if value is not None:
                if index:
                    await self._notify_fallback_async()
                return value
        if failures and responses:
            await self._notify_fallback_async()
        self._raise_if_all_failed(failures, responses)
        return None

    def set(self, key: str, value: bytes, *, ttl: float | None) -> bool:
        """Write to the first store that accepts the value.
        """  # fmt: skip
        failures: list[Exception] = []
        responses = 0
        for index, store in enumerate(self._stores):
            try:
                written = store.set(key, value, ttl=ttl)
            except Exception as error:
                failures.append(error)
                continue
            responses += 1
            if written:
                if index:
                    self._on_fallback()
                return True
        if failures and responses:
            self._on_fallback()
        self._raise_if_all_failed(failures, responses)
        return False

    async def set_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Asynchronously write to the first store that accepts a value.
        """  # fmt: skip
        failures: list[Exception] = []
        responses = 0
        for index, store in enumerate(self._stores):
            try:
                written = await store.set_async(key, value, ttl=ttl)
            except Exception as error:
                failures.append(error)
                continue
            responses += 1
            if written:
                if index:
                    await self._notify_fallback_async()
                return True
        if failures and responses:
            await self._notify_fallback_async()
        self._raise_if_all_failed(failures, responses)
        return False

    def delete(self, key: str) -> bool:
        """Remove a key from every child to prevent stale fallback values.
        """  # fmt: skip
        failures: list[Exception] = []
        removed = False
        responses = 0
        fallback_emitted = False
        for index, store in enumerate(self._stores):
            try:
                result = store.delete(key)
            except Exception as error:
                failures.append(error)
                continue
            responses += 1
            removed = removed or result
            if index and result:
                self._on_fallback()
                fallback_emitted = True
        if failures and responses and not fallback_emitted:
            self._on_fallback()
        self._raise_if_any_failed(failures)
        return removed

    async def delete_async(self, key: str) -> bool:
        """Asynchronously remove one key from every child store.
        """  # fmt: skip
        failures: list[Exception] = []
        removed = False
        responses = 0
        fallback_emitted = False
        for index, store in enumerate(self._stores):
            try:
                result = await store.delete_async(key)
            except Exception as error:
                failures.append(error)
                continue
            responses += 1
            removed = removed or result
            if index and result:
                await self._notify_fallback_async()
                fallback_emitted = True
        if failures and responses and not fallback_emitted:
            await self._notify_fallback_async()
        self._raise_if_any_failed(failures)
        return removed

    def clear(self) -> None:
        """Clear this application's configured child namespaces only.
        """  # fmt: skip
        failures: list[Exception] = []
        responses = 0
        for clear_store in self._clear_stores:
            try:
                clear_store.clear_prefix(self._prefix)
            except Exception as error:
                failures.append(error)
                continue
            responses += 1
        if failures and responses:
            self._on_fallback()
        self._raise_if_any_failed(failures)

    async def clear_async(self) -> None:
        """Asynchronously clear configured child namespaces only.
        """  # fmt: skip
        failures: list[Exception] = []
        responses = 0
        for clear_store in self._clear_stores:
            try:
                await clear_store.clear_prefix_async(self._prefix)
            except Exception as error:
                failures.append(error)
                continue
            responses += 1
        if failures and responses:
            await self._notify_fallback_async()
        self._raise_if_any_failed(failures)

    def touch(self, key: str, *, ttl: float | None) -> bool:
        """Update expiry on every child that currently owns the key.
        """  # fmt: skip
        failures: list[Exception] = []
        touched = False
        responses = 0
        fallback_emitted = False
        for index, store in enumerate(self._stores):
            try:
                result = store.touch(key, ttl=ttl)
            except Exception as error:
                failures.append(error)
                continue
            responses += 1
            touched = touched or result
            if index and result:
                self._on_fallback()
                fallback_emitted = True
        if failures and responses and not fallback_emitted:
            self._on_fallback()
        self._raise_if_any_failed(failures)
        return touched

    async def touch_async(
        self,
        key: str,
        *,
        ttl: float | None,
    ) -> bool:
        """Asynchronously update expiry on all matching child entries.
        """  # fmt: skip
        failures: list[Exception] = []
        touched = False
        responses = 0
        fallback_emitted = False
        for index, store in enumerate(self._stores):
            try:
                result = await store.touch_async(key, ttl=ttl)
            except Exception as error:
                failures.append(error)
                continue
            responses += 1
            touched = touched or result
            if index and result:
                await self._notify_fallback_async()
                fallback_emitted = True
        if failures and responses and not fallback_emitted:
            await self._notify_fallback_async()
        self._raise_if_any_failed(failures)
        return touched

    def add(self, key: str, value: bytes, *, ttl: float | None) -> bool:
        """Reject add because child stores cannot coordinate atomically.

        Independent child backends cannot provide a shared atomic write.
        """
        del key, value, ttl
        raise CacheCapabilityError(_UNSUPPORTED)

    async def add_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Reject asynchronous add for the same coordination limitation.
        """  # fmt: skip
        return self.add(key, value, ttl=ttl)

    def pull(self, key: str) -> bytes | None:
        """Reject pull because cross-store atomicity is unavailable.

        Independent child backends cannot provide one atomic removal.
        """
        del key
        raise CacheCapabilityError(_UNSUPPORTED)

    async def pull_async(self, key: str) -> bytes | None:
        """Reject atomic async retrieve-and-remove across child stores.
        """  # fmt: skip
        return self.pull(key)

    def increment(self, key: str, amount: int) -> int:
        """Reject counter changes across independent child backends.
        """  # fmt: skip
        del key, amount
        raise CacheCapabilityError(_UNSUPPORTED)

    async def increment_async(self, key: str, amount: int) -> int:
        """Reject async counter changes across independent child backends.
        """  # fmt: skip
        return self.increment(key, amount)

    async def aclose(self) -> None:
        """Leave child cleanup to their application-owned CacheManager.
        """  # fmt: skip

    async def _notify_fallback_async(self) -> None:
        """Dispatch fallback metadata through the async event boundary.
        """  # fmt: skip
        callback = self._on_fallback_async
        if callback is None:
            self._on_fallback()
            return
        await callback()

    @staticmethod
    def _raise_if_all_failed(
        failures: list[Exception],
        responses: int,
    ) -> None:
        """Raise only when every child store failed to answer.
        """  # fmt: skip
        if failures and not responses:
            raise CacheBackendError(_ALL_FAILED) from None

    @staticmethod
    def _raise_if_any_failed(failures: list[Exception]) -> None:
        """Report partial deletion when any child store could not respond.
        """  # fmt: skip
        if failures:
            raise CacheBackendError(_ALL_FAILED) from None

    _stores: tuple[CacheStore, ...]
    _clear_stores: tuple[PrefixClearStore, ...]
    _prefix: str
    _on_fallback: Callable[[], None]
    _on_fallback_async: Callable[[], Awaitable[None]] | None


__all__ = ["FailoverStore"]
