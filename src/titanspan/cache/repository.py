"""Provide the native repository API over one configured cache store.

The repository owns key validation, safe serialization, expiration
normalization, and explicit capability checks. Backend engines remain private.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
from inspect import isawaitable, iscoroutine
from math import isfinite
from threading import RLock, get_ident
from time import time
from typing import TYPE_CHECKING, cast

import anyio

from titanspan._application_context import active_application_context
from titanspan.cache._callbacks import invoke_async
from titanspan.cache.exceptions import (
    CacheBackendError,
    CacheCapabilityError,
    CacheKeyError,
)
from titanspan.cache.expiration import normalize_ttl
from titanspan.contracts.cache import LockClearStore, TaggableCacheStore

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence

    from anyio.abc import TaskGroup

    from titanspan.cache._serialization import JSONSerializer
    from titanspan.cache.lock import Lock
    from titanspan.cache.manager import CacheManager
    from titanspan.contracts.cache import (
        CacheCapabilities,
        CacheStore,
        CacheTTL,
    )

_KEY_LIMIT = 512
_MISSING = object()
_KEY_ERROR = "Cache keys must be non-empty text without control characters."
_BATCH_ERROR = "Cache bulk operations exceed the configured key limit."
_CONTROL_CHARACTER_LIMIT = 32
_DELETE_CHARACTER_CODE = 127
_REMEMBER_LOCK_TTL = 60.0
_REMEMBER_LOCK_WAIT = 5.0
_FLEXIBLE_MARKER = "titanspan.cache.flexible.v1"
_TAG_COUNT_LIMIT = 16
_TAG_NAME_LIMIT = 128
_TAG_PREFIX = "tagset:"
_RESERVED_TAG_NAMESPACE_ERROR = (
    "The cache tag namespace is reserved for tagged entries."
)
_MEMO_ENTRY_LIMIT = 1000
_INVALID_TAG_ERROR = "Cache tags must be bounded, safe text names."


@dataclass(slots=True)
class _MemoState:
    """Retain values owned by one execution scope and fake identity.
    """  # fmt: skip

    scope: object | None
    fake: object | None
    execution: tuple[str, int]
    generation: int
    values: dict[str, tuple[int, object]]


class Repository:
    """Expose native cache operations for one application-owned store.

    A repository is a lightweight manager view. It resolves the current
    backend on each operation so execution-local test substitutions also
    affect repositories already injected into application services.
    """

    def __init__(
        self,
        manager: CacheManager,
        name: str,
        *,
        tags: tuple[str, ...] = (),
    ) -> None:
        """Bind a repository view to one configured store name.

        Args:
            manager: Application-owned manager that creates and closes stores.
            name: Validated name in the manager's immutable configuration.
            tags: Canonical tag group applied to keys and clearing.
        """
        self._manager = manager
        self._name = name
        self._tags = tags
        self._tag_group = (
            sha256("\0".join(tags).encode("ascii")).hexdigest()
            if tags
            else None
        )

    @property
    def name(self) -> str:
        """Return this repository's configured store name.
        """  # fmt: skip
        return self._name

    @property
    def capabilities(self) -> CacheCapabilities:
        """Return explicit guarantees for the selected backend.
        """  # fmt: skip
        return self._manager.resolve_backend(self._name).capabilities

    def tags(self, *names: str) -> Repository:
        """Return a repository isolated to one canonical tag group.

        Tag names are sorted and deduplicated, so argument order does not
        affect identity. Tag flushing scans one hashed key prefix and is not
        atomic with concurrent Redis writes.

        Args:
            *names: One or more bounded tag names.

        Returns:
            A repository view that writes and clears only this tag group.

        Raises:
            CacheCapabilityError: If the selected backend lacks tag support.
            CacheKeyError: If any tag name is invalid or the group is large.
        """
        selected = _normalize_tags((*self._tags, *names))
        if not self.capabilities.tags:
            msg = f"Store [{self._name}] does not support cache tags."
            raise CacheCapabilityError(msg)
        return Repository(self._manager, self._name, tags=selected)

    def get[ValueT](
        self,
        key: str,
        default: ValueT | Callable[[], ValueT] | None = None,
    ) -> ValueT | None:
        """Retrieve a value and resolve a fallback only after a miss.

        Args:
            key: Application key within this configured store.
            default: Value or synchronous zero-argument fallback.

        Returns:
            The cached value or resolved default, preserving false-like values.

        Raises:
            CacheKeyError: If the key is empty, oversized, or malformed.
            CacheBackendError: If the selected backend fails.
        """
        backend = self._manager.resolve_backend(self._name)
        backend_key = self.backend_key(key)
        try:
            payload = backend.get(backend_key)
        except Exception as error:
            self._manager.emit("failure", self._name, success=False)
            raise _backend_error(error) from None
        self._manager.emit(
            "hit" if payload is not None else "miss",
            self._name,
        )
        if payload is None:
            self._manager.record_fake(self._name, "get", key, False)
            return _resolve_default(default)
        self._manager.record_fake(self._name, "get", key, True)
        return cast("ValueT | None", self._serializer().decode(payload))

    async def get_async[ValueT](
        self,
        key: str,
        default: (
            ValueT | Callable[[], ValueT | Awaitable[ValueT]] | None
        ) = None,
    ) -> ValueT | None:
        """Asynchronously retrieve a value and resolve its fallback.

        Args:
            key: Application key within this configured store.
            default: Value or zero-argument synchronous or async fallback.

        Returns:
            The cached value or resolved fallback.

        Raises:
            CacheKeyError: If the key is malformed.
            CacheBackendError: If the selected backend fails.
        """
        backend = self._manager.resolve_backend(self._name)
        backend_key = self.backend_key(key)
        try:
            payload = await backend.get_async(backend_key)
        except Exception as error:
            await self._manager.emit_async(
                "failure",
                self._name,
                success=False,
            )
            raise _backend_error(error) from None
        await self._manager.emit_async(
            "hit" if payload is not None else "miss",
            self._name,
        )
        if payload is None:
            self._manager.record_fake(self._name, "get", key, False)
            return await _resolve_default_async(default)
        self._manager.record_fake(self._name, "get", key, True)
        return cast("ValueT | None", self._serializer().decode(payload))

    def put(self, key: str, value: object, *, ttl: CacheTTL = None) -> bool:
        """Store a JSON-safe value with an optional duration.

        Args:
            key: Application key within this configured store.
            value: JSON-safe built-in value.
            ttl: Seconds, ``timedelta``, aware absolute time, or ``None``.

        Returns:
            Whether the backend accepted the write.

        Raises:
            CacheKeyError: If the key is malformed.
            CacheBackendError: If the backend fails.
        """
        backend = self._manager.resolve_backend(self._name)
        backend_key = self.backend_key(key)
        payload = self._serializer().encode(value)
        ttl_seconds = normalize_ttl(ttl)
        try:
            result = backend.set(backend_key, payload, ttl=ttl_seconds)
        except Exception as error:
            self._manager.emit("failure", self._name, success=False)
            raise _backend_error(error) from None
        if result:
            self._manager.invalidate(self._name)
        self._manager.emit("write", self._name, success=result)
        self._manager.record_fake(self._name, "put", key, result)
        return result

    async def put_async(
        self,
        key: str,
        value: object,
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Asynchronously store one JSON-safe value.

        Args:
            key: Application key within this configured store.
            value: JSON-safe built-in value.
            ttl: Seconds, ``timedelta``, aware absolute time, or ``None``.

        Returns:
            Whether the backend accepted the write.
        """
        backend = self._manager.resolve_backend(self._name)
        backend_key = self.backend_key(key)
        payload = self._serializer().encode(value)
        ttl_seconds = normalize_ttl(ttl)
        try:
            result = await backend.set_async(
                backend_key,
                payload,
                ttl=ttl_seconds,
            )
        except Exception as error:
            await self._manager.emit_async(
                "failure",
                self._name,
                success=False,
            )
            raise _backend_error(error) from None
        if result:
            self._manager.invalidate(self._name)
        await self._manager.emit_async("write", self._name, success=result)
        self._manager.record_fake(self._name, "put", key, result)
        return result

    def forever(self, key: str, value: object) -> bool:
        """Store a value indefinitely.

        Args:
            key: Application key within this configured store.
            value: JSON-safe built-in value.

        Returns:
            Whether the backend accepted the write.
        """
        return self.put(key, value)

    async def forever_async(self, key: str, value: object) -> bool:
        """Asynchronously store a value indefinitely.

        Args:
            key: Application key within this configured store.
            value: JSON-safe built-in value.

        Returns:
            Whether the backend accepted the write.
        """
        return await self.put_async(key, value)

    def add(self, key: str, value: object, *, ttl: CacheTTL = None) -> bool:
        """Atomically store a value only when the key is absent.

        Args:
            key: Application key within this configured store.
            value: JSON-safe built-in value.
            ttl: Seconds, ``timedelta``, aware absolute time, or ``None``.

        Returns:
            Whether this call stored the value.
        """
        backend = self._manager.resolve_backend(self._name)
        if not backend.capabilities.atomic_add:
            msg = f"Store [{self._name}] does not support atomic add."
            raise CacheCapabilityError(msg)
        ttl_seconds = normalize_ttl(ttl)
        if ttl_seconds is not None and ttl_seconds <= 0:
            return False
        backend_key = self.backend_key(key)
        try:
            added = backend.add(
                backend_key,
                self._serializer().encode(value),
                ttl=ttl_seconds,
            )
        except Exception as error:
            self._manager.emit("failure", self._name, success=False)
            raise _backend_error(error) from None
        if added:
            self._manager.invalidate(self._name)
        self._manager.emit("write", self._name, success=added)
        self._manager.record_fake(self._name, "add", key, added)
        return added

    async def add_async(
        self,
        key: str,
        value: object,
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Asynchronously perform atomic add-if-absent.

        Args:
            key: Application key within this configured store.
            value: JSON-safe built-in value.
            ttl: Seconds, ``timedelta``, aware absolute time, or ``None``.

        Returns:
            Whether this call stored the value.
        """
        backend = self._manager.resolve_backend(self._name)
        if not backend.capabilities.atomic_add:
            msg = f"Store [{self._name}] does not support atomic add."
            raise CacheCapabilityError(msg)
        ttl_seconds = normalize_ttl(ttl)
        if ttl_seconds is not None and ttl_seconds <= 0:
            return False
        backend_key = self.backend_key(key)
        try:
            added = await backend.add_async(
                backend_key,
                self._serializer().encode(value),
                ttl=ttl_seconds,
            )
        except Exception as error:
            await self._manager.emit_async(
                "failure",
                self._name,
                success=False,
            )
            raise _backend_error(error) from None
        if added:
            self._manager.invalidate(self._name)
        await self._manager.emit_async("write", self._name, success=added)
        self._manager.record_fake(self._name, "add", key, added)
        return added

    def has(self, key: str) -> bool:
        """Check key presence without confusing cached ``None`` with a miss.

        Args:
            key: Application key within this configured store.

        Returns:
            Whether the backend returned a stored payload.
        """
        backend = self._manager.resolve_backend(self._name)
        backend_key = self.backend_key(key)
        try:
            found = backend.get(backend_key) is not None
        except Exception as error:
            self._manager.emit("failure", self._name, success=False)
            raise _backend_error(error) from None
        self._manager.emit("hit" if found else "miss", self._name)
        self._manager.record_fake(self._name, "has", key, found)
        return found

    async def has_async(self, key: str) -> bool:
        """Asynchronously check key presence.

        Args:
            key: Application key within this configured store.

        Returns:
            Whether the backend returned a stored payload.
        """
        backend = self._manager.resolve_backend(self._name)
        backend_key = self.backend_key(key)
        try:
            found = await backend.get_async(backend_key) is not None
        except Exception as error:
            await self._manager.emit_async(
                "failure",
                self._name,
                success=False,
            )
            raise _backend_error(error) from None
        await self._manager.emit_async("hit" if found else "miss", self._name)
        self._manager.record_fake(self._name, "has", key, found)
        return found

    def missing(self, key: str) -> bool:
        """Return whether the key is absent.

        Args:
            key: Application key within this configured store.

        Returns:
            Whether the key is missing.
        """
        return not self.has(key)

    async def missing_async(self, key: str) -> bool:
        """Asynchronously return whether the key is absent.

        Args:
            key: Application key within this configured store.

        Returns:
            Whether the key is missing.
        """
        return not await self.has_async(key)

    def many(
        self,
        keys: Sequence[str],
        *,
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve several values while preserving requested key order.

        Args:
            keys: Ordered application keys.
            default: Value returned for each missing key.

        Returns:
            Values keyed by each unique requested key.
        """
        self._validate_batch(keys)
        return {key: self.get(key, default) for key in dict.fromkeys(keys)}

    async def many_async(
        self,
        keys: Sequence[str],
        *,
        default: object = None,
    ) -> Mapping[str, object]:
        """Asynchronously retrieve a bounded group of values.

        Args:
            keys: Ordered application keys.
            default: Value or async fallback for missing keys.

        Returns:
            Values keyed by each unique requested key.
        """
        self._validate_batch(keys)
        values: dict[str, object] = {}
        for key in dict.fromkeys(keys):
            values[key] = await self.get_async(key, default)
        return values

    def put_many(
        self,
        values: Mapping[str, object],
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Store a bounded set of values after validating the complete batch.

        Args:
            values: Mapping of application keys to JSON-safe values.
            ttl: Shared expiration for every stored value.

        Returns:
            Whether every backend write succeeded.
        """
        self._validate_batch(tuple(values))
        prepared = {
            self.backend_key(key): self._serializer().encode(value)
            for key, value in values.items()
        }
        ttl_seconds = normalize_ttl(ttl)
        backend = self._manager.resolve_backend(self._name)
        try:
            result = True
            for key, payload in prepared.items():
                result = backend.set(key, payload, ttl=ttl_seconds) and result
        except Exception as error:
            self._manager.emit("failure", self._name, success=False)
            raise _backend_error(error) from None
        if prepared:
            self._manager.invalidate(self._name)
        self._manager.emit("write", self._name, success=result)
        return result

    async def put_many_async(
        self,
        values: Mapping[str, object],
        *,
        ttl: CacheTTL = None,
    ) -> bool:
        """Asynchronously store a bounded mapping of values.

        Args:
            values: Mapping of application keys to JSON-safe values.
            ttl: Shared expiration for every stored value.

        Returns:
            Whether every backend write succeeded.
        """
        self._validate_batch(tuple(values))
        prepared = {
            self.backend_key(key): self._serializer().encode(value)
            for key, value in values.items()
        }
        ttl_seconds = normalize_ttl(ttl)
        backend = self._manager.resolve_backend(self._name)
        result = True
        try:
            for key, payload in prepared.items():
                stored = await backend.set_async(
                    key,
                    payload,
                    ttl=ttl_seconds,
                )
                result = stored and result
        except Exception as error:
            await self._manager.emit_async(
                "failure",
                self._name,
                success=False,
            )
            raise _backend_error(error) from None
        if prepared:
            self._manager.invalidate(self._name)
        await self._manager.emit_async("write", self._name, success=result)
        return result

    def pull[ValueT](
        self,
        key: str,
        default: ValueT | Callable[[], ValueT] | None = None,
    ) -> ValueT | None:
        """Atomically retrieve and remove a value when the backend supports it.

        Args:
            key: Application key within this configured store.
            default: Value or synchronous fallback used on a miss.

        Returns:
            The removed value or resolved fallback.

        Raises:
            CacheCapabilityError: If atomic retrieval and removal are absent.
        """
        backend = self._manager.resolve_backend(self._name)
        if not backend.capabilities.atomic_pull:
            msg = f"Store [{self._name}] does not support atomic pull."
            raise CacheCapabilityError(msg)
        backend_key = self.backend_key(key)
        try:
            payload = backend.pull(backend_key)
        except Exception as error:
            self._manager.emit("failure", self._name, success=False)
            raise _backend_error(error) from None
        if payload is not None:
            self._manager.invalidate(self._name)
        if payload is None:
            self._manager.emit("miss", self._name)
            return _resolve_default(default)
        self._manager.emit("removal", self._name)
        return cast("ValueT | None", self._serializer().decode(payload))

    async def pull_async[ValueT](
        self,
        key: str,
        default: (
            ValueT | Callable[[], ValueT | Awaitable[ValueT]] | None
        ) = None,
    ) -> ValueT | None:
        """Asynchronously atomically retrieve and remove one value.

        Args:
            key: Application key within this configured store.
            default: Value or sync or async fallback used on a miss.

        Returns:
            The removed value or resolved fallback.
        """
        backend = self._manager.resolve_backend(self._name)
        if not backend.capabilities.atomic_pull:
            msg = f"Store [{self._name}] does not support atomic pull."
            raise CacheCapabilityError(msg)
        backend_key = self.backend_key(key)
        try:
            payload = await backend.pull_async(backend_key)
        except Exception as error:
            await self._manager.emit_async(
                "failure",
                self._name,
                success=False,
            )
            raise _backend_error(error) from None
        if payload is not None:
            self._manager.invalidate(self._name)
        if payload is None:
            await self._manager.emit_async("miss", self._name)
            return await _resolve_default_async(default)
        await self._manager.emit_async("removal", self._name)
        return cast("ValueT", self._serializer().decode(payload))

    def forget(self, key: str) -> bool:
        """Remove one key and report whether the backend contained it.

        Args:
            key: Application key within this configured store.

        Returns:
            Whether the backend removed a value.
        """
        backend = self._manager.resolve_backend(self._name)
        backend_key = self.backend_key(key)
        try:
            removed = backend.delete(backend_key)
        except Exception as error:
            self._manager.emit("failure", self._name, success=False)
            raise _backend_error(error) from None
        if removed:
            self._manager.invalidate(self._name)
        self._manager.emit("removal", self._name, success=removed)
        self._manager.record_fake(self._name, "forget", key, removed)
        return removed

    async def forget_async(self, key: str) -> bool:
        """Asynchronously remove one key.

        Args:
            key: Application key within this configured store.

        Returns:
            Whether the backend removed a value.
        """
        backend = self._manager.resolve_backend(self._name)
        backend_key = self.backend_key(key)
        try:
            removed = await backend.delete_async(backend_key)
        except Exception as error:
            await self._manager.emit_async(
                "failure",
                self._name,
                success=False,
            )
            raise _backend_error(error) from None
        if removed:
            self._manager.invalidate(self._name)
        await self._manager.emit_async("removal", self._name, success=removed)
        self._manager.record_fake(self._name, "forget", key, removed)
        return removed

    def flush(self) -> None:
        """Clear values within this application's selected store namespace.

        No Redis database-wide flush is used by native stores.
        """
        backend = self._manager.resolve_backend(self._name)
        tagged_backend = (
            _taggable_backend(backend, self._name)
            if self._tag_group is not None
            else None
        )
        try:
            if tagged_backend is None:
                backend.clear()
            else:
                tagged_backend.clear_tagged(self._tagged_backend_prefix)
        except Exception as error:
            self._manager.emit("failure", self._name, success=False)
            raise _backend_error(error) from None
        self._manager.invalidate(self._name)
        self._manager.emit("clear", self._name)
        self._manager.record_fake(self._name, "flush", None, True)

    async def flush_async(self) -> None:
        """Asynchronously clear this configured store namespace.
        """  # fmt: skip
        backend = self._manager.resolve_backend(self._name)
        tagged_backend = (
            _taggable_backend(backend, self._name)
            if self._tag_group is not None
            else None
        )
        try:
            if tagged_backend is None:
                await backend.clear_async()
            else:
                await tagged_backend.clear_tagged_async(
                    self._tagged_backend_prefix
                )
        except Exception as error:
            await self._manager.emit_async(
                "failure",
                self._name,
                success=False,
            )
            raise _backend_error(error) from None
        self._manager.invalidate(self._name)
        await self._manager.emit_async("clear", self._name)
        self._manager.record_fake(self._name, "flush", None, True)

    def flush_locks(self) -> None:
        """Clear leases within this application's selected store namespace.

        Redis clears matching namespaced keys through bounded scans. The
        operation is administrative and can invalidate a live owner's lease.
        """
        backend = self._manager.resolve_backend(self._name)
        if not backend.capabilities.lock_scoped_clear or not isinstance(
            backend,
            LockClearStore,
        ):
            msg = f"Store [{self._name}] does not support scoped lock clear."
            raise CacheCapabilityError(msg)
        try:
            backend.clear_locks()
        except Exception as error:
            self._manager.emit("failure", self._name, success=False)
            raise _backend_error(error) from None
        self._manager.emit("lock_clear", self._name)
        self._manager.record_fake(
            self._name,
            "lock_clear",
            None,
            True,
        )

    async def flush_locks_async(self) -> None:
        """Asynchronously clear leases in the selected store namespace.

        Cancellation propagates to the backend operation. Redis deletion is
        bounded and may be partial if its connection fails during scanning.
        """
        backend = self._manager.resolve_backend(self._name)
        if not backend.capabilities.lock_scoped_clear or not isinstance(
            backend,
            LockClearStore,
        ):
            msg = f"Store [{self._name}] does not support scoped lock clear."
            raise CacheCapabilityError(msg)
        try:
            await backend.clear_locks_async()
        except Exception as error:
            await self._manager.emit_async(
                "failure",
                self._name,
                success=False,
            )
            raise _backend_error(error) from None
        await self._manager.emit_async("lock_clear", self._name)
        self._manager.record_fake(
            self._name,
            "lock_clear",
            None,
            True,
        )

    def increment(self, key: str, amount: int = 1) -> int:
        """Atomically increment a non-negative integer value.

        Args:
            key: Application key within this configured store.
            amount: Non-negative increase.

        Returns:
            The resulting integer value.
        """
        _validate_amount(amount)
        backend = self._manager.resolve_backend(self._name)
        if not backend.capabilities.atomic_increment:
            msg = f"Store [{self._name}] does not support atomic increment."
            raise CacheCapabilityError(msg)
        backend_key = self.backend_key(key)
        try:
            value = backend.increment(backend_key, amount)
        except Exception as error:
            raise _backend_error(error) from None
        self._manager.invalidate(self._name)
        self._manager.emit("write", self._name)
        return value

    async def increment_async(self, key: str, amount: int = 1) -> int:
        """Asynchronously atomically increment a counter.

        Args:
            key: Application key within this configured store.
            amount: Non-negative increase.

        Returns:
            The resulting integer value.
        """
        _validate_amount(amount)
        backend = self._manager.resolve_backend(self._name)
        if not backend.capabilities.atomic_increment:
            msg = f"Store [{self._name}] does not support atomic increment."
            raise CacheCapabilityError(msg)
        backend_key = self.backend_key(key)
        try:
            value = await backend.increment_async(
                backend_key,
                amount,
            )
        except Exception as error:
            raise _backend_error(error) from None
        self._manager.invalidate(self._name)
        await self._manager.emit_async("write", self._name)
        return value

    def decrement(self, key: str, amount: int = 1) -> int:
        """Atomically decrement an integer value by a non-negative amount.

        Args:
            key: Application key within this configured store.
            amount: Non-negative decrease.

        Returns:
            The resulting integer value.
        """
        _validate_amount(amount)
        backend = self._manager.resolve_backend(self._name)
        if not backend.capabilities.atomic_increment:
            msg = f"Store [{self._name}] does not support atomic decrement."
            raise CacheCapabilityError(msg)
        backend_key = self.backend_key(key)
        try:
            value = backend.increment(backend_key, -amount)
        except Exception as error:
            raise _backend_error(error) from None
        self._manager.invalidate(self._name)
        self._manager.emit("write", self._name)
        return value

    async def decrement_async(self, key: str, amount: int = 1) -> int:
        """Asynchronously decrement an integer value atomically.

        Args:
            key: Application key within this configured store.
            amount: Non-negative decrease.

        Returns:
            The resulting integer value.
        """
        _validate_amount(amount)
        backend = self._manager.resolve_backend(self._name)
        if not backend.capabilities.atomic_increment:
            msg = f"Store [{self._name}] does not support atomic decrement."
            raise CacheCapabilityError(msg)
        backend_key = self.backend_key(key)
        try:
            value = await backend.increment_async(
                backend_key,
                -amount,
            )
        except Exception as error:
            raise _backend_error(error) from None
        self._manager.invalidate(self._name)
        await self._manager.emit_async("write", self._name)
        return value

    def remember[ValueT](
        self,
        key: str,
        *,
        ttl: CacheTTL,
        callback: Callable[[], ValueT],
    ) -> ValueT:
        """Retrieve a value or synchronously compute and store it.

        Args:
            key: Application key within this configured store.
            ttl: Expiration applied to a newly computed value.
            callback: Sync factory called only after a miss.

        Returns:
            The cached or newly computed value.
        """
        cached = self.get(key, _MISSING)
        if cached is not _MISSING:
            return cast("ValueT", cached)
        backend = self._manager.resolve_backend(self._name)

        def compute() -> ValueT:
            """Compute once after the lock owner confirms a cache miss.
            """  # fmt: skip
            current = self.get(key, _MISSING)
            if current is not _MISSING:
                return cast("ValueT", current)
            result = callback()
            self.put(key, result, ttl=ttl)
            return result

        if backend.capabilities.locks:
            lock = self._manager.lock(
                self._lock_key(key),
                ttl=_REMEMBER_LOCK_TTL,
                store=self._name,
            )
            with lock.block(_REMEMBER_LOCK_WAIT):
                return compute()
        return compute()

    async def remember_async[ValueT](
        self,
        key: str,
        *,
        ttl: CacheTTL,
        callback: Callable[[], ValueT | Awaitable[ValueT]],
    ) -> ValueT:
        """Asynchronously retrieve or compute and store one value.

        Args:
            key: Application key within this configured store.
            ttl: Expiration applied to a newly computed value.
            callback: Sync or async factory called only after a miss.

        Returns:
            The cached or newly computed value.
        """
        cached = await self.get_async(key, _MISSING)
        if cached is not _MISSING:
            return cast("ValueT", cached)
        backend = self._manager.resolve_backend(self._name)

        async def compute() -> ValueT:
            """Recheck the value before running its sync or async factory.
            """  # fmt: skip
            current = await self.get_async(key, _MISSING)
            if current is not _MISSING:
                return cast("ValueT", current)
            result = await invoke_async(callback)
            await self.put_async(key, result, ttl=ttl)
            return result

        if backend.capabilities.locks:
            lock = self._manager.lock(
                self._lock_key(key),
                ttl=_REMEMBER_LOCK_TTL,
                store=self._name,
            )
            async with lock.block_async(_REMEMBER_LOCK_WAIT):
                return await compute()
        return await compute()

    def remember_forever[ValueT](
        self,
        key: str,
        *,
        callback: Callable[[], ValueT],
    ) -> ValueT:
        """Retrieve or compute a value stored without expiration.

        Args:
            key: Application key within this configured store.
            callback: Sync factory called only after a miss.

        Returns:
            The cached or newly computed value.
        """
        return self.remember(key, ttl=None, callback=callback)

    async def remember_forever_async[ValueT](
        self,
        key: str,
        *,
        callback: Callable[[], ValueT | Awaitable[ValueT]],
    ) -> ValueT:
        """Asynchronously retrieve or compute a permanent value.

        Args:
            key: Application key within this configured store.
            callback: Sync or async factory called only after a miss.

        Returns:
            The cached or newly computed value.
        """
        return await self.remember_async(key, ttl=None, callback=callback)

    async def flexible_async[ValueT](
        self,
        key: str,
        *,
        fresh: int | float,
        stale: int | float,
        callback: Callable[[], ValueT | Awaitable[ValueT]],
        task_group: TaskGroup | None = None,
    ) -> ValueT:
        """Return fresh or eligible stale data and coordinate refresh.

        ``stale`` is the maximum total age in seconds, not an additional
        duration. Refresh runs only in the caller-owned task group. Without a
        task group, stale data is returned and recomputed after its window.
        """
        fresh_age, stale_age = _validate_flexible_ages(fresh, stale)
        cached = await self.get_async(key, _MISSING)
        value, age = _flexible_entry(cached)
        if value is not _MISSING and age <= fresh_age:
            return cast("ValueT", value)
        if value is not _MISSING and age <= stale_age:
            if task_group is not None:
                await self._schedule_flexible_refresh(
                    key,
                    stale_age,
                    callback,
                    task_group,
                )
            return cast("ValueT", value)
        return await self._refresh_flexible_now(key, stale_age, callback)

    async def _schedule_flexible_refresh[ValueT](
        self,
        key: str,
        stale: float,
        callback: Callable[[], ValueT | Awaitable[ValueT]],
        task_group: TaskGroup,
    ) -> None:
        """Schedule a coordinated refresh in the caller-owned task group.
        """  # fmt: skip
        backend = self._manager.resolve_backend(self._name)
        if not backend.capabilities.locks:
            return
        lock = self._manager.lock(
            self._lock_key(key),
            ttl=min(stale, _REMEMBER_LOCK_TTL),
            store=self._name,
        )
        try:
            if not await lock.acquire_async():
                return
            try:
                task_group.start_soon(
                    self._refresh_flexible,
                    key,
                    stale,
                    callback,
                    lock,
                )
            except BaseException as scheduling_error:
                with anyio.CancelScope(shield=True):
                    try:
                        await lock.release_async()
                    except Exception as cleanup_error:
                        scheduling_error.add_note(
                            "Flexible refresh lease cleanup failed "
                            f"({type(cleanup_error).__name__})."
                        )
                raise
        except CacheBackendError:
            await self._manager.emit_async(
                "failure",
                self._name,
                success=False,
            )

    async def _refresh_flexible_now[ValueT](
        self,
        key: str,
        stale: float,
        callback: Callable[[], ValueT | Awaitable[ValueT]],
    ) -> ValueT:
        """Recheck and compute after the total stale age has expired.
        """  # fmt: skip
        backend = self._manager.resolve_backend(self._name)
        if backend.capabilities.locks:
            lock = self._manager.lock(
                self._lock_key(key),
                ttl=max(stale, _REMEMBER_LOCK_TTL),
                store=self._name,
            )
            async with lock.block_async(_REMEMBER_LOCK_WAIT):
                cached, age = _flexible_entry(
                    await self.get_async(key, _MISSING)
                )
                if cached is not _MISSING and age <= stale:
                    return cast("ValueT", cached)
                value = await invoke_async(callback)
                await self.put_async(
                    key,
                    _make_flexible_entry(value),
                    ttl=stale,
                )
                return value
        value = await invoke_async(callback)
        await self.put_async(
            key,
            _make_flexible_entry(value),
            ttl=stale,
        )
        return value

    async def _refresh_flexible[ValueT](
        self,
        key: str,
        stale: float,
        callback: Callable[[], ValueT | Awaitable[ValueT]],
        lock: Lock,
    ) -> None:
        """Refresh one stale value in the caller-owned task group.
        """  # fmt: skip
        try:
            value = await invoke_async(callback)
            await self.put_async(
                key,
                _make_flexible_entry(value),
                ttl=stale,
            )
        except Exception:
            await self._manager.emit_async(
                "failure",
                self._name,
                success=False,
            )
        finally:
            with anyio.CancelScope(shield=True):
                await lock.release_async()

    def touch(self, key: str, *, ttl: CacheTTL) -> bool:
        """Replace a live value's expiration.

        Args:
            key: Application key within this configured store.
            ttl: New expiration duration or aware absolute time.

        Returns:
            Whether a live entry was touched.
        """
        backend = self._manager.resolve_backend(self._name)
        backend_key = self.backend_key(key)
        ttl_seconds = normalize_ttl(ttl)
        try:
            touched = backend.touch(
                backend_key,
                ttl=ttl_seconds,
            )
        except Exception as error:
            raise _backend_error(error) from None
        if touched:
            self._manager.invalidate(self._name)
        return touched

    async def touch_async(self, key: str, *, ttl: CacheTTL) -> bool:
        """Asynchronously change expiration on a live value.

        Args:
            key: Application key within this configured store.
            ttl: New expiration duration or aware absolute time.

        Returns:
            Whether a live entry was touched.
        """
        backend = self._manager.resolve_backend(self._name)
        backend_key = self.backend_key(key)
        ttl_seconds = normalize_ttl(ttl)
        try:
            touched = await backend.touch_async(
                backend_key,
                ttl=ttl_seconds,
            )
        except Exception as error:
            raise _backend_error(error) from None
        if touched:
            self._manager.invalidate(self._name)
        return touched

    def backend_key(self, key: str) -> str:
        """Validate a logical key and add its application store prefix.

        Args:
            key: Caller-provided logical cache key.

        Returns:
            Store-prefixed backend key.

        Raises:
            CacheKeyError: If the key is empty, too large, or contains control
                characters.
        """
        if not key:
            raise CacheKeyError(_KEY_ERROR)
        try:
            byte_length = len(key.encode("utf-8"))
        except UnicodeEncodeError:
            raise CacheKeyError(_KEY_ERROR) from None
        if byte_length > _KEY_LIMIT or any(
            ord(character) < _CONTROL_CHARACTER_LIMIT
            or ord(character) == _DELETE_CHARACTER_CODE
            for character in key
        ):
            raise CacheKeyError(_KEY_ERROR)
        if self._tag_group is None and key.startswith(_TAG_PREFIX):
            raise CacheKeyError(_RESERVED_TAG_NAMESPACE_ERROR)
        prefix = self._manager.key_prefix(self._name)
        if self._tag_group is not None:
            prefix += self._tag_key_prefix
        return prefix + key

    @property
    def _tag_key_prefix(self) -> str:
        """Return one deterministic prefix for the selected tag group.
        """  # fmt: skip
        if self._tag_group is None:
            return ""
        return f"{_TAG_PREFIX}{self._tag_group}:"

    @property
    def _tagged_backend_prefix(self) -> str:
        """Return the fully application-scoped prefix used for tag clearing.
        """  # fmt: skip
        return self._manager.key_prefix(self._name) + self._tag_key_prefix

    def _lock_key(self, key: str) -> str:
        """Separate stampede locks for distinct tag groups.
        """  # fmt: skip
        if self._tag_group is None:
            return key
        return f"tag-lock:{self._tag_group}:{key}"

    def _serializer(self) -> JSONSerializer:
        """Return the application's size-limited JSON serializer.
        """  # fmt: skip
        return self._manager.serializer

    def _validate_batch(self, keys: Sequence[str]) -> None:
        """Reject large batches before allocating backend operations.

        Args:
            keys: Keys selected for one bulk operation.

        Raises:
            CacheKeyError: If the requested batch exceeds its configured cap.
        """
        if len(keys) > self._manager.configuration.max_batch_size:
            raise CacheKeyError(_BATCH_ERROR)

    _manager: CacheManager
    _name: str


class MemoRepository(Repository):
    """Memoize successful reads within one application execution scope.
    """  # fmt: skip

    def __init__(
        self,
        manager: CacheManager,
        name: str,
        *,
        tags: tuple[str, ...] = (),
    ) -> None:
        """Create one execution-local view over a canonical store.

        Args:
            manager: Application-owned manager that tracks mutations.
            name: Configured underlying store name.
            tags: Optional canonical tag group applied to this view.
        """
        super().__init__(manager, name, tags=tags)
        self._state: ContextVar[_MemoState | None] = ContextVar(
            f"titanspan_cache_memo_{id(self)}",
            default=None,
        )
        self._state_lock = RLock()

    def get[ValueT](
        self,
        key: str,
        default: ValueT | Callable[[], ValueT] | None = None,
    ) -> ValueT | None:
        """Return a memoized hit or read one value from the underlying store.

        Missing results and fallback values are not memoized. This keeps a
        later write visible within the same execution scope.
        """
        state = self._current_state()
        with self._state_lock:
            entry = state.values.get(key)
        if entry is not None and entry[0] == state.generation:
            return cast("ValueT | None", entry[1])
        generation = state.generation
        value = super().get(key, _MISSING)
        if value is _MISSING:
            return _resolve_default(default)
        self._remember(key, state, generation, value)
        return cast("ValueT | None", value)

    async def get_async[ValueT](
        self,
        key: str,
        default: (
            ValueT | Callable[[], ValueT | Awaitable[ValueT]] | None
        ) = None,
    ) -> ValueT | None:
        """Asynchronously reuse one value inside the active execution scope.
        """  # fmt: skip
        state = self._current_state()
        with self._state_lock:
            entry = state.values.get(key)
        if entry is not None and entry[0] == state.generation:
            return cast("ValueT | None", entry[1])
        generation = state.generation
        value = await super().get_async(key, _MISSING)
        if value is _MISSING:
            return await _resolve_default_async(default)
        self._remember(key, state, generation, value)
        return cast("ValueT | None", value)

    def has(self, key: str) -> bool:
        """Check presence through the memoized read path.
        """  # fmt: skip
        return self.get(key, _MISSING) is not _MISSING

    async def has_async(self, key: str) -> bool:
        """Asynchronously check presence through the memoized path.
        """  # fmt: skip
        return await self.get_async(key, _MISSING) is not _MISSING

    def tags(self, *names: str) -> MemoRepository:
        """Return a memoized view with a combined canonical tag group.
        """  # fmt: skip
        tags = _normalize_tags((*self._tags, *names))
        if not self.capabilities.tags:
            msg = f"Store [{self._name}] does not support cache tags."
            raise CacheCapabilityError(msg)
        return MemoRepository(
            self._manager,
            self._name,
            tags=tags,
        )

    def _current_state(self) -> _MemoState:
        """Resolve scope identity and invalidate values after store writes.
        """  # fmt: skip
        active = active_application_context()
        scope = None if active is None else active.scope
        fake = self._manager.fake_identity()
        execution = _memo_execution_identity()
        generation = self._manager.version(self._name)
        if scope is None:
            return _MemoState(
                scope,
                fake,
                execution,
                generation,
                {},
            )
        state = self._state.get()
        if (
            state is None
            or state.scope is not scope
            or state.fake is not fake
            or state.execution != execution
        ):
            state = _MemoState(scope, fake, execution, generation, {})
            self._state.set(state)
        elif state.generation != generation:
            with self._state_lock:
                state.values.clear()
                state.generation = generation
        return state

    def _remember(
        self,
        key: str,
        state: _MemoState,
        generation: int,
        value: object,
    ) -> None:
        """Retain one current-generation result within the active scope.
        """  # fmt: skip
        with self._state_lock:
            if (
                state.generation != generation
                or self._manager.version(self._name) != generation
            ):
                return
            if len(state.values) >= _MEMO_ENTRY_LIMIT:
                state.values.clear()
            state.values[key] = (generation, value)

    _state: ContextVar[_MemoState | None]
    _state_lock: RLock


def _memo_execution_identity() -> tuple[str, int]:
    """Identify the current AnyIO task or synchronous worker thread.
    """  # fmt: skip
    try:
        return ("task", anyio.get_current_task().id)
    except anyio.NoEventLoopError:
        return ("thread", get_ident())


def _resolve_default[DefaultT](
    default: DefaultT | Callable[[], DefaultT] | None,
) -> DefaultT | None:
    """Resolve one synchronous fallback without inspecting cached values.

    Args:
        default: Literal fallback or synchronous zero-argument callable.

    Returns:
        The literal fallback or callback result.
    """
    if callable(default):
        result = default()
        if isawaitable(result):
            if iscoroutine(result):
                result.close()
            msg = "Async defaults require the async cache API."
            raise TypeError(msg)
        return cast("DefaultT | None", result)
    return cast("DefaultT | None", default)


def _normalize_tags(names: tuple[str, ...]) -> tuple[str, ...]:
    """Validate and sort one tag group before deriving its opaque identity.
    """  # fmt: skip
    if not names or len(set(names)) > _TAG_COUNT_LIMIT:
        raise CacheKeyError(_INVALID_TAG_ERROR)
    if any(
        not name
        or len(name) > _TAG_NAME_LIMIT
        or not name.isascii()
        or not name[0].isalnum()
        or any(
            not (character.isalnum() or character in "_.-")
            for character in name
        )
        for name in names
    ):
        raise CacheKeyError(_INVALID_TAG_ERROR)
    return tuple(sorted(set(names)))


def _taggable_backend(
    backend: CacheStore,
    store: str,
) -> TaggableCacheStore:
    """Require explicit tag-group support before starting a clear operation.

    Args:
        backend: Resolved backend selected by one repository.
        store: Store name used only in the native capability error.

    Returns:
        A backend that provides scoped prefix clearing.

    Raises:
        CacheCapabilityError: If grouped clearing is unsupported.
    """
    if not backend.capabilities.tags or not isinstance(
        backend,
        TaggableCacheStore,
    ):
        msg = f"Store [{store}] does not support cache tags."
        raise CacheCapabilityError(msg)
    return backend


async def _resolve_default_async[DefaultT](
    default: (DefaultT | Callable[[], DefaultT | Awaitable[DefaultT]] | None),
) -> DefaultT | None:
    """Resolve a synchronous or asynchronous fallback after a cache miss.

    Args:
        default: Literal value or zero-argument value factory.

    Returns:
        The supplied fallback value.
    """
    if callable(default):
        callback = cast(
            "Callable[[], DefaultT | Awaitable[DefaultT]]",
            default,
        )
        return await invoke_async(callback)
    return cast("DefaultT | None", default)


def _validate_amount(amount: int) -> None:
    """Require a non-negative integer counter adjustment.

    Args:
        amount: Counter change supplied by the caller.

    Raises:
        ValueError: If the amount is negative or not an exact integer.
    """
    if type(amount) is not int or amount < 0:
        msg = "Counter amounts must be non-negative integers."
        raise ValueError(msg)


def _validate_flexible_ages(
    fresh: int | float,
    stale: int | float,
) -> tuple[float, float]:
    """Validate fresh and maximum total stale ages in seconds.
    """  # fmt: skip
    if (
        type(fresh) not in (int, float)
        or type(stale) not in (int, float)
        or not isfinite(fresh)
        or not isfinite(stale)
        or fresh < 0
        or stale <= fresh
    ):
        msg = "Flexible cache ages must be finite with 0 <= fresh < stale."
        raise ValueError(msg)
    return float(fresh), float(stale)


def _make_flexible_entry(value: object) -> dict[str, object]:
    """Wrap a value with the write time used by stale-age checks.
    """  # fmt: skip
    return {
        "marker": _FLEXIBLE_MARKER,
        "written_at": time(),
        "value": value,
    }


def _flexible_entry(value: object) -> tuple[object, float]:
    """Read one compatible flexible entry and compute its total age.
    """  # fmt: skip
    if not isinstance(value, dict):
        return _MISSING, float("inf")
    entry = cast("dict[str, object]", value)
    if entry.get("marker") != _FLEXIBLE_MARKER:
        return _MISSING, float("inf")
    raw_time = entry.get("written_at")
    if type(raw_time) is int:
        written_at = float(raw_time)
    elif type(raw_time) is float:
        written_at = raw_time
    else:
        return _MISSING, float("inf")
    if not isfinite(written_at):
        return _MISSING, float("inf")
    cached_value = entry.get("value", _MISSING)
    if cached_value is _MISSING:
        return _MISSING, float("inf")
    return cached_value, max(0.0, time() - written_at)


def _backend_error(error: Exception) -> CacheBackendError:
    """Translate private backend errors without rendering their messages.

    Args:
        error: Error raised by one backend operation.

    Returns:
        Native error with no private backend message in its exception chain.
    """
    if isinstance(error, ValueError) and str(error).startswith(
        "Cache counters require"
    ):
        return CacheBackendError("Cache counter value is invalid.")
    return CacheBackendError(
        f"Cache backend operation failed ({type(error).__name__})."
    )


__all__ = ["Repository"]
