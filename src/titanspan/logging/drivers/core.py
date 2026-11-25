"""Provide in-memory, discard, and emergency logging destinations.

These small drivers are useful in tests, disabled logging configurations, and
fallback paths where the primary output has failed.
"""

import sys
from collections import deque
from threading import Lock
from typing import TextIO

from titanspan.logging.exceptions import (
    LogConfigurationError,
    LogLifecycleError,
)
from titanspan.logging.record import LogRecord


class MemoryLogDriver:
    """Capture a bounded sequence of records for tests and local tooling.

    Attributes:
        records: A stable snapshot of currently retained records.
        closed: Whether this driver has been finalized.

    The driver retains at most ``max_records`` entries and is safe for
    concurrent writes from application threads.
    """

    def __init__(self, max_records: int = 1000) -> None:
        """Create a bounded in-memory sink.

        Args:
            max_records: Maximum number of records retained.

        Raises:
            ValueError: If the record capacity is less than one.
        """
        if max_records < 1:
            msg = "Memory log capacity must be at least one"
            raise LogConfigurationError(
                msg,
            )
        self._records: deque[LogRecord] = deque(maxlen=max_records)
        self._lock = Lock()
        self._closed = False

    @property
    def records(self) -> tuple[LogRecord, ...]:
        """Return a snapshot of retained records.

        Returns:
            Records in delivery order, oldest first.
        """
        with self._lock:
            return tuple(self._records)

    @property
    def closed(self) -> bool:
        """Return whether the driver has been closed.

        Returns:
            ``True`` after the first successful close.
        """
        return self._closed

    def write(self, record: LogRecord) -> None:
        """Append a record, evicting the oldest entry at capacity.

        Args:
            record: A sanitized native log record.

        Raises:
            RuntimeError: If the driver has already been closed.
        """
        with self._lock:
            if self._closed:
                msg = "The memory log driver is closed"
                raise LogLifecycleError(msg)
            self._records.append(record)

    def flush(self) -> None:
        """Complete immediately because no external buffer is used.

        Raises:
            LogLifecycleError: If the in-memory driver is already closed.
        """
        if self._closed:
            msg = "The memory log driver is closed"
            raise LogLifecycleError(msg)

    def close(self) -> None:
        """Mark the driver closed without clearing retained test records.

        Repeated calls remain safe for manager shutdown and fixture cleanup.
        """
        with self._lock:
            self._closed = True


class NullLogDriver:
    """Discard records for explicitly disabled logging channels.

    This driver intentionally accepts every record and owns no resources.
    """

    def write(self, record: LogRecord) -> None:
        """Discard a record.

        Args:
            record: The record to intentionally discard.
        """
        del record

    def flush(self) -> None:
        """Complete immediately because the driver retains no state.

        No destination or buffered data needs to be finalized.
        """

    def close(self) -> None:
        """Complete immediately because the driver owns no resources.

        The null destination remains safe to call after manager shutdown.
        """


class EmergencyLogDriver:
    """Write a sanitized fallback message directly to standard error.

    The fallback deliberately avoids the configured logging manager and its
    handlers so it remains usable after channel initialization or delivery
    failures.
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        """Create a fallback writer.

        Args:
            stream: A text stream, defaulting to the current standard error.
        """
        self._stream = stream or sys.stderr
        self._lock = Lock()

    def write(self, record: LogRecord) -> None:
        """Write a minimal JSON-safe diagnostic line.

        Args:
            record: A record already normalized and redacted by Titanspan.

        Raises:
            OSError: If the fallback stream itself cannot accept output.
        """
        line = (
            f"TITANSPAN EMERGENCY [{record.channel}] "
            f"{record.level.value}: {record.message}\n"
        )
        with self._lock:
            self._stream.write(line)
            self._stream.flush()

    def report_failure(self, channel: str, error_type: str) -> None:
        """Report a failed destination without including payload data.

        Args:
            channel: The destination whose delivery failed.
            error_type: Exception class name for actionable diagnostics.
        """
        with self._lock:
            self._stream.write(
                f"TITANSPAN LOGGING FAILURE [{channel}]: {error_type}\n",
            )
            self._stream.flush()

    def flush(self) -> None:
        """Flush fallback output to its owned standard-error stream.

        Raises:
            OSError: If the fallback stream cannot be flushed.
        """
        with self._lock:
            self._stream.flush()

    def close(self) -> None:
        """Leave process-owned standard error open.

        The emergency writer does not own the process stream lifecycle.
        """
