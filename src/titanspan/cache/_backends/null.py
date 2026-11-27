"""Provide an explicitly disabled cache backend.
"""  # fmt: skip

from titanspan.contracts.cache import CacheCapabilities

_PREFIX_LIMIT = 512
_INVALID_PREFIX_ERROR = "Cache clear prefixes must be safe non-empty text."


class NullStore:
    """Discard writes and return misses for every key.
    """  # fmt: skip

    capabilities = CacheCapabilities(
        atomic_add=False,
        atomic_increment=False,
        atomic_pull=False,
        tags=False,
        tag_invalidation_atomic=False,
        scoped_clear=True,
        locks=False,
        distributed_locks=False,
        lock_scoped_clear=False,
    )

    def get(self, key: str) -> bytes | None:
        """Return a miss for a key without storing it.
        """  # fmt: skip
        del key
        return None

    async def get_async(self, key: str) -> bytes | None:
        """Return an asynchronous cache miss.
        """  # fmt: skip
        return self.get(key)

    def set(self, key: str, value: bytes, *, ttl: float | None) -> bool:
        """Discard one write and report successful handling.
        """  # fmt: skip
        del key, value, ttl
        return True

    async def set_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Asynchronously discard one write.
        """  # fmt: skip
        return self.set(key, value, ttl=ttl)

    def add(self, key: str, value: bytes, *, ttl: float | None) -> bool:
        """Report no insertion because the null store retains no values.
        """  # fmt: skip
        del key, value, ttl
        return False

    async def add_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Asynchronously report no retained value.
        """  # fmt: skip
        return self.add(key, value, ttl=ttl)

    def pull(self, key: str) -> bytes | None:
        """Return a miss because the store is always empty.
        """  # fmt: skip
        return self.get(key)

    async def pull_async(self, key: str) -> bytes | None:
        """Asynchronously return a miss.
        """  # fmt: skip
        return self.get(key)

    def delete(self, key: str) -> bool:
        """Report no removal because no value can exist.
        """  # fmt: skip
        del key
        return False

    async def delete_async(self, key: str) -> bool:
        """Asynchronously report that no value was removed.
        """  # fmt: skip
        return self.delete(key)

    def clear(self) -> None:
        """Complete a clear against an always-empty store.
        """  # fmt: skip

    async def clear_async(self) -> None:
        """Asynchronously clear an always-empty store.
        """  # fmt: skip

    def clear_prefix(self, prefix: str) -> None:
        """Complete a scoped clear against an always-empty store.
        """  # fmt: skip
        _validate_prefix(prefix)

    async def clear_prefix_async(self, prefix: str) -> None:
        """Asynchronously complete a scoped clear against an empty store.
        """  # fmt: skip
        self.clear_prefix(prefix)

    def increment(self, key: str, amount: int) -> int:
        """Reject unsupported counter mutation.
        """  # fmt: skip
        del key, amount
        raise NotImplementedError

    async def increment_async(self, key: str, amount: int) -> int:
        """Reject asynchronous counter mutation.
        """  # fmt: skip
        return self.increment(key, amount)

    def touch(self, key: str, *, ttl: float | None) -> bool:
        """Report that no value was touched.
        """  # fmt: skip
        del key, ttl
        return False

    async def touch_async(self, key: str, *, ttl: float | None) -> bool:
        """Asynchronously report that no value was touched.
        """  # fmt: skip
        return self.touch(key, ttl=ttl)

    async def aclose(self) -> None:
        """Release no resources.
        """  # fmt: skip


def _validate_prefix(prefix: str) -> None:
    """Reject empty or pattern-sensitive prefix inputs.
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


__all__ = ["NullStore"]
