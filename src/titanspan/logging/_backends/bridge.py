"""Bridge selected standard-library loggers to native Titanspan channels.

Only explicit manager calls create these handlers. The adapter does not
configure root loggers or replace process-wide logging factories.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from titanspan.logging.exceptions import LogBackendError
from titanspan.logging.level import from_python_level
from titanspan.logging.record import LogRecord

if TYPE_CHECKING:
    from collections.abc import Callable

    from titanspan.logging.channel import LogChannel

_ACTIVE_CHANNELS: ContextVar[frozenset[int]] = ContextVar(
    "titanspan_bridged_channel_ids",
    default=frozenset(),
)
_BRIDGED_CHANNELS_ATTRIBUTE = "_titanspan_bridged_channel_ids"


class _BridgeHandler(logging.Handler):
    """Convert standard records and route them to one native channel.

    A recursion guard and per-record marker prevent duplicate capture while
    preserving other standard-library handlers attached to the logger.
    """

    def __init__(
        self,
        channel: LogChannel,
        on_failure: Callable[[str, str], None],
    ) -> None:
        """Create a handler without changing global logging configuration.

        Args:
            channel: Native channel receiving converted records.
            on_failure: Sanitized fallback reporter for bridge errors.
        """
        super().__init__(logging.NOTSET)
        self._channel = channel
        self._on_failure = on_failure
        self._channel_id = id(channel)

    def emit(self, record: logging.LogRecord) -> None:
        """Convert one selected record and prevent recursive capture.

        Args:
            record: A record produced by the selected standard logger.

        Notes:
            Some applications attach bridges to both parent and child logger
            names. A record marker prevents duplicate routing to this channel.
        """
        active = _ACTIVE_CHANNELS.get()
        if self._channel_id in active:
            return
        routed = record.__dict__.get(_BRIDGED_CHANNELS_ATTRIBUTE)
        routed_ids: tuple[int, ...] = ()
        if isinstance(routed, tuple):
            candidate = cast("tuple[object, ...]", routed)
            routed_ids = tuple(item for item in candidate if type(item) is int)
        if self._channel_id in routed_ids:
            return
        record.__dict__[_BRIDGED_CHANNELS_ATTRIBUTE] = (
            *routed_ids,
            self._channel_id,
        )
        token = _ACTIVE_CHANNELS.set(active | {self._channel_id})
        try:
            self._channel.write(_convert_record(record, self._channel.name))
        except Exception as error:
            with suppress(OSError):
                self._on_failure(self._channel.name, type(error).__name__)
        finally:
            _ACTIVE_CHANNELS.reset(token)


class StandardLibraryBridgeBackend:
    """Own one handler attached to a specifically requested logger.

    Existing thresholds, handlers, and propagation flags remain application
    owned and are never changed by this adapter.
    """

    def __init__(
        self,
        logger_name: str,
        channel: LogChannel,
        on_failure: Callable[[str, str], None],
    ) -> None:
        """Attach a handler while preserving all existing logger settings.

        Args:
            logger_name: Name selected by the application.
            channel: Titanspan channel receiving converted records.
            on_failure: Fallback callback that does not log recursively.
        """
        if not logger_name or logger_name != logger_name.strip():
            message = "A standard logger name must be non-empty"
            raise LogBackendError(message)
        self._logger = logging.getLogger(logger_name)
        self._handler = _BridgeHandler(channel, on_failure)
        self._closed = False
        self._logger.addHandler(self._handler)

    def close(self) -> None:
        """Remove and close only the handler owned by this backend.

        The operation is idempotent and leaves all neighboring handlers
        attached to the source logger.
        """
        if self._closed:
            return
        self._logger.removeHandler(self._handler)
        self._handler.close()
        self._closed = True


def _convert_record(
    source: logging.LogRecord,
    channel: str,
) -> LogRecord:
    """Convert a standard record into a bounded native record.

    Args:
        source: The selected third-party or standard-library event.
        channel: Titanspan channel that receives the new record.

    Returns:
        A sanitized native record retaining source time and exception type.

    Raises:
        Exception: If the source message cannot be formatted safely.
    """
    exception: BaseException | None = None
    if source.exc_info is not None:
        candidate = source.exc_info[1]
        if isinstance(candidate, BaseException):
            exception = candidate
    context: dict[str, object] = {
        "source_logger": source.name,
        "source_module": source.module,
        "source_function": source.funcName,
        "source_line": source.lineno,
    }
    converted = LogRecord.create(
        level=from_python_level(source.levelno),
        channel=channel,
        message=source.getMessage(),
        context=context,
        exception=exception,
    )
    return LogRecord(
        timestamp=datetime.fromtimestamp(source.created, UTC),
        level=converted.level,
        channel=converted.channel,
        message=converted.message,
        context=converted.context,
        exception=converted.exception,
    )
