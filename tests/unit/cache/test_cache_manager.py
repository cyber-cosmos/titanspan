"""Verify manager ownership, trusted drivers, and scoped substitutions.

Manager tests use genuine application backend instances and contract-level
custom drivers.
"""

from collections.abc import Mapping
from traceback import format_exception
from typing import TYPE_CHECKING, cast

import anyio
import pytest

from titanspan._application_context import bind_application_context
from titanspan.cache import (
    CacheBackendError,
    CacheConfiguration,
    CacheConfigurationError,
    CacheManager,
    CacheStoreConfiguration,
)
from titanspan.cache._backends.memory import MemoryStore
from titanspan.cache.events import CacheEvent
from titanspan.container import Container
from titanspan.contracts.cache import CacheStore
from titanspan.events import NativeEventDispatcher

if TYPE_CHECKING:
    from titanspan.contracts.logging import LogWriter

pytestmark = pytest.mark.unit
_PRIVATE_ERROR = "private redis password"
_CACHE_VALUE = 42


class _BrokenStore(MemoryStore):
    """Raise a secret-bearing transport error at the storage boundary.
    """  # fmt: skip

    def get(self, key: str) -> bytes | None:
        """Raise without returning any backend data.
        """  # fmt: skip
        del key
        raise OSError(_PRIVATE_ERROR)

    async def get_async(self, key: str) -> bytes | None:
        """Raise asynchronously without returning a backend payload.
        """  # fmt: skip
        del key
        raise OSError(_PRIVATE_ERROR)


def test_repository_views_are_stable_and_stores_are_lazy() -> None:
    """Return stable repositories without eagerly constructing a driver.
    """  # fmt: skip
    constructed: list[str] = []

    def create_store(configuration: CacheStoreConfiguration) -> CacheStore:
        """Record actual backend construction before returning memory.
        """  # fmt: skip
        constructed.append(configuration.driver)
        return MemoryStore()

    manager = CacheManager(
        CacheConfiguration(
            stores={"custom": {"driver": "counted"}},
            default="custom",
        ),
        drivers={"counted": create_store},
    )

    assert manager.store() is manager.store("custom")
    assert constructed == []
    assert manager.store().put("key", "value")
    assert constructed == ["counted"]


def test_manager_closes_only_backends_it_created() -> None:
    """Close initialized resources deterministically and reject later use.
    """  # fmt: skip
    closed: list[bool] = []

    class TrackingStore(MemoryStore):
        """Record deterministic async close of one manager-owned instance.
        """  # fmt: skip

        async def aclose(self) -> None:
            """Close local memory then record ownership finalization.
            """  # fmt: skip
            await super().aclose()
            closed.append(True)

    def create_store(_: CacheStoreConfiguration) -> CacheStore:
        """Create one locally tracked store resource.
        """  # fmt: skip
        return TrackingStore()

    manager = CacheManager(
        CacheConfiguration(
            stores={"tracked": {"driver": "tracked"}},
            default="tracked",
        ),
        drivers={"tracked": create_store},
    )
    repository = manager.store()
    repository.put("key", "value")

    anyio.run(manager.aclose)

    assert closed == [True]
    with pytest.raises(CacheBackendError, match="closed"):
        repository.get("key")


def test_driver_extension_is_trusted_and_rejects_conflicts() -> None:
    """Allow a named custom backend before store use and reject built-ins.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            stores={"custom": {"driver": "local"}},
            default="custom",
        )
    )
    manager.extend("local", lambda _: MemoryStore())

    assert manager.store().put("key", _CACHE_VALUE)
    assert manager.store().get("key") == _CACHE_VALUE
    with pytest.raises(CacheConfigurationError):
        manager.extend("memory", lambda _: MemoryStore())


def test_fake_substitution_affects_existing_repositories() -> None:
    """Redirect stable views, block other stores, and restore production.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            namespace="fake-scope",
            stores={
                "memory": {"driver": "memory"},
                "secondary": {"driver": "memory"},
            },
        )
    )
    primary = manager.store("memory")
    secondary = manager.store("secondary")
    primary.put("key", "production")

    with manager.fake("memory") as fake:
        assert primary.put("key", "fake")
        fake.assert_has("key", store="memory")
        fake.assert_performed("put", "key")
        with pytest.raises(CacheBackendError, match="blocked"):
            secondary.get("key")

    assert primary.get("key") == "production"


def test_fake_without_store_redirects_every_configured_repository() -> None:
    """Keep all store-specific repository calls inside a shared fake.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            stores={
                "memory": {"driver": "memory"},
                "secondary": {"driver": "memory"},
            },
        )
    )

    with manager.fake() as fake:
        manager.store("memory").put("key", 1)
        manager.store("secondary").put("key", 2)
        fake.assert_has("key")


def test_backend_failures_are_native_and_do_not_leak_secrets() -> None:
    """Wrap backend exceptions without exposing their sensitive message.
    """  # fmt: skip

    def create_broken_store(_: CacheStoreConfiguration) -> CacheStore:
        """Return one store that raises a secret-bearing error.
        """  # fmt: skip
        return _BrokenStore()

    manager = CacheManager(
        CacheConfiguration(
            stores={"broken": {"driver": "broken"}},
            default="broken",
        ),
        drivers={"broken": create_broken_store},
    )

    with pytest.raises(CacheBackendError) as captured:
        manager.store().get("key")

    assert "OSError" in str(captured.value)
    assert "private redis password" not in str(captured.value)
    rendered = "".join(format_exception(captured.value))
    assert "private redis password" not in rendered


def test_sync_failover_listener_failure_preserves_operation_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Preserve a completed fallback read when its listener fails.
    """  # fmt: skip
    dispatcher = NativeEventDispatcher()

    def fail_on_failover(event: CacheEvent) -> None:
        """Raise only after a successful fallback operation.
        """  # fmt: skip
        if event.action == "failover":
            raise RuntimeError(_PRIVATE_ERROR)

    dispatcher.listen(CacheEvent, fail_on_failover)
    manager = CacheManager(
        CacheConfiguration(
            default="fallback",
            stores={
                "broken": {"driver": "broken"},
                "backup": {"driver": "memory"},
                "fallback": {
                    "driver": "failover",
                    "options": {"stores": ["broken", "backup"]},
                },
            },
        ),
        drivers={"broken": lambda _: _BrokenStore()},
        events=dispatcher,
    )

    with caplog.at_level("WARNING"):
        assert manager.store().get("missing") is None

    warning = next(
        record
        for record in caplog.records
        if record.getMessage()
        == "Cache failover event listener failed after a completed operation."
    )
    assert warning.__dict__.get("exception_type") == "RuntimeError"
    assert _PRIVATE_ERROR not in caplog.text


def test_failover_listener_failure_survives_logger_failure() -> None:
    """Keep successful cache results when diagnostic logging also fails.
    """  # fmt: skip

    class RaisingLogger:
        """Fail warning delivery without changing cache behavior.
        """  # fmt: skip

        def warning(
            self,
            message: str,
            context: Mapping[str, object] | None = None,
            **values: object,
        ) -> None:
            """Raise a private logging failure for the manager to contain.
            """  # fmt: skip
            _ = message, context, values
            raise OSError(_PRIVATE_ERROR)

    dispatcher = NativeEventDispatcher()

    def fail_on_failover(event: CacheEvent) -> None:
        """Raise only after a successful fallback operation.
        """  # fmt: skip
        if event.action == "failover":
            message = "listener failed"
            raise RuntimeError(message)

    dispatcher.listen(CacheEvent, fail_on_failover)
    manager = CacheManager(
        CacheConfiguration(
            default="fallback",
            stores={
                "broken": {"driver": "broken"},
                "backup": {"driver": "memory"},
                "fallback": {
                    "driver": "failover",
                    "options": {"stores": ["broken", "backup"]},
                },
            },
        ),
        drivers={"broken": lambda _: _BrokenStore()},
        events=dispatcher,
        logger=cast("LogWriter", RaisingLogger()),
    )

    assert manager.store().get("missing") is None


def test_memo_reuses_reads_and_observes_all_repository_mutations() -> None:
    """Memoize repeated reads and invalidate after shared writes.
    """  # fmt: skip
    reads = [0]

    class CountingStore(MemoryStore):
        """Count backend calls while retaining real memory semantics.
        """  # fmt: skip

        def get(self, key: str) -> bytes | None:
            """Record and delegate one sync retrieval.
            """  # fmt: skip
            reads[0] += 1
            return super().get(key)

        async def get_async(self, key: str) -> bytes | None:
            """Record and delegate one async retrieval.
            """  # fmt: skip
            reads[0] += 1
            return await super().get_async(key)

    def create_store(_: CacheStoreConfiguration) -> CacheStore:
        """Create one counting cachetools-backed memory store.
        """  # fmt: skip
        return CountingStore()

    manager = CacheManager(
        CacheConfiguration(
            stores={"counted": {"driver": "counted"}},
            default="counted",
        ),
        drivers={"counted": create_store},
    )
    repository = manager.store()
    memo = manager.memo()
    repository.put("key", "initial")
    container = Container()
    execution_scope = object()

    with bind_application_context(manager, container, execution_scope):
        assert memo is manager.memo()
        assert memo.get("key") == "initial"
        assert memo.get("key") == "initial"
    assert reads == [1]
    with bind_application_context(manager, container, execution_scope):
        repository.put("key", "updated")
        assert memo.get("key") == "updated"
    assert reads == [2]


@pytest.mark.anyio
async def test_memo_scope_isolation_and_fake_cleanup() -> None:
    """Keep memo values within native scopes and fake substitutions.
    """  # fmt: skip
    reads = [0]

    class CountingStore(MemoryStore):
        """Count reads while preserving real memory backend behavior.
        """  # fmt: skip

        def get(self, key: str) -> bytes | None:
            """Count one synchronous retrieval.
            """  # fmt: skip
            reads[0] += 1
            return super().get(key)

    def create_store(_: CacheStoreConfiguration) -> CacheStore:
        """Create one custom store used to inspect memoized reads.
        """  # fmt: skip
        return CountingStore()

    manager = CacheManager(
        CacheConfiguration(
            stores={"counted": {"driver": "counted"}},
            default="counted",
        ),
        drivers={"counted": create_store},
    )
    repository = manager.store()
    memo = manager.memo()
    repository.put("key", "production")
    container = Container()
    first_scope = object()
    second_scope = object()

    with bind_application_context(manager, container, first_scope):
        assert await memo.get_async("key") == "production"
        assert await memo.get_async("key") == "production"
    with bind_application_context(manager, container, second_scope):
        assert await memo.get_async("key") == "production"
    assert reads == [2]

    with manager.fake() as fake:
        await memo.put_async("key", "fake")
        assert await memo.get_async("key") == "fake"
        fake.assert_has("key")
    assert await memo.get_async("key") == "production"


@pytest.mark.anyio
async def test_memo_separates_unscoped_and_inherited_task_reads() -> None:
    """Avoid retaining memo values outside or across execution scopes.
    """  # fmt: skip
    reads = [0]

    class CountingStore(MemoryStore):
        """Count actual reads from the application memory backend.
        """  # fmt: skip

        def get(self, key: str) -> bytes | None:
            """Count one synchronous read before delegating.
            """  # fmt: skip
            reads[0] += 1
            return super().get(key)

    def create_store(_: CacheStoreConfiguration) -> CacheStore:
        """Create a real memory store with read instrumentation.
        """  # fmt: skip
        return CountingStore()

    manager = CacheManager(
        CacheConfiguration(
            default="counted",
            stores={"counted": {"driver": "counted"}},
        ),
        drivers={"counted": create_store},
    )
    repository = manager.store()
    memo = manager.memo()
    assert repository.put("key", "value")

    assert memo.get("key") == "value"
    assert memo.get("key") == "value"
    assert reads == [2]

    container = Container()
    scope = object()
    with bind_application_context(manager, container, scope):
        assert await memo.get_async("key") == "value"
        child_value: list[str | None] = []

        async def read_in_child() -> None:
            """Read through a ContextVar-inheriting child task.
            """  # fmt: skip
            child_value.append(await memo.get_async("key"))

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(read_in_child)

        assert child_value == ["value"]
        assert await memo.get_async("key") == "value"

    assert reads == [4]


@pytest.mark.anyio
async def test_memo_does_not_publish_a_read_across_a_mutation() -> None:
    """Reject an in-flight read when a mutation advances its generation.
    """  # fmt: skip
    read_started = anyio.Event()
    continue_read = anyio.Event()
    pause_read = True

    class SuspendedStore(MemoryStore):
        """Return the pre-mutation payload after a controlled suspension.
        """  # fmt: skip

        async def get_async(self, key: str) -> bytes | None:
            """Snapshot one payload before the test permits its return.
            """  # fmt: skip
            nonlocal pause_read
            payload = await super().get_async(key)
            if key.endswith(":key") and pause_read:
                pause_read = False
                read_started.set()
                await continue_read.wait()
            return payload

    manager = CacheManager(
        CacheConfiguration(
            default="suspended",
            stores={"suspended": {"driver": "suspended"}},
        ),
        drivers={"suspended": lambda _: SuspendedStore()},
    )
    repository = manager.store()
    memo = manager.memo()
    assert await repository.put_async("key", "old")
    container = Container()
    scope = object()
    stale_values: list[str | None] = []

    with bind_application_context(manager, container, scope):

        async def suspended_read() -> None:
            """Read an old snapshot while another task mutates its key.
            """  # fmt: skip
            stale_values.append(await memo.get_async("key"))

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(suspended_read)
            await read_started.wait()
            assert await repository.put_async("key", "new")
            continue_read.set()

        assert stale_values == ["old"]
        assert await memo.get_async("key") == "new"


def test_memo_returns_shared_mutable_values_within_one_scope() -> None:
    """Share the memoized object by reference until the scope invalidates it.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(default="memory"))
    repository = manager.store()
    memo = manager.memo()
    assert repository.put("document", ["draft"])
    container = Container()
    scope = object()

    with bind_application_context(manager, container, scope):
        first = memo.get("document")
        second = memo.get("document")

        assert isinstance(first, list)
        assert isinstance(second, list)
        assert first is second
        first.append("reviewed")
        assert second == ["draft", "reviewed"]

    assert repository.get("document") == ["draft"]
