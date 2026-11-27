"""Expose native cache operations through the active application context.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.cache.manager import CacheManager
from titanspan.contracts.cache import CacheRepository
from titanspan.facades.base import Facade

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence

    from anyio.abc import TaskGroup

    from titanspan.cache.lock import Lock
    from titanspan.cache.manager import CacheFakeScope
    from titanspan.contracts.cache import CacheTTL


class Cache(Facade[CacheRepository]):
    """Resolve Cache operations from the active application's service graph.

    Values use Titanspan's safe JSON format. Sync operations remain sync-safe;
    network I/O has an explicit ``_async`` method.
    """

    service_contract = CacheRepository

    @classmethod
    def repository(cls, store: str | None = None) -> CacheRepository:
        """Return the stable repository view for one configured store.
        """  # fmt: skip
        if store is None:
            return cls.resolve_service()
        return cls.manager().store(store)

    @classmethod
    def manager(cls) -> CacheManager:
        """Return the manager shared by facade and injected consumers.
        """  # fmt: skip
        return cls.active_container().make(CacheManager)

    @classmethod
    def store(cls, name: str) -> CacheRepository:
        """Select a configured named store.
        """  # fmt: skip
        return cls.manager().store(name)

    @classmethod
    def memo(cls, store: str | None = None) -> CacheRepository:
        """Memoize successful reads within the current execution scope.
        """  # fmt: skip
        return cls.manager().memo(store)

    @classmethod
    def tags(cls, *names: str) -> CacheRepository:
        """Select a canonical cache tag group for grouped invalidation.
        """  # fmt: skip
        return cls.repository().tags(*names)

    @classmethod
    def get[ValueT](
        cls,
        key: str,
        default: ValueT | Callable[[], ValueT] | None = None,
    ) -> ValueT | None:
        """Retrieve a cached value or lazily resolve a fallback.
        """  # fmt: skip
        return cls.repository().get(key, default)

    @classmethod
    async def get_async[ValueT](
        cls,
        key: str,
        default: (
            ValueT | Callable[[], ValueT | Awaitable[ValueT]] | None
        ) = None,
    ) -> ValueT | None:
        """Asynchronously retrieve a value or fallback.
        """  # fmt: skip
        return await cls.repository().get_async(key, default)

    @classmethod
    def put(
        cls,
        key: str,
        value: object,
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Store one JSON-safe value with optional seconds-based expiry.
        """  # fmt: skip
        return cls.repository().put(key, value, ttl=ttl)

    @classmethod
    async def put_async(
        cls,
        key: str,
        value: object,
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Asynchronously store one JSON-safe value.
        """  # fmt: skip
        return await cls.repository().put_async(key, value, ttl=ttl)

    @classmethod
    def forever(cls, key: str, value: object) -> bool:
        """Store a value without an expiration deadline.
        """  # fmt: skip
        return cls.repository().forever(key, value)

    @classmethod
    async def forever_async(cls, key: str, value: object) -> bool:
        """Asynchronously store a value indefinitely.
        """  # fmt: skip
        return await cls.repository().forever_async(key, value)

    @classmethod
    def add(
        cls,
        key: str,
        value: object,
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Atomically add a key only when no value exists.
        """  # fmt: skip
        return cls.repository().add(key, value, ttl=ttl)

    @classmethod
    async def add_async(
        cls,
        key: str,
        value: object,
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Asynchronously atomically add a missing key.
        """  # fmt: skip
        return await cls.repository().add_async(key, value, ttl=ttl)

    @classmethod
    def has(cls, key: str) -> bool:
        """Check presence while preserving cached ``None`` values.
        """  # fmt: skip
        return cls.repository().has(key)

    @classmethod
    async def has_async(cls, key: str) -> bool:
        """Asynchronously check key presence.
        """  # fmt: skip
        return await cls.repository().has_async(key)

    @classmethod
    def missing(cls, key: str) -> bool:
        """Return whether the selected store has no value for a key.
        """  # fmt: skip
        return cls.repository().missing(key)

    @classmethod
    async def missing_async(cls, key: str) -> bool:
        """Asynchronously check whether the selected key is absent.
        """  # fmt: skip
        return await cls.repository().missing_async(key)

    @classmethod
    def many(
        cls,
        keys: Sequence[str],
        *,
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve a bounded set of keys using one shared default.
        """  # fmt: skip
        return cls.repository().many(keys, default=default)

    @classmethod
    async def many_async(
        cls,
        keys: Sequence[str],
        *,
        default: object = None,
    ) -> Mapping[str, object]:
        """Asynchronously retrieve a bounded set of keys.
        """  # fmt: skip
        return await cls.repository().many_async(keys, default=default)

    @classmethod
    def put_many(
        cls,
        values: Mapping[str, object],
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Store a bounded mapping using a shared optional expiry.
        """  # fmt: skip
        return cls.repository().put_many(values, ttl=ttl)

    @classmethod
    async def put_many_async(
        cls,
        values: Mapping[str, object],
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Asynchronously store a bounded mapping of values.
        """  # fmt: skip
        return await cls.repository().put_many_async(values, ttl=ttl)

    @classmethod
    def pull[ValueT](
        cls,
        key: str,
        default: ValueT | Callable[[], ValueT] | None = None,
    ) -> ValueT | None:
        """Atomically retrieve and remove a value when supported.
        """  # fmt: skip
        return cls.repository().pull(key, default)

    @classmethod
    async def pull_async[ValueT](
        cls,
        key: str,
        default: (
            ValueT | Callable[[], ValueT | Awaitable[ValueT]] | None
        ) = None,
    ) -> ValueT | None:
        """Asynchronously retrieve and remove one value.
        """  # fmt: skip
        return await cls.repository().pull_async(key, default)

    @classmethod
    def forget(cls, key: str) -> bool:
        """Remove one key and report whether it existed.
        """  # fmt: skip
        return cls.repository().forget(key)

    @classmethod
    async def forget_async(cls, key: str) -> bool:
        """Asynchronously remove one key.
        """  # fmt: skip
        return await cls.repository().forget_async(key)

    @classmethod
    def flush(cls, store: str | None = None) -> None:
        """Clear only the selected application and store namespace.
        """  # fmt: skip
        cls.repository(store).flush()

    @classmethod
    async def flush_async(cls, store: str | None = None) -> None:
        """Asynchronously clear only the selected namespace.
        """  # fmt: skip
        await cls.repository(store).flush_async()

    @classmethod
    def flush_locks(cls, store: str | None = None) -> None:
        """Administratively clear locks in one selected store namespace.
        """  # fmt: skip
        cls.repository(store).flush_locks()

    @classmethod
    async def flush_locks_async(cls, store: str | None = None) -> None:
        """Asynchronously clear locks in one selected store namespace.
        """  # fmt: skip
        await cls.repository(store).flush_locks_async()

    @classmethod
    def increment(cls, key: str, amount: int = 1) -> int:
        """Atomically increment a counter on supported backends.
        """  # fmt: skip
        return cls.repository().increment(key, amount)

    @classmethod
    async def increment_async(cls, key: str, amount: int = 1) -> int:
        """Asynchronously atomically increment a counter.
        """  # fmt: skip
        return await cls.repository().increment_async(key, amount)

    @classmethod
    def decrement(cls, key: str, amount: int = 1) -> int:
        """Atomically decrement a counter on supported backends.
        """  # fmt: skip
        return cls.repository().decrement(key, amount)

    @classmethod
    async def decrement_async(cls, key: str, amount: int = 1) -> int:
        """Asynchronously atomically decrement a counter.
        """  # fmt: skip
        return await cls.repository().decrement_async(key, amount)

    @classmethod
    def remember[ValueT](
        cls,
        key: str,
        *,
        ttl: CacheTTL,
        callback: Callable[[], ValueT],
    ) -> ValueT:
        """Retrieve a value or compute and store it after a miss.
        """  # fmt: skip
        return cls.repository().remember(key, ttl=ttl, callback=callback)

    @classmethod
    async def remember_async[ValueT](
        cls,
        key: str,
        *,
        ttl: CacheTTL,
        callback: Callable[[], ValueT | Awaitable[ValueT]],
    ) -> ValueT:
        """Asynchronously retrieve or compute a value.
        """  # fmt: skip
        return await cls.repository().remember_async(
            key,
            ttl=ttl,
            callback=callback,
        )

    @classmethod
    def remember_forever[ValueT](
        cls,
        key: str,
        *,
        callback: Callable[[], ValueT],
    ) -> ValueT:
        """Compute a missing value and retain it indefinitely.
        """  # fmt: skip
        return cls.repository().remember_forever(key, callback=callback)

    @classmethod
    async def remember_forever_async[ValueT](
        cls,
        key: str,
        *,
        callback: Callable[[], ValueT | Awaitable[ValueT]],
    ) -> ValueT:
        """Asynchronously compute and retain a missing value forever.
        """  # fmt: skip
        return await cls.repository().remember_forever_async(
            key,
            callback=callback,
        )

    @classmethod
    def touch(cls, key: str, *, ttl: CacheTTL) -> bool:
        """Replace a live key's expiration deadline.
        """  # fmt: skip
        repository = cls.repository()
        return repository.touch(key, ttl=ttl)

    @classmethod
    async def touch_async(cls, key: str, *, ttl: CacheTTL) -> bool:
        """Asynchronously replace a key's expiration deadline.
        """  # fmt: skip
        return await cls.repository().touch_async(key, ttl=ttl)

    @classmethod
    def lock(
        cls,
        key: str,
        *,
        ttl: CacheTTL,
        store: str | None = None,
    ) -> Lock:
        """Create a backend-owned lease lock for one resource name.
        """  # fmt: skip
        return cls.manager().lock(key, ttl=ttl, store=store)

    @classmethod
    def restore_lock(
        cls,
        key: str,
        owner: str,
        *,
        ttl: CacheTTL,
        store: str | None = None,
    ) -> Lock:
        """Restore a trusted ownership token transferred by application code.
        """  # fmt: skip
        return cls.manager().restore_lock(
            key,
            owner,
            ttl=ttl,
            store=store,
        )

    @classmethod
    async def flexible_async[ValueT](
        cls,
        key: str,
        *,
        fresh: int | float,
        stale: int | float,
        callback: Callable[[], ValueT | Awaitable[ValueT]],
        task_group: TaskGroup | None = None,
    ) -> ValueT:
        """Return fresh or stale data and refresh in a caller-owned task.
        """  # fmt: skip
        return await cls.repository().flexible_async(
            key,
            fresh=fresh,
            stale=stale,
            callback=callback,
            task_group=task_group,
        )

    @classmethod
    def fake(cls, store: str | None = None) -> CacheFakeScope:
        """Substitute all or one store in the current execution context.
        """  # fmt: skip
        return cls.manager().fake(store)

    @classmethod
    def status(cls, store: str | None = None) -> Mapping[str, object]:
        """Inspect driver capabilities and safe aggregate statistics.
        """  # fmt: skip
        return cls.manager().status(store)

    @classmethod
    async def status_async(
        cls,
        store: str | None = None,
    ) -> Mapping[str, object]:
        """Asynchronously inspect cache store status.
        """  # fmt: skip
        return await cls.manager().status_async(store)


__all__ = ["Cache"]
