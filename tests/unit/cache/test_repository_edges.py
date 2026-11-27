"""Verify repository error paths, optional capabilities, and edge inputs.

Production operations use the real memory adapter except when a narrow
failure adapter exercises the repository's error translation.
"""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from traceback import format_exception
from typing import cast

import anyio
import pytest

import titanspan.cache.repository as repository_module
from titanspan.cache import (
    CacheBackendError,
    CacheCapabilityError,
    CacheConfiguration,
    CacheKeyError,
    CacheManager,
    CacheSerializationError,
    Repository,
)
from titanspan.cache._backends.memory import MemoryStore
from titanspan.contracts.cache import (
    CacheCapabilities,
    CacheRepository,
    CacheStore,
    CacheTTL,
)
from titanspan.events import NativeEventDispatcher

pytestmark = pytest.mark.unit
_PRIVATE_BACKEND_ERROR = "private backend detail"
_ASYNC_REMEMBER_VALUE = 2
_ASYNC_FOREVER_VALUE = 3
_FLEXIBLE_VALUE = 4
_ASYNC_ADD_VALUE = 5
_MAX_INVALID_TTL = 315_576_001
_MEMO_ENTRY_CAPACITY = 1_000
_MEMO_ENTRY_COUNT = 1_001
_REFRESH_FAILURE = "refresh failed"
_PRIVATE_EVENT_ERROR = "private event failure"


class _NoLockStore(MemoryStore):
    """Keep memory semantics while making coordination unavailable.
    """  # fmt: skip

    capabilities = CacheCapabilities(
        atomic_add=True,
        atomic_increment=True,
        atomic_pull=True,
        tags=True,
        tag_invalidation_atomic=False,
        scoped_clear=True,
        locks=False,
        distributed_locks=False,
        lock_scoped_clear=False,
    )


def _no_lock_store(_: object) -> CacheStore:
    """Return a real memory store without any lock capabilities.
    """  # fmt: skip
    return _NoLockStore()


class _FailingStore(MemoryStore):
    """Raise selected errors while retaining memory-store capabilities.
    """  # fmt: skip

    def __init__(self, failures: set[str]) -> None:
        """Create one store whose named operations raise safely.
        """  # fmt: skip
        super().__init__()
        self._failures: set[str] = failures

    def _check(self, operation: str) -> None:
        """Raise when this test selected an operation for failure.
        """  # fmt: skip
        if operation in self._failures:
            message = _PRIVATE_BACKEND_ERROR
            raise OSError(message)

    def get(self, key: str) -> bytes | None:
        """Fail or delegate synchronous retrieval.
        """  # fmt: skip
        self._check("get")
        return super().get(key)

    async def get_async(self, key: str) -> bytes | None:
        """Fail or delegate asynchronous retrieval.
        """  # fmt: skip
        self._check("get")
        return await super().get_async(key)

    def set(self, key: str, value: bytes, *, ttl: float | None) -> bool:
        """Fail or delegate synchronous storage.
        """  # fmt: skip
        self._check("set")
        return super().set(key, value, ttl=ttl)

    async def set_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Fail or delegate asynchronous storage.
        """  # fmt: skip
        self._check("set")
        return await super().set_async(key, value, ttl=ttl)

    def add(self, key: str, value: bytes, *, ttl: float | None) -> bool:
        """Fail or delegate atomic add.
        """  # fmt: skip
        self._check("add")
        return super().add(key, value, ttl=ttl)

    async def add_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Fail or delegate asynchronous atomic add.
        """  # fmt: skip
        self._check("add")
        return await super().add_async(key, value, ttl=ttl)

    def pull(self, key: str) -> bytes | None:
        """Fail or delegate atomic retrieval and removal.
        """  # fmt: skip
        self._check("pull")
        return super().pull(key)

    async def pull_async(self, key: str) -> bytes | None:
        """Fail or delegate asynchronous atomic retrieval and removal.
        """  # fmt: skip
        self._check("pull")
        return await super().pull_async(key)

    def delete(self, key: str) -> bool:
        """Fail or delegate synchronous deletion.
        """  # fmt: skip
        self._check("delete")
        return super().delete(key)

    async def delete_async(self, key: str) -> bool:
        """Fail or delegate asynchronous deletion.
        """  # fmt: skip
        self._check("delete")
        return await super().delete_async(key)

    def clear(self) -> None:
        """Fail or delegate synchronous clear.
        """  # fmt: skip
        self._check("clear")
        super().clear()

    async def clear_async(self) -> None:
        """Fail or delegate asynchronous clear.
        """  # fmt: skip
        self._check("clear")
        await super().clear_async()

    def clear_locks(self) -> None:
        """Fail or delegate synchronous lock namespace clearing.
        """  # fmt: skip
        self._check("clear_locks")
        super().clear_locks()

    async def clear_locks_async(self) -> None:
        """Fail or delegate asynchronous lock namespace clearing.
        """  # fmt: skip
        self._check("clear_locks")
        await super().clear_locks_async()

    def clear_tagged(self, prefix: str) -> None:
        """Fail or delegate synchronous tag invalidation.
        """  # fmt: skip
        self._check("clear_tagged")
        super().clear_tagged(prefix)

    async def clear_tagged_async(self, prefix: str) -> None:
        """Fail or delegate asynchronous tag invalidation.
        """  # fmt: skip
        self._check("clear_tagged")
        await super().clear_tagged_async(prefix)

    def increment(self, key: str, amount: int) -> int:
        """Fail or delegate atomic counter mutation.
        """  # fmt: skip
        self._check("increment")
        return super().increment(key, amount)

    async def increment_async(self, key: str, amount: int) -> int:
        """Fail or delegate asynchronous counter mutation.
        """  # fmt: skip
        self._check("increment")
        return await super().increment_async(key, amount)

    def touch(self, key: str, *, ttl: float | None) -> bool:
        """Fail or delegate synchronous expiration changes.
        """  # fmt: skip
        self._check("touch")
        return super().touch(key, ttl=ttl)

    async def touch_async(self, key: str, *, ttl: float | None) -> bool:
        """Fail or delegate asynchronous expiration changes.
        """  # fmt: skip
        self._check("touch")
        return await super().touch_async(key, ttl=ttl)


class _FailingEventDispatcher(NativeEventDispatcher):
    """Raise during dispatch to pin cache event failure behavior.

    This models listener failures owned by the Events component.
    """

    def dispatch(
        self,
        event: object | str,
        payload: object = None,
    ) -> list[object]:
        """Raise after a synchronous cache operation has completed.

        The backend has already stored the value before dispatch begins.
        """
        del event, payload
        raise RuntimeError(_PRIVATE_EVENT_ERROR)

    async def dispatch_async(
        self,
        event: object | str,
        payload: object = None,
    ) -> list[object]:
        """Raise after an asynchronous cache operation has completed.

        The backend has already stored the value before dispatch begins.
        """
        del event, payload
        raise RuntimeError(_PRIVATE_EVENT_ERROR)


def _manager(failures: set[str]) -> CacheManager:
    """Create an application manager with one scripted real memory store.
    """  # fmt: skip

    def create_store(_: object) -> CacheStore:
        """Return a memory adapter that fails only selected calls.
        """  # fmt: skip
        return _FailingStore(failures)

    return CacheManager(
        CacheConfiguration(
            default="scripted",
            stores={"scripted": {"driver": "scripted"}},
        ),
        drivers={"scripted": create_store},
    )


_SYNC_FAILURES: tuple[tuple[str, Callable[[CacheRepository], object]], ...] = (
    ("get", lambda cache: cache.get("key")),
    ("set", lambda cache: cache.put("key", "value")),
    ("add", lambda cache: cache.add("key", "value")),
    ("get", lambda cache: cache.has("key")),
    ("set", lambda cache: cache.put_many({"key": "value"})),
    ("pull", lambda cache: cache.pull("key")),
    ("delete", lambda cache: cache.forget("key")),
    ("clear", lambda cache: cache.flush()),
    ("clear_locks", lambda cache: cache.flush_locks()),
    ("increment", lambda cache: cache.increment("key")),
    ("increment", lambda cache: cache.decrement("key")),
    ("touch", lambda cache: cache.touch("key", ttl=5)),
    (
        "clear_tagged",
        lambda cache: cache.tags("users").flush(),
    ),
)


def test_repository_rejects_non_json_objects() -> None:
    """Reject custom objects before they reach the selected backend.
    """  # fmt: skip
    cache = CacheManager(CacheConfiguration(namespace="objects")).store()

    with pytest.raises(CacheSerializationError):
        cache.put("object", object())


@pytest.mark.parametrize(
    "ttl",
    [Decimal("1"), float("inf"), _MAX_INVALID_TTL],
)
def test_repository_rejects_invalid_expirations(ttl: object) -> None:
    """Reject unsupported types, non-finite durations, and excessive TTLs.
    """  # fmt: skip
    cache = CacheManager(CacheConfiguration(namespace="ttl-edges")).store()

    with pytest.raises(ValueError, match="Cache expiration"):
        cache.put("key", "value", ttl=cast("CacheTTL", ttl))


@pytest.mark.parametrize(
    ("failure", "operation"),
    _SYNC_FAILURES,
    ids=[
        f"{failure}-{index}"
        for index, (failure, _) in enumerate(_SYNC_FAILURES)
    ],
)
def test_sync_repository_wraps_backend_failures(
    failure: str,
    operation: Callable[[CacheRepository], object],
) -> None:
    """Translate sync backend errors without exposing their message.
    """  # fmt: skip
    cache = _manager({failure}).store()

    with pytest.raises(CacheBackendError) as captured:
        operation(cache)

    assert _PRIVATE_BACKEND_ERROR not in str(captured.value)
    rendered = "".join(format_exception(captured.value))
    assert _PRIVATE_BACKEND_ERROR not in rendered


_ASYNC_FAILURES: tuple[
    tuple[str, Callable[[CacheRepository], Awaitable[object]]], ...
] = (
    ("get", lambda cache: cache.get_async("key")),
    ("set", lambda cache: cache.put_async("key", "value")),
    ("add", lambda cache: cache.add_async("key", "value")),
    ("get", lambda cache: cache.has_async("key")),
    ("set", lambda cache: cache.put_many_async({"key": "value"})),
    ("pull", lambda cache: cache.pull_async("key")),
    ("delete", lambda cache: cache.forget_async("key")),
    ("clear", lambda cache: cache.flush_async()),
    ("clear_locks", lambda cache: cache.flush_locks_async()),
    ("increment", lambda cache: cache.increment_async("key")),
    ("increment", lambda cache: cache.decrement_async("key")),
    ("touch", lambda cache: cache.touch_async("key", ttl=5)),
    (
        "clear_tagged",
        lambda cache: cache.tags("users").flush_async(),
    ),
)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "operation"),
    _ASYNC_FAILURES,
    ids=[
        f"{failure}-{index}"
        for index, (failure, _) in enumerate(_ASYNC_FAILURES)
    ],
)
async def test_async_repository_wraps_backend_failures(
    failure: str,
    operation: Callable[[CacheRepository], Awaitable[object]],
) -> None:
    """Translate async backend errors without swallowing cancellation.
    """  # fmt: skip
    cache = _manager({failure}).store()

    with pytest.raises(CacheBackendError) as captured:
        await operation(cache)

    assert _PRIVATE_BACKEND_ERROR not in str(captured.value)
    rendered = "".join(format_exception(captured.value))
    assert _PRIVATE_BACKEND_ERROR not in rendered


def test_repository_validates_tags_defaults_and_counter_inputs() -> None:
    """Reject unsafe tags, sync async-factories, and invalid counter amounts.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="repository-edges"))
    cache = manager.store()

    assert cache.name == "memory"
    with pytest.raises(CacheKeyError):
        cache.tags()
    with pytest.raises(CacheKeyError):
        cache.tags("unsafe tag")
    with pytest.raises(CacheKeyError):
        cache.tags("üser")
    with pytest.raises(CacheKeyError):
        cache.tags(*(f"tag-{index}" for index in range(17)))
    with pytest.raises(CacheKeyError):
        cache.get("\ud800")
    with pytest.raises(CacheKeyError):
        cache.get("")
    with pytest.raises(ValueError, match="non-negative integers"):
        cache.increment("counter", True)
    with pytest.raises(ValueError, match="non-negative integers"):
        cache.decrement("counter", -1)

    async def async_default() -> str:
        """Return a value that requires explicit async retrieval.
        """  # fmt: skip
        return "async"

    with pytest.raises(TypeError, match="async cache API"):
        cache.get("missing", async_default)


@pytest.mark.anyio
async def test_async_bulk_and_pull_defaults_preserve_missing_values() -> None:
    """Resolve async defaults only for misses and preserve cached empties.
    """  # fmt: skip
    cache = CacheManager(CacheConfiguration(namespace="async-empty")).store()
    await cache.put_async("none", None)
    await cache.put_async("false", False)

    async def fallback() -> str:
        """Return the missing key's asynchronous fallback.
        """  # fmt: skip
        return "fallback"

    assert await cache.get_async("none", fallback) is None
    assert await cache.get_async("false", fallback) is False
    assert await cache.many_async(["false", "missing"], default=fallback) == {
        "false": False,
        "missing": "fallback",
    }
    assert await cache.pull_async("missing", fallback) == "fallback"


@pytest.mark.parametrize("ttl", [0, timedelta(seconds=-1)])
def test_add_with_immediate_expiration_does_not_call_backend(
    ttl: int | timedelta,
) -> None:
    """Report that an already-expired value was not added.
    """  # fmt: skip
    cache = CacheManager(CacheConfiguration(namespace="expired-add")).store()

    assert not cache.add("key", "value", ttl=ttl)


@pytest.mark.anyio
async def test_async_add_with_immediate_expiration_does_not_call_backend() -> (
    None
):
    """Return false for zero-duration async adds without storing a key.
    """  # fmt: skip
    cache = CacheManager(CacheConfiguration(namespace="async-add-zero")).store()

    assert not await cache.add_async("key", "value", ttl=0)


@pytest.mark.anyio
async def test_null_store_exposes_unsupported_atomic_operations() -> None:
    """Fail clearly when a disabled store cannot coordinate mutations.
    """  # fmt: skip
    cache = CacheManager(
        CacheConfiguration(
            default="disabled",
            stores={"disabled": {"driver": "null"}},
        )
    ).store()

    with pytest.raises(CacheCapabilityError, match="atomic add"):
        cache.add("key", "value")
    with pytest.raises(CacheCapabilityError, match="atomic add"):
        await cache.add_async("key", "value")
    with pytest.raises(CacheCapabilityError, match="atomic pull"):
        cache.pull("key")
    with pytest.raises(CacheCapabilityError, match="atomic pull"):
        await cache.pull_async("key")
    with pytest.raises(CacheCapabilityError, match="atomic decrement"):
        await cache.decrement_async("key")
    with pytest.raises(CacheCapabilityError, match="atomic decrement"):
        cache.decrement("key")
    with pytest.raises(CacheCapabilityError, match="cache tags"):
        cache.tags("users")


@pytest.mark.anyio
async def test_null_store_remember_and_flexible_recompute_without_locks() -> (
    None
):
    """Compute safely when a backend deliberately lacks lock support.
    """  # fmt: skip
    cache = CacheManager(
        CacheConfiguration(
            default="disabled",
            stores={"disabled": {"driver": "null"}},
        )
    ).store()
    calls = 0

    def synchronous() -> int:
        """Count one sync recomputation discarded by the null store.
        """  # fmt: skip
        nonlocal calls
        calls += 1
        return calls

    async def asynchronous() -> int:
        """Count one async recomputation discarded by the null store.
        """  # fmt: skip
        nonlocal calls
        calls += 1
        return calls

    assert cache.remember("sync", ttl=10, callback=synchronous) == 1
    assert (
        await cache.remember_async(
            "async",
            ttl=10,
            callback=asynchronous,
        )
        == _ASYNC_REMEMBER_VALUE
    )
    assert (
        await cache.remember_forever_async(callback=asynchronous, key="x")
        == _ASYNC_FOREVER_VALUE
    )
    assert (
        await cache.flexible_async(
            "flexible",
            fresh=1,
            stale=5,
            callback=asynchronous,
        )
        == _FLEXIBLE_VALUE
    )


@pytest.mark.anyio
async def test_async_add_invalidates_memo_after_a_successful_write() -> None:
    """Make successful async mutations visible through memo views.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="async-add-success"))
    repository = manager.store()
    memo = manager.memo()

    assert await repository.add_async("key", _ASYNC_ADD_VALUE)
    assert await memo.get_async("key") == _ASYNC_ADD_VALUE
    assert not await repository.add_async("key", 99)


@pytest.mark.anyio
async def test_flexible_cache_without_locks_returns_stale_without_scheduling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return stale memory values when the configured backend cannot lock.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            default="local",
            stores={"local": {"driver": "nolock"}},
        ),
        drivers={"nolock": _no_lock_store},
    )
    cache = manager.store()
    now = 100.0
    monkeypatch.setattr(repository_module, "time", lambda: now)

    async def initial() -> str:
        """Create one flexible entry in the no-lock store.
        """  # fmt: skip
        return "initial"

    assert (
        await cache.flexible_async(
            "key",
            fresh=1,
            stale=10,
            callback=initial,
        )
        == "initial"
    )
    now += 2

    async def refresh() -> str:
        """Return a value that must not be scheduled without lock support.
        """  # fmt: skip
        return "refreshed"

    async with anyio.create_task_group() as tasks:
        value = await cache.flexible_async(
            "key",
            fresh=1,
            stale=10,
            callback=refresh,
            task_group=tasks,
        )
        assert value == "initial"


@pytest.mark.anyio
async def test_memo_defaults_presence_tags_and_bounded_values() -> None:
    """Keep memo reads execution-local, invalidatable, and memory-bounded.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            namespace="memo-edges",
            max_batch_size=_MEMO_ENTRY_COUNT,
        )
    )
    repository = manager.store()
    memo = manager.memo()
    repository.put("present", None)

    def fallback() -> str:
        """Return one value for a synchronous memoized miss.
        """  # fmt: skip
        return "fallback"

    async def fallback_async() -> str:
        """Return one value for an asynchronous memoized miss.
        """  # fmt: skip
        return "fallback"

    assert memo.get("missing", fallback) == "fallback"
    assert await memo.get_async("missing-async", fallback_async) == "fallback"
    assert memo.has("present")
    assert not memo.has("missing")
    assert await memo.has_async("present")
    assert not await memo.has_async("missing")

    tagged = memo.tags("users")
    await tagged.put_async("tagged", "value")
    assert tagged.get("tagged") == "value"

    values = {f"memo:{index}": index for index in range(_MEMO_ENTRY_COUNT)}
    assert repository.put_many(values)
    for key in values:
        memo.get(key)
    assert memo.get("memo:0") == 0

    disabled = CacheManager(
        CacheConfiguration(
            default="null",
            stores={"null": {"driver": "null"}},
        )
    ).memo()
    with pytest.raises(CacheCapabilityError, match="cache tags"):
        disabled.tags("users")


def test_remember_rechecks_a_value_written_after_the_initial_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the under-lock recheck when another caller wins the race.
    """  # fmt: skip
    cache = CacheManager(CacheConfiguration(namespace="remember-race")).store()
    original_get = Repository.get
    reads = 0

    def racing_get[ValueT](
        repository: Repository,
        key: str,
        default: ValueT | Callable[[], ValueT] | None = None,
    ) -> ValueT | None:
        """Publish one competing result after the initial storage miss.
        """  # fmt: skip
        nonlocal reads
        value = original_get(repository, key, default)
        reads += 1
        if reads == 1:
            repository.put(key, "winner")
        return value

    monkeypatch.setattr(Repository, "get", racing_get)

    def should_not_run() -> str:
        """Fail if remembered work ignores the under-lock result.
        """  # fmt: skip
        pytest.fail("The cache value was populated by another caller.")

    assert cache.remember("key", ttl=10, callback=should_not_run) == "winner"


@pytest.mark.anyio
async def test_flexible_refresh_failure_returns_stale_data_and_releases_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep stale values available when caller-owned refresh work fails.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="refresh-failure"))
    cache = manager.store()
    now = 100.0
    monkeypatch.setattr(repository_module, "time", lambda: now)

    async def initial() -> str:
        """Create one value before it becomes stale.
        """  # fmt: skip
        return "old"

    assert (
        await cache.flexible_async(
            "key",
            fresh=1,
            stale=10,
            callback=initial,
        )
        == "old"
    )
    now += 2

    async def broken_refresh() -> str:
        """Raise inside the owned task so the stale response survives.
        """  # fmt: skip
        message = _REFRESH_FAILURE
        raise RuntimeError(message)

    async with anyio.create_task_group() as tasks:
        result = await cache.flexible_async(
            "key",
            fresh=1,
            stale=10,
            callback=broken_refresh,
            task_group=tasks,
        )
        assert result == "old"
    assert await cache.get_async("key") == {
        "marker": "titanspan.cache.flexible.v1",
        "written_at": 100.0,
        "value": "old",
    }


@pytest.mark.anyio
async def test_flexible_cache_validates_ages_and_recovers_invalid_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recalculate malformed entries and reject impossible age thresholds.
    """  # fmt: skip
    cache = CacheManager(CacheConfiguration(namespace="flexible-edges")).store()
    monkeypatch.setattr(repository_module, "time", lambda: 100.0)

    async def fresh() -> str:
        """Return one fresh value after the invalid payload is rejected.
        """  # fmt: skip
        return "fresh"

    for fresh_age, stale_age in (
        (-1, 5),
        (2, 2),
        (1, float("inf")),
        (True, 5),
    ):
        with pytest.raises(ValueError, match="Flexible cache ages"):
            await cache.flexible_async(
                "key",
                fresh=fresh_age,
                stale=stale_age,
                callback=fresh,
            )

    malformed_values: list[object] = [
        "not-a-record",
        {"marker": "wrong"},
        {
            "marker": "titanspan.cache.flexible.v1",
            "written_at": "old",
            "value": "stale",
        },
        {
            "marker": "titanspan.cache.flexible.v1",
            "written_at": 94.0,
            "value": "stale",
        },
        {
            "marker": "titanspan.cache.flexible.v1",
            "written_at": 99.0,
        },
    ]
    for index, value in enumerate(malformed_values):
        await cache.put_async(f"bad-{index}", value)
        result = await cache.flexible_async(
            f"bad-{index}",
            fresh=1,
            stale=5,
            callback=fresh,
        )
        assert result == "fresh"

    malformed_nan = {
        "marker": "titanspan.cache.flexible.v1",
        "written_at": float("nan"),
        "value": "stale",
    }
    # Safe JSON decoding rejects non-finite values before flexible lookup.
    entry_reader_name = "_flexible_entry"
    flexible_entry = cast(
        "Callable[[object], tuple[object, float]]",
        getattr(repository_module, entry_reader_name),
    )
    _, malformed_age = flexible_entry(malformed_nan)
    assert malformed_age == float("inf")


def test_memory_counter_errors_are_native_and_namespaced() -> None:
    """Reject non-integer cached counters and avoid exposing their values.
    """  # fmt: skip
    cache = CacheManager(CacheConfiguration(namespace="bad-counter")).store()
    cache.put("counter", "not-an-integer")

    with pytest.raises(
        CacheBackendError,
        match="counter value is invalid",
    ) as captured:
        cache.increment("counter")
    rendered = "".join(format_exception(captured.value))
    assert "not-an-integer" not in rendered


def test_event_listener_failure_is_visible_after_sync_cache_write() -> None:
    """Keep event errors visible after a completed synchronous cache write.

    The test checks backend state without dispatching a second event.
    """
    manager = CacheManager(
        CacheConfiguration(namespace="event-write-failure"),
        events=_FailingEventDispatcher(),
    )
    cache = manager.store()
    backend = manager.resolve_backend(cache.name)
    backend_key = cast("Repository", cache).backend_key("key")

    with pytest.raises(RuntimeError, match=_PRIVATE_EVENT_ERROR):
        cache.put("key", "stored")

    payload = backend.get(backend_key)
    assert payload is not None
    assert manager.serializer.decode(payload) == "stored"


@pytest.mark.anyio
async def test_async_event_failure_after_cache_write() -> None:
    """Keep async event errors visible after a completed cache write.

    The test checks backend state without dispatching a second event.
    """
    manager = CacheManager(
        CacheConfiguration(namespace="async-event-write-failure"),
        events=_FailingEventDispatcher(),
    )
    cache = manager.store()
    backend = manager.resolve_backend(cache.name)
    backend_key = cast("Repository", cache).backend_key("key")

    with pytest.raises(RuntimeError, match=_PRIVATE_EVENT_ERROR):
        await cache.put_async("key", "stored")

    payload = await backend.get_async(backend_key)
    assert payload is not None
    assert manager.serializer.decode(payload) == "stored"


def test_tagged_clear_requires_explicit_tag_capability() -> None:
    """Reject a manually composed tagged repository over a null backend.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            default="disabled",
            stores={"disabled": {"driver": "null"}},
        )
    )
    tagged = Repository(manager, "disabled", tags=("users",))

    with pytest.raises(CacheCapabilityError, match="cache tags"):
        tagged.flush()
