"""Define the application-facing cache repository protocol.

The repository provides one native API over named backend stores.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence

    from anyio.abc import TaskGroup

    from titanspan.contracts.cache.capabilities import CacheCapabilities

type CacheTTL = int | float | timedelta | datetime | None


@runtime_checkable
class CacheRepository(Protocol):
    """Describe sync and async operations for one named cache store.

    A missing key is distinct from a stored ``None``. ``ttl`` values are
    seconds, timedeltas, absolute aware datetimes, or ``None`` for forever.
    """

    @property
    def capabilities(self) -> CacheCapabilities:
        """Return the active store's explicit feature guarantees.
        """  # fmt: skip
        ...

    @property
    def name(self) -> str:
        """Return the configured store name without connection details.
        """  # fmt: skip
        ...

    def get[ValueT](
        self,
        key: str,
        default: ValueT | Callable[[], ValueT] | None = None,
    ) -> ValueT | None:
        """Retrieve a value and resolve a fallback only on a miss.
        """  # fmt: skip
        ...

    async def get_async[ValueT](
        self,
        key: str,
        default: ValueT
        | Callable[[], ValueT | Awaitable[ValueT]]
        | None = None,
    ) -> ValueT | None:
        """Asynchronously retrieve a value and resolve its fallback.
        """  # fmt: skip
        ...

    def put(self, key: str, value: object, *, ttl: CacheTTL = None) -> bool:
        """Store one JSON-safe value, indefinitely when ``ttl`` is ``None``.
        """  # fmt: skip
        ...

    async def put_async(
        self,
        key: str,
        value: object,
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Asynchronously store one JSON-safe value.
        """  # fmt: skip
        ...

    def forever(self, key: str, value: object) -> bool:
        """Store one JSON-safe value without expiration.
        """  # fmt: skip
        ...

    async def forever_async(self, key: str, value: object) -> bool:
        """Asynchronously store one value without expiration.
        """  # fmt: skip
        ...

    def add(self, key: str, value: object, *, ttl: CacheTTL = None) -> bool:
        """Atomically store a value only when the key is missing.
        """  # fmt: skip
        ...

    async def add_async(
        self,
        key: str,
        value: object,
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Asynchronously add a value only when the key is missing.
        """  # fmt: skip
        ...

    def has(self, key: str) -> bool:
        """Return whether the key exists, including a stored ``None``.
        """  # fmt: skip
        ...

    async def has_async(self, key: str) -> bool:
        """Asynchronously check whether the key exists.
        """  # fmt: skip
        ...

    def missing(self, key: str) -> bool:
        """Return whether the key does not exist.
        """  # fmt: skip
        ...

    def tags(self, *names: str) -> CacheRepository:
        """Select a canonical tag set for grouped invalidation.
        """  # fmt: skip
        ...

    async def missing_async(self, key: str) -> bool:
        """Asynchronously check whether the key does not exist.
        """  # fmt: skip
        ...

    def many(
        self,
        keys: Sequence[str],
        *,
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve a bounded group of values in input order.
        """  # fmt: skip
        ...

    async def many_async(
        self,
        keys: Sequence[str],
        *,
        default: object = None,
    ) -> Mapping[str, object]:
        """Asynchronously retrieve a bounded group of values.
        """  # fmt: skip
        ...

    def put_many(
        self,
        values: Mapping[str, object],
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Store a bounded mapping of JSON-safe values.
        """  # fmt: skip
        ...

    async def put_many_async(
        self,
        values: Mapping[str, object],
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Asynchronously store a bounded mapping of values.
        """  # fmt: skip
        ...

    def pull[ValueT](
        self,
        key: str,
        default: ValueT | Callable[[], ValueT] | None = None,
    ) -> ValueT | None:
        """Atomically retrieve and remove one value when supported.
        """  # fmt: skip
        ...

    async def pull_async[ValueT](
        self,
        key: str,
        default: ValueT
        | Callable[[], ValueT | Awaitable[ValueT]]
        | None = None,
    ) -> ValueT | None:
        """Asynchronously retrieve and remove one value.
        """  # fmt: skip
        ...

    def forget(self, key: str) -> bool:
        """Remove one key and report whether it existed.
        """  # fmt: skip
        ...

    async def forget_async(self, key: str) -> bool:
        """Asynchronously remove one key.
        """  # fmt: skip
        ...

    def flush(self) -> None:
        """Clear only the configured application and store namespace.
        """  # fmt: skip
        ...

    async def flush_async(self) -> None:
        """Asynchronously clear only this configured namespace.
        """  # fmt: skip
        ...

    def flush_locks(self) -> None:
        """Clear locks only when this backend supports scoped lock clearing.
        """  # fmt: skip
        ...

    async def flush_locks_async(self) -> None:
        """Asynchronously clear this store's scoped lock namespace.
        """  # fmt: skip
        ...

    def increment(self, key: str, amount: int = 1) -> int:
        """Atomically increase an integer value by ``amount``.
        """  # fmt: skip
        ...

    async def increment_async(self, key: str, amount: int = 1) -> int:
        """Asynchronously atomically increase an integer value.
        """  # fmt: skip
        ...

    def decrement(self, key: str, amount: int = 1) -> int:
        """Atomically decrease an integer value by ``amount``.
        """  # fmt: skip
        ...

    async def decrement_async(self, key: str, amount: int = 1) -> int:
        """Asynchronously atomically decrease an integer value.
        """  # fmt: skip
        ...

    def remember[ValueT](
        self,
        key: str,
        *,
        ttl: CacheTTL,
        callback: Callable[[], ValueT],
    ) -> ValueT:
        """Retrieve or compute and store one value.
        """  # fmt: skip
        ...

    async def remember_async[ValueT](
        self,
        key: str,
        *,
        ttl: CacheTTL,
        callback: Callable[[], ValueT | Awaitable[ValueT]],
    ) -> ValueT:
        """Asynchronously retrieve or compute one value.
        """  # fmt: skip
        ...

    def remember_forever[ValueT](
        self,
        key: str,
        *,
        callback: Callable[[], ValueT],
    ) -> ValueT:
        """Retrieve or compute a value retained indefinitely.
        """  # fmt: skip
        ...

    async def remember_forever_async[ValueT](
        self,
        key: str,
        *,
        callback: Callable[[], ValueT | Awaitable[ValueT]],
    ) -> ValueT:
        """Asynchronously retrieve or compute an indefinite value.
        """  # fmt: skip
        ...

    def touch(self, key: str, *, ttl: CacheTTL) -> bool:
        """Change the expiration of a live entry.
        """  # fmt: skip
        ...

    async def touch_async(self, key: str, *, ttl: CacheTTL) -> bool:
        """Asynchronously change one live entry's expiration.
        """  # fmt: skip
        ...

    async def flexible_async[ValueT](
        self,
        key: str,
        *,
        fresh: int | float,
        stale: int | float,
        callback: Callable[[], ValueT | Awaitable[ValueT]],
        task_group: TaskGroup | None = None,
    ) -> ValueT:
        """Return fresh or eligible stale data using an owned task group.
        """  # fmt: skip
        ...


__all__ = ["CacheRepository", "CacheTTL"]
