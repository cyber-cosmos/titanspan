"""Verify bounded background dispatch and asynchronous queue backpressure.

Threading events make sink saturation deterministic without wall-clock
performance assertions.
"""

from __future__ import annotations

from io import StringIO
from threading import Event
from typing import TYPE_CHECKING, TextIO

import anyio
import pytest

from titanspan.logging import (
    DeliveryStatus,
    LogDeliveryError,
    LogManager,
    LogQueueFullError,
    MemoryLogDriver,
)

if TYPE_CHECKING:
    from titanspan.logging.configuration import ChannelConfiguration
    from titanspan.logging.contracts.log_driver import LogDriver
    from titanspan.logging.events import MessageLogged
    from titanspan.logging.record import LogRecord

pytestmark = pytest.mark.unit
WAIT_TIMEOUT_SECONDS = 2.0
QUEUE_CAPACITY = 1
SHORT_WAIT_TIMEOUT_SECONDS = 0.02
SINK_FAILURE_MESSAGE = "sink failure"


class BlockingDriver:
    """Hold its worker until the test explicitly allows delivery.

    Threading events make queue capacity deterministic without sleeps.
    """

    def __init__(self) -> None:
        """Create thread-safe coordination and a record list.

        The test controls when the blocked sink resumes.
        """
        self.started = Event()
        self.release = Event()
        self.records: list[LogRecord] = []

    def write(self, record: LogRecord) -> None:
        """Pause one worker delivery, then retain the native record.

        Args:
            record: The queued and sanitized record.

        Raises:
            TimeoutError: If the test does not release the worker in time.
        """
        self.started.set()
        if not self.release.wait(WAIT_TIMEOUT_SECONDS):
            message = "Test did not release the background worker"
            raise TimeoutError(message)
        self.records.append(record)

    def flush(self) -> None:
        """Complete immediately because writes run in the worker.

        Queue draining belongs to the background wrapper.
        """

    def close(self) -> None:
        """Release no resource beyond test-controlled synchronization.

        The wrapper owns and joins its worker thread.
        """


def _manager(
    driver: LogDriver,
    policy: str,
    *,
    wait_timeout: float = 5.0,
    emergency_stream: TextIO | None = None,
) -> LogManager:
    """Create a manager with a single bounded background channel.

    Args:
        driver: Blocking sink used to make queue saturation deterministic.
        policy: Configured behavior when synchronous capacity is exhausted.
        wait_timeout: Maximum bounded async wait for queue capacity.
        emergency_stream: Optional fallback output used by overflow handling.

    Returns:
        A manager that owns the background worker and wrapped driver.
    """

    def factory(_: ChannelConfiguration) -> LogDriver:
        """Return the configured native test sink.

        Returns:
            The provided destination driver.
        """
        return driver

    return LogManager(
        {
            "channels": {
                "default": {
                    "driver": "memory",
                    "background": True,
                    "queue_capacity": QUEUE_CAPACITY,
                    "overflow_policy": policy,
                    "queue_wait_timeout": wait_timeout,
                },
            },
        },
        drivers={"memory": factory},
        emergency_stream=emergency_stream,
    )


@pytest.mark.parametrize(
    ("policy", "expected_messages", "expected_status"),
    [
        (
            "drop_newest",
            ("first", "second"),
            DeliveryStatus.DROPPED,
        ),
        (
            "drop_oldest",
            ("first", "third"),
            DeliveryStatus.QUEUED,
        ),
    ],
)
def test_sync_background_queue_applies_bounded_overflow_policy(
    policy: str,
    expected_messages: tuple[str, ...],
    expected_status: DeliveryStatus,
) -> None:
    """Keep pending records bounded and make overflow visible to listeners.

    Args:
        policy: The selected synchronous overflow behavior.
        expected_messages: Records delivered after the queue is drained.
        expected_status: Status assigned to the final log call.
    """
    sink = BlockingDriver()
    manager = _manager(sink, policy)
    events: list[MessageLogged] = []
    logger = manager.channel()
    logger.listen(events.append)

    logger.info("first")
    assert sink.started.wait(WAIT_TIMEOUT_SECONDS)
    logger.info("second")
    logger.info("third")
    sink.release.set()
    manager.flush()
    manager.close()

    assert [record.message for record in sink.records] == list(
        expected_messages,
    )
    assert events[-1].status is expected_status


@pytest.mark.anyio
async def test_async_logging_waits_for_queue_capacity() -> None:
    """Let an async caller await bounded queue capacity without blocking.

    The async API waits in AnyIO's worker pool until the sink frees a slot and
    preserves all accepted records in queue order.
    """
    sink = BlockingDriver()
    manager = _manager(sink, "await")
    logger = manager.channel()
    await logger.info_async("first")
    is_started = await anyio.to_thread.run_sync(
        sink.started.wait,
        WAIT_TIMEOUT_SECONDS,
    )
    assert is_started
    await logger.info_async("second")
    finished = anyio.Event()

    async def write_after_capacity() -> None:
        """Await a third message and signal completion to the test scope.

        Completion is signaled only after the queue accepts the record.
        """
        await logger.info_async("third")
        finished.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(write_after_capacity)
        sink.release.set()
        await finished.wait()

    await manager.aclose()

    assert [record.message for record in sink.records] == [
        "first",
        "second",
        "third",
    ]


@pytest.mark.parametrize("policy", ["raise", "await"])
def test_synchronous_wait_policies_never_block_when_queue_is_full(
    policy: str,
) -> None:
    """Reject synchronous overflow rather than blocking a caller thread.

    Args:
        policy: Overflow setting that has no safe synchronous wait form.
    """
    sink = BlockingDriver()
    manager = _manager(sink, policy)
    logger = manager.channel()
    logger.info("active")
    assert sink.started.wait(WAIT_TIMEOUT_SECONDS)
    logger.info("queued")

    with pytest.raises(LogQueueFullError):
        logger.info("overflow")

    sink.release.set()
    manager.flush()
    manager.close()


def test_emergency_overflow_policy_reports_fallback_delivery() -> None:
    """Write overflow records to the independent emergency sink.

    The emergency destination receives only the already-redacted record.
    """
    sink = BlockingDriver()
    emergency_stream = StringIO()
    manager = _manager(
        sink,
        "emergency",
        emergency_stream=emergency_stream,
    )
    events: list[MessageLogged] = []
    logger = manager.channel()
    logger.listen(events.append)
    logger.info("active")
    assert sink.started.wait(WAIT_TIMEOUT_SECONDS)
    logger.info("queued")
    logger.warning("fallback", context={"token": "redaction-marker"})
    sink.release.set()
    manager.close()

    assert events[-1].status is DeliveryStatus.FALLBACK
    assert "fallback" in emergency_stream.getvalue()
    assert "redaction-marker" not in emergency_stream.getvalue()


@pytest.mark.anyio
async def test_async_wait_policy_times_out_when_sink_never_frees_capacity() -> (
    None
):
    """Raise a native queue error after the bounded wait expires.

    The asynchronous caller never waits indefinitely for a full queue.
    """
    sink = BlockingDriver()
    manager = _manager(
        sink,
        "await",
        wait_timeout=SHORT_WAIT_TIMEOUT_SECONDS,
    )
    logger = manager.channel()
    await logger.info_async("active")
    is_started = await anyio.to_thread.run_sync(
        sink.started.wait,
        WAIT_TIMEOUT_SECONDS,
    )
    assert is_started
    await logger.info_async("queued")

    with pytest.raises(LogQueueFullError):
        await logger.info_async("timed out")

    sink.release.set()
    await manager.aclose()


class _FailingDriver(MemoryLogDriver):
    """Fail one background delivery for worker error reporting.

    This deterministic sink exposes failures during graceful shutdown.
    """

    def write(self, record: LogRecord) -> None:
        """Fail a delivery so worker error reporting can be inspected.

        Args:
            record: The queued record that cannot reach its destination.
        """
        del record
        raise RuntimeError(SINK_FAILURE_MESSAGE)


def test_background_sink_failure_surfaces_during_graceful_close() -> None:
    """Report worker failures after draining accepted work.

    Shutdown must release the sink even when one buffered write failed.
    """
    emergency_stream = StringIO()
    sink = _FailingDriver()
    manager = _manager(
        sink,
        "drop_newest",
        emergency_stream=emergency_stream,
    )
    logger = manager.channel()
    logger.error("accepted before sink failure")

    with pytest.raises(LogDeliveryError):
        manager.close()

    assert sink.closed
    assert "RuntimeError" in emergency_stream.getvalue()
