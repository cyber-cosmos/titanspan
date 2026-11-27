"""Verify native cache repository behavior against the real memory backend.

The memory adapter is the integration boundary for portable repository
semantics and is used here without backend mocks.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import anyio
import pytest

if TYPE_CHECKING:
    from anyio.abc import TaskGroup

import titanspan.cache.repository as repository_module
from titanspan.cache import (
    CacheCapabilityError,
    CacheConfiguration,
    CacheKeyError,
    CacheManager,
    CacheSerializationError,
)
from titanspan.cache._backends.memory import MemoryStore

pytestmark = pytest.mark.unit
_EXPECTED_COUNTER = 3
_COUNTER_MAXIMUM = 5
_CONCURRENT_INCREMENT_COUNT = 100
_SECONDARY_STORE_VALUE = 2
_PRIMARY_TAG_VALUE = 3
_SECONDARY_TAG_VALUE = 4
_PRIVATE_BACKEND_ERROR = "private backend detail"


def test_get_distinguishes_missing_from_stored_none() -> None:
    """Return cached ``None`` without resolving the supplied default.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="tests"))
    cache = manager.store()
    cache.put("present", None)

    assert cache.get("present", default="fallback") is None
    assert cache.get("missing", default="fallback") == "fallback"


@pytest.mark.parametrize(
    "value",
    [None, False, 0, "", [], {}],
)
def test_get_preserves_every_supported_false_like_value(value: object) -> None:
    """Return valid empty JSON values instead of selecting a fallback.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="false-like"))
    cache = manager.store()
    cache.put("key", value)

    assert cache.get("key", default="fallback") == value


def test_get_resolves_a_synchronous_default_only_after_a_miss() -> None:
    """Call the fallback exactly when a key has no stored payload.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="defaults"))
    cache = manager.store()
    calls = 0

    def fallback() -> str:
        """Return a value while recording one factory invocation.
        """  # fmt: skip
        nonlocal calls
        calls += 1
        return "created"

    cache.put("present", "cached")

    assert cache.get("present", fallback) == "cached"
    assert cache.get("missing", fallback) == "created"
    assert calls == 1


def test_put_expiration_and_timedelta_semantics() -> None:
    """Treat zero as immediate expiry and positive TTL as seconds.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="expiration"))
    cache = manager.store()
    cache.put("immediate", "gone", ttl=0)
    cache.put("timed", "live", ttl=timedelta(seconds=5))

    assert cache.missing("immediate")
    assert cache.get("timed") == "live"
    assert cache.touch("timed", ttl=0)
    assert cache.missing("timed")


def test_absolute_expiration_requires_timezone_awareness() -> None:
    """Accept aware deadlines and reject ambiguous naive datetimes.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="absolute"))
    cache = manager.store()
    cache.put(
        "future",
        "value",
        ttl=datetime.now(UTC) + timedelta(minutes=1),
    )

    assert cache.get("future") == "value"
    with pytest.raises(ValueError, match="timezone-aware"):
        cache.put(
            "naive",
            "value",
            ttl=datetime.fromisoformat("2026-01-01"),
        )


def test_add_increment_decrement_and_pull_are_atomic() -> None:
    """Preserve backend atomic operations through the native repository.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="atomic"))
    cache = manager.store()

    assert cache.add("once", False)
    assert not cache.add("once", True)
    assert cache.get("once") is False
    assert cache.increment("counter") == 1
    assert cache.increment("counter", 4) == _COUNTER_MAXIMUM
    assert cache.decrement("counter", 2) == _EXPECTED_COUNTER
    assert cache.pull("counter") == _EXPECTED_COUNTER
    assert cache.pull("counter", "missing") == "missing"


def test_concurrent_add_has_exactly_one_winner() -> None:
    """Serialize parallel add-if-absent calls through the memory adapter.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="add-race"))
    cache = manager.store()

    def add_one(_: int) -> bool:
        """Try the same key from one worker thread.
        """  # fmt: skip
        return cache.add("single", True)

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(add_one, range(64)))

    assert sum(results) == 1


def test_concurrent_increments_keep_every_update() -> None:
    """Keep the atomic integer count under concurrent thread access.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="counter-race"))
    cache = manager.store()

    def increment_one(_: int) -> int:
        """Apply one counter update from a worker thread.
        """  # fmt: skip
        return cache.increment("count")

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(
            executor.map(
                increment_one,
                range(_CONCURRENT_INCREMENT_COUNT),
            )
        )

    assert cache.get("count") == _CONCURRENT_INCREMENT_COUNT
    assert max(results) == _CONCURRENT_INCREMENT_COUNT


def test_bulk_operations_preserve_values_and_bound_batches() -> None:
    """Read and write bounded mappings with one shared expiration value.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            namespace="bulk",
            max_batch_size=3,
        )
    )
    cache = manager.store()

    assert cache.put_many({"a": None, "b": 0}, ttl=10)
    assert cache.many(["a", "b", "missing"], default="fallback") == {
        "a": None,
        "b": 0,
        "missing": "fallback",
    }
    with pytest.raises(CacheKeyError, match="bulk operations"):
        cache.many(["a", "b", "c", "d"])


def test_namespace_clear_does_not_clear_other_stores() -> None:
    """Clear only the selected configured store's prefixed entries.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            namespace="isolation",
            stores={
                "memory": {"driver": "memory"},
                "secondary": {"driver": "memory"},
            },
        )
    )
    primary = manager.store("memory")
    secondary = manager.store("secondary")
    primary.put("key", 1)
    secondary.put("key", 2)

    primary.flush()

    assert primary.missing("key")
    assert secondary.get("key") == _SECONDARY_STORE_VALUE


def test_tagged_cache_flush_is_scoped_to_a_canonical_tag_group() -> None:
    """Invalidate one order-independent tag group within its store.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            namespace="tagged",
            stores={
                "memory": {"driver": "memory"},
                "secondary": {"driver": "memory"},
            },
        )
    )
    primary = manager.store("memory")
    secondary = manager.store("secondary")
    primary.tags("users", "profiles").put("one", 1)
    primary.tags("profiles", "users").put("two", 2)
    primary.tags("users").put("three", 3)
    secondary.tags("users", "profiles").put("four", 4)

    primary.tags("users", "profiles").flush()

    assert primary.tags("users", "profiles").missing("one")
    assert primary.tags("users", "profiles").missing("two")
    assert primary.tags("users").get("three") == _PRIMARY_TAG_VALUE
    assert (
        secondary.tags("users", "profiles").get("four") == _SECONDARY_TAG_VALUE
    )
    assert not primary.capabilities.tag_invalidation_atomic


def test_same_manager_sync_and_async_methods_share_memory() -> None:
    """Observe values across both explicit execution styles.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="cross-mode"))
    cache = manager.store()

    async def exercise() -> None:
        """Write asynchronously and read through the sync contract.
        """  # fmt: skip
        await cache.put_async("shared", {"value": 3})
        assert cache.get("shared") == {"value": 3}
        assert await cache.get_async("shared") == {"value": 3}

    anyio.run(exercise)


def test_remember_computes_once_for_repeated_reads() -> None:
    """Cache the factory result for subsequent remember calls.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="remember"))
    cache = manager.store()
    calls = 0

    def calculate() -> list[int]:
        """Return a new value and count calls to the factory.
        """  # fmt: skip
        nonlocal calls
        calls += 1
        return [calls]

    assert cache.remember("key", ttl=20, callback=calculate) == [1]
    assert cache.remember("key", ttl=20, callback=calculate) == [1]
    assert calls == 1


def test_unsafe_payload_values_are_rejected() -> None:
    """Reject arbitrary Python objects instead of deserializing code.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="safe-json"))

    with pytest.raises(CacheSerializationError):
        manager.store().put("object", object())


def test_key_validation_rejects_controls_and_oversized_keys() -> None:
    """Reject key inputs that can escape or overload a store namespace.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="keys"))
    cache = manager.store()

    with pytest.raises(CacheKeyError):
        cache.put("line\nbreak", "value")
    with pytest.raises(CacheKeyError):
        cache.get("k" * 513)


def test_null_store_rejects_atomic_operations_explicitly() -> None:
    """Report unsupported atomic operations instead of emulating them.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            default="disabled",
            stores={"disabled": {"driver": "null"}},
        )
    )

    with pytest.raises(CacheCapabilityError, match="atomic increment"):
        manager.store().increment("counter")


@pytest.mark.anyio
async def test_async_factories_and_bulk_operations_are_supported() -> None:
    """Await async defaults and factories through explicit async methods.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="async"))
    cache = manager.store()
    calls = 0

    async def fallback() -> str:
        """Return one asynchronous fallback value.
        """  # fmt: skip
        return "fallback"

    async def calculate() -> dict[str, bool]:
        """Return one asynchronous remember result.
        """  # fmt: skip
        nonlocal calls
        calls += 1
        await anyio.lowlevel.checkpoint()
        return {"ok": True}

    assert await cache.get_async("missing", fallback) == "fallback"
    assert await cache.remember_async(
        "remembered",
        ttl=10,
        callback=calculate,
    ) == {"ok": True}
    assert await cache.remember_async(
        "remembered",
        ttl=10,
        callback=calculate,
    ) == {"ok": True}
    assert await cache.put_many_async({"a": False, "b": []})
    assert await cache.many_async(["a", "b"]) == {"a": False, "b": []}
    assert calls == 1


@pytest.mark.anyio
async def test_async_remember_stampede_runs_factory_once() -> None:
    """Coordinate concurrent async misses with backend owner locks.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="stampede"))
    cache = manager.store()
    calls = 0

    async def calculate() -> str:
        """Pause briefly so competing calls overlap their cache miss.
        """  # fmt: skip
        nonlocal calls
        calls += 1
        await anyio.sleep(0.02)
        return "computed"

    async def request() -> str:
        """Return a shared remember result.
        """  # fmt: skip
        return await cache.remember_async(
            "key",
            ttl=30,
            callback=calculate,
        )

    async with anyio.create_task_group() as tasks:
        for _ in range(12):
            tasks.start_soon(request)

    assert calls == 1
    assert await cache.get_async("key") == "computed"


@pytest.mark.anyio
async def test_flexible_refresh_uses_caller_owned_task_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return stale data immediately and refresh within caller ownership.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="flexible"))
    cache = manager.store()
    now = 1_000.0
    monkeypatch.setattr(repository_module, "time", lambda: now)

    async def old_value() -> str:
        """Return initial data used to establish a stale entry.
        """  # fmt: skip
        return "old"

    assert (
        await cache.flexible_async(
            "key",
            fresh=1,
            stale=10,
            callback=old_value,
        )
        == "old"
    )
    now += 2
    refreshed: list[str] = []

    async def refresh() -> str:
        """Return replacement data and expose that refresh completed.
        """  # fmt: skip
        refreshed.append("new")
        return "new"

    stale_values: list[str] = []
    async with anyio.create_task_group() as tasks:
        stale_values.append(
            await cache.flexible_async(
                "key",
                fresh=1,
                stale=10,
                callback=refresh,
                task_group=tasks,
            )
        )

    assert stale_values == ["old"]
    assert refreshed == ["new"]
    assert (
        await cache.flexible_async(
            "key",
            fresh=1,
            stale=10,
            callback=old_value,
        )
        == "new"
    )


@pytest.mark.anyio
async def test_flexible_schedule_cancellation_releases_refresh_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Release a lease when the caller group rejects refresh scheduling.
    """  # fmt: skip
    release_fails = False

    class UncertainReleaseStore(MemoryStore):
        """Release the lease, then report one uncertain backend result.
        """  # fmt: skip

        async def release_lock_async(self, key: str, owner: str) -> bool:
            """Release through memory before simulating a lost response.
            """  # fmt: skip
            nonlocal release_fails
            released = await super().release_lock_async(key, owner)
            if release_fails and released:
                raise OSError(_PRIVATE_BACKEND_ERROR)
            return released

    manager = CacheManager(
        CacheConfiguration(
            namespace="schedule-cancel",
            stores={"refresh": {"driver": "refresh"}},
            default="refresh",
        ),
        drivers={"refresh": lambda _: UncertainReleaseStore()},
    )
    cache = manager.store()
    now = 1_000.0
    monkeypatch.setattr(repository_module, "time", lambda: now)

    async def old_value() -> str:
        """Return one value to create the stale entry.
        """  # fmt: skip
        return "old"

    assert (
        await cache.flexible_async(
            "key",
            fresh=1,
            stale=10,
            callback=old_value,
        )
        == "old"
    )
    now += 2
    release_fails = True

    class CancelledTaskGroup:
        """Reject task creation with the active AnyIO cancellation type.
        """  # fmt: skip

        def start_soon(
            self,
            *args: object,
            **kwargs: object,
        ) -> None:
            """Raise cancellation after the cache acquired its refresh lease.
            """  # fmt: skip
            _ = args, kwargs
            raise anyio.get_cancelled_exc_class()

    with pytest.raises(anyio.get_cancelled_exc_class()) as captured:
        await cache.flexible_async(
            "key",
            fresh=1,
            stale=10,
            callback=old_value,
            task_group=cast("TaskGroup", CancelledTaskGroup()),
        )

    notes = getattr(captured.value, "__notes__", [])
    assert any("CacheBackendError" in note for note in notes)
    assert all(_PRIVATE_BACKEND_ERROR not in note for note in notes)
    competitor = manager.lock("key", ttl=10)
    assert await competitor.acquire_async()


@pytest.mark.anyio
async def test_tagged_remember_uses_a_group_specific_lock_key() -> None:
    """Use the namespaced coordination key for tagged cache groups.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="tag-lock-key"))
    cache = manager.store().tags("documents")
    calls = 0

    async def calculate() -> str:
        """Count and return one tagged value.
        """  # fmt: skip
        nonlocal calls
        calls += 1
        return "stored"

    assert (
        await cache.remember_async(
            "document",
            ttl=30,
            callback=calculate,
        )
        == "stored"
    )
    assert (
        await cache.remember_async(
            "document",
            ttl=30,
            callback=calculate,
        )
        == "stored"
    )
    assert calls == 1
