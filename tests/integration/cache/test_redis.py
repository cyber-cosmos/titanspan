"""Verify the optional Redis adapter against an isolated local server.
"""  # fmt: skip

from __future__ import annotations

import shutil
import socket
import subprocess
import tempfile
from importlib import import_module
from os import environ
from time import monotonic, sleep
from typing import TYPE_CHECKING

import pytest

from titanspan.cache import CacheConfiguration, CacheManager
from titanspan.cache.exceptions import CacheBackendError

pytestmark = pytest.mark.integration

if TYPE_CHECKING:
    from collections.abc import Iterator


_ASYNC_VALUE = 4
_EXPECTED_COUNTER = 3
_COUNTER_AFTER_DECREMENT = 2
_LAST_BATCH_INDEX = 500
_OTHER_APPLICATION_VALUE = 2
_REDIS_REQUIRED_ENV = "TITANSPAN_REQUIRE_REDIS"
_REDIS_PORT_ENV = "TITANSPAN_TEST_REDIS_PORT"


@pytest.fixture(scope="module", autouse=True)
def redis_dependency() -> None:
    """Require redis-py in mandatory jobs and skip optional local runs.
    """  # fmt: skip
    try:
        import_module("redis")
    except ImportError:
        message = "The redis optional dependency is required for Redis tests."
        if environ.get(_REDIS_REQUIRED_ENV) == "1":
            pytest.fail(message)
        pytest.skip(message)


@pytest.fixture
def redis_port() -> Iterator[int]:
    """Use the CI Redis service or start an isolated local process.
    """  # fmt: skip
    required = environ.get(_REDIS_REQUIRED_ENV) == "1"
    configured_port = environ.get(_REDIS_PORT_ENV)
    if configured_port is not None:
        try:
            port = int(configured_port)
        except ValueError:
            pytest.fail("The configured Redis test port must be an integer.")
        yield port
        return
    executable = shutil.which("redis-server")
    if executable is None:
        if required:
            pytest.fail("Mandatory Redis tests need a Redis service or binary.")
        pytest.skip("redis-server is not installed")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="titanspan-redis-") as data:
        # The binary and arguments come from this local integration fixture.
        process = subprocess.Popen(  # noqa: S603
            [
                executable,
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
                "--save",
                "",
                "--appendonly",
                "no",
                "--dir",
                data,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = monotonic() + 5
        while monotonic() < deadline and process.poll() is None:
            try:
                with socket.create_connection(
                    ("127.0.0.1", port),
                    timeout=0.1,
                ):
                    break
            except OSError:
                sleep(0.05)
        else:
            process.terminate()
            process.wait(timeout=3)
            pytest.fail("Local Redis did not start within five seconds")
        try:
            yield port
        finally:
            process.terminate()
            process.wait(timeout=3)


def _manager(port: int, namespace: str) -> CacheManager:
    """Create a namespaced Redis manager without opening a connection.
    """  # fmt: skip
    return CacheManager(
        CacheConfiguration(
            default="redis",
            namespace=namespace,
            stores={
                "redis": {
                    "driver": "redis",
                    "options": {
                        "host": "127.0.0.1",
                        "port": port,
                    },
                }
            },
        )
    )


@pytest.mark.anyio
async def test_redis_shares_sync_async_state_and_atomic_operations(
    redis_port: int,
) -> None:
    """Exercise real Redis reads, counters, pull, locks, and cleanup.
    """  # fmt: skip
    manager = _manager(redis_port, "redis-integration")
    repository = manager.store()

    assert repository.put("shared", {"ok": True})
    assert await repository.get_async("shared") == {"ok": True}
    assert await repository.put_async("async", _ASYNC_VALUE)
    assert repository.get("async") == _ASYNC_VALUE
    assert repository.add("once", False)
    assert not await repository.add_async("once", True)
    assert await repository.add_async("async-once", False)
    assert not repository.add("async-once", True)
    assert repository.increment("counter") == 1
    assert await repository.increment_async("counter", 2) == _EXPECTED_COUNTER
    assert (
        await repository.decrement_async("counter", 1)
        == _COUNTER_AFTER_DECREMENT
    )
    assert await repository.pull_async("shared") == {"ok": True}
    assert repository.missing("shared")
    assert repository.put("pull-sync", "value")
    assert repository.pull("pull-sync") == "value"
    assert await repository.put_async("delete-async", "value")
    assert await repository.forget_async("delete-async")
    assert repository.put("delete-sync", "value")
    assert repository.forget("delete-sync")

    lock = manager.lock("resource", ttl=2)
    competitor = manager.lock("resource", ttl=2)
    assert await lock.acquire_async()
    assert not competitor.acquire()
    assert lock.release()
    assert not lock.acquired

    await manager.aclose()


@pytest.mark.anyio
async def test_redis_clear_preserves_other_application_namespace(
    redis_port: int,
) -> None:
    """Clear only one application's key prefix in a shared Redis database.
    """  # fmt: skip
    first = _manager(redis_port, "application-one")
    second = _manager(redis_port, "application-two")
    await first.store().put_async("value", 1)
    await second.store().put_async("value", _OTHER_APPLICATION_VALUE)

    await first.store().flush_async()

    assert await first.store().get_async("value") is None
    assert await second.store().get_async("value") == _OTHER_APPLICATION_VALUE
    await first.aclose()
    await second.aclose()


@pytest.mark.anyio
async def test_redis_lock_clear_preserves_other_store_and_application(
    redis_port: int,
) -> None:
    """Clear only lock keys under the selected Redis store namespace.
    """  # fmt: skip
    first = CacheManager(
        CacheConfiguration(
            default="primary",
            namespace="lock-isolation-one",
            stores={
                name: {
                    "driver": "redis",
                    "options": {
                        "host": "127.0.0.1",
                        "port": redis_port,
                    },
                }
                for name in ("primary", "secondary")
            },
        )
    )
    second = _manager(redis_port, "lock-isolation-two")
    primary = first.lock("resource", ttl=10, store="primary")
    secondary = first.lock("resource", ttl=10, store="secondary")
    other_application = second.lock("resource", ttl=10)

    assert await primary.acquire_async()
    assert await secondary.acquire_async()
    assert await other_application.acquire_async()

    await first.store("primary").flush_locks_async()

    assert not await primary.acquired_async()
    assert await secondary.acquired_async()
    assert await other_application.acquired_async()
    await first.aclose()
    await second.aclose()


@pytest.mark.anyio
async def test_redis_tag_clear_isolated_to_canonical_group(
    redis_port: int,
) -> None:
    """Invalidate one hashed tag group without enumerating application keys.
    """  # fmt: skip
    manager = _manager(redis_port, "redis-tags")
    first = manager.store().tags("users", "profiles")
    same_group = manager.store().tags("profiles", "users")
    separate_group = manager.store().tags("sessions")
    await first.put_async("shared", {"id": 42})
    await separate_group.put_async("shared", "keep")

    await same_group.flush_async()

    assert await first.missing_async("shared")
    assert await separate_group.get_async("shared") == "keep"
    sync_tagged = manager.store().tags("sessions")
    assert sync_tagged.put("sync", "value")
    sync_tagged.flush()
    assert sync_tagged.missing("sync")
    await manager.aclose()


@pytest.mark.anyio
async def test_redis_url_bulk_expiry_stats_and_lock_admin(
    redis_port: int,
) -> None:
    """Exercise URL clients, bounded batches, TTL changes, and lock admin.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            default="redis",
            namespace="redis-capabilities",
            stores={
                "redis": {
                    "driver": "redis",
                    "options": {
                        "url": f"redis://127.0.0.1:{redis_port}/0",
                    },
                }
            },
        )
    )
    repository = manager.store()
    values = {f"batch:{index}": index for index in range(501)}

    assert await repository.put_many_async(values)
    last_key = f"batch:{_LAST_BATCH_INDEX}"
    assert await repository.get_async(last_key) == _LAST_BATCH_INDEX
    assert repository.touch(last_key, ttl=30)
    assert await repository.touch_async(last_key, ttl=None)
    assert await repository.touch_async(last_key, ttl=0)
    assert repository.get(last_key) is None
    assert repository.add("expires", 1, ttl=0) is False
    assert repository.put("expires", 1, ttl=0)
    assert repository.missing("expires")

    lock = manager.lock("administrative", ttl=5)
    assert lock.acquire()
    assert await lock.acquired_async()
    assert await lock.force_release_async()
    assert not lock.acquired
    assert manager.status("redis")["redis"]
    assert await manager.status_async("redis")

    await repository.flush_async()
    assert repository.put_many(values)
    repository.flush()
    await manager.aclose()
    await manager.aclose()


@pytest.mark.anyio
async def test_redis_failover_clears_only_its_child_prefix(
    redis_port: int,
) -> None:
    """Use Redis prefix deletion without clearing sibling application keys.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            default="failover",
            namespace="redis-failover",
            stores={
                "redis": {
                    "driver": "redis",
                    "options": {"host": "127.0.0.1", "port": redis_port},
                },
                "memory": {"driver": "memory"},
                "failover": {
                    "driver": "failover",
                    "options": {"stores": ["redis", "memory"]},
                },
            },
        )
    )
    direct = manager.store("redis")
    failover = manager.store()
    assert await direct.put_async("sibling", "keep")
    assert await failover.put_async("owned", "remove")

    await failover.flush_async()

    assert await failover.missing_async("owned")
    assert await direct.get_async("sibling") == "keep"
    await manager.aclose()


@pytest.mark.anyio
async def test_redis_connection_failure_uses_native_error() -> None:
    """Report a refused local connection without backend details.
    """  # fmt: skip
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    manager = _manager(port, "redis-failure")

    with pytest.raises(CacheBackendError) as captured:
        manager.store().get("unavailable")

    assert "password" not in str(captured.value)
    await manager.aclose()
