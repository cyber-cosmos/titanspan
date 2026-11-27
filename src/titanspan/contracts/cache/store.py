"""Define the portable sync and async cache backend contract.

The contract transports safe serialized bytes and keeps infrastructure types
inside private adapters.
"""

from typing import Protocol, runtime_checkable

from titanspan.contracts.cache.capabilities import CacheCapabilities


@runtime_checkable
class CacheStore(Protocol):
    """Describe one application-owned backend with explicit capabilities.

    Implementations own bounded storage and connection cleanup. Values cross
    this boundary as bytes produced by Titanspan's safe serializer.
    """

    @property
    def capabilities(self) -> CacheCapabilities:
        """Return guarantees supported by this store instance.
        """  # fmt: skip
        ...

    def get(self, key: str) -> bytes | None:
        """Return one serialized value, or ``None`` for a cache miss.
        """  # fmt: skip
        ...

    async def get_async(self, key: str) -> bytes | None:
        """Asynchronously return one serialized value or a cache miss.
        """  # fmt: skip
        ...

    def set(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Store bytes for a duration in seconds or indefinitely.
        """  # fmt: skip
        ...

    async def set_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Asynchronously store bytes for a duration in seconds.
        """  # fmt: skip
        ...

    def add(self, key: str, value: bytes, *, ttl: float | None) -> bool:
        """Atomically store bytes only when the key is absent.
        """  # fmt: skip
        ...

    async def add_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Asynchronously add bytes only when the key is absent.
        """  # fmt: skip
        ...

    def pull(self, key: str) -> bytes | None:
        """Atomically retrieve and remove one key when supported.
        """  # fmt: skip
        ...

    async def pull_async(self, key: str) -> bytes | None:
        """Asynchronously retrieve and remove one key atomically.
        """  # fmt: skip
        ...

    def delete(self, key: str) -> bool:
        """Remove one key and report whether it existed.
        """  # fmt: skip
        ...

    async def delete_async(self, key: str) -> bool:
        """Asynchronously remove one key.
        """  # fmt: skip
        ...

    def clear(self) -> None:
        """Remove cache data owned by this store namespace.
        """  # fmt: skip
        ...

    async def clear_async(self) -> None:
        """Asynchronously remove data owned by this namespace.
        """  # fmt: skip
        ...

    def increment(self, key: str, amount: int) -> int:
        """Atomically increment a non-negative integer value.
        """  # fmt: skip
        ...

    async def increment_async(self, key: str, amount: int) -> int:
        """Asynchronously increment an integer value atomically.
        """  # fmt: skip
        ...

    def touch(self, key: str, *, ttl: float | None) -> bool:
        """Replace expiration for an existing value.
        """  # fmt: skip
        ...

    async def touch_async(self, key: str, *, ttl: float | None) -> bool:
        """Asynchronously replace expiration for an existing value.
        """  # fmt: skip
        ...

    async def aclose(self) -> None:
        """Release backend resources owned by this application.
        """  # fmt: skip
        ...


__all__ = ["CacheStore"]
