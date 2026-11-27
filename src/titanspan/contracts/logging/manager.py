"""Define the shared logging service used by facades and application code.

The manager owns channel creation, context propagation, bridge ownership,
and coordinated finalization for one application.
"""

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

from titanspan.contracts.logging.bridge import LogBridge
from titanspan.contracts.logging.logger import LogWriter


@runtime_checkable
class LoggingManager(Protocol):
    """Resolve channels and manage shared logging context and resources.

    The contract contains no backend logger or handler types. Configuration
    metadata is intentionally opaque here; channel construction and validation
    belong to the owning logging component.
    """

    @property
    def configuration(self) -> object:
        """Return implementation-owned native logging configuration data.

        Returns:
            Configuration metadata used by the logging service itself.
        """
        ...

    def channel(self, name: str | None = None) -> LogWriter:
        """Resolve a configured channel by name.

        Args:
            name: Optional configured channel name.

        Returns:
            A native structured logger.
        """
        ...

    def emergency(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a safe emergency record through the fallback destination.

        Implementations keep this operation available after normal channel
        resources close.

        Args:
            message: Bounded diagnostic text without sensitive payloads.
            context: Optional structured context mapping.
            **values: Additional structured values.
        """
        ...

    def build(self, configuration: Mapping[str, object]) -> LogWriter:
        """Create a logger from an independent native configuration.

        Args:
            configuration: Titanspan-owned channel settings.

        Returns:
            A logger with an independently owned destination.
        """
        ...

    def stack(
        self,
        channels: list[str] | tuple[str, ...],
        *,
        channel: str | None = None,
        ignore_exceptions: bool = False,
    ) -> LogWriter:
        """Create an ordered logger that writes to several channels.

        Args:
            channels: Configured destinations in delivery order.
            channel: Optional name attached to stack records.
            ignore_exceptions: Whether later channels run after a failure.

        Returns:
            A native logger backed by the selected destinations.
        """
        ...

    def bridge_standard_logger(
        self,
        logger_name: str,
        channel: str | None = None,
    ) -> LogBridge:
        """Attach one explicitly selected Python logger to a channel.

        Args:
            logger_name: Standard logger name selected by the application.
            channel: Optional Titanspan destination name.

        Returns:
            A native bridge handle whose lifecycle is owned by this manager.
        """
        ...

    def get_default_channel(self) -> str:
        """Return the currently selected default channel name.

        Returns:
            The configured channel used by ordinary facade operations.
        """
        ...

    def set_default_channel(self, name: str) -> None:
        """Select a declared channel as the manager default.

        Args:
            name: Existing channel name.
        """
        ...

    def extend(
        self,
        name: str,
        factory: Callable[..., object],
    ) -> None:
        """Register an application-defined native driver factory.

        Args:
            name: New driver identifier.
            factory: Callable adapted by the logging component.
        """
        ...

    def flush(self) -> None:
        """Flush resolved channel buffers before continuing.

        The operation may wait for the configured synchronous drivers.
        """
        ...

    async def flush_async(self) -> None:
        """Flush channel buffers without blocking the event loop.

        The operation propagates delivery failures from managed channels.
        """
        ...

    def close(self) -> None:
        """Finalize synchronously owned destinations.

        The operation is idempotent and prevents later channel use.
        """
        ...

    async def aclose(self) -> None:
        """Finalize logging resources through an asynchronous boundary.

        Pending managed deliveries are flushed before destination cleanup.
        """
        ...

    def with_context(
        self,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Merge values into context local to the current execution.

        Args:
            context: Optional initial context mapping.
            **values: Additional values overriding matching keys.
        """
        ...

    def share_context(
        self,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Merge values visible to all channels in the current execution.

        Args:
            context: Optional initial context mapping.
            **values: Additional values overriding matching keys.
        """
        ...

    def context(self, **values: object) -> AbstractContextManager[None]:
        """Temporarily bind values and restore them when the scope exits.

        Args:
            **values: Context entries visible inside the scope.

        Returns:
            A synchronous context manager restoring prior values.
        """
        ...

    def without_context(
        self,
        keys: str | Sequence[str] | None = None,
        *additional: str,
    ) -> None:
        """Remove selected values from current and shared context.

        Args:
            keys: One or more keys, or ``None`` to remove all values.
            *additional: Additional keys to remove.
        """
        ...

    def flush_context(self) -> None:
        """Clear local and shared context in the current execution.

        Other task-local execution contexts retain their own values.
        """
        ...

    def flush_shared_context(self) -> None:
        """Clear context shared by channels in the current execution.

        The operation does not alter logger-bound or message-local fields.
        """
        ...

    def get_context(self) -> dict[str, object]:
        """Return a detached snapshot of the merged execution context.

        Returns:
            The current context values without exposing internal storage.
        """
        ...

    def shared_context(self) -> dict[str, object]:
        """Return a detached snapshot of shared execution metadata.

        Returns:
            The shared values visible to channels in this execution.
        """
        ...

    def get_channels(self) -> Mapping[str, LogWriter]:
        """Return resolved native loggers without resolving additional ones.

        Returns:
            A snapshot of channels currently cached by this manager.
        """
        ...

    def forget_channel(self, name: str | None = None) -> None:
        """Close and remove one cached channel.

        Args:
            name: Channel to remove, defaulting to the configured channel.
        """
        ...

    def forget_channels(self) -> None:
        """Close and remove all cached channels.

        Only resources owned by this manager are finalized.
        """
        ...


__all__ = ["LoggingManager"]
