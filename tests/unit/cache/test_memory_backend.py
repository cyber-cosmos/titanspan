"""Verify bounded memory adapter behavior through its real public methods.
"""  # fmt: skip

from typing import TYPE_CHECKING

import pytest

from titanspan.cache._backends.memory import MemoryStore
from titanspan.cache.exceptions import CacheBackendError

pytestmark = pytest.mark.unit
_LOCK_OWNER = "owner-token"
_COUNTER_TWO = 2

if TYPE_CHECKING:
    from collections.abc import Iterator


def test_memory_store_rejects_invalid_capacity_and_counter_payloads() -> None:
    """Validate construction limits and strict integer counter encoding.
    """  # fmt: skip
    with pytest.raises(ValueError, match="max_items"):
        MemoryStore(max_items=0)
    store = MemoryStore()
    for payload in (b"01", b"not-ascii-\xff"):
        store.set("counter", payload, ttl=None)
        with pytest.raises(ValueError, match="integer values"):
            store.increment("counter", 1)
    with pytest.raises(ValueError, match="prefixes"):
        store.clear_prefix("bad*")


def test_memory_store_reclaims_clock_expired_owner_records() -> None:
    """Defend release and inspection against a lease expiring mid-call.
    """  # fmt: skip
    release_times: Iterator[float] = iter((100.0, 100.5, 101.5))
    release_store = MemoryStore(clock=lambda: next(release_times))
    assert release_store.acquire_lock("release", _LOCK_OWNER, 1)
    assert not release_store.release_lock("release", _LOCK_OWNER)

    inspect_times: Iterator[float] = iter((200.0, 200.5, 201.5))
    inspect_store = MemoryStore(clock=lambda: next(inspect_times))
    assert inspect_store.acquire_lock("inspect", _LOCK_OWNER, 1)
    assert inspect_store.lock_owner("inspect") is None


@pytest.mark.anyio
async def test_memory_store_async_methods_share_bounded_sync_state() -> None:
    """Use each async method against the same lock-protected memory store.
    """  # fmt: skip
    store = MemoryStore()

    assert await store.set_async("one", b"1", ttl=None)
    assert await store.get_async("one") == b"1"
    assert await store.add_async("two", b"2", ttl=5)
    assert not await store.add_async("two", b"x", ttl=5)
    assert await store.pull_async("two") == b"2"
    assert await store.delete_async("one")
    assert await store.set_async("three", b"3", ttl=None)
    assert await store.clear_tagged_async("three") is None
    assert await store.set_async("prefix:key", b"4", ttl=None)
    assert await store.clear_prefix_async("prefix:") is None
    assert await store.increment_async("count", _COUNTER_TWO) == _COUNTER_TWO
    assert await store.touch_async("count", ttl=0)
    assert not await store.touch_async("count", ttl=None)
    assert await store.acquire_lock_async("lock", _LOCK_OWNER, 5)
    assert await store.lock_owner_async("lock") == _LOCK_OWNER
    assert await store.force_release_lock_async("lock")
    assert await store.release_lock_async("missing", _LOCK_OWNER) is False
    assert await store.clear_async() is None
    await store.aclose()

    with pytest.raises(CacheBackendError, match="closed"):
        await store.get_async("closed")
