"""Verify owner-token cache lock leases and structured cleanup behavior.

Lease tests use a deterministic application-owned memory backend clock.
"""

import anyio
import pytest

from titanspan.cache import (
    CacheBackendError,
    CacheCapabilityError,
    CacheConfiguration,
    CacheConfigurationError,
    CacheLockTimeoutError,
    CacheManager,
    CacheStoreConfiguration,
)
from titanspan.cache._backends.memory import MemoryStore
from titanspan.cache.events import CacheEvent
from titanspan.contracts.cache import CacheStore
from titanspan.events import NativeEventDispatcher

pytestmark = [pytest.mark.concurrency, pytest.mark.unit]
_UNCERTAIN_ACQUIRE_ERROR = "transport response lost"


def _clocked_manager(now: list[float]) -> CacheManager:
    """Create a cache manager whose memory lease clock is test-controlled.
    """  # fmt: skip

    def create_store(_: CacheStoreConfiguration) -> CacheStore:
        """Create one store that reads the shared fake clock.
        """  # fmt: skip
        return MemoryStore(clock=lambda: now[0])

    return CacheManager(
        CacheConfiguration(
            default="clocked",
            stores={"clocked": {"driver": "clocked"}},
        ),
        drivers={"clocked": create_store},
    )


def test_lock_has_atomic_owner_checked_acquisition_and_release() -> None:
    """Allow one owner, reject competing and incorrect owner releases.
    """  # fmt: skip
    manager = _clocked_manager([1_000.0])
    first = manager.lock("resource", ttl=10)
    competing = manager.lock("resource", ttl=10)
    incorrect = manager.restore_lock(
        "resource",
        "0" * 32,
        ttl=10,
    )

    assert first.acquire()
    assert not competing.acquire()
    assert first.acquired
    assert not incorrect.release()
    assert first.release()
    assert not first.acquired


def test_flush_locks_is_scoped_to_the_selected_memory_store() -> None:
    """Clear only the selected application's outstanding lock leases.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            default="primary",
            namespace="lock-clear",
            stores={
                "primary": {"driver": "memory"},
                "secondary": {"driver": "memory"},
            },
        )
    )
    primary = manager.lock("resource", ttl=10, store="primary")
    secondary = manager.lock("resource", ttl=10, store="secondary")

    assert primary.acquire()
    assert secondary.acquire()

    manager.store("primary").flush_locks()

    assert not primary.acquired
    assert secondary.acquired


@pytest.mark.anyio
async def test_flush_locks_async_is_scoped_to_one_memory_store() -> None:
    """Clear selected process-local lock leases through the async API.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            default="primary",
            stores={
                "primary": {"driver": "memory"},
                "secondary": {"driver": "memory"},
            },
        )
    )
    primary = manager.lock("resource", ttl=10, store="primary")
    secondary = manager.lock("resource", ttl=10, store="secondary")

    assert await primary.acquire_async()
    assert await secondary.acquire_async()
    await manager.store("primary").flush_locks_async()

    assert not await primary.acquired_async()
    assert await secondary.acquired_async()


def test_flush_locks_rejects_unsupported_failover_store() -> None:
    """Reject lock clearing when a backend cannot safely coordinate it.
    """  # fmt: skip
    manager = CacheManager(
        CacheConfiguration(
            default="fallback",
            stores={
                "memory": {"driver": "memory"},
                "secondary": {"driver": "memory"},
                "fallback": {
                    "driver": "failover",
                    "options": {"stores": ["memory", "secondary"]},
                },
            },
        )
    )

    with pytest.raises(CacheCapabilityError, match="scoped lock clear"):
        manager.store().flush_locks()


def test_lock_owner_transfer_restores_only_trusted_token_shape() -> None:
    """Restore the exact ownership token without accepting arbitrary text.
    """  # fmt: skip
    manager = _clocked_manager([1_000.0])
    original = manager.lock("transfer", ttl=10)
    restored = manager.restore_lock(
        "transfer",
        original.transfer(),
        ttl=10,
    )

    assert original.acquire()
    assert restored.acquired
    assert restored.release()
    with pytest.raises(CacheConfigurationError, match="owner token"):
        manager.restore_lock("transfer", "untrusted", ttl=10)


def test_memory_lock_metadata_is_bounded_and_reclaims_expired_leases() -> None:
    """Bound process-local lock metadata and reclaim expired owner records.
    """  # fmt: skip
    now = [1_000.0]
    backend = MemoryStore(max_items=1, clock=lambda: now[0])

    assert backend.acquire_lock("first", "owner-a", 1)
    with pytest.raises(CacheBackendError):
        backend.acquire_lock("second", "owner-b", 1)

    now[0] += 1
    assert backend.acquire_lock("second", "owner-b", 1)


def test_lock_lease_expiry_allows_a_new_owner_without_stale_release() -> None:
    """Expire leases by clock and reject a stale owner's release attempt.
    """  # fmt: skip
    now = [1_000.0]
    manager = _clocked_manager(now)
    expired = manager.lock("lease", ttl=2)
    current = manager.lock("lease", ttl=2)

    assert expired.acquire()
    now[0] += 2.1
    assert current.acquire()
    assert not expired.release()
    assert current.acquired


def test_lock_backend_failure_uses_native_error_and_emits_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wrap private failures without leaking backend details to callers.
    """  # fmt: skip
    manager = _clocked_manager([1_000.0])
    lock = manager.lock("failure", ttl=10)
    backend = manager.resolve_backend("clocked")

    def fail_acquire(key: str, owner: str, ttl: float) -> bool:
        """Simulate a private connection error.
        """  # fmt: skip
        _ = key, owner, ttl
        detail = "sensitive redis password"
        raise OSError(detail)

    monkeypatch.setattr(backend, "acquire_lock", fail_acquire)

    with pytest.raises(CacheBackendError) as captured:
        lock.acquire()

    assert "password" not in str(captured.value)


def test_lock_context_releases_after_body_and_bounds_waiting() -> None:
    """Release on normal exit and reject an unavailable zero-wait lease.
    """  # fmt: skip
    manager = _clocked_manager([1_000.0])
    owner = manager.lock("context", ttl=10)
    waiting = manager.lock("context", ttl=10)

    with owner:
        assert owner.acquired
        with pytest.raises(CacheLockTimeoutError), waiting.block(0):
            pytest.fail("A competing lock unexpectedly acquired.")

    assert not owner.acquired


def test_lock_force_release_is_explicitly_owner_independent() -> None:
    """Allow explicit administrative recovery of a live scoped lease.
    """  # fmt: skip
    manager = _clocked_manager([1_000.0])
    owner = manager.lock("administrative", ttl=10)
    administrator = manager.lock("administrative", ttl=10)

    assert owner.acquire()
    assert not administrator.release()
    assert administrator.force_release()
    assert not owner.acquired


@pytest.mark.anyio
async def test_async_lock_context_releases_after_cancellation() -> None:
    """Shield owner-checked cleanup when the protected task is cancelled.
    """  # fmt: skip
    manager = _clocked_manager([1_000.0])
    lock = manager.lock("cancelled", ttl=10)
    entered = anyio.Event()

    async def hold_lock() -> None:
        """Acquire one lease and wait until its task is cancelled.
        """  # fmt: skip
        async with lock:
            entered.set()
            await anyio.sleep_forever()

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(hold_lock)
        await entered.wait()
        tasks.cancel_scope.cancel()

    assert not lock.acquired


@pytest.mark.anyio
async def test_async_lock_inspection_and_force_release() -> None:
    """Inspect and administer one lease through explicit async methods.
    """  # fmt: skip
    manager = _clocked_manager([1_000.0])
    owner = manager.lock("async-administrative", ttl=10)
    administrator = manager.lock("async-administrative", ttl=10)

    assert await owner.acquire_async()
    assert await owner.acquired_async()
    assert await administrator.force_release_async()
    assert not await owner.acquired_async()


@pytest.mark.anyio
async def test_cancelled_acquisition_notification_releases_owned_lease() -> (
    None
):
    """Release the lease when cancellation interrupts async notification.
    """  # fmt: skip
    dispatcher = NativeEventDispatcher()
    manager = CacheManager(
        CacheConfiguration(default="memory"),
        events=dispatcher,
    )
    acquired = manager.lock("notify-cancel", ttl=10)
    competing = manager.lock("notify-cancel", ttl=10)
    notification_started = anyio.Event()
    pause_once = True

    async def wait_for_notification(event: CacheEvent) -> None:
        """Hold acquisition notification until the test cancels its task.
        """  # fmt: skip
        nonlocal pause_once
        if event.action == "lock_acquire" and event.success:
            if not pause_once:
                return
            pause_once = False
            notification_started.set()
            await anyio.sleep_forever()

    dispatcher.listen(CacheEvent, wait_for_notification)

    async def acquire() -> None:
        """Start a lease acquisition whose event listener is suspended.
        """  # fmt: skip
        await acquired.acquire_async()

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(acquire)
        await notification_started.wait()
        tasks.cancel_scope.cancel()

    assert await competing.acquire_async()


@pytest.mark.anyio
async def test_failed_lease_cleanup_is_reported_without_secret_text() -> None:
    """Keep the cancellation cause while reporting owner cleanup failure.
    """  # fmt: skip
    notification_started = anyio.Event()
    release_fails = True

    class FailingReleaseStore(MemoryStore):
        """Fail one cleanup attempt after acquiring the real memory lease.
        """  # fmt: skip

        async def release_lock_async(self, key: str, owner: str) -> bool:
            """Raise once, then delegate owner-checked release.
            """  # fmt: skip
            nonlocal release_fails
            if release_fails:
                raise OSError(_UNCERTAIN_ACQUIRE_ERROR)
            return await super().release_lock_async(key, owner)

    dispatcher = NativeEventDispatcher()
    manager = CacheManager(
        CacheConfiguration(
            default="failing_release",
            stores={"failing_release": {"driver": "failing_release"}},
        ),
        drivers={
            "failing_release": lambda _: FailingReleaseStore(),
        },
        events=dispatcher,
    )
    owner = manager.lock("cleanup-error", ttl=10)
    caught: list[BaseException] = []

    async def pause_notification(event: CacheEvent) -> None:
        """Wait until acquisition notification receives cancellation.
        """  # fmt: skip
        if event.action == "lock_acquire" and event.success:
            notification_started.set()
            await anyio.sleep_forever()

    dispatcher.listen(CacheEvent, pause_notification)

    async def acquire() -> None:
        """Capture cancellation after the lease cleanup attempt.
        """  # fmt: skip
        try:
            await owner.acquire_async()
        except BaseException as error:
            caught.append(error)

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(acquire)
        await notification_started.wait()
        tasks.cancel_scope.cancel()

    cancellation_type = anyio.get_cancelled_exc_class()
    assert len(caught) == 1
    assert isinstance(caught[0], cancellation_type)
    notes = getattr(caught[0], "__notes__", [])
    assert any("OSError" in note for note in notes)
    assert all(_UNCERTAIN_ACQUIRE_ERROR not in note for note in notes)

    release_fails = False
    assert await owner.release_async()


@pytest.mark.anyio
async def test_uncertain_async_acquisition_releases_only_its_owner() -> None:
    """Release a lease when a backend reports failure after acquiring it.
    """  # fmt: skip

    class UncertainStore(MemoryStore):
        """Acquire one lease, then report a transport failure once.
        """  # fmt: skip

        uncertain: bool

        def __init__(self) -> None:
            """Create a store with one uncertain acquisition result.

            The first result simulates a lost backend response.
            """
            super().__init__()
            self.uncertain = True

        async def acquire_lock_async(
            self,
            key: str,
            owner: str,
            ttl: float,
        ) -> bool:
            """Raise after the first successful backend acquisition.

            The lease remains visible until Lock performs cleanup.
            """
            acquired = await super().acquire_lock_async(key, owner, ttl)
            if acquired and self.uncertain:
                self.uncertain = False
                raise OSError(_UNCERTAIN_ACQUIRE_ERROR)
            return acquired

    manager = CacheManager(
        CacheConfiguration(
            default="uncertain",
            stores={"uncertain": {"driver": "uncertain"}},
        ),
        drivers={"uncertain": lambda _: UncertainStore()},
    )
    failed_owner = manager.lock("uncertain", ttl=10)
    next_owner = manager.lock("uncertain", ttl=10)

    with pytest.raises(CacheBackendError):
        await failed_owner.acquire_async()

    assert await next_owner.acquire_async()
    assert await next_owner.acquired_async()
    assert not await failed_owner.acquired_async()


@pytest.mark.anyio
async def test_cancelled_backend_acquire_releases_lease() -> None:
    """Release a grant when backend cancellation occurs before return.
    """  # fmt: skip
    acquired = anyio.Event()
    pause_once = True

    class SuspendedStore(MemoryStore):
        """Pause after writing a lease but before returning its grant.
        """  # fmt: skip

        async def acquire_lock_async(
            self,
            key: str,
            owner: str,
            ttl: float,
        ) -> bool:
            """Write the lease and wait until the owner task is cancelled.

            The pause makes acquisition uncertainty deterministic.
            """
            nonlocal pause_once
            result = await super().acquire_lock_async(key, owner, ttl)
            if result and pause_once:
                pause_once = False
                acquired.set()
                await anyio.sleep_forever()
            return result

    manager = CacheManager(
        CacheConfiguration(
            default="suspended",
            stores={"suspended": {"driver": "suspended"}},
        ),
        drivers={"suspended": lambda _: SuspendedStore()},
    )
    owner = manager.lock("cancel-before-return", ttl=10)
    competitor = manager.lock("cancel-before-return", ttl=10)

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(owner.acquire_async)
        await acquired.wait()
        tasks.cancel_scope.cancel()

    assert await competitor.acquire_async()
