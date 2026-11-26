"""Bridge native records through Structlog and an isolated stdlib logger.

The adapter uses no process-wide configuration. Its private logger dispatches
only to a Titanspan-owned handler and does not propagate to the root logger.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextvars import ContextVar
from uuid import uuid4

import structlog
from structlog.stdlib import BoundLogger, render_to_log_kwargs

from titanspan.contracts.logging import DeliveryStatus
from titanspan.logging.exceptions import LogBackendError, LogLifecycleError
from titanspan.logging.level import to_python_level
from titanspan.logging.record import LogRecord

RecordCallback = Callable[[LogRecord], DeliveryStatus | None]
_DISPATCHING: ContextVar[tuple[int, ...]] = ContextVar(
    "titanspan_logging_dispatching",
    default=(),
)
_DELIVERY_RESULT: ContextVar[DeliveryStatus | None] = ContextVar(
    "titanspan_log_delivery_result",
    default=None,
)


class _DispatchHandler(logging.Handler):
    """Forward only private structured payloads to a native callback.

    Do not forward arbitrary records from the process root logger. The
    handler is attached to a private, non-propagating logger only.
    """

    def __init__(self, callback: RecordCallback) -> None:
        """Create a handler for one channel's native delivery callback.

        Args:
            callback: The channel callback receiving a Titanspan record.
        """
        super().__init__(logging.NOTSET)
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        """Forward a Titanspan record carried through Structlog.

        Args:
            record: A standard record created by the private adapter.

        Raises:
            TypeError: If the adapter did not provide a native record.
        """
        candidate = record.__dict__.get("titanspan_record")
        if not isinstance(candidate, LogRecord):
            msg = "Structured backend omitted the native record"
            raise LogBackendError(
                msg,
            )
        _DELIVERY_RESULT.set(self._callback(candidate))


class StructuredBackend:
    """Dispatch native records using a private Structlog wrapper.

    The adapter turns the record into a structured event and sends it through
    Python logging to one private handler. It does not alter global factories,
    handlers, level names, or root logger configuration.
    """

    def __init__(self, callback: RecordCallback) -> None:
        """Create an isolated structured logger for one channel.

        Args:
            callback: A Titanspan callback that owns final delivery.
        """
        self._handler = _DispatchHandler(callback)
        # ``getLogger`` registers names globally; an isolated instance avoids
        # adding process-wide logging state for a local Titanspan channel.
        self._logger = logging.Logger(  # noqa: LOG001
            f"titanspan.private.{uuid4().hex}",
            level=logging.NOTSET,
        )
        self._logger.propagate = False
        self._logger.addHandler(self._handler)
        self._bound: BoundLogger = structlog.wrap_logger(
            self._logger,
            processors=[render_to_log_kwargs],
            wrapper_class=BoundLogger,
        )
        self._closed = False

    def write(self, record: LogRecord) -> DeliveryStatus | None:
        """Dispatch a record without exposing backend types to callers.

        Args:
            record: The sanitized native record to deliver.

        Raises:
            RuntimeError: If backend delivery recursively re-enters itself.
        """
        if self._closed:
            msg = "The structured backend is closed"
            raise LogLifecycleError(msg)
        active = _DISPATCHING.get()
        if id(self) in active:
            msg = "Recursive log delivery was prevented"
            raise LogBackendError(msg)
        token = _DISPATCHING.set((*active, id(self)))
        result_token = _DELIVERY_RESULT.set(None)
        try:
            self._bound.bind(
                titanspan_record=record,
                channel=record.channel,
                context=dict(record.context),
                level=record.level.value,
            ).log(to_python_level(record.level), record.message)
            return _DELIVERY_RESULT.get()
        finally:
            _DELIVERY_RESULT.reset(result_token)
            _DISPATCHING.reset(token)

    def close(self) -> None:
        """Detach and close the private dispatch handler once.

        The logger is isolated and never removes handlers owned by other
        application code.
        """
        if self._closed:
            return
        self._logger.removeHandler(self._handler)
        self._handler.close()
        self._closed = True
