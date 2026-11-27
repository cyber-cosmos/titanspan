"""Adapt cachetools' bounded TLRU collection to the native store contract.

cachetools supplies eviction and time-based expiry. A reentrant lock protects
its documented non-thread-safe collection across sync and async callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import TYPE_CHECKING

from cachetools import TLRUCache

from titanspan.cache.exceptions import CacheBackendError
from titanspan.contracts.cache import CacheCapabilities

if TYPE_CHECKING:
    from collections.abc import Callable

_CLOSED_ERROR = "The memory cache store is closed."
_INVALID_COUNTER_ERROR = "Cache counters require stored integer values."
_INVALID_PREFIX_ERROR = "Cache clear prefixes must be safe non-empty text."
_PREFIX_LIMIT = 512
_LOCK_CAPACITY_ERROR = "The memory cache lock limit has been reached."


@dataclass(frozen=True, slots=True)
class _Entry:
    """Retain one already-serialized value and its absolute expiry.

    Attributes:
        payload: Safe JSON bytes written by the native repository.
        expires_at: Monotonic expiry used by cachetools' TLRU policy.
    """

    payload: bytes
    expires_at: float


class MemoryStore:
    """Provide bounded process-local storage shared by sync and async calls.

    The store uses cachetools' public ``TLRUCache`` API. Its public methods
    never perform I/O or create event loops.
    """

    capabilities = CacheCapabilities(
        atomic_add=True,
        atomic_increment=True,
        atomic_pull=True,
        tags=True,
        tag_invalidation_atomic=False,
        scoped_clear=True,
        locks=True,
        distributed_locks=False,
        lock_scoped_clear=True,
    )

    def __init__(
        self,
        *,
        max_items: int = 10_000,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        """Create a bounded store using a monotonic expiry clock.

        Args:
            max_items: Maximum number of live values retained by the store.
            clock: Monotonic time source used for deterministic testing.

        Raises:
            ValueError: If ``max_items`` is not a positive integer.
        """
        if type(max_items) is not int or max_items < 1:
            msg = "Memory cache max_items must be positive."
            raise ValueError(msg)
        self._clock = clock
        self._lock = RLock()
        self._closed = False
        self._locks: dict[str, tuple[str, float]] = {}
        self._entries: TLRUCache[str, _Entry] = TLRUCache(
            maxsize=max_items,
            ttu=_entry_expiry,
            timer=clock,
        )

    def get(self, key: str) -> bytes | None:
        """Return one live payload without conflating false-like bytes.

        Args:
            key: Backend key already scoped by its repository.

        Returns:
            Payload bytes or ``None`` when the key is missing or expired.
        """
        with self._lock:
            self._ensure_open()
            entry = self._entries.get(key)
            return None if entry is None else entry.payload

    async def get_async(self, key: str) -> bytes | None:
        """Asynchronously return a payload from process-local storage.

        Args:
            key: Backend key already scoped by its repository.

        Returns:
            Payload bytes or ``None`` for a miss.
        """
        return self.get(key)

    def set(self, key: str, value: bytes, *, ttl: float | None) -> bool:
        """Store a value with optional duration-based expiration.

        Args:
            key: Backend key already scoped by its repository.
            value: Safe serialized bytes.
            ttl: Positive duration in seconds or ``None`` for forever.

        Returns:
            Whether the value was retained.
        """
        if ttl is not None and ttl <= 0:
            self.delete(key)
            return True
        expiry = float("inf") if ttl is None else self._clock() + ttl
        with self._lock:
            self._ensure_open()
            self._entries[key] = _Entry(value, expiry)
        return True

    async def set_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Asynchronously store a value in process-local storage.

        Args:
            key: Backend key already scoped by its repository.
            value: Safe serialized bytes.
            ttl: Positive duration in seconds or ``None`` for forever.

        Returns:
            Whether the value was retained.
        """
        return self.set(key, value, ttl=ttl)

    def add(self, key: str, value: bytes, *, ttl: float | None) -> bool:
        """Atomically add a value only when the key is absent.

        Args:
            key: Backend key already scoped by its repository.
            value: Safe serialized bytes.
            ttl: Positive duration in seconds or ``None`` for forever.

        Returns:
            Whether this call stored the value.
        """
        with self._lock:
            self._ensure_open()
            if key in self._entries or (ttl is not None and ttl <= 0):
                return False
            expiry = float("inf") if ttl is None else self._clock() + ttl
            self._entries[key] = _Entry(value, expiry)
            return True

    async def add_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Asynchronously perform atomic add-if-absent.

        Args:
            key: Backend key already scoped by its repository.
            value: Safe serialized bytes.
            ttl: Positive duration in seconds or ``None`` for forever.

        Returns:
            Whether this call stored the value.
        """
        return self.add(key, value, ttl=ttl)

    def pull(self, key: str) -> bytes | None:
        """Atomically read and remove a value under the store lock.

        Args:
            key: Backend key already scoped by its repository.

        Returns:
            Payload bytes or ``None`` for a miss.
        """
        with self._lock:
            self._ensure_open()
            entry = self._entries.pop(key, None)
            return None if entry is None else entry.payload

    async def pull_async(self, key: str) -> bytes | None:
        """Asynchronously retrieve and remove one value atomically.

        Args:
            key: Backend key already scoped by its repository.

        Returns:
            Payload bytes or ``None`` for a miss.
        """
        return self.pull(key)

    def delete(self, key: str) -> bool:
        """Remove one key and report whether it existed.

        Args:
            key: Backend key already scoped by its repository.

        Returns:
            Whether a value was removed.
        """
        with self._lock:
            self._ensure_open()
            return self._entries.pop(key, None) is not None

    async def delete_async(self, key: str) -> bool:
        """Asynchronously remove one process-local value.

        Args:
            key: Backend key already scoped by its repository.

        Returns:
            Whether a value was removed.
        """
        return self.delete(key)

    def clear(self) -> None:
        """Remove every value owned by this application store.

        Memory stores are application-owned instances, so this cannot clear a
        different application's data.
        """
        with self._lock:
            self._ensure_open()
            self._entries.clear()

    async def clear_async(self) -> None:
        """Asynchronously clear this application-owned memory store.
        """  # fmt: skip
        self.clear()

    def clear_tagged(self, prefix: str) -> None:
        """Remove only entries in one already validated tag key group.
        """  # fmt: skip
        with self._lock:
            self._ensure_open()
            for key in tuple(self._entries):
                if key.startswith(prefix):
                    self._entries.pop(key, None)

    async def clear_tagged_async(self, prefix: str) -> None:
        """Asynchronously clear one application-scoped tag group.
        """  # fmt: skip
        self.clear_tagged(prefix)

    def clear_prefix(self, prefix: str) -> None:
        """Remove entries under one bounded, safe logical key prefix.
        """  # fmt: skip
        _validate_prefix(prefix)
        with self._lock:
            self._ensure_open()
            for key in tuple(self._entries):
                if key.startswith(prefix):
                    self._entries.pop(key, None)

    async def clear_prefix_async(self, prefix: str) -> None:
        """Asynchronously clear only keys under a logical key prefix.
        """  # fmt: skip
        self.clear_prefix(prefix)

    def contains_suffix(self, prefix: str, suffix: str) -> bool:
        """Find one live fake entry without exposing cached payloads.
        """  # fmt: skip
        with self._lock:
            self._ensure_open()
            self._entries.expire()
            return any(
                key.startswith(prefix) and key.endswith(suffix)
                for key in self._entries
            )

    def increment(self, key: str, amount: int) -> int:
        """Atomically increment an integer and retain its current expiry.

        Args:
            key: Backend key already scoped by its repository.
            amount: Non-negative amount added to the current integer.

        Returns:
            The resulting integer value.

        Raises:
            ValueError: If the stored payload is not an integer.
        """
        with self._lock:
            self._ensure_open()
            entry = self._entries.get(key)
            current = 0 if entry is None else _decode_integer(entry.payload)
            result = current + amount
            expiry = float("inf") if entry is None else entry.expires_at
            self._entries[key] = _Entry(str(result).encode("ascii"), expiry)
            return result

    async def increment_async(self, key: str, amount: int) -> int:
        """Asynchronously increment one integer value atomically.

        Args:
            key: Backend key already scoped by its repository.
            amount: Non-negative amount added to the current integer.

        Returns:
            The resulting integer value.
        """
        return self.increment(key, amount)

    def touch(self, key: str, *, ttl: float | None) -> bool:
        """Replace expiration without restoring an expired key.

        Args:
            key: Backend key already scoped by its repository.
            ttl: Positive duration or ``None`` for indefinite storage.

        Returns:
            Whether a live value received the new expiry.
        """
        with self._lock:
            self._ensure_open()
            entry = self._entries.get(key)
            if entry is None:
                return False
            if ttl is not None and ttl <= 0:
                del self._entries[key]
                return True
            expiry = float("inf") if ttl is None else self._clock() + ttl
            self._entries[key] = _Entry(entry.payload, expiry)
            return True

    async def touch_async(self, key: str, *, ttl: float | None) -> bool:
        """Asynchronously change expiration on a live value.

        Args:
            key: Backend key already scoped by its repository.
            ttl: Positive duration or ``None`` for indefinite storage.

        Returns:
            Whether the value existed when touched.
        """
        return self.touch(key, ttl=ttl)

    def acquire_lock(self, key: str, owner: str, ttl: float) -> bool:
        """Acquire one process-local lease atomically.
        """  # fmt: skip
        with self._lock:
            self._ensure_open()
            now = self._clock()
            self._expire_locks(now)
            current = self._locks.get(key)
            if current is not None and current[1] > now:
                return False
            if len(self._locks) >= self._entries.maxsize:
                raise CacheBackendError(_LOCK_CAPACITY_ERROR)
            self._locks[key] = (owner, now + ttl)
            return True

    async def acquire_lock_async(
        self,
        key: str,
        owner: str,
        ttl: float,
    ) -> bool:
        """Asynchronously acquire one process-local lease.
        """  # fmt: skip
        return self.acquire_lock(key, owner, ttl)

    def release_lock(self, key: str, owner: str) -> bool:
        """Release a lease only if the supplied token still owns it.
        """  # fmt: skip
        with self._lock:
            self._ensure_open()
            self._expire_locks(self._clock())
            current = self._locks.get(key)
            if current is None:
                return False
            if current[1] <= self._clock():
                self._locks.pop(key, None)
                return False
            if current[0] != owner:
                return False
            self._locks.pop(key)
            return True

    async def release_lock_async(self, key: str, owner: str) -> bool:
        """Asynchronously release a process-local lease.
        """  # fmt: skip
        return self.release_lock(key, owner)

    def lock_owner(self, key: str) -> str | None:
        """Return the live owner token or ``None`` after lease expiry.
        """  # fmt: skip
        with self._lock:
            self._ensure_open()
            self._expire_locks(self._clock())
            current = self._locks.get(key)
            if current is None:
                return None
            if current[1] <= self._clock():
                self._locks.pop(key, None)
                return None
            return current[0]

    async def lock_owner_async(self, key: str) -> str | None:
        """Asynchronously inspect a process-local lease owner.
        """  # fmt: skip
        return self.lock_owner(key)

    def force_release_lock(self, key: str) -> bool:
        """Administratively remove a lease without owner validation.
        """  # fmt: skip
        with self._lock:
            self._ensure_open()
            return self._locks.pop(key, None) is not None

    async def force_release_lock_async(self, key: str) -> bool:
        """Asynchronously force release a process-local lease.
        """  # fmt: skip
        return self.force_release_lock(key)

    def clear_locks(self) -> None:
        """Clear leases owned by this application store instance.
        """  # fmt: skip
        with self._lock:
            self._ensure_open()
            self._locks.clear()

    async def clear_locks_async(self) -> None:
        """Asynchronously clear leases in this process-local store.
        """  # fmt: skip
        self.clear_locks()

    def stats(self) -> dict[str, int | float | None]:
        """Return bounded counts without exposing keys or cached payloads.
        """  # fmt: skip
        with self._lock:
            self._ensure_open()
            self._expire_locks(self._clock())
            self._entries.expire()
            return {
                "items": len(self._entries),
                "capacity": self._entries.maxsize,
                "locks": len(self._locks),
            }

    async def aclose(self) -> None:
        """Close this store and release its bounded in-memory entries.
        """  # fmt: skip
        with self._lock:
            self._entries.clear()
            self._locks.clear()
            self._closed = True

    def _ensure_open(self) -> None:
        """Reject access after application-owned shutdown.

        Raises:
            CacheBackendError: If the manager already closed this store.
        """
        if self._closed:
            raise CacheBackendError(_CLOSED_ERROR)

    def _expire_locks(self, now: float) -> None:
        """Release expired ownership metadata before bounded lock access.
        """  # fmt: skip
        for key, (_, deadline) in tuple(self._locks.items()):
            if deadline <= now:
                self._locks.pop(key, None)

    _clock: Callable[[], float]
    _lock: RLock
    _closed: bool
    _entries: TLRUCache[str, _Entry]


def _entry_expiry(key: str, entry: _Entry, now: float) -> float:
    """Return a TLRU deadline for one serialized value.

    Args:
        key: Unused cache key passed by cachetools' public callback contract.
        entry: Value carrying its exact deadline.
        now: Current monotonic time supplied by the collection.

    Returns:
        The entry's finite or indefinite expiry deadline.
    """
    del key, now
    return entry.expires_at


def _decode_integer(payload: bytes) -> int:
    """Accept only exact JSON integer bytes for atomic counter operations.

    Args:
        payload: Serialized value stored for a counter key.

    Returns:
        The stored integer.

    Raises:
        ValueError: If the value is not a strict integer representation.
    """
    try:
        decoded = payload.decode("ascii")
        value = int(decoded)
    except (UnicodeDecodeError, ValueError):
        raise ValueError(_INVALID_COUNTER_ERROR) from None
    if str(value) != decoded:
        raise ValueError(_INVALID_COUNTER_ERROR)
    return value


def _validate_prefix(prefix: str) -> None:
    """Reject empty, oversized, or pattern-sensitive key prefixes.
    """  # fmt: skip
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    allowed += "0123456789:_-."
    if (
        type(prefix) is not str
        or not prefix
        or len(prefix.encode("utf-8")) > _PREFIX_LIMIT
        or any(character not in allowed for character in prefix)
    ):
        raise ValueError(_INVALID_PREFIX_ERROR)


__all__ = ["MemoryStore"]
