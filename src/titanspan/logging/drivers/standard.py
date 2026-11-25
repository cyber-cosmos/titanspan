"""Implement stream and file channels with standard logging handlers.

Python's handlers own stream synchronization, file I/O, rotation, and cleanup.
Titanspan supplies the native formatter and lifecycle wrapper.
"""

import calendar
import logging
import logging.handlers
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO, override

from titanspan.logging._backends.standard import StandardHandlerBackend
from titanspan.logging.contracts.log_formatter import LogFormatter
from titanspan.logging.record import LogRecord

_MONTH_SUFFIX = re.compile(r"^\d{4}-\d{2}$", re.ASCII)
_FIRST_MONTH = 1
_LAST_MONTH = 12


class _MonthlyRotatingFileHandler(
    logging.handlers.TimedRotatingFileHandler,
):
    """Rotate a standard file handler on UTC calendar-month boundaries.

    The standard handler continues to own file opening, rollover, and
    retention. This subclass changes only the next rollover timestamp and
    archive suffix because the standard handler has no monthly interval.
    """

    def __init__(
        self,
        filename: str | Path,
        backup_count: int,
    ) -> None:
        """Create a delayed file handler with calendar-month archives.

        Args:
            filename: Active log path owned by this handler.
            backup_count: Number of old monthly archives to retain.
        """
        super().__init__(
            filename,
            when="midnight",
            interval=1,
            backupCount=backup_count,
            encoding="utf-8",
            delay=True,
            utc=True,
        )
        self.suffix = "%Y-%m"
        self.extMatch = _MONTH_SUFFIX

    @override
    def computeRollover(self, currentTime: int) -> int:
        """Return the next UTC calendar-month boundary.

        Args:
            currentTime: Current Unix timestamp supplied by the handler.

        Returns:
            Unix timestamp for midnight at the start of the next month.
        """
        return next_monthly_rollover_timestamp(currentTime)


def next_monthly_rollover_timestamp(current_time: int) -> int:
    """Calculate the next UTC calendar-month boundary.

    Args:
        current_time: Current Unix timestamp.

    Returns:
        Unix timestamp for midnight at the start of the next month.
    """
    current = datetime.fromtimestamp(current_time, UTC)
    # Calendar months vary in length, so a fixed-second interval would drift
    # and mislabel retained archives.
    if current.month == _LAST_MONTH:
        next_year = current.year + 1
        next_month = _FIRST_MONTH
    else:
        next_year = current.year
        next_month = current.month + 1
    boundary = datetime(
        next_year,
        next_month,
        _FIRST_MONTH,
        tzinfo=UTC,
    )
    return calendar.timegm(boundary.utctimetuple())


class _TitanspanSyslogHandler(logging.handlers.SysLogHandler):
    """Map Titanspan severity names to exact syslog priority names.

    Python's default handler maps unknown names to ``warning``. Preserving the
    original native level name lets the override distinguish adjacent RFC
    severities without registering process-global logging levels.
    """

    @override
    def mapPriority(
        self,
        levelName: str,
    ) -> str:
        """Return the RFC syslog priority represented by a native level.

        Args:
            levelName: Titanspan's lowercase level stored on the record.

        Returns:
            A syslog priority name understood by the standard handler.
        """
        priorities = {
            "emergency": "emerg",
            "alert": "alert",
            "critical": "crit",
            "error": "err",
            "warning": "warning",
            "notice": "notice",
            "info": "info",
            "debug": "debug",
        }
        priority = priorities.get(levelName.casefold())
        if priority is not None:
            return priority
        return super().mapPriority(levelName)


class StandardHandlerLogDriver:
    """Wrap an owned standard-library handler behind a native driver.

    The wrapped handler remains private. Callers interact only with the
    Titanspan ``LogDriver`` contract.
    """

    def __init__(
        self,
        handler: logging.Handler,
        formatter: LogFormatter,
    ) -> None:
        """Create a destination adapter.

        Args:
            handler: The standard handler owned by this channel.
            formatter: The Titanspan output formatter.
        """
        self._backend = StandardHandlerBackend(handler, formatter)

    def write(self, record: LogRecord) -> None:
        """Deliver one record through the configured handler.

        Args:
            record: The normalized record to format and deliver.
        """
        self._backend.write(record)

    def flush(self) -> None:
        """Flush the destination handler.

        The standard handler reports stream and file flush failures.
        """
        self._backend.flush()

    def close(self) -> None:
        """Close the handler and resources owned by the channel.

        Process-owned stdout and stderr remain open after handler shutdown.
        """
        self._backend.close()


def create_console_driver(
    formatter: LogFormatter,
    *,
    stream: TextIO,
) -> StandardHandlerLogDriver:
    """Create a line-buffered stream driver.

    Args:
        formatter: Native formatter selected for the channel.
        stream: Standard output, standard error, or another text stream.

    Returns:
        A Titanspan driver backed by ``logging.StreamHandler``.
    """
    return StandardHandlerLogDriver(logging.StreamHandler(stream), formatter)


def create_single_file_driver(
    formatter: LogFormatter,
    path: Path,
) -> StandardHandlerLogDriver:
    """Create a single append-only file driver.

    Args:
        formatter: Native formatter selected for the channel.
        path: File path owned by this destination.

    Returns:
        A driver backed by ``logging.FileHandler``.
    """
    _prepare_path(path)
    handler = logging.FileHandler(
        path,
        mode="a",
        encoding="utf-8",
        delay=True,
    )
    return StandardHandlerLogDriver(handler, formatter)


def create_daily_file_driver(
    formatter: LogFormatter,
    path: Path,
    days: int,
) -> StandardHandlerLogDriver:
    """Create a UTC midnight-rotating file driver with retention.

    Args:
        formatter: Native formatter selected for the channel.
        path: Base path for the active log file.
        days: Number of rotated files to retain.

    Returns:
        A driver backed by ``TimedRotatingFileHandler``.
    """
    _prepare_path(path)
    handler = logging.handlers.TimedRotatingFileHandler(
        path,
        when="midnight",
        interval=1,
        backupCount=days,
        encoding="utf-8",
        delay=True,
        utc=True,
    )
    return StandardHandlerLogDriver(handler, formatter)


def create_monthly_file_driver(
    formatter: LogFormatter,
    path: Path,
    max_files: int,
) -> StandardHandlerLogDriver:
    """Create a UTC calendar-month rotating file driver.

    Args:
        formatter: Native formatter selected for the channel.
        path: Base path for the active log file.
        max_files: Number of rotated monthly files to retain.

    Returns:
        A driver backed by the standard timed file handler.
    """
    _prepare_path(path)
    handler = _MonthlyRotatingFileHandler(
        path,
        backup_count=max_files,
    )
    return StandardHandlerLogDriver(handler, formatter)


def create_rotating_file_driver(
    formatter: LogFormatter,
    path: Path,
    max_bytes: int,
    backup_count: int,
) -> StandardHandlerLogDriver:
    """Create a size-limited rotating file driver.

    Args:
        formatter: Native formatter selected for the channel.
        path: Base path for the active log file.
        max_bytes: Maximum active file size before rotation.
        backup_count: Number of rotated files to retain.

    Returns:
        A driver backed by ``RotatingFileHandler``.
    """
    _prepare_path(path)
    handler = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
        delay=True,
    )
    return StandardHandlerLogDriver(handler, formatter)


def create_syslog_driver(
    formatter: LogFormatter,
    address: str | tuple[str, int],
) -> StandardHandlerLogDriver:
    """Create a syslog driver using the platform handler implementation.

    Args:
        formatter: Native formatter selected for the channel.
        address: Unix socket path or network host and port.

    Returns:
        A driver backed by ``SysLogHandler``.

    Raises:
        OSError: If the configured syslog destination cannot be opened.
    """
    handler = _TitanspanSyslogHandler(address=address)
    return StandardHandlerLogDriver(handler, formatter)


def _prepare_path(path: Path) -> None:
    """Create the configured parent directory without deleting existing data.

    Args:
        path: The configured destination path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
