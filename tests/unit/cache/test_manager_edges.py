"""Verify manager validation, lifecycle failures, and fake scope behavior.

All successful manager paths construct application-owned cachetools memory
stores; failure factories are limited to lifecycle boundary cases.
"""

from collections.abc import Mapping
from traceback import format_exception
from typing import TYPE_CHECKING, cast

import pytest

from titanspan.cache import (
    CacheBackendError,
    CacheConfiguration,
    CacheConfigurationError,
    CacheDriverFactory,
    CacheManager,
    CacheStoreConfiguration,
)
from titanspan.cache._backends.memory import MemoryStore
from titanspan.contracts.cache import CacheCapabilities, CacheStore

if TYPE_CHECKING:
    from titanspan.contracts.events import EventDispatcher

pytestmark = pytest.mark.unit
_PRIVATE_CLOSE_ERROR = "private close detail"
_PRIVATE_DRIVER_ERROR = "private driver detail"
_EVENT_COUNT = 2
_FAKE_OPERATION_LIMIT = 10_000
_FAKE_OPERATION_COUNT = _FAKE_OPERATION_LIMIT + 1


def _memory_factory(_: CacheStoreConfiguration) -> CacheStore:
    """Return a memory store for driver-registration validation cases.
    """  # fmt: skip
    return MemoryStore()


class _CloseFailureStore(MemoryStore):
    """Raise during shutdown to verify manager cleanup aggregation.
    """  # fmt: skip

    async def aclose(self) -> None:
        """Raise one private shutdown error for the selected store.
        """  # fmt: skip
        message = _PRIVATE_CLOSE_ERROR
        raise OSError(message)


class _UnscopedStore(MemoryStore):
    """Advertise no scoped clear for failover construction checks.
    """  # fmt: skip

    @property
    def capabilities(self) -> CacheCapabilities:
        """Return otherwise normal capabilities without scoped clear.
        """  # fmt: skip
        return CacheCapabilities(
            atomic_add=True,
            atomic_increment=True,
            atomic_pull=True,
            tags=True,
            tag_invalidation_atomic=False,
            scoped_clear=False,
            locks=True,
            distributed_locks=False,
            lock_scoped_clear=False,
        )


def _configuration(
    stores: Mapping[str, CacheStoreConfiguration | Mapping[str, object]],
    *,
    default: str,
) -> CacheConfiguration:
    """Build an immutable configuration for focused manager tests.
    """  # fmt: skip
    return CacheConfiguration(stores=stores, default=default)


@pytest.mark.parametrize(
    "registration",
    [
        pytest.param({"bad-name": _memory_factory}, id="bad-name"),
        pytest.param({"memory": _memory_factory}, id="builtin"),
        pytest.param(
            {"broken": cast("CacheDriverFactory", None)},
            id="not-callable",
        ),
    ],
)
def test_manager_rejects_invalid_driver_registrations(
    registration: Mapping[str, CacheDriverFactory],
) -> None:
    """Reject invalid trusted factory names before application startup.
    """  # fmt: skip
    with pytest.raises(CacheConfigurationError, match="driver registration"):
        CacheManager(
            CacheConfiguration(),
            drivers=registration,
        )


def test_manager_reports_names_and_unknown_store_references() -> None:
    """Expose configured names and reject every unknown selection path.
    """  # fmt: skip
    manager = CacheManager(
        _configuration(
            {
                "main": {"driver": "memory"},
                "alternate": {"driver": "memory"},
            },
            default="main",
        )
    )

    assert manager.default_store == "main"
    assert manager.store_names == ("main", "alternate")
    assert "memory" in manager.driver_names
    assert manager.configuration.default == "main"
    for operation in (
        lambda: manager.store("missing"),
        lambda: manager.memo("missing"),
        lambda: manager.status("missing"),
        lambda: manager.lock("key", ttl=2, store="missing"),
        lambda: manager.restore_lock("key", "0" * 32, ttl=2, store="missing"),
        lambda: manager.resolve_backend("missing"),
        lambda: manager.fake("missing"),
    ):
        with pytest.raises(CacheConfigurationError, match="not configured"):
            operation()


@pytest.mark.parametrize("ttl", [None, 0, -1])
def test_manager_rejects_lock_without_a_positive_lease(ttl: object) -> None:
    """Require positive finite lock leases before constructing a handle.
    """  # fmt: skip
    manager = CacheManager()

    with pytest.raises(CacheConfigurationError, match="positive duration"):
        manager.lock("key", ttl=cast("int | None", ttl))


@pytest.mark.parametrize(
    "owner",
    ["", "x" * 32, "G" * 32, "0" * 31],
)
def test_manager_rejects_invalid_restored_lock_tokens(owner: str) -> None:
    """Accept only opaque 32-character lowercase hexadecimal tokens.
    """  # fmt: skip
    with pytest.raises(CacheConfigurationError, match="owner token is invalid"):
        CacheManager().restore_lock("key", owner, ttl=10)


def test_custom_drivers_must_be_registered_before_backend_use() -> None:
    """Prevent factories from replacing already constructed store owners.
    """  # fmt: skip
    manager = CacheManager()
    manager.store().get("key")

    with pytest.raises(CacheConfigurationError, match="before store use"):
        manager.extend("late", lambda _: MemoryStore())
    with pytest.raises(CacheConfigurationError, match="already registered"):
        manager.extend("memory", lambda _: MemoryStore())
    with pytest.raises(CacheConfigurationError, match="already registered"):
        manager.extend("invalid-name", lambda _: MemoryStore())


def test_manager_wraps_custom_factory_and_memory_configuration_errors() -> None:
    """Report safe native errors for driver failures and memory limits.
    """  # fmt: skip
    broken = CacheManager(
        CacheConfiguration(
            default="broken",
            stores={"broken": {"driver": "broken"}},
        ),
        drivers={
            "broken": _raise_factory_error,
        },
    )
    with pytest.raises(
        CacheBackendError,
        match="could not be created",
    ) as captured:
        broken.store().get("key")
    rendered = "".join(format_exception(captured.value))
    assert _PRIVATE_DRIVER_ERROR not in rendered

    invalid_memory = CacheManager(
        CacheConfiguration(
            default="limited",
            stores={
                "limited": {
                    "driver": "memory",
                    "options": {"max_items": True},
                }
            },
        )
    )
    with pytest.raises(CacheConfigurationError, match="max_items"):
        invalid_memory.store().get("key")

    unknown_driver = CacheManager(
        CacheConfiguration(
            default="unknown",
            stores={"unknown": {"driver": "not-registered"}},
        )
    )
    with pytest.raises(CacheConfigurationError, match="driver registration"):
        unknown_driver.store().get("key")


def test_status_suppresses_private_backend_statistics_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep statistics failure messages out of ordinary status errors.

    Status shares the backend error boundary used by repository operations.
    """
    manager = CacheManager()
    backend = manager.resolve_backend("memory")

    def fail_stats() -> dict[str, object]:
        """Raise a private status error for the memory backend.

        The status adapter must suppress the backend message.
        """
        raise OSError(_PRIVATE_DRIVER_ERROR)

    monkeypatch.setattr(backend, "stats", fail_stats)

    with pytest.raises(CacheBackendError) as captured:
        manager.status()

    rendered = "".join(format_exception(captured.value))
    assert _PRIVATE_DRIVER_ERROR not in rendered


@pytest.mark.anyio
async def test_status_async_suppresses_private_statistics_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hide private backend messages when async stats collection fails.

    Status uses the same safe error boundary as ordinary cache operations.
    """
    manager = CacheManager()
    backend = manager.resolve_backend("memory")

    async def fail_stats() -> dict[str, object]:
        """Raise a private status error for the memory backend.

        The status adapter must suppress the backend message.
        """
        raise OSError(_PRIVATE_DRIVER_ERROR)

    monkeypatch.setattr(
        backend,
        "stats_async",
        fail_stats,
        raising=False,
    )

    with pytest.raises(CacheBackendError) as captured:
        await manager.status_async()

    rendered = "".join(format_exception(captured.value))
    assert _PRIVATE_DRIVER_ERROR not in rendered


def _raise_factory_error(_: CacheStoreConfiguration) -> CacheStore:
    """Raise a private driver error before returning any backend resource.
    """  # fmt: skip
    message = _PRIVATE_DRIVER_ERROR
    raise OSError(message)


@pytest.mark.parametrize(
    "options",
    [
        pytest.param({}, id="unknown-option"),
        pytest.param({"stores": "memory"}, id="wrong-list-type"),
        pytest.param({"stores": ("primary",)}, id="one-child"),
        pytest.param({"stores": (1, "secondary")}, id="child-type"),
        pytest.param({"stores": ("primary", "primary")}, id="duplicate"),
        pytest.param({"stores": ("primary", "missing")}, id="missing-child"),
        pytest.param({"stores": ("fallback", "nested")}, id="nested-child"),
        pytest.param(
            {"stores": ("primary", "failover")},
            id="self-child",
        ),
    ],
)
def test_failover_configuration_rejects_unsafe_children(
    options: Mapping[str, object],
) -> None:
    """Reject failover configurations that cannot provide scoped cleanup.
    """  # fmt: skip
    stores: dict[str, Mapping[str, object]] = {
        "primary": {"driver": "memory"},
        "fallback": {"driver": "memory"},
        "nested": {
            "driver": "failover",
            "options": {"stores": ["primary", "fallback"]},
        },
        "failover": {"driver": "failover", "options": options},
    }
    manager = CacheManager(
        CacheConfiguration(default="failover", stores=stores)
    )

    with pytest.raises(CacheConfigurationError):
        manager.store().get("key")


def test_failover_rejects_children_without_scoped_prefix_clear() -> None:
    """Require each failover child to safely clear one logical prefix.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            default="failover",
            stores={
                "unscoped": {"driver": "unscoped"},
                "fallback": {"driver": "memory"},
                "failover": {
                    "driver": "failover",
                    "options": {"stores": ["unscoped", "fallback"]},
                },
            },
        ),
        drivers={"unscoped": lambda _: _UnscopedStore()},
    )

    with pytest.raises(CacheConfigurationError, match="scoped key clearing"):
        manager.store().get("key")


@pytest.mark.anyio
async def test_manager_aggregates_close_failures_and_is_idempotent() -> None:
    """Close each owned backend once and keep private errors out of output.
    """  # fmt: skip
    closed: list[str] = []

    class TrackedFailureStore(_CloseFailureStore):
        """Record attempts before raising the configured shutdown error.
        """  # fmt: skip

        async def aclose(self) -> None:
            """Record close ordering before delegating to the failing store.
            """  # fmt: skip
            closed.append("failed")
            await super().aclose()

    class TrackedStore(MemoryStore):
        """Record a normal close after releasing local memory state.
        """  # fmt: skip

        async def aclose(self) -> None:
            """Close the store and record one completed lifecycle action.
            """  # fmt: skip
            await super().aclose()
            closed.append("ok")

    def create_failure(_: CacheStoreConfiguration) -> CacheStore:
        """Create one owned store with an erroring close operation.
        """  # fmt: skip
        return TrackedFailureStore()

    def create_success(_: CacheStoreConfiguration) -> CacheStore:
        """Create one owned store with successful deterministic cleanup.
        """  # fmt: skip
        return TrackedStore()

    manager = CacheManager(
        CacheConfiguration(
            default="first",
            stores={
                "first": {"driver": "failure"},
                "second": {"driver": "success"},
            },
        ),
        drivers={"failure": create_failure, "success": create_success},
    )
    manager.store("first").get("key")
    manager.store("second").get("key")

    with pytest.raises(
        CacheBackendError,
        match="resources could not be closed",
    ) as captured:
        await manager.aclose()
    rendered = "".join(format_exception(captured.value))
    assert _PRIVATE_CLOSE_ERROR not in rendered
    await manager.aclose()

    assert closed == ["ok", "failed"]


def test_fake_assertions_and_scope_misuse_are_reported() -> None:
    """Make fake assertions useful and reject invalid context transitions.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            stores={"memory": {"driver": "memory"}},
        )
    )
    scope = manager.fake()
    with pytest.raises(RuntimeError, match="not active"):
        scope.__exit__()

    with scope as fake:
        with pytest.raises(RuntimeError, match="cannot be re-entered"):
            scope.__enter__()
        with pytest.raises(AssertionError, match="to exist"):
            fake.assert_has("missing")
        manager.store().put("present", 1)
        with pytest.raises(AssertionError, match="to be missing"):
            fake.assert_missing("present")
        with pytest.raises(AssertionError, match="was not recorded"):
            fake.assert_performed("forget")
        fake.assert_has("present")
        fake.assert_missing("missing")
        fake.assert_performed("put", "present")


def test_fake_asserts_hits_misses_locks_and_unexpected_access() -> None:
    """Assert reads and leases while production access stays blocked.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            stores={
                "memory": {"driver": "memory"},
                "other": {"driver": "memory"},
            },
        )
    )
    repository = manager.store()

    with manager.fake("memory") as fake:
        assert repository.get("missing") is None
        assert repository.put("present", 1)
        assert repository.get("present") == 1
        lock = manager.lock("resource", ttl=10)
        assert lock.acquire()
        assert lock.release()
        manager.store().flush_locks()
        fake.assert_missed("missing")
        fake.assert_hit("present")
        fake.assert_lock_acquired("resource")
        fake.assert_performed("lock_clear")
        fake.assert_not_performed("forget", "unexpected")

        with pytest.raises(CacheBackendError, match="blocked"):
            manager.store("other").get("unexpected")


def test_fake_operation_ledger_discards_oldest_records_at_its_limit() -> None:
    """Keep the scoped fake operation record bounded.
    """  # fmt: skip
    manager = CacheManager()

    with manager.fake() as fake:
        for index in range(_FAKE_OPERATION_COUNT):
            fake.record("read", str(index), True)

        assert len(fake.operations) == _FAKE_OPERATION_LIMIT
        fake.assert_not_performed("read", "0")
        fake.assert_performed("read", str(_FAKE_OPERATION_COUNT - 1))


@pytest.mark.anyio
async def test_fake_async_context_restores_the_previous_fake() -> None:
    """Support async context-manager cleanup without replacing other scopes.
    """  # fmt: skip
    manager = CacheManager()
    async with manager.fake() as fake:
        await manager.store().put_async("key", "value")
        fake.assert_has("key")
        fake.assert_performed("put", "key")

    assert manager.fake_identity() is None


@pytest.mark.anyio
async def test_manager_emits_only_when_events_are_enabled() -> None:
    """Respect application and per-store event switches before dispatch.
    """  # fmt: skip

    class Dispatcher:
        """Record metadata event objects delivered by the manager.
        """  # fmt: skip

        def __init__(self) -> None:
            """Initialize an empty event list.
            """  # fmt: skip
            self.events: list[object] = []

        def dispatch(self, event: object) -> None:
            """Record one synchronous event for assertions.
            """  # fmt: skip
            self.events.append(event)

        async def dispatch_async(self, event: object) -> None:
            """Record one asynchronous event for assertions.
            """  # fmt: skip
            self.events.append(event)

    dispatcher = Dispatcher()
    manager = CacheManager(
        CacheConfiguration(
            default="enabled",
            events=True,
            stores={
                "enabled": {"driver": "memory", "events": True},
                "disabled": {"driver": "memory", "events": False},
            },
        ),
        events=cast("EventDispatcher", dispatcher),
    )
    manager.emit("hit", "enabled")
    manager.emit("hit", "disabled")
    await manager.emit_async("miss", "enabled")
    await manager.emit_async("miss", "disabled")

    assert len(dispatcher.events) == _EVENT_COUNT
