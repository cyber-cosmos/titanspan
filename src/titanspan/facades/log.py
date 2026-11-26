"""Provide an explicitly bound, execution-local logging facade.

The facade resolves a manager from the active context and never owns a
process-global application logger or backend instance.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

from titanspan._application_context import ApplicationContextError
from titanspan.contracts.logging import LogBridge, LoggingManager, LogWriter
from titanspan.facades.base import Facade
from titanspan.logging.configuration import (
    ChannelConfiguration,
    LoggingConfiguration,
)
from titanspan.logging.drivers import MemoryLogDriver
from titanspan.logging.exceptions import LogContextError
from titanspan.logging.level import LogLevel
from titanspan.logging.manager import LogManager
from titanspan.logging.testing import FakeLog

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping

    from titanspan.contracts.logging import LogDriver
    from titanspan.logging.record import LogRecord

_ACTIVE_FAKE: ContextVar[FakeLog | None] = ContextVar(
    "titanspan_active_log_fake",
    default=None,
)
_FAKE_CONFIGURATION_ERROR = (
    "The active logging service cannot be captured by Log.fake()."
)


class Log(Facade[LoggingManager]):
    """Resolve logging operations from the active application manager.

    The facade resolves its manager through the active application
    container. Use :meth:`Facade.use` for temporary, container-owned service
    replacement in tests and execution-local customization.
    """

    service_contract = LoggingManager

    @classmethod
    def manager(cls) -> LoggingManager:
        """Return the active manager for this execution context.

        Returns:
            The manager registered by the active application.

        Raises:
            LogContextError: If no application context is active.
        """
        try:
            return cls.resolve_service()
        except ApplicationContextError as error:
            message = "Bind an application context before using the Log facade."
            raise LogContextError(message) from error

    @classmethod
    def channel(cls, name: str | None = None) -> LogWriter:
        """Resolve a named or default logger from the active manager.

        Args:
            name: Optional configured channel name.

        Returns:
            The native Titanspan logger for that channel.
        """
        return cls.manager().channel(name)

    @classmethod
    def build(cls, configuration: Mapping[str, object]) -> LogWriter:
        """Build an independently owned logger from native settings.

        Args:
            configuration: A Titanspan channel configuration mapping.

        Returns:
            An on-demand logger that owns its destination resources.
        """
        return cls.manager().build(configuration)

    @classmethod
    def stack(
        cls,
        channels: tuple[str, ...] | list[str],
        *,
        channel: str | None = None,
        ignore_exceptions: bool = False,
    ) -> LogWriter:
        """Create a fan-out logger from configured channel names.

        Args:
            channels: Channel names in deterministic delivery order.
            channel: Optional name attached to stack-level records.
            ignore_exceptions: Continue after failures from child channels.

        Returns:
            An on-demand logger that owns only its stack coordinator.
        """
        return cls.manager().stack(
            channels,
            channel=channel,
            ignore_exceptions=ignore_exceptions,
        )

    @classmethod
    def bridge_standard_logger(
        cls,
        logger_name: str,
        channel: str | None = None,
    ) -> LogBridge:
        """Bridge one selected standard logger into a native channel.

        Args:
            logger_name: The explicitly selected stdlib logger name.
            channel: Optional Titanspan destination channel.

        Returns:
            A native bridge handle owned by the active manager.
        """
        return cls.manager().bridge_standard_logger(logger_name, channel)

    @classmethod
    def get_default_channel(cls) -> str:
        """Return the configured default channel name.

        Returns:
            The name currently selected as the manager default.
        """
        return cls.manager().get_default_channel()

    @classmethod
    def set_default_channel(cls, name: str) -> None:
        """Select a configured channel as the default destination.

        Args:
            name: Declared channel name to select.
        """
        cls.manager().set_default_channel(name)

    @classmethod
    def extend(
        cls,
        name: str,
        factory: Callable[[ChannelConfiguration], LogDriver[LogRecord]],
    ) -> None:
        """Register a native custom driver factory.

        Args:
            name: Custom driver identifier.
            factory: Callable accepting channel configuration and returning a
                Titanspan-owned logging driver.
        """
        cls.manager().extend(name, factory)

    @classmethod
    def flush(cls) -> None:
        """Flush every channel resolved by the active application.

        Raises:
            LogDeliveryError: If any configured destination cannot flush.
        """
        cls.manager().flush()

    @classmethod
    async def flush_async(cls) -> None:
        """Flush resolved channels without blocking the event loop.

        This method delegates blocking destination cleanup to AnyIO's worker
        pool and preserves cancellation until the operation completes.
        """
        await cls.manager().flush_async()

    @classmethod
    def close(cls) -> None:
        """Close every channel and bridge owned by the active manager.

        Raises:
            LogDeliveryError: If resource finalization reports a failure.
        """
        cls.manager().close()

    @classmethod
    async def close_async(cls) -> None:
        """Close logging resources without blocking the event loop.

        AnyIO runs synchronous sink shutdown in its worker pool.
        """
        await cls.manager().aclose()

    @classmethod
    def log(
        cls,
        level: LogLevel | str | int,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a structured message through the default channel.

        Args:
            level: A native level, case-insensitive name, or RFC number.
            message: The application message.
            context: Optional positional mapping of structured fields.
            **values: Keyword fields that override mapping values.
        """
        cls.channel().log(level, message, context, **values)

    @classmethod
    async def log_async(
        cls,
        level: LogLevel | str | int,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a record without blocking the current event loop.

        Args:
            level: Native RFC level, name, or severity number.
            message: The application message.
            context: Optional positional structured fields.
            **values: Keyword fields overriding duplicate mapping keys.
        """
        await cls.channel().log_async(level, message, context, **values)

    @classmethod
    def exception(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an error with the active or supplied exception.

        Args:
            message: A concise failure description.
            context: Optional structured failure metadata.
            **values: Additional metadata, including an optional exception.
        """
        cls.channel().exception(message, context, **values)

    @classmethod
    async def exception_async(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an exception record through the async channel interface.

        Args:
            message: A concise failure description.
            context: Optional structured failure metadata.
            **values: Additional metadata, including an optional exception.
        """
        await cls.channel().exception_async(message, context, **values)

    @classmethod
    def emergency(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a system-unavailable emergency event.

        Args:
            message: The emergency message.
            context: Optional structured context mapping.
            **values: Additional structured context.
        """
        cls.channel().emergency(message, context, **values)

    @classmethod
    def alert(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an alert event.

        Args:
            message: The alert message.
            context: Optional structured context mapping.
            **values: Additional structured context.
        """
        cls.channel().alert(message, context, **values)

    @classmethod
    def critical(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a critical event.

        Args:
            message: The critical message.
            context: Optional structured context mapping.
            **values: Additional structured context.
        """
        cls.channel().critical(message, context, **values)

    @classmethod
    def error(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an error event.

        Args:
            message: The error message.
            context: Optional structured context mapping.
            **values: Additional structured context.
        """
        cls.channel().error(message, context, **values)

    @classmethod
    def warning(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a warning event.

        Args:
            message: The warning message.
            context: Optional structured context mapping.
            **values: Additional structured context.
        """
        cls.channel().warning(message, context, **values)

    @classmethod
    def notice(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a significant informational event.

        Args:
            message: The notice message.
            context: Optional structured context mapping.
            **values: Additional structured context.
        """
        cls.channel().notice(message, context, **values)

    @classmethod
    def info(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an informational event.

        Args:
            message: The informational message.
            context: Optional structured context mapping.
            **values: Additional structured context.
        """
        cls.channel().info(message, context, **values)

    @classmethod
    def debug(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a diagnostic event.

        Args:
            message: The diagnostic message.
            context: Optional structured context mapping.
            **values: Additional structured context.
        """
        cls.channel().debug(message, context, **values)

    @classmethod
    async def emergency_async(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an emergency message through async delivery.

        Args:
            message: The system-unavailable message.
            context: Optional structured fields.
            **values: Additional structured values.
        """
        await cls.log_async(LogLevel.EMERGENCY, message, context, **values)

    @classmethod
    async def alert_async(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an alert message through async delivery.

        Args:
            message: The immediate-intervention message.
            context: Optional structured fields.
            **values: Additional structured values.
        """
        await cls.log_async(LogLevel.ALERT, message, context, **values)

    @classmethod
    async def critical_async(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a critical message through async delivery.

        Args:
            message: The critical condition.
            context: Optional structured fields.
            **values: Additional structured values.
        """
        await cls.log_async(LogLevel.CRITICAL, message, context, **values)

    @classmethod
    async def error_async(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an error message through async delivery.

        Args:
            message: The failure message.
            context: Optional structured fields.
            **values: Additional structured values.
        """
        await cls.log_async(LogLevel.ERROR, message, context, **values)

    @classmethod
    async def warning_async(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a warning through async delivery.

        Args:
            message: The recoverable condition.
            context: Optional structured fields.
            **values: Additional structured values.
        """
        await cls.log_async(LogLevel.WARNING, message, context, **values)

    @classmethod
    async def notice_async(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a notice through async delivery.

        Args:
            message: The significant normal-operation message.
            context: Optional structured fields.
            **values: Additional structured values.
        """
        await cls.log_async(LogLevel.NOTICE, message, context, **values)

    @classmethod
    async def info_async(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an informational message through async delivery.

        Args:
            message: The informational message.
            context: Optional structured fields.
            **values: Additional structured values.
        """
        await cls.log_async(LogLevel.INFO, message, context, **values)

    @classmethod
    async def debug_async(
        cls,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a diagnostic message through async delivery.

        Args:
            message: The development diagnostic.
            context: Optional structured fields.
            **values: Additional structured values.
        """
        await cls.log_async(LogLevel.DEBUG, message, context, **values)

    @classmethod
    def with_context(
        cls,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Add context shared by logger calls in the active execution.

        Args:
            context: Optional positional context mapping.
            **values: Additional values overriding mapping keys.
        """
        cls.manager().with_context(context, **values)

    @classmethod
    def share_context(
        cls,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Add context visible through all channels in this execution.

        Args:
            context: Optional positional context mapping.
            **values: Additional values overriding mapping keys.
        """
        cls.manager().share_context(context, **values)

    @classmethod
    def context(cls, **values: object) -> AbstractContextManager[None]:
        """Return a manager context scope for temporary values.

        Args:
            **values: Values active until the returned context exits.

        Returns:
            A context manager that restores the previous context on exit.
        """
        return cls.manager().context(**values)

    @classmethod
    def without_context(cls, *keys: str) -> None:
        """Remove selected keys from the current logger context.

        Args:
            *keys: Names to remove from local and shared values.
        """
        cls.manager().without_context(*keys)

    @classmethod
    def flush_context(cls) -> None:
        """Clear local and shared context in the active execution scope.

        Other tasks retain their independent context mappings.
        """
        cls.manager().flush_context()

    @classmethod
    def get_context(cls) -> dict[str, object]:
        """Return a detached snapshot of merged active context.

        Shared values are merged before local execution values.
        """
        return cls.manager().get_context()

    @classmethod
    def shared_context(cls) -> dict[str, object]:
        """Return shared values as a detached mapping.

        Returns:
            Context values visible across channels in the current execution.
        """
        return cls.manager().shared_context()

    @classmethod
    def flush_shared_context(cls) -> None:
        """Remove shared values while preserving local values.

        The operation is limited to the current task or thread context.
        """
        cls.manager().flush_shared_context()

    @classmethod
    def get_channels(cls) -> Mapping[str, LogWriter]:
        """Return a read-only snapshot of resolved native channels.

        Returns:
            Channels instantiated by the active manager so far.
        """
        return cls.manager().get_channels()

    @classmethod
    def forget_channel(cls, name: str | None = None) -> None:
        """Close one cached channel and allow later re-resolution.

        Args:
            name: Channel to forget, defaulting to the selected channel.
        """
        cls.manager().forget_channel(name)

    @classmethod
    def forget_channels(cls) -> None:
        """Close cached channels while retaining validated configuration.

        A subsequent lookup creates a fresh channel with the same settings.
        """
        cls.manager().forget_channels()

    @classmethod
    @contextmanager
    def fake(cls) -> Generator[FakeLog, None, None]:
        """Replace configured destinations with one bounded memory driver.

        The fake manager is scoped to the current context and restores the
        previous manager even if the test body raises.

        Yields:
            Assertions and captured records for the fake scope.
        """
        source = cls.manager()
        configuration = source.configuration
        if not isinstance(configuration, LoggingConfiguration):
            raise LogContextError(_FAKE_CONFIGURATION_ERROR)
        fake_driver = MemoryLogDriver()
        channels = {
            name: _fake_configuration(channel)
            for name, channel in configuration.channels.items()
        }
        fake_manager = LogManager(
            LoggingConfiguration(
                default=source.get_default_channel(),
                channels=channels,
            ),
            drivers={"memory": lambda _: fake_driver},
        )
        fake = FakeLog(fake_driver)
        fake_token = _ACTIVE_FAKE.set(fake)
        try:
            with cls.use(fake_manager):
                yield fake
        finally:
            _ACTIVE_FAKE.reset(fake_token)
            fake_manager.close()

    @classmethod
    def assert_logged(
        cls,
        level: LogLevel | str | int | None = None,
        message: str | None = None,
        *,
        channel: str | None = None,
        context: Mapping[str, object] | None = None,
        predicate: Callable[[LogRecord], bool] | None = None,
    ) -> LogRecord:
        """Assert that the active fake captured a matching record.

        Args:
            level: Optional severity filter.
            message: Optional exact message filter.
            channel: Optional channel filter.
            context: Required structured context subset.
            predicate: Optional native record predicate.

        Returns:
            The first matching record.
        """
        return cls._fake().assert_logged(
            level,
            message,
            channel=channel,
            context=context,
            predicate=predicate,
        )

    @classmethod
    def assert_not_logged(
        cls,
        level: LogLevel | str | int | None = None,
        message: str | None = None,
        *,
        channel: str | None = None,
        context: Mapping[str, object] | None = None,
        predicate: Callable[[LogRecord], bool] | None = None,
    ) -> None:
        """Assert that the active fake did not capture a matching record.

        Args:
            level: Optional severity filter.
            message: Optional exact message filter.
            channel: Optional channel filter.
            context: Required structured context subset.
            predicate: Optional native record predicate.
        """
        cls._fake().assert_not_logged(
            level,
            message,
            channel=channel,
            context=context,
            predicate=predicate,
        )

    @classmethod
    def assert_logged_times(
        cls,
        count: int,
        level: LogLevel | str | int | None = None,
        message: str | None = None,
        *,
        channel: str | None = None,
        context: Mapping[str, object] | None = None,
        predicate: Callable[[LogRecord], bool] | None = None,
    ) -> None:
        """Assert an exact count of matching fake records.

        Args:
            count: Number of expected matching records.
            level: Optional severity filter.
            message: Optional exact message filter.
            channel: Optional channel filter.
            context: Required structured context subset.
            predicate: Optional native record predicate.
        """
        cls._fake().assert_logged_times(
            count,
            level,
            message,
            channel=channel,
            context=context,
            predicate=predicate,
        )

    @classmethod
    def assert_nothing_logged(cls) -> None:
        """Assert that the active fake captured no records.

        Raises:
            LogAssertionError: If at least one native record was captured.
        """
        cls._fake().assert_nothing_logged()

    @classmethod
    def _fake(cls) -> FakeLog:
        """Return the fake active in the current execution context.

        Raises:
            RuntimeError: If no fake scope is active.
        """
        fake = _ACTIVE_FAKE.get()
        if fake is None:
            message = "Use Log.fake() before logging assertions"
            raise LogContextError(message)
        return fake


def _fake_configuration(
    configuration: ChannelConfiguration,
) -> ChannelConfiguration:
    """Convert a channel configuration to a fake sink equivalent.

    Args:
        configuration: One already validated source channel model.

    Returns:
        A copied channel configuration targeting the memory driver.
    """
    if configuration.driver == "stack":
        return configuration
    return configuration.model_copy(
        update={"driver": "memory", "options": {}},
    )
