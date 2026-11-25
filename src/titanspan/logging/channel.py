"""Coordinate filtering, processing, backend dispatch, and driver ownership.

Channels translate framework records to private backend events while keeping
the native driver contract visible to custom integrations.
"""

from collections.abc import Iterable
from contextvars import ContextVar
from threading import Lock
from typing import TYPE_CHECKING

import anyio

from titanspan.logging._backends.structured import StructuredBackend
from titanspan.logging.contracts.async_log_driver import AsyncLogDriver
from titanspan.logging.contracts.log_driver import LogDriver
from titanspan.logging.contracts.log_processor import LogProcessor
from titanspan.logging.delivery import DeliveryStatus
from titanspan.logging.drivers.core import EmergencyLogDriver
from titanspan.logging.events import MessageLogged
from titanspan.logging.exceptions import (
    LogDeliveryError,
    LogEventError,
    LogLifecycleError,
)
from titanspan.logging.level import LogLevel
from titanspan.logging.processors import process_record
from titanspan.logging.record import LogRecord

if TYPE_CHECKING:
    from collections.abc import Callable

type LogEventListener = Callable[[MessageLogged], None]
_EVENT_DISPATCHING: ContextVar[bool] = ContextVar(
    "titanspan_log_event_dispatching",
    default=False,
)


class LogChannel:
    """Own a named destination and its ordered record processors.

    Attributes:
        name: The channel identifier attached to delivered records.
        level: The least severe RFC level accepted by this channel.

    The channel owns its driver and an isolated private backend adapter.
    Closing it is idempotent and prevents later writes.
    """

    def __init__(
        self,
        name: str,
        driver: LogDriver,
        *,
        level: LogLevel,
        processors: Iterable[LogProcessor] = (),
        emergency_driver: EmergencyLogDriver | None = None,
    ) -> None:
        """Create a channel around one native destination driver.

        Args:
            name: The configured channel name.
            driver: A Titanspan driver owned by this channel.
            level: Minimum accepted RFC severity.
            processors: Ordered transformations applied before delivery.
            emergency_driver: Minimal fallback used when delivery fails.
        """
        self.name = name
        self.level = level
        self._driver = driver
        self._processors = tuple(processors)
        self._emergency = emergency_driver or EmergencyLogDriver()
        self._backend = StructuredBackend(self._deliver)
        self._closed = False
        self._listeners: list[LogEventListener] = []
        self._listener_lock = Lock()

    @property
    def closed(self) -> bool:
        """Return whether the channel has released its resources.

        Returns:
            ``True`` after close has completed.
        """
        return self._closed

    @property
    def driver(self) -> LogDriver:
        """Return this channel's Titanspan-owned driver abstraction.

        Returns:
            The native driver wrapper, not its private backend handler.
        """
        return self._driver

    def is_enabled(self, level: LogLevel) -> bool:
        """Check whether the configured threshold accepts a severity.

        Args:
            level: The candidate RFC severity.

        Returns:
            ``True`` if the message is at least as severe as the threshold.
        """
        return level.severity <= self.level.severity

    def listen(self, callback: LogEventListener) -> None:
        """Subscribe to successfully delivered records on this channel.

        Args:
            callback: Synchronous function receiving a native event.

        Listener changes are protected independently from destination I/O.
        Callbacks execute without holding that lock.
        """
        with self._listener_lock:
            self._listeners.append(callback)

    def write(self, record: LogRecord) -> DeliveryStatus:
        """Process and deliver a record through the private adapter.

        Args:
            record: A normalized native log record.

        Raises:
            LogDeliveryError: If processing or destination delivery fails.
            RuntimeError: If the channel has been closed.
        """
        if self._closed:
            msg = f"Log channel {self.name!r} is closed"
            raise LogLifecycleError(msg)
        if not self.is_enabled(record.level):
            return DeliveryStatus.DELIVERED
        try:
            processed = process_record(record, self._processors)
            outcome = self._backend.write(processed)
        except LogDeliveryError:
            raise
        except Exception as error:
            self._report_failure(error)
            raise LogDeliveryError(
                self.name,
                type(error).__name__,
            ) from error
        status = outcome or DeliveryStatus.DELIVERED
        self._notify_listeners(processed, status)
        return status

    async def write_async(self, record: LogRecord) -> DeliveryStatus:
        """Deliver a record through a native asynchronous driver when present.

        Args:
            record: A normalized Titanspan log record.

        Returns:
            The outcome observed at this channel boundary.

        Raises:
            LogDeliveryError: If processing or destination delivery fails.
            LogLifecycleError: If the channel has already been closed.
        """
        if self._closed:
            message = f"Log channel {self.name!r} is closed"
            raise LogLifecycleError(message)
        if not self.is_enabled(record.level):
            return DeliveryStatus.DELIVERED
        if not isinstance(self._driver, AsyncLogDriver):
            return await anyio.to_thread.run_sync(
                self.write,
                record,
                abandon_on_cancel=False,
            )
        try:
            processed = process_record(record, self._processors)
            outcome = await self._driver.write_async(processed)
        except LogDeliveryError:
            raise
        except Exception as error:
            self._report_failure(error)
            raise LogDeliveryError(
                self.name,
                type(error).__name__,
            ) from error
        status = outcome or DeliveryStatus.DELIVERED
        self._notify_listeners(processed, status)
        return status

    def flush(self) -> None:
        """Flush backend and driver buffers.

        Raises:
            LogDeliveryError: If the driver cannot flush its output.
            RuntimeError: If the channel has been closed.
        """
        if self._closed:
            msg = f"Log channel {self.name!r} is closed"
            raise LogLifecycleError(msg)
        try:
            self._driver.flush()
        except Exception as error:
            self._report_failure(error)
            raise LogDeliveryError(
                self.name,
                type(error).__name__,
            ) from error

    def close(self) -> None:
        """Release backend and driver resources exactly once.

        If driver cleanup fails, the backend is still detached before the
        error is propagated to the manager.
        """
        if self._closed:
            return
        self._closed = True
        try:
            self._driver.close()
        finally:
            self._backend.close()

    def _deliver(self, record: LogRecord) -> DeliveryStatus | None:
        """Deliver one backend-decoded native record to the owned driver.

        Args:
            record: The record transported through Structlog.

        Raises:
            Exception: The destination failure for wrapping by ``write``.
        """
        return self._driver.write(record)

    def _notify_listeners(
        self,
        record: LogRecord,
        status: DeliveryStatus,
    ) -> None:
        """Notify a stable listener snapshot after destination delivery.

        Args:
            record: The redacted record accepted by the driver.
            status: Whether delivery completed, queued, or was degraded.

        Raises:
            LogEventError: If a listener raises after delivery.
        """
        if _EVENT_DISPATCHING.get():
            return
        with self._listener_lock:
            listeners = tuple(self._listeners)
        if not listeners:
            return
        token = _EVENT_DISPATCHING.set(True)
        event = MessageLogged(record, status)
        try:
            for listener in listeners:
                try:
                    listener(event)
                except Exception as error:
                    raise LogEventError(
                        self.name,
                        type(error).__name__,
                    ) from error
        finally:
            _EVENT_DISPATCHING.reset(token)

    def _report_failure(self, error: Exception) -> None:
        """Use the isolated emergency path without record payloads.

        Args:
            error: The exception raised by a processor or driver.
        """
        try:
            self._emergency.report_failure(
                self.name,
                type(error).__name__,
            )
        except OSError:
            # No second destination is available if standard error itself
            # failed; the original typed delivery error remains authoritative.
            return
