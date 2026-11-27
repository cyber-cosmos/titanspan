"""Verify Cache composes through Foundation, Config, Container, and Events.

The integration uses a real ASGI application and the native memory adapter.
"""

from http import HTTPStatus
from typing import TYPE_CHECKING

import anyio
import pytest
from fastapi.testclient import TestClient

from titanspan.cache import CacheBackendError, CacheServiceProvider
from titanspan.cache._backends.memory import MemoryStore
from titanspan.cache.configuration import CacheStoreConfiguration
from titanspan.cache.events import CacheEvent
from titanspan.contracts.cache import CacheRepository, CacheStore
from titanspan.facades.cache import Cache
from titanspan.facades.event import Event
from titanspan.foundation import Application

if TYPE_CHECKING:
    from titanspan.cache.manager import CacheManager

pytestmark = [pytest.mark.integration, pytest.mark.architecture]
_COUNTER_THREE = 3
_COUNTER_TWO = 2
_TAG_VALUE = 8


async def _async_factory() -> str:
    """Return one asynchronous cache factory value.
    """  # fmt: skip
    return "async"


async def _exercise_values_and_bulk() -> None:
    """Exercise facade values, defaults, named stores, and bulk operations.
    """  # fmt: skip
    assert Cache.repository() is Cache.store("memory")
    assert Cache.manager().store() is Cache.resolve_service()
    assert Cache.put("none", None)
    assert Cache.get("none", default="fallback") is None
    assert Cache.has("none")
    assert not Cache.missing("none")
    assert await Cache.put_async("async", False)
    assert await Cache.get_async("async", default="fallback") is False
    assert await Cache.has_async("async")
    assert not await Cache.missing_async("async")
    assert Cache.forever("forever", 1)
    assert await Cache.forever_async("forever-async", 2)
    assert Cache.add("add", _COUNTER_THREE)
    assert not await Cache.add_async("add", 4)
    assert Cache.put_many({"many-a": 5, "many-b": 6})
    assert await Cache.many_async(["many-a", "many-b"]) == {
        "many-a": 5,
        "many-b": 6,
    }
    assert Cache.many(["many-a", "missing"], default=0) == {
        "many-a": 5,
        "missing": 0,
    }
    assert await Cache.put_many_async({"async-many": 7})
    assert Cache.pull("add") == _COUNTER_THREE
    assert await Cache.pull_async("async") is False
    assert Cache.forget("many-a")
    assert await Cache.forget_async("many-b")


async def _exercise_factories_and_memo() -> None:
    """Exercise facade counters, value factories, expiration, and memo.
    """  # fmt: skip
    assert Cache.increment("counter") == 1
    assert await Cache.increment_async("counter", _COUNTER_TWO) == (
        _COUNTER_THREE
    )
    assert Cache.decrement("counter") == _COUNTER_TWO
    assert await Cache.decrement_async("counter") == 1
    assert (
        Cache.remember(
            "remember",
            ttl=30,
            callback=lambda: "sync",
        )
        == "sync"
    )

    assert (
        await Cache.remember_async(
            "remember-async",
            ttl=30,
            callback=_async_factory,
        )
        == "async"
    )
    assert (
        Cache.remember_forever(
            "remember-forever",
            callback=lambda: "permanent",
        )
        == "permanent"
    )
    assert (
        await Cache.remember_forever_async(
            "remember-forever-async",
            callback=_async_factory,
        )
        == "async"
    )
    assert Cache.touch("remember", ttl=60)
    assert await Cache.touch_async("remember", ttl=None)
    assert Cache.memo().get("remember") == "sync"
    assert Cache.memo().get("remember") == "sync"
    assert Cache.tags("one", "two").put("tagged", _TAG_VALUE)
    assert Cache.tags("two", "one").get("tagged") == _TAG_VALUE


async def _exercise_locks_and_status() -> None:
    """Exercise lock ownership transfer and safe facade status methods.
    """  # fmt: skip
    lock = Cache.lock("resource", ttl=30)
    assert await lock.acquire_async()
    restored = Cache.restore_lock(
        "resource",
        lock.transfer(),
        ttl=30,
    )
    assert restored.acquired
    assert restored.release()
    synchronous = Cache.lock("sync-admin", ttl=30)
    assert synchronous.acquire()
    Cache.flush_locks("memory")
    assert not synchronous.acquired
    administrative = Cache.lock("admin", ttl=30)
    assert await administrative.acquire_async()
    await Cache.flush_locks_async("memory")
    assert not await administrative.acquired_async()
    assert Cache.status("memory")["memory"]
    assert await Cache.status_async("memory")


def test_application_provider_shares_facade_injection_and_scoped_fake() -> None:
    """Share one manager, repository, event dispatcher, and app lifecycle.
    """  # fmt: skip
    captured: dict[str, CacheManager] = {}
    constructed: list[bool] = []

    def create_store(_: CacheStoreConfiguration) -> CacheStore:
        """Record first backend use and return the real local adapter.
        """  # fmt: skip
        constructed.append(True)
        return MemoryStore()

    application = Application(
        config={
            "app": {"name": "cache-integration"},
            "cache": {
                "default": "local",
                "stores": {"local": {"driver": "counted"}},
            },
        },
        service_providers=(
            CacheServiceProvider(drivers={"counted": create_store}),
        ),
    )

    async def exercise_cache(cache: CacheRepository) -> dict[str, object]:
        """Compare injected and facade services through one request.
        """  # fmt: skip
        created_before_operation = bool(constructed)
        manager = Cache.manager()
        captured["manager"] = manager
        with Event.fake([CacheEvent]) as events:
            await cache.put_async("shared", {"ready": True})
            facade_value = await Cache.get_async("shared")
            same_repository = Cache.resolve_service() is cache
            same_manager = manager.store() is cache
            with Cache.fake() as fake:
                Cache.put("shared", {"ready": False})
                fake_value = cache.get("shared")
                manager.store().put("isolated", 10)
                fake.assert_has("isolated")
            restored_value = cache.get("shared")
            events.assert_dispatched(CacheEvent, times=6)
        return {
            "facade_value": facade_value,
            "fake_value": fake_value,
            "restored_value": restored_value,
            "same_repository": same_repository,
            "same_manager": same_manager,
            "created_before_operation": created_before_operation,
            "created_after_operation": bool(constructed),
        }

    application.router.get("/cache", exercise_cache)

    with TestClient(application.asgi) as client:
        response = client.get("/cache")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "facade_value": {"ready": True},
        "fake_value": {"ready": False},
        "restored_value": {"ready": True},
        "same_repository": True,
        "same_manager": True,
        "created_before_operation": False,
        "created_after_operation": True,
    }
    with pytest.raises(CacheBackendError, match="closed"):
        captured["manager"].store().get("shared")


def test_cache_facade_exposes_coherent_sync_and_async_operations() -> None:
    """Exercise the public facade through one real application context.
    """  # fmt: skip
    app = Application(
        config={
            "app": {"name": "cache-facade"},
            "cache": {
                "default": "memory",
                "stores": {
                    "memory": {"driver": "memory"},
                    "secondary": {"driver": "memory"},
                },
            },
        },
        service_providers=(CacheServiceProvider(),),
    )

    async def exercise() -> dict[str, bool]:
        """Verify facade operations share their manager's store state.
        """  # fmt: skip
        await _exercise_values_and_bulk()
        await _exercise_factories_and_memo()
        await _exercise_locks_and_status()
        Cache.flush("secondary")
        await Cache.flush_async("secondary")

        async with anyio.create_task_group() as tasks:
            assert (
                await Cache.flexible_async(
                    "flexible",
                    fresh=30,
                    stale=60,
                    callback=_async_factory,
                    task_group=tasks,
                )
                == "async"
            )
        Cache.flush()
        await Cache.flush_async()
        return {"complete": True}

    app.router.get("/cache-facade", exercise)

    with TestClient(app.asgi) as client:
        response = client.get("/cache-facade")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"complete": True}
