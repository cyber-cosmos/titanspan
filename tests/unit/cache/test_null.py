"""Verify the explicitly disabled backend's empty-store semantics.
"""  # fmt: skip

import pytest

from titanspan.cache._backends.null import NullStore

pytestmark = pytest.mark.unit


def test_null_store_sync_operations_discard_values() -> None:
    """Keep a null store empty while treating writes as accepted.
    """  # fmt: skip
    store = NullStore()

    assert store.get("key") is None
    assert store.set("key", b"value", ttl=None)
    assert not store.add("key", b"value", ttl=None)
    assert store.pull("key") is None
    assert not store.delete("key")
    assert not store.touch("key", ttl=10)
    store.clear()
    store.clear_prefix("safe:")
    with pytest.raises(NotImplementedError):
        store.increment("key", 1)


@pytest.mark.anyio
async def test_null_store_async_operations_discard_values() -> None:
    """Keep asynchronous null operations aligned with synchronous calls.
    """  # fmt: skip
    store = NullStore()

    assert await store.get_async("key") is None
    assert await store.set_async("key", b"value", ttl=None)
    assert not await store.add_async("key", b"value", ttl=None)
    assert await store.pull_async("key") is None
    assert not await store.delete_async("key")
    assert not await store.touch_async("key", ttl=10)
    await store.clear_async()
    await store.clear_prefix_async("safe:")
    with pytest.raises(NotImplementedError):
        await store.increment_async("key", 1)
    await store.aclose()


def test_null_store_validates_scoped_clear_grammar() -> None:
    """Reject wildcard characters even when the null store is empty.
    """  # fmt: skip
    with pytest.raises(ValueError, match="safe non-empty text"):
        NullStore().clear_prefix("bad*")
