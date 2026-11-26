"""Define the application-facing structured logger contract.

The protocol exposes typed synchronous and asynchronous writes while keeping
third-party logger and handler representations behind private adapters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping
    from types import TracebackType


@runtime_checkable
class LogWriter(Protocol):
    """Write structured messages without exposing a logging backend.

    The contract requires the ordinary synchronous and asynchronous write
    operations. Channel-specific convenience methods remain available on the
    concrete native logger returned by the logging component.
    """

    def __enter__(self) -> LogWriter:
        """Enter an independently owned logger lifecycle when supported.

        Returns:
            This logger for use in a ``with`` statement.
        """
        ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release an independently owned logger after a context scope.

        Args:
            exception_type: Active exception class, if any.
            exception: Active exception, if any.
            traceback: Active traceback, if any.
        """
        ...

    def log(
        self,
        level: str | int,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Deliver one structured message to the selected channel.

        Args:
            level: Native severity name or numeric value.
            message: Human-readable event description.
            context: Optional structured field mapping.
            **values: Additional structured fields.
        """
        ...

    async def log_async(
        self,
        level: str | int,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Deliver one structured message through an asynchronous sink.

        Args:
            level: Native severity name or numeric value.
            message: Human-readable event description.
            context: Optional structured field mapping.
            **values: Additional structured fields.
        """
        ...

    def exception(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Log diagnostic information for an exception.

        Args:
            message: Human-readable failure description.
            context: Optional structured field mapping.
            **values: Additional fields, including an optional exception.
        """
        ...

    async def exception_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Log exception information through an asynchronous sink.

        Args:
            message: Human-readable failure description.
            context: Optional structured field mapping.
            **values: Additional fields, including an optional exception.
        """
        ...

    def emergency(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a message for an unavailable system component.

        Args:
            message: Human-readable emergency description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    def alert(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a message requiring immediate intervention.

        Args:
            message: Human-readable alert description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    def critical(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a message for a critical application failure.

        Args:
            message: Human-readable failure description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    def error(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an application error message.

        Args:
            message: Human-readable error description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    def warning(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a recoverable warning message.

        Args:
            message: Human-readable warning description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    def notice(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a significant normal-operation message.

        Args:
            message: Human-readable notice description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    def info(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an informational message.

        Args:
            message: Human-readable activity description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    def debug(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a diagnostic message.

        Args:
            message: Human-readable diagnostic description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    async def emergency_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an emergency message through an asynchronous sink.

        Args:
            message: Human-readable emergency description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    async def alert_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an alert through an asynchronous sink.

        Args:
            message: Human-readable alert description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    async def critical_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a critical message through an asynchronous sink.

        Args:
            message: Human-readable failure description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    async def error_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an error through an asynchronous sink.

        Args:
            message: Human-readable error description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    async def warning_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a warning through an asynchronous sink.

        Args:
            message: Human-readable warning description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    async def notice_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a notice through an asynchronous sink.

        Args:
            message: Human-readable notice description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    async def info_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write information through an asynchronous sink.

        Args:
            message: Human-readable activity description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...

    async def debug_async(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write diagnostics through an asynchronous sink.

        Args:
            message: Human-readable diagnostic description.
            context: Optional structured field mapping.
            **values: Structured fields attached to the message.
        """
        ...


__all__ = ["LogWriter"]
