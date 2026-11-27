"""Verify cache lock lifecycle, waiting, errors, and owner transfers.

The lock tests exercise the real memory lease implementation and one narrow
failure adapter for native error translation.
"""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TYPE_CHECKING, cast

import anyio
import pytest

from titanspan.cache import (
    CacheBackendError,
    CacheCapabilityError,
    CacheConfiguration,
    CacheLockTimeoutError,
    CacheManager,
    Lock,
)
from titanspan.cache._backends.memory import MemoryStore
from titanspan.contracts.cache import CacheStore

if TYPE_CHECKING:
    from titanspan.contracts.events import EventDispatcher

pytestmark = pytest.mark.unit
_OWNER_LENGTH = 32
_LEASE_SECONDS = 4
_PRIVATE_LOCK_ERROR = "private lock service detail"
_LISTENER_FAILURE = "listener failure"


class _FailingLockStore(MemoryStore):
    """Raise from selected lock methods while advertising lock support.
    """  # fmt: skip

    def __init__(self, failures: set[str]) -> None:
        """Create one cache store with deterministic lock failures.
        """  # fmt: skip
        super().__init__()
        self._failures: set[str] = failures

    def _check(self, operation: str) -> None:
        """Raise one private error if this lock call is selected.
        """  # fmt: skip
        if operation in self._failures:
            message = _PRIVATE_LOCK_ERROR
            raise OSError(message)

    def lock_owner(self, key: str) -> str | None:
        """Fail or delegate synchronous owner inspection.
        """  # fmt: skip
        self._check("inspect")
        return super().lock_owner(key)

    async def lock_owner_async(self, key: str) -> str | None:
        """Fail or delegate asynchronous owner inspection.
        """  # fmt: skip
        self._check("inspect")
        return await super().lock_owner_async(key)

    def acquire_lock(self, key: str, owner: str, ttl: float) -> bool:
        """Fail or delegate synchronous lease acquisition.
        """  # fmt: skip
        self._check("acquire")
        return super().acquire_lock(key, owner, ttl)

    async def acquire_lock_async(
        self,
        key: str,
        owner: str,
        ttl: float,
    ) -> bool:
        """Fail or delegate asynchronous lease acquisition.
        """  # fmt: skip
        self._check("acquire")
        return await super().acquire_lock_async(key, owner, ttl)

    def release_lock(self, key: str, owner: str) -> bool:
        """Fail or delegate owner-checked synchronous release.
        """  # fmt: skip
        self._check("release")
        return super().release_lock(key, owner)

    async def release_lock_async(self, key: str, owner: str) -> bool:
        """Fail or delegate owner-checked asynchronous release.
        """  # fmt: skip
        self._check("release")
        return await super().release_lock_async(key, owner)

    def force_release_lock(self, key: str) -> bool:
        """Fail or delegate synchronous administrative release.
        """  # fmt: skip
        self._check("force_release")
        return super().force_release_lock(key)

    async def force_release_lock_async(self, key: str) -> bool:
        """Fail or delegate asynchronous administrative release.
        """  # fmt: skip
        self._check("force_release")
        return await super().force_release_lock_async(key)


def _manager(failures: set[str] | None = None) -> CacheManager:
    """Create an application manager with a real memory lock backend.
    """  # fmt: skip
    selected: set[str] = set() if failures is None else failures

    def create_store(_: object) -> CacheStore:
        """Return one memory store configured for selected failures.
        """  # fmt: skip
        return _FailingLockStore(selected)

    return CacheManager(
        CacheConfiguration(
            default="scripted",
            stores={"scripted": {"driver": "scripted"}},
        ),
        drivers={"scripted": create_store},
    )


_SYNC_FAILURES: tuple[tuple[str, Callable[[Lock], object]], ...] = (
    ("inspect", lambda lock: lock.acquired),
    ("acquire", lambda lock: lock.acquire()),
    ("release", lambda lock: lock.release()),
    ("force_release", lambda lock: lock.force_release()),
)


@pytest.mark.parametrize(
    ("failure", "operation"),
    _SYNC_FAILURES,
    ids=[
        f"{failure}-{index}"
        for index, (failure, _) in enumerate(_SYNC_FAILURES)
    ],
)
def test_sync_lock_operations_translate_backend_errors(
    failure: str,
    operation: Callable[[Lock], object],
) -> None:
    """Raise native lock errors without rendering private details.
    """  # fmt: skip
    lock = _manager({failure}).lock("resource", ttl=10)

    with pytest.raises(CacheBackendError) as captured:
        operation(lock)

    assert _PRIVATE_LOCK_ERROR not in str(captured.value)


_ASYNC_FAILURES: tuple[tuple[str, Callable[[Lock], Awaitable[object]]], ...] = (
    ("inspect", lambda lock: lock.acquired_async()),
    ("acquire", lambda lock: lock.acquire_async()),
    ("release", lambda lock: lock.release_async()),
    ("force_release", lambda lock: lock.force_release_async()),
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
async def test_async_lock_operations_translate_backend_errors(
    failure: str,
    operation: Callable[[Lock], Awaitable[object]],
) -> None:
    """Wrap async lock failures and keep backend details private.
    """  # fmt: skip
    lock = _manager({failure}).lock("resource", ttl=10)

    with pytest.raises(CacheBackendError) as captured:
        await operation(lock)

    assert _PRIVATE_LOCK_ERROR not in str(captured.value)


def test_sync_lock_context_blocking_and_callback() -> None:
    """Wait within the requested bound and release after managed work.
    """  # fmt: skip
    manager = _manager()
    owner = manager.lock("resource", ttl=10)
    contender = manager.lock("resource", ttl=10)
    assert owner.acquire()
    assert contender.block(0.01) is contender

    with pytest.raises(CacheLockTimeoutError), contender:
        pytest.fail("A competing lock owner must not enter.")
    owner.release()

    assert contender.run(lambda: "completed") == "completed"
    assert not contender.acquired
    assert contender.block(0.01) is contender
    assert contender.run(lambda: "bounded") == "bounded"


@pytest.mark.anyio
async def test_async_lock_context_blocking_and_callback() -> None:
    """Wait without blocking and release after synchronous or async work.
    """  # fmt: skip
    manager = _manager()
    owner = manager.lock("resource", ttl=10)
    contender = manager.lock("resource", ttl=10)
    assert await owner.acquire_async()
    contender.block_async(0.01)

    with pytest.raises(CacheLockTimeoutError):
        async with contender:
            pytest.fail("A competing lock owner must not enter.")
    await owner.release_async()

    async def work() -> str:
        """Return a result after yielding to the async scheduler.
        """  # fmt: skip
        await anyio.lowlevel.checkpoint()
        return "async"

    assert await contender.run_async(work) == "async"
    assert not await contender.acquired_async()
    owner = manager.lock("resource", ttl=10)
    assert await owner.acquire_async()
    contender.block_async(0.01)
    with pytest.raises(CacheLockTimeoutError):
        async with contender:
            pytest.fail("A competing lock owner must remain excluded.")
    await owner.release_async()
    assert await contender.run_async(lambda: "bounded") == "bounded"


@pytest.mark.parametrize("wait", [-1.0, 30.1, float("inf"), float("nan")])
def test_lock_wait_is_finite_non_negative_and_bounded(wait: float) -> None:
    """Reject unbounded or negative waits before any backend call.
    """  # fmt: skip
    lock = _manager().lock("resource", ttl=10)

    with pytest.raises(ValueError, match="between 0 and 30 seconds"):
        lock.block(wait)


@pytest.mark.parametrize("ttl", [0.0, -1.0, float("inf"), float("nan")])
def test_lock_lease_must_be_finite_and_positive(ttl: float) -> None:
    """Reject leases that expire immediately or cannot be compared safely.
    """  # fmt: skip
    with pytest.raises(ValueError, match="finite and positive"):
        Lock(_manager(), "scripted", "resource", ttl)


@pytest.mark.anyio
async def test_lock_capability_errors_remain_explicit() -> None:
    """Expose unsupported locking as a capability error.
    """  # fmt: skip
    lock = CacheManager(
        CacheConfiguration(
            default="disabled",
            stores={"disabled": {"driver": "null"}},
        )
    ).lock("resource", ttl=10)

    with pytest.raises(CacheCapabilityError, match="does not support"):
        lock.acquire()
    with pytest.raises(CacheCapabilityError, match="does not support"):
        await lock.acquire_async()

    manager = CacheManager(
        CacheConfiguration(
            default="disabled",
            stores={"disabled": {"driver": "null"}},
        )
    )
    with pytest.raises(CacheCapabilityError, match="does not support"):
        assert manager.lock("inspect", ttl=10).acquired
    with pytest.raises(CacheCapabilityError, match="does not support"):
        manager.lock("release", ttl=10).release()
    with pytest.raises(CacheCapabilityError, match="does not support"):
        manager.lock("force", ttl=10).force_release()
    with pytest.raises(CacheCapabilityError, match="does not support"):
        await manager.lock("inspect", ttl=10).acquired_async()
    with pytest.raises(CacheCapabilityError, match="does not support"):
        await manager.lock("release", ttl=10).release_async()
    with pytest.raises(CacheCapabilityError, match="does not support"):
        await manager.lock("force", ttl=10).force_release_async()


@pytest.mark.anyio
async def test_lock_event_failures_do_not_change_lease_outcomes() -> None:
    """Keep listener failures from hiding lock acquisition and release.
    """  # fmt: skip

    class BrokenDispatcher:
        """Raise from explicit sync and async dispatch entry points.
        """  # fmt: skip

        def dispatch(self, event: object) -> list[object]:
            """Raise a listener error during synchronous dispatch.
            """  # fmt: skip
            del event
            message = _LISTENER_FAILURE
            raise RuntimeError(message)

        async def dispatch_async(self, event: object) -> list[object]:
            """Raise a listener error during asynchronous dispatch.
            """  # fmt: skip
            del event
            message = _LISTENER_FAILURE
            raise RuntimeError(message)

    manager = CacheManager(
        CacheConfiguration(),
        events=cast("EventDispatcher", BrokenDispatcher()),
    )
    lock = manager.lock("sync", ttl=10)
    assert lock.acquire()
    assert lock.release()

    async_lock = manager.lock("async", ttl=10)
    assert await async_lock.acquire_async()
    assert await async_lock.release_async()


def test_lock_owner_properties_and_transfer_are_explicit() -> None:
    """Expose a restorable opaque owner token and selected lease details.
    """  # fmt: skip
    manager = _manager()
    lock = manager.lock("resource", ttl=timedelta(seconds=4))

    assert len(lock.owner) == _OWNER_LENGTH
    assert lock.transfer() == lock.owner
    assert lock.store_name == "scripted"
    assert lock.lease_seconds == _LEASE_SECONDS
    assert (
        manager.restore_lock(
            "resource",
            lock.transfer(),
            ttl=timedelta(seconds=_LEASE_SECONDS),
        ).owner
        == lock.owner
    )
