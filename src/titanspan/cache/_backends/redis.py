"""Adapt redis-py sync and async clients to the private cache store API.

All keys receive a configured application and store prefix. Clearing scans
and deletes only that prefix; it never issues a database-wide flush command.
"""

from __future__ import annotations

from math import ceil, isfinite
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit

from titanspan.cache.exceptions import (
    CacheBackendError,
    CacheConfigurationError,
)
from titanspan.contracts.cache import CacheCapabilities

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Mapping
    from typing import Any

    from redis import Redis
    from redis.asyncio import Redis as AsyncRedis

    from titanspan.cache.configuration import CacheStoreConfiguration

_MAX_DELETE_BATCH = 500
_FROM_URL_METHOD = "from_url"
_INVALID_RESPONSE_ERROR = "Redis returned a non-byte cache value."
_TAG_PREFIX = "tagset:"
_PREFIX_LIMIT = 512
_PORT_LIMIT = 65535
_MAX_SOCKET_TIMEOUT = 60.0
_INVALID_REDIS_URL = "Redis URL must use redis:// or rediss:// with a host."
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""
_PULL_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if value then redis.call('DEL', KEYS[1]) end
return value
"""


def _milliseconds(ttl: float) -> int:
    """Convert positive seconds into Redis millisecond precision.
    """  # fmt: skip
    return max(1, ceil(ttl * 1000))


def _redis_options(
    configuration: CacheStoreConfiguration,
) -> dict[str, object]:
    """Validate a small redis-py connection option allowlist.

    Args:
        configuration: Named store options from application settings.

    Returns:
        Options passed to the sync and async redis-py clients.

    Raises:
        CacheConfigurationError: If an option is malformed.
    """
    options = dict(configuration.options)
    url = options.pop("url", None)
    _validate_redis_url(url)
    allowed = {
        "host",
        "port",
        "db",
        "username",
        "password",
        "ssl",
        "socket_timeout",
        "socket_connect_timeout",
        "max_connections",
    }
    if set(options) - allowed:
        msg = "Redis options contain an unknown key."
        raise CacheConfigurationError(msg)
    _validate_redis_options(options)
    options.setdefault("decode_responses", False)
    options.setdefault("socket_connect_timeout", 2.0)
    options.setdefault("socket_timeout", 2.0)
    options.setdefault("max_connections", 50)
    options["protocol"] = 2
    if url is not None:
        options["url"] = url
    return options


def _validate_redis_url(url: object) -> None:
    """Reject malformed or unsupported connection URLs before creation.
    """  # fmt: skip
    if url is None:
        return
    if not isinstance(url, str) or not url:
        raise CacheConfigurationError(_INVALID_REDIS_URL)
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme in {"redis", "rediss"}
            and parsed.hostname is not None
            and bool(parsed.hostname)
            and (parsed.port is None or 1 <= parsed.port <= _PORT_LIMIT)
        )
    except ValueError:
        valid = False
    if not valid:
        raise CacheConfigurationError(_INVALID_REDIS_URL)


def _validate_redis_options(options: dict[str, object]) -> None:
    """Validate primitive redis-py options without rendering their values.
    """  # fmt: skip
    for name in ("port", "db"):
        value = options.get(name)
        if value is not None and type(value) is not int:
            msg = f"Redis {name} must be an integer."
            raise CacheConfigurationError(msg)
    if type(options.get("ssl", False)) is not bool:
        msg = "Redis ssl must be a boolean."
        raise CacheConfigurationError(msg)
    maximum = options.get("max_connections")
    if maximum is not None:
        if type(maximum) is not int:
            msg = "Redis max_connections must be an integer."
            raise CacheConfigurationError(msg)
        if maximum < 1:
            msg = "Redis max_connections must be positive."
            raise CacheConfigurationError(msg)
    for name in ("host", "username", "password"):
        value = options.get(name)
        if value is not None and not isinstance(value, str):
            msg = f"Redis {name} must be text."
            raise CacheConfigurationError(msg)
    _validate_redis_timeouts(options)


def _validate_redis_timeouts(options: dict[str, object]) -> None:
    """Validate bounded connection and operation timeout settings.
    """  # fmt: skip
    for name in ("socket_timeout", "socket_connect_timeout"):
        value = options.get(name)
        if value is None:
            continue
        if type(value) in (int, float):
            timeout = cast("int | float", value)
            valid = 0 < timeout <= _MAX_SOCKET_TIMEOUT and isfinite(timeout)
        else:
            valid = False
        if not valid:
            msg = f"Redis {name} must be a positive duration."
            raise CacheConfigurationError(msg)


class RedisStore:
    """Provide namespace-safe storage through redis-py clients.
    """  # fmt: skip

    capabilities = CacheCapabilities(
        atomic_add=True,
        atomic_increment=True,
        atomic_pull=True,
        tags=True,
        tag_invalidation_atomic=False,
        scoped_clear=True,
        locks=True,
        distributed_locks=True,
        lock_scoped_clear=True,
    )

    def __init__(
        self,
        configuration: CacheStoreConfiguration,
        *,
        prefix: str,
    ) -> None:
        """Prepare client options without opening network connections.
        """  # fmt: skip
        try:
            import redis  # noqa: PLC0415
            from redis import asyncio as redis_async  # noqa: PLC0415
        except ImportError:
            msg = "Redis caching requires the optional redis extra."
            raise CacheConfigurationError(msg) from None
        options = _redis_options(configuration)
        self._prefix = prefix
        url = options.pop("url", None)
        sync_options = cast("Any", options)
        async_options = cast("Any", options)
        if isinstance(url, str):
            sync_factory = getattr(redis.Redis, _FROM_URL_METHOD)
            async_factory = getattr(redis_async.Redis, _FROM_URL_METHOD)
            self._sync = cast("Redis", sync_factory(url, **sync_options))
            self._async = cast(
                "AsyncRedis",
                async_factory(url, **async_options),
            )
        else:
            self._sync = redis.Redis(**sync_options)
            self._async = redis_async.Redis(**async_options)
        self._closed = False

    def _key(self, key: str) -> str:
        """Prefix a repository key within this store namespace.
        """  # fmt: skip
        logical = self._logical_key(key)
        return f"{self._prefix}data:{logical}"

    def _lock_key(self, key: str) -> str:
        """Keep coordination keys outside the ordinary clear namespace.
        """  # fmt: skip
        logical = self._logical_key(key)
        return f"{self._prefix}locks:{logical}"

    def _logical_key(self, key: str) -> str:
        """Remove the application prefix already applied by Repository.
        """  # fmt: skip
        return key.removeprefix(self._prefix)

    def get(self, key: str) -> bytes | None:
        """Return serialized bytes for a key or a miss.
        """  # fmt: skip
        return _as_bytes(self._sync.get(self._key(key)))

    async def get_async(self, key: str) -> bytes | None:
        """Asynchronously return serialized bytes for a key or a miss.
        """  # fmt: skip
        return _as_bytes(await self._async.get(self._key(key)))

    def set(self, key: str, value: bytes, *, ttl: float | None) -> bool:
        """Write bytes with Redis expiry or indefinite retention.
        """  # fmt: skip
        redis_key = self._key(key)
        if ttl is not None and ttl <= 0:
            self._sync.delete(redis_key)
            return True
        result = self._sync.set(
            redis_key,
            value,
            px=None if ttl is None else _milliseconds(ttl),
        )
        return result is True

    async def set_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Asynchronously write bytes with a bounded expiration.
        """  # fmt: skip
        redis_key = self._key(key)
        if ttl is not None and ttl <= 0:
            await self._async.delete(redis_key)
            return True
        result = await self._async.set(
            redis_key,
            value,
            px=None if ttl is None else _milliseconds(ttl),
        )
        return result is True

    def add(self, key: str, value: bytes, *, ttl: float | None) -> bool:
        """Atomically create a key using Redis SET NX.
        """  # fmt: skip
        if ttl is not None and ttl <= 0:
            return False
        return (
            self._sync.set(
                self._key(key),
                value,
                nx=True,
                px=None if ttl is None else _milliseconds(ttl),
            )
            is True
        )

    async def add_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Asynchronously create a key using Redis SET NX.
        """  # fmt: skip
        if ttl is not None and ttl <= 0:
            return False
        return (
            await self._async.set(
                self._key(key),
                value,
                nx=True,
                px=None if ttl is None else _milliseconds(ttl),
            )
            is True
        )

    def pull(self, key: str) -> bytes | None:
        """Atomically retrieve and delete a key using one Lua script.
        """  # fmt: skip
        return _as_bytes(self._sync.eval(_PULL_SCRIPT, 1, self._key(key)))

    async def pull_async(self, key: str) -> bytes | None:
        """Asynchronously atomically retrieve and delete a key.
        """  # fmt: skip
        return _as_bytes(
            await self._async.eval(_PULL_SCRIPT, 1, self._key(key))
        )

    def delete(self, key: str) -> bool:
        """Remove one key and report whether it existed.
        """  # fmt: skip
        return self._sync.delete(self._key(key)) > 0

    async def delete_async(self, key: str) -> bool:
        """Asynchronously remove one key.
        """  # fmt: skip
        return await self._async.delete(self._key(key)) > 0

    def clear(self) -> None:
        """Delete keys matching only this configured application prefix.
        """  # fmt: skip
        self._delete_matching(f"{self._prefix}data:*")

    async def clear_async(self) -> None:
        """Asynchronously delete only keys in this configured namespace.
        """  # fmt: skip
        await self._delete_matching_async(f"{self._prefix}data:*")

    def clear_prefix(self, prefix: str) -> None:
        """Delete keys below one safe logical prefix within this store.
        """  # fmt: skip
        _validate_logical_prefix(prefix)
        self._delete_matching(f"{self._prefix}data:{prefix}*")

    async def clear_prefix_async(self, prefix: str) -> None:
        """Asynchronously delete keys below one logical prefix.
        """  # fmt: skip
        _validate_logical_prefix(prefix)
        await self._delete_matching_async(f"{self._prefix}data:{prefix}*")

    def clear_tagged(self, prefix: str) -> None:
        """Scan and delete keys under a validated tag-group prefix.
        """  # fmt: skip
        logical = self._tag_group_prefix(prefix)
        self._delete_matching(f"{self._prefix}data:{logical}*")

    async def clear_tagged_async(self, prefix: str) -> None:
        """Asynchronously clear one tag group within the configured prefix.
        """  # fmt: skip
        logical = self._tag_group_prefix(prefix)
        await self._delete_matching_async(f"{self._prefix}data:{logical}*")

    def _tag_group_prefix(self, prefix: str) -> str:
        """Validate opaque tag-group hashes before forming a Redis pattern.
        """  # fmt: skip
        if not prefix.startswith(self._prefix):
            msg = "Cache tag clearing is outside the configured namespace."
            raise CacheConfigurationError(msg)
        logical = self._logical_key(prefix)
        expected_length = len(_TAG_PREFIX) + 64 + 1
        digest = logical[len(_TAG_PREFIX) : -1]
        if (
            len(logical) != expected_length
            or not logical.startswith(_TAG_PREFIX)
            or not logical.endswith(":")
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            msg = "Cache tag clearing requires a valid tag-group prefix."
            raise CacheConfigurationError(msg)
        return logical

    def _delete_matching(self, pattern: str) -> None:
        """Scan and batch-delete one application-owned Redis key pattern.
        """  # fmt: skip
        batch: list[bytes] = []
        client = cast("Any", self._sync)
        keys = cast(
            "Iterator[object]",
            client.scan_iter(match=pattern),
        )
        for raw_key in keys:
            key = _as_bytes(raw_key)
            if key is None:
                continue
            batch.append(key)
            if len(batch) == _MAX_DELETE_BATCH:
                self._sync.delete(*batch)
                batch.clear()
        if batch:
            self._sync.delete(*batch)

    async def _delete_matching_async(self, pattern: str) -> None:
        """Asynchronously scan and batch-delete one Redis key pattern.
        """  # fmt: skip
        batch: list[bytes] = []
        client = cast("Any", self._async)
        keys = cast(
            "AsyncIterator[object]",
            client.scan_iter(match=pattern),
        )
        async for raw_key in keys:
            key = _as_bytes(raw_key)
            if key is None:
                continue
            batch.append(key)
            if len(batch) == _MAX_DELETE_BATCH:
                await self._async.delete(*batch)
                batch.clear()
        if batch:
            await self._async.delete(*batch)

    def increment(self, key: str, amount: int) -> int:
        """Atomically increment a strict integer value with Redis INCRBY.
        """  # fmt: skip
        return self._sync.incrby(self._key(key), amount)

    async def increment_async(self, key: str, amount: int) -> int:
        """Asynchronously atomically increment a Redis integer value.
        """  # fmt: skip
        return await self._async.incrby(self._key(key), amount)

    def touch(self, key: str, *, ttl: float | None) -> bool:
        """Change expiration for an existing key without rewriting bytes.
        """  # fmt: skip
        redis_key = self._key(key)
        if ttl is not None and ttl <= 0:
            return self._sync.delete(redis_key) > 0
        if ttl is None:
            return bool(self._sync.persist(redis_key))
        return bool(self._sync.pexpire(redis_key, _milliseconds(ttl)))

    async def touch_async(self, key: str, *, ttl: float | None) -> bool:
        """Asynchronously replace a key's expiration policy.
        """  # fmt: skip
        redis_key = self._key(key)
        if ttl is not None and ttl <= 0:
            return await self._async.delete(redis_key) > 0
        if ttl is None:
            return bool(await self._async.persist(redis_key))
        return bool(await self._async.pexpire(redis_key, _milliseconds(ttl)))

    def acquire_lock(self, key: str, owner: str, ttl: float) -> bool:
        """Acquire one distributed lock with SET NX and a millisecond lease.
        """  # fmt: skip
        return (
            self._sync.set(
                self._lock_key(key),
                owner.encode("ascii"),
                nx=True,
                px=_milliseconds(ttl),
            )
            is True
        )

    async def acquire_lock_async(
        self,
        key: str,
        owner: str,
        ttl: float,
    ) -> bool:
        """Asynchronously acquire an owner-token Redis lease.
        """  # fmt: skip
        return (
            await self._async.set(
                self._lock_key(key),
                owner.encode("ascii"),
                nx=True,
                px=_milliseconds(ttl),
            )
            is True
        )

    def release_lock(self, key: str, owner: str) -> bool:
        """Release a lock only when Redis still stores the owner token.
        """  # fmt: skip
        return bool(
            self._sync.eval(
                _RELEASE_SCRIPT,
                1,
                self._lock_key(key),
                owner,
            )
        )

    async def release_lock_async(self, key: str, owner: str) -> bool:
        """Asynchronously owner-check and release a Redis lock.
        """  # fmt: skip
        return bool(
            await self._async.eval(
                _RELEASE_SCRIPT,
                1,
                self._lock_key(key),
                owner,
            )
        )

    def lock_owner(self, key: str) -> str | None:
        """Return a lock owner token for explicit ownership inspection.
        """  # fmt: skip
        value = _as_bytes(self._sync.get(self._lock_key(key)))
        return None if value is None else value.decode("ascii")

    async def lock_owner_async(self, key: str) -> str | None:
        """Asynchronously return the current lock owner token.
        """  # fmt: skip
        value = _as_bytes(await self._async.get(self._lock_key(key)))
        return None if value is None else value.decode("ascii")

    def force_release_lock(self, key: str) -> bool:
        """Administratively remove one lock inside this store namespace.
        """  # fmt: skip
        return self._sync.delete(self._lock_key(key)) > 0

    async def force_release_lock_async(self, key: str) -> bool:
        """Asynchronously administratively remove one scoped lock.
        """  # fmt: skip
        return await self._async.delete(self._lock_key(key)) > 0

    def clear_locks(self) -> None:
        """Clear only lock leases inside this Redis store namespace.
        """  # fmt: skip
        self._delete_matching(f"{self._prefix}locks:*")

    async def clear_locks_async(self) -> None:
        """Asynchronously clear lock leases inside this Redis namespace.
        """  # fmt: skip
        await self._delete_matching_async(f"{self._prefix}locks:*")

    def stats(self) -> dict[str, int | float | None]:
        """Return safe aggregate server metadata without keys or secrets.
        """  # fmt: skip
        client = cast("Any", self._sync)
        info = cast("Mapping[str, object]", client.info("memory"))
        return {
            "used_memory": _number_or_none(info.get("used_memory")),
            "maxmemory": _number_or_none(info.get("maxmemory")),
        }

    async def stats_async(self) -> dict[str, int | float | None]:
        """Asynchronously return safe aggregate memory metadata.
        """  # fmt: skip
        client = cast("Any", self._async)
        info = cast(
            "Mapping[str, object]",
            await client.info("memory"),
        )
        return {
            "used_memory": _number_or_none(info.get("used_memory")),
            "maxmemory": _number_or_none(info.get("maxmemory")),
        }

    async def aclose(self) -> None:
        """Close sync and async clients without opening unused connections.
        """  # fmt: skip
        if self._closed:
            return
        self._closed = True
        try:
            await self._async.aclose()
        finally:
            self._sync.close()

    _prefix: str
    _sync: Redis
    _async: AsyncRedis
    _closed: bool


def _number_or_none(value: object) -> int | float | None:
    """Retain only finite numeric Redis diagnostic values.
    """  # fmt: skip
    if type(value) is int:
        return value
    if type(value) is float and isfinite(value):
        return value
    return None


def _as_bytes(value: object) -> bytes | None:
    """Validate the configured byte response mode at the Redis boundary.
    """  # fmt: skip
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    raise CacheBackendError(_INVALID_RESPONSE_ERROR)


def _validate_logical_prefix(prefix: str) -> None:
    """Reject Redis glob syntax and unbounded scoped-clear patterns.
    """  # fmt: skip
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    allowed += "0123456789:_-."
    if (
        type(prefix) is not str
        or not prefix
        or len(prefix.encode("utf-8")) > _PREFIX_LIMIT
        or any(character not in allowed for character in prefix)
    ):
        msg = "Cache clear prefixes must be safe non-empty text."
        raise CacheConfigurationError(msg)


__all__ = ["RedisStore"]
