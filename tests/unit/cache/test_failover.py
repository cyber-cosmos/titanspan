"""Verify ordered failover and safe child-store namespace isolation.
"""  # fmt: skip

from __future__ import annotations

from traceback import format_exception

import pytest

from titanspan.cache import (
    CacheBackendError,
    CacheCapabilityError,
    CacheConfiguration,
    CacheConfigurationError,
    CacheManager,
    CacheStoreConfiguration,
)
from titanspan.cache._backends.failover import FailoverStore
from titanspan.cache._backends.memory import MemoryStore
from titanspan.cache.events import CacheEvent
from titanspan.contracts.cache import CacheCapabilities
from titanspan.events import NativeEventDispatcher

pytestmark = [pytest.mark.unit, pytest.mark.feature]

_PRIVATE_BACKEND_ERROR = "private backend detail"
_DIRECT_VALUE = 2


class BrokenStore(MemoryStore):
    """Simulate a configured backend that fails cache data operations.
    """  # fmt: skip

    def get(self, key: str) -> bytes | None:
        """Raise a private connection failure for every read.
        """  # fmt: skip
        del key
        raise OSError(_PRIVATE_BACKEND_ERROR)

    async def get_async(self, key: str) -> bytes | None:
        """Raise a private connection failure for every async read.
        """  # fmt: skip
        del key
        raise OSError(_PRIVATE_BACKEND_ERROR)

    def set(self, key: str, value: bytes, *, ttl: float | None) -> bool:
        """Raise a private connection failure for every write.
        """  # fmt: skip
        del key, value, ttl
        raise OSError(_PRIVATE_BACKEND_ERROR)

    async def set_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Raise a private connection failure for every async write.
        """  # fmt: skip
        del key, value, ttl
        raise OSError(_PRIVATE_BACKEND_ERROR)


class UnscopedStore(MemoryStore):
    """Represent a custom backend without namespaced prefix deletion.
    """  # fmt: skip

    capabilities = CacheCapabilities(
        atomic_add=False,
        atomic_increment=False,
        atomic_pull=False,
        tags=False,
        tag_invalidation_atomic=False,
        scoped_clear=False,
        locks=False,
        distributed_locks=False,
        lock_scoped_clear=False,
    )


class FailingMaintenanceStore(MemoryStore):
    """Raise on deletion and expiry updates to test partial failover.
    """  # fmt: skip

    def delete(self, key: str) -> bool:
        """Raise while attempting one synchronous child removal.
        """  # fmt: skip
        del key
        raise OSError(_PRIVATE_BACKEND_ERROR)

    async def delete_async(self, key: str) -> bool:
        """Raise while attempting one asynchronous child removal.
        """  # fmt: skip
        del key
        raise OSError(_PRIVATE_BACKEND_ERROR)

    def clear_prefix(self, prefix: str) -> None:
        """Raise while attempting one synchronous child clear.
        """  # fmt: skip
        del prefix
        raise OSError(_PRIVATE_BACKEND_ERROR)

    async def clear_prefix_async(self, prefix: str) -> None:
        """Raise while attempting one asynchronous child clear.
        """  # fmt: skip
        del prefix
        raise OSError(_PRIVATE_BACKEND_ERROR)

    def touch(self, key: str, *, ttl: float | None) -> bool:
        """Raise while attempting one synchronous expiry update.
        """  # fmt: skip
        del key, ttl
        raise OSError(_PRIVATE_BACKEND_ERROR)

    async def touch_async(
        self,
        key: str,
        *,
        ttl: float | None,
    ) -> bool:
        """Raise while attempting one asynchronous expiry update.
        """  # fmt: skip
        del key, ttl
        raise OSError(_PRIVATE_BACKEND_ERROR)


class RefusingStore(MemoryStore):
    """Return a negative write result without raising a backend failure.
    """  # fmt: skip

    def set(self, key: str, value: bytes, *, ttl: float | None) -> bool:
        """Decline one synchronous write without changing child state.
        """  # fmt: skip
        del key, value, ttl
        return False

    async def set_async(
        self,
        key: str,
        value: bytes,
        *,
        ttl: float | None,
    ) -> bool:
        """Decline one asynchronous write without changing child state.
        """  # fmt: skip
        del key, value, ttl
        return False


def _manager(events: NativeEventDispatcher | None = None) -> CacheManager:
    """Create one failover manager with a broken primary and memory backup.
    """  # fmt: skip

    def broken(_: CacheStoreConfiguration) -> BrokenStore:
        """Create one isolated failure simulator.
        """  # fmt: skip
        return BrokenStore()

    return CacheManager(
        CacheConfiguration(
            default="default",
            namespace="failover-test",
            stores={
                "primary": {"driver": "broken"},
                "backup": {"driver": "memory"},
                "default": {
                    "driver": "failover",
                    "options": {"stores": ["primary", "backup"]},
                },
            },
        ),
        drivers={"broken": broken},
        events=events,
    )


def test_failover_routes_reads_and_writes_to_first_usable_store() -> None:
    """Use a later child after primary failure without changing key identity.
    """  # fmt: skip
    manager = _manager()
    repository = manager.store()

    assert repository.put("profile", {"name": "Ada"})
    assert repository.get("profile") == {"name": "Ada"}
    assert repository.capabilities.atomic_add is False
    with pytest.raises(CacheCapabilityError):
        repository.add("once", 1)


def test_failover_flush_does_not_clear_direct_child_store_data() -> None:
    """Scope clearing to the failover repository prefix in every child.
    """  # fmt: skip
    manager = _manager()
    manager.store().put("through-failover", 1)
    manager.store("backup").put("direct", _DIRECT_VALUE)

    manager.store().flush()

    assert manager.store().missing("through-failover")
    assert manager.store("backup").get("direct") == _DIRECT_VALUE


def test_failover_dispatches_events_without_store_payloads() -> None:
    """Emit metadata when a child failure routes an operation to backup.
    """  # fmt: skip
    dispatcher = NativeEventDispatcher()
    received: list[CacheEvent] = []

    def receive(event: CacheEvent) -> None:
        """Retain one safe metadata event for assertions.
        """  # fmt: skip
        received.append(event)

    dispatcher.listen(CacheEvent, receive)
    manager = _manager(dispatcher)

    manager.store().put("private-key", "private-value")

    assert [event.action for event in received] == ["failover", "write"]
    assert "private-key" not in repr(received)
    assert "private-value" not in repr(received)


def test_failover_requires_scoped_clear_capability() -> None:
    """Reject child backends that could clear unrelated store entries.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            default="fallback",
            stores={
                "a": {"driver": "unscoped"},
                "b": {"driver": "memory"},
                "fallback": {
                    "driver": "failover",
                    "options": {"stores": ["a", "b"]},
                },
            },
        ),
        drivers={"unscoped": lambda _: UnscopedStore()},
    )
    with pytest.raises(CacheConfigurationError, match="scoped key clearing"):
        manager.resolve_backend("fallback")


def test_failover_rejects_direct_construction_with_one_child() -> None:
    """Require paired stores and matching scoped-clear adapters.
    """  # fmt: skip
    store = MemoryStore()

    with pytest.raises(ValueError, match="at least two children"):
        FailoverStore((store,), (store,), "owned:", lambda: None)


@pytest.mark.anyio
async def test_failover_reports_degraded_reads_writes_and_deletes() -> None:
    """Report fallback after partial outages even when no data was found.
    """  # fmt: skip
    broken = BrokenStore()
    missing = MemoryStore()
    events: list[str] = []
    backend = FailoverStore(
        (broken, missing),
        (broken, missing),
        "read:",
        lambda: events.append("fallback"),
    )

    assert backend.get("missing") is None
    assert await backend.get_async("missing") is None
    assert events == ["fallback", "fallback"]

    refusing = RefusingStore()
    writes = FailoverStore(
        (BrokenStore(), refusing),
        (BrokenStore(), refusing),
        "write:",
        lambda: events.append("write-fallback"),
    )
    assert not writes.set("key", b"value", ttl=None)
    assert not await writes.set_async("key", b"value", ttl=None)

    failed_deletion = FailoverStore(
        (FailingMaintenanceStore(), missing),
        (FailingMaintenanceStore(), missing),
        "delete:",
        lambda: events.append("delete-fallback"),
    )
    with pytest.raises(CacheBackendError):
        failed_deletion.delete("missing")
    with pytest.raises(CacheBackendError):
        await failed_deletion.delete_async("missing")
    assert events[-4:] == [
        "write-fallback",
        "write-fallback",
        "delete-fallback",
        "delete-fallback",
    ]


def test_failover_rejects_self_reference_and_all_child_failures() -> None:
    """Fail configuration cycles and surface a native bounded failure.
    """  # fmt: skip
    invalid = CacheManager(
        CacheConfiguration(
            default="default",
            stores={
                "default": {
                    "driver": "failover",
                    "options": {"stores": ["default", "other"]},
                },
                "other": {"driver": "memory"},
            },
        )
    )
    with pytest.raises(CacheConfigurationError, match="unique child"):
        invalid.resolve_backend("default")

    failing = CacheManager(
        CacheConfiguration(
            default="default",
            stores={
                "first": {"driver": "broken"},
                "second": {"driver": "broken"},
                "default": {
                    "driver": "failover",
                    "options": {"stores": ["first", "second"]},
                },
            },
        ),
        drivers={
            "broken": lambda _: BrokenStore(),
        },
    )
    with pytest.raises(CacheBackendError) as captured:
        failing.store().get("key")
    assert "private backend detail" not in str(captured.value)
    rendered = "".join(format_exception(captured.value))
    assert "private backend detail" not in rendered


@pytest.mark.anyio
async def test_failover_sync_async_methods_keep_scoped_child_data() -> None:
    """Cover fallback routing, expiry, deletion, and scoped child clearing.
    """  # fmt: skip
    primary = BrokenStore()
    backup = MemoryStore()
    events: list[str] = []
    backend = FailoverStore(
        (primary, backup),
        (primary, backup),
        "owned:default:",
        lambda: events.append("fallback"),
    )
    key = "owned:default:key"
    payload = b"safe"

    assert backend.set(key, payload, ttl=None)
    assert backend.get(key) == payload
    assert backend.touch(key, ttl=10)
    assert backend.delete(key)
    assert await backend.set_async(key, payload, ttl=None)
    assert await backend.get_async(key) == payload
    assert await backend.touch_async(key, ttl=10)
    assert await backend.delete_async(key)
    assert backend.set("other:store:key", payload, ttl=None)
    assert await backend.set_async("other:store:async", payload, ttl=None)

    await backend.clear_async()

    assert backup.get("other:store:key") == payload
    assert backup.get("other:store:async") == payload
    assert events
    await backend.aclose()


@pytest.mark.anyio
async def test_failover_reports_partial_maintenance_failures() -> None:
    """Raise when one child failed even if another child completed cleanup.
    """  # fmt: skip
    primary = FailingMaintenanceStore()
    backup = MemoryStore()
    events: list[str] = []
    backend = FailoverStore(
        (primary, backup),
        (primary, backup),
        "maintenance:",
        lambda: events.append("fallback"),
    )
    backup.set("maintenance:key", b"value", ttl=None)

    with pytest.raises(CacheBackendError):
        backend.delete("maintenance:key")
    with pytest.raises(CacheBackendError):
        await backend.delete_async("maintenance:key")
    with pytest.raises(CacheBackendError):
        backend.clear()
    with pytest.raises(CacheBackendError):
        await backend.clear_async()
    with pytest.raises(CacheBackendError):
        backend.touch("maintenance:key", ttl=1)
    with pytest.raises(CacheBackendError):
        await backend.touch_async("maintenance:key", ttl=1)

    assert events


@pytest.mark.anyio
async def test_failover_uses_primary_and_returns_declined_writes() -> None:
    """Prefer the first healthy child and preserve negative write results.
    """  # fmt: skip
    primary = MemoryStore()
    secondary = MemoryStore()
    events: list[str] = []
    backend = FailoverStore(
        (primary, secondary),
        (primary, secondary),
        "priority:",
        lambda: events.append("fallback"),
    )

    assert backend.get("missing") is None
    assert backend.set("priority:sync", b"one", ttl=None)
    assert primary.get("priority:sync") == b"one"
    assert events == []

    refusing_primary = RefusingStore()
    refusing_secondary = RefusingStore()
    declined = FailoverStore(
        (refusing_primary, refusing_secondary),
        (refusing_primary, refusing_secondary),
        "declined:",
        lambda: events.append("declined"),
    )
    assert not declined.set("declined:key", b"value", ttl=None)
    assert not await declined.set_async(
        "declined:async",
        b"value",
        ttl=None,
    )


@pytest.mark.anyio
async def test_failover_atomic_methods_fail_clearly() -> None:
    """Refuse all operations that require child-store coordination.
    """  # fmt: skip
    first = MemoryStore()
    second = MemoryStore()
    backend = FailoverStore(
        (first, second),
        (first, second),
        "owned:default:",
        lambda: None,
    )

    with pytest.raises(CacheCapabilityError):
        backend.add("key", b"value", ttl=None)
    with pytest.raises(CacheCapabilityError):
        backend.pull("key")
    with pytest.raises(CacheCapabilityError):
        backend.increment("key", 1)

    async def unsupported_async_operations() -> None:
        """Verify async atomic methods preserve unsupported behavior.
        """  # fmt: skip
        with pytest.raises(CacheCapabilityError):
            await backend.add_async("key", b"value", ttl=None)
        with pytest.raises(CacheCapabilityError):
            await backend.pull_async("key")
        with pytest.raises(CacheCapabilityError):
            await backend.increment_async("key", 1)

    await unsupported_async_operations()
