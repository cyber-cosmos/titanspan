"""Dispatch log records through a bounded, owned worker thread.

The driver preserves native ``LogRecord`` values and delegates final output
to another Titanspan driver. Queue size bounds pending records and memory.
"""

from __future__ import annotations

from collections import deque
from contextlib import suppress
from enum import Enum
from queue import Empty, Full, Queue
from threading import Condition, Lock, Thread
from typing import TYPE_CHECKING, Literal

import anyio

from titanspan.contracts.logging import DeliveryStatus
from titanspan.logging.exceptions import (
    LogDeliveryError,
    LogLifecycleError,
    LogQueueFullError,
)

if TYPE_CHECKING:
    from titanspan.contracts.logging import LogDriver
    from titanspan.logging.drivers.core import EmergencyLogDriver
    from titanspan.logging.record import LogRecord

type OverflowPolicy = Literal[
    "drop_newest",
    "drop_oldest",
    "raise",
    "emergency",
    "await",
]


class _StopSignal(Enum):
    """Mark the end of the background worker's owned queue.

    A typed sentinel avoids confusing shutdown with an application record.
    """

    STOP = "stop"


_STOP = _StopSignal.STOP


class BackgroundLogDriver:
    """Move synchronous destination writes to one bounded worker.

    Attributes:
        capacity: Maximum number of records waiting for the sink.
        dropped_count: Number of records rejected by a drop policy.

    The wrapper owns its worker thread and the wrapped driver. Synchronous
    calls never wait for queue capacity. The asynchronous ``write_async``
    method can wait up to the configured timeout when policy is ``await``.
    """

    def __init__(
        self,
        driver: LogDriver[LogRecord],
        *,
        channel: str,
        capacity: int,
        overflow_policy: OverflowPolicy,
        wait_timeout: float,
        emergency: EmergencyLogDriver,
    ) -> None:
        """Create a worker and start it only after validating its capacity.

        Args:
            driver: Destination that receives records from the worker.
            channel: Name used in safe delivery diagnostics.
            capacity: Positive maximum number of pending records.
            overflow_policy: Behavior when the bounded queue is full.
            wait_timeout: Maximum async wait for available capacity.
            emergency: Minimal fallback writer for emergency overflow.

        Raises:
            ValueError: If the capacity or timeout is invalid.
        """
        if capacity < 1 or wait_timeout <= 0:
            message = "Background capacity and timeout must be positive"
            raise ValueError(message)
        self.capacity = capacity
        self._driver = driver
        self._channel = channel
        self._overflow_policy = overflow_policy
        self._wait_timeout = wait_timeout
        self._emergency = emergency
        self._queue: Queue[LogRecord | _StopSignal] = Queue(
            maxsize=capacity,
        )
        self._condition = Condition()
        self._enqueue_lock = Lock()
        self._active_writers = 0
        self._closing = False
        self._closed = False
        self._failures: deque[str] = deque(maxlen=100)
        self._dropped_count = 0
        self._thread = Thread(
            target=self._run,
            name=f"titanspan-log-{channel}",
            daemon=True,
        )
        self._thread.start()

    @property
    def dropped_count(self) -> int:
        """Return the number of records discarded by overflow policies.

        Returns:
            A monotonic count for the lifetime of this driver.
        """
        with self._condition:
            return self._dropped_count

    @property
    def inner_driver(self) -> LogDriver[LogRecord]:
        """Return the native destination wrapped by background dispatch.

        Returns:
            The Titanspan driver that owns the final output destination.
        """
        return self._driver

    @property
    def failures(self) -> tuple[str, ...]:
        """Return bounded diagnostics without retaining payloads.

        Returns:
            Channel and exception type pairs from sink failures.
        """
        with self._condition:
            return tuple(self._failures)

    def write(self, record: LogRecord) -> DeliveryStatus:
        """Queue one record without waiting for sink capacity.

        Args:
            record: Sanitized record captured in the caller context.

        Returns:
            The queue or fallback outcome observed by this call.

        Raises:
            LogQueueFullError: For ``raise`` and synchronous ``await`` policy.
            LogLifecycleError: If shutdown has begun.
        """
        self._begin_write()
        try:
            return self._enqueue_nowait(record)
        finally:
            self._end_write()

    async def write_async(self, record: LogRecord) -> DeliveryStatus:
        """Queue a record, awaiting bounded capacity only for ``await``.

        Args:
            record: Sanitized record captured in the caller context.

        Returns:
            The queue or fallback outcome observed by this call.

        Raises:
            LogQueueFullError: If the configured wait expires.
            LogLifecycleError: If shutdown has begun.

        Notes:
            Queue insertion runs in AnyIO's worker pool. Cancellation is
            delayed until the bounded insertion operation finishes.
        """
        if self._overflow_policy != "await":
            return self.write(record)
        return await anyio.to_thread.run_sync(
            self._enqueue_wait,
            record,
            abandon_on_cancel=False,
        )

    def flush(self) -> None:
        """Wait for accepted queue records and flush the destination.

        Raises:
            LogDeliveryError: If any background sink write failed.
            LogLifecycleError: If the worker was closed first.
        """
        if self._closed:
            message = f"Background channel {self._channel!r} is closed"
            raise LogLifecycleError(message)
        self._queue.join()
        with self._condition:
            had_failures = bool(self._failures)
        self._driver.flush()
        if had_failures:
            raise LogDeliveryError(
                self._channel,
                "one or more background writes failed",
            )

    def close(self) -> None:
        """Stop the worker and release the wrapped destination once.

        Closing waits for active producers, then queues a sentinel behind all
        accepted records. This prevents writes from being stranded after the
        worker observes shutdown.
        """
        with self._condition:
            if self._closed:
                return
            if self._closing:
                while not self._closed:
                    self._condition.wait()
                return
            self._closing = True
            while self._active_writers:
                self._condition.wait()
        try:
            self._queue.put(_STOP)
            self._thread.join()
            self._driver.close()
        finally:
            with self._condition:
                self._closed = True
                self._condition.notify_all()

    def _begin_write(self) -> None:
        """Reserve an enqueue operation against concurrent shutdown.

        Raises:
            LogLifecycleError: If the queue is closing or already closed.
        """
        with self._condition:
            if self._closing or self._closed:
                message = f"Background channel {self._channel!r} is closed"
                raise LogLifecycleError(message)
            self._active_writers += 1

    def _end_write(self) -> None:
        """Release the enqueue reservation and wake shutdown if needed.

        Shutdown waits for this reservation before inserting its sentinel.
        """
        with self._condition:
            self._active_writers -= 1
            self._condition.notify_all()

    def _enqueue_wait(self, record: LogRecord) -> DeliveryStatus:
        """Wait a bounded time for queue space on a worker thread.

        Args:
            record: A sanitized record captured before entering the worker.

        Returns:
            The queued status after the record enters available capacity.

        Raises:
            LogQueueFullError: If the configured wait expires.
        """
        self._begin_write()
        try:
            try:
                self._queue.put(record, timeout=self._wait_timeout)
            except Full as error:
                message = "Background log queue remained full until timeout"
                raise LogQueueFullError(self._channel, message) from error
            return DeliveryStatus.QUEUED
        finally:
            self._end_write()

    def _enqueue_nowait(self, record: LogRecord) -> DeliveryStatus:
        """Apply one nonblocking overflow policy to a record.

        Args:
            record: The sanitized record to queue or reject.

        Returns:
            An explicit queued, dropped, or fallback status.
        """
        with self._enqueue_lock:
            try:
                self._queue.put_nowait(record)
            except Full:
                return self._handle_full_queue(record)
        return DeliveryStatus.QUEUED

    def _handle_full_queue(self, record: LogRecord) -> DeliveryStatus:
        """Apply a deterministic configured full-queue policy.

        Args:
            record: The new record submitted while the queue is full.

        Returns:
            The outcome reported to the calling channel.

        Raises:
            LogQueueFullError: If the selected policy rejects with an error.
        """
        policy = self._overflow_policy
        if policy == "drop_oldest":
            try:
                discarded = self._queue.get_nowait()
            except Empty:
                # A concurrent worker may have freed the queue already.
                pass
            else:
                self._queue.task_done()
                if isinstance(discarded, _StopSignal):
                    self._queue.put_nowait(discarded)
                    return self._drop(record)
                self._drop(discarded)
            try:
                self._queue.put_nowait(record)
            except Full:
                return self._drop(record)
            return DeliveryStatus.QUEUED
        if policy == "drop_newest":
            return self._drop(record)
        if policy == "emergency":
            self._emergency.write(record)
            return DeliveryStatus.FALLBACK
        message = "Background log queue is full"
        raise LogQueueFullError(self._channel, message)

    def _drop(self, record: LogRecord) -> DeliveryStatus:
        """Count and explicitly report a record dropped by queue pressure.

        Args:
            record: The record discarded by an overflow policy.

        Returns:
            The native dropped status.
        """
        del record
        with self._condition:
            self._dropped_count += 1
        return DeliveryStatus.DROPPED

    def _run(self) -> None:
        """Deliver queue records serially and signal queue completion.

        Sink failures are retained as bounded type-only diagnostics and are
        reported through the independent emergency writer.
        """
        while True:
            item = self._queue.get()
            try:
                if isinstance(item, _StopSignal):
                    return
                self._driver.write(item)
            except Exception as error:
                with self._condition:
                    self._failures.append(type(error).__name__)
                with suppress(OSError):
                    self._emergency.report_failure(
                        self._channel,
                        type(error).__name__,
                    )
            finally:
                self._queue.task_done()
