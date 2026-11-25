"""Expose an owned handle for standard-library log interoperability.

The bridge contains no standard-library logger or handler object in its
public interface; implementation details remain in the private backend.
"""

from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class StandardLogBridge:
    """Own one explicit connection from a standard logger to a channel.

    Use :meth:`close` to detach only the bridge-owned handler. Existing
    handlers, thresholds, and propagation settings belong to the application
    and remain unchanged.
    """

    def __init__(
        self,
        logger_name: str,
        channel_name: str,
        close_callback: Callable[[], None],
    ) -> None:
        """Create the native handle for a configured logging bridge.

        Args:
            logger_name: Selected standard-library logger name.
            channel_name: Titanspan destination receiving converted records.
            close_callback: Private backend cleanup operation.
        """
        self.logger_name = logger_name
        self.channel_name = channel_name
        self._close_callback = close_callback
        self._closed = False
        self._lock = Lock()

    @property
    def closed(self) -> bool:
        """Return whether the bridge has detached its handler.

        Returns:
            ``True`` after the first successful close operation.
        """
        with self._lock:
            return self._closed

    def close(self) -> None:
        """Detach the selected bridge handler exactly once.

        The callback only removes a handler installed by this bridge and
        never changes logger settings or application-owned handlers.
        """
        with self._lock:
            if self._closed:
                return
            self._close_callback()
            self._closed = True

    def __enter__(self) -> StandardLogBridge:
        """Return this active bridge for context-managed cleanup.

        Returns:
            The bridge handle.
        """
        if self.closed:
            message = "A closed standard logging bridge cannot be re-entered"
            raise RuntimeError(message)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        """Detach the bridge when its ownership scope exits.

        Args:
            exc_type: Exception type raised in the scope, if any.
            exc_value: Exception instance raised in the scope, if any.
            traceback: Traceback object associated with the exception.
        """
        del exc_type, exc_value, traceback
        self.close()
