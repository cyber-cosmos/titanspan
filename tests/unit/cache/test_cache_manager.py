"""Verify manager ownership, trusted drivers, and scoped substitutions.

Manager tests use genuine application backend instances and contract-level
custom drivers.
"""

from traceback import format_exception

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
from titanspan.container import Container
from titanspan.contracts.cache import CacheStore

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

    assert memo is manager.memo()
    assert memo.get("key") == "initial"
    assert memo.get("key") == "initial"
    assert reads == [1]
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
