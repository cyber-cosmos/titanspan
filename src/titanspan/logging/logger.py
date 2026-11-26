"""Expose expressive synchronous and asynchronous native log methods.

Logger instances merge manager execution context with immutable logger-bound
context before constructing a sanitized record.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from titanspan.logging.exceptions import (
    InvalidLogContextError,
    LogLifecycleError,
)
from titanspan.logging.level import LogLevel
from titanspan.logging.record import LogRecord

if TYPE_CHECKING:
    from types import TracebackType

    from titanspan.logging.channel import LogChannel
    from titanspan.logging.events import MessageLogged

ContextProvider = Callable[[], Mapping[str, object]]


class Logger:
    """Write structured events to one Titanspan channel.

    Attributes:
        channel: The native channel receiving this logger's records.

    ``with_context`` returns a bound logger instead of mutating a shared
    instance, which keeps concurrent request and workflow calls isolated.
    """

    def __init__(
        self,
        channel: LogChannel,
        *,
        context_provider: ContextProvider | None = None,
        context: Mapping[str, object] | None = None,
        owns_channel: bool = False,
    ) -> None:
        """Bind a logger to a channel and optional execution context.

        Args:
            channel: The destination channel owned by a manager or build call.
            context_provider: Returns context active for the current task.
            context: Immutable-by-convention values bound to this logger.
            owns_channel: Whether this logger owns an on-demand channel.
        """
        self.channel = channel
        self._context_provider = context_provider or _empty_context
        self._context = dict(context or {})
        self._owns_channel = owns_channel

    def log(
        self,
        level: LogLevel | str | int,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a record at the selected RFC severity.

        Args:
            level: A native level, case-insensitive name, or RFC number.
            message: The message to write.
            context: Optional positional structured context mapping.
            **values: Keyword context values, overriding mapping values.

        Raises:
            ValueError: If the log level or context is invalid.
            LogDeliveryError: If the configured output cannot accept a record.
        """
        parsed = LogLevel.parse(level)
        if not self.channel.is_enabled(parsed):
            return
        record = self._make_record(parsed, message, context, values)
        self.channel.write(record)

    def emergency(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a system-unavailable emergency event.

        Args:
            message: The emergency message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.log(LogLevel.EMERGENCY, message, context, **values)

    def alert(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an alert that requires immediate intervention.

        Args:
            message: The alert message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.log(LogLevel.ALERT, message, context, **values)

    def critical(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a critical event for a failed application component.

        Args:
            message: The critical message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.log(LogLevel.CRITICAL, message, context, **values)

    def error(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an error event.

        Args:
            message: The error message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.log(LogLevel.ERROR, message, context, **values)

    def warning(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a warning about an unexpected but recoverable condition.

        Args:
            message: The warning message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.log(LogLevel.WARNING, message, context, **values)

    def notice(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a normal but significant application event.

        Args:
            message: The notice message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.log(LogLevel.NOTICE, message, context, **values)

    def info(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an informational event.

        Args:
            message: The informational message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.log(LogLevel.INFO, message, context, **values)

    def debug(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a diagnostic event intended for development analysis.

        Args:
            message: The diagnostic message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.log(LogLevel.DEBUG, message, context, **values)

    def exception(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an error event with the active or supplied exception.

        Args:
            message: The failure message.
            context: Optional structured context mapping.
            **values: Structured values, optionally including ``exception``.

        Raises:
            TypeError: If ``exception`` is not a BaseException instance.
        """
        if "exception" not in values:
            active_exception = sys.exception()
            if active_exception is not None:
                values["exception"] = active_exception
        self.log(LogLevel.ERROR, message, context, **values)

    def flush(self) -> None:
        """Flush the destination currently owned by this channel.

        Raises:
            LogDeliveryError: If the destination cannot be flushed.
        """
        self.channel.flush()

    def listen(self, callback: Callable[[MessageLogged], None]) -> None:
        """Subscribe to successful native delivery on this channel.

        Args:
            callback: Synchronous function receiving a redacted event.

        Raises:
            LogLifecycleError: If the channel is already closed.
        """
        if self.channel.closed:
            message = "Cannot subscribe to a closed log channel"
            raise LogLifecycleError(message)
        self.channel.listen(callback)

    async def log_async(
        self,
        level: LogLevel | str | int,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a record without blocking the caller's event loop.

        Native async drivers may await bounded capacity. Synchronous drivers
        are dispatched through AnyIO's worker pool; cancellation is delayed
        until a synchronous write completes because threads cannot be safely
        interrupted mid-delivery.

        Args:
            level: A native level, case-insensitive name, or RFC number.
            message: The message to write.
            context: Optional positional structured context mapping.
            **values: Additional structured context values.
        """
        parsed = LogLevel.parse(level)
        if not self.channel.is_enabled(parsed):
            return
        record = self._make_record(parsed, message, context, values)
        await self.channel.write_async(record)

    async def emergency_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Asynchronously write an emergency message.

        Args:
            message: The emergency message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        await self.log_async(
            LogLevel.EMERGENCY,
            message,
            context,
            **values,
        )

    async def alert_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Asynchronously write an alert message.

        Args:
            message: The alert message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        await self.log_async(LogLevel.ALERT, message, context, **values)

    async def critical_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Asynchronously write a critical message.

        Args:
            message: The critical message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        await self.log_async(LogLevel.CRITICAL, message, context, **values)

    async def error_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Asynchronously write an error message.

        Args:
            message: The error message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        await self.log_async(LogLevel.ERROR, message, context, **values)

    async def warning_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Asynchronously write a warning message.

        Args:
            message: The warning message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        await self.log_async(LogLevel.WARNING, message, context, **values)

    async def notice_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Asynchronously write a notice message.

        Args:
            message: The notice message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        await self.log_async(LogLevel.NOTICE, message, context, **values)

    async def info_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Asynchronously write an informational message.

        Args:
            message: The informational message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        await self.log_async(LogLevel.INFO, message, context, **values)

    async def debug_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Asynchronously write a diagnostic message.

        Args:
            message: The diagnostic message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        await self.log_async(LogLevel.DEBUG, message, context, **values)

    async def exception_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an error with the active or explicitly supplied exception.

        Args:
            message: A concise description of the failure.
            context: Optional structured failure metadata.
            **values: Additional fields, including an optional exception.

        Raises:
            InvalidLogContextError: If the exception value is not an error.
        """
        if "exception" not in values:
            active_exception = sys.exception()
            if active_exception is not None:
                values["exception"] = active_exception
        await self.log_async(LogLevel.ERROR, message, context, **values)

    def with_context(
        self,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> Logger:
        """Return a logger bound to additional immutable-by-convention values.

        Args:
            context: Optional mapping of values bound to the new logger.
            **values: Additional values that override mapping keys.

        Returns:
            A new logger sharing the channel and context provider.
        """
        merged = dict(self._context)
        if context is not None:
            merged.update(context)
        merged.update(values)
        return Logger(
            self.channel,
            context_provider=self._context_provider,
            context=merged,
            owns_channel=self._owns_channel,
        )

    def without_context(self, *keys: str) -> Logger:
        """Return a new logger with selected bound values removed.

        Args:
            *keys: Bound values to remove; no keys clears all bound values.

        Returns:
            A logger sharing this channel and execution context provider.
        """
        removed = set(keys)
        remaining = {
            key: value
            for key, value in self._context.items()
            if key not in removed
        }
        return Logger(
            self.channel,
            context_provider=self._context_provider,
            context=remaining,
            owns_channel=self._owns_channel,
        )

    def _make_record(
        self,
        level: LogLevel,
        message: str,
        context: Mapping[str, object] | None,
        values: Mapping[str, object],
    ) -> LogRecord:
        """Combine active and per-call values into a safe record.

        Args:
            level: The parsed RFC severity.
            message: The application message.
            context: Positional structured values.
            values: Keyword structured values.

        Returns:
            A copied and redacted native log record.

        Raises:
            InvalidLogContextError: If context or exception values are invalid.
        """
        combined: dict[str, object] = dict(self._context_provider())
        combined.update(self._context)
        if context is not None:
            combined.update(context)
        combined.update(values)
        exception_value = combined.pop("exception", None)
        if exception_value is not None and not isinstance(
            exception_value,
            BaseException,
        ):
            msg = "The exception context value must be an exception"
            raise InvalidLogContextError(
                msg,
            )
        exception = (
            exception_value
            if isinstance(exception_value, BaseException)
            else None
        )
        return LogRecord.create(
            level=level,
            channel=self.channel.name,
            message=message,
            context=combined,
            exception=exception,
        )

    def __enter__(self) -> Logger:
        """Enter the lifecycle scope for an on-demand built logger.

        Returns:
            This logger when it owns a dynamically built channel.

        Raises:
            LogLifecycleError: If the logger references a manager-owned channel.
        """
        if not self._owns_channel:
            msg = "Only on-demand loggers own their channels"
            raise LogLifecycleError(
                msg,
            )
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close an on-demand channel when its context manager exits.

        Raises:
            LogLifecycleError: If the logger does not own the shared channel.
        """
        del exception_type, exception, traceback
        if not self._owns_channel:
            msg = "Only on-demand loggers own their channels"
            raise LogLifecycleError(
                msg,
            )
        self.channel.close()


def _empty_context() -> Mapping[str, object]:
    """Return an empty context for standalone native logger instances.

    Returns:
        An immutable empty mapping.
    """
    return {}
