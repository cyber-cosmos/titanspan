"""Provide an explicitly bound, execution-local logging facade.

The facade resolves a manager from the active context and never owns a
process-global application logger or backend instance.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

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

    from titanspan.logging.bridge import StandardLogBridge
    from titanspan.logging.contracts.log_driver import LogDriver
    from titanspan.logging.logger import Logger
    from titanspan.logging.record import LogRecord

_ACTIVE_MANAGER: ContextVar[LogManager | None] = ContextVar(
    "titanspan_active_log_manager",
    default=None,
)
_ACTIVE_FAKE: ContextVar[FakeLog | None] = ContextVar(
    "titanspan_active_log_fake",
    default=None,
)


class Log:
    """Resolve logging operations from an explicitly active manager.

    Use ``with Log.use(manager):`` around application code or bind the
    manager within an application execution scope. The context variable is
    isolated across asynchronous tasks and restored on scope exit.
    """

    @classmethod
    @contextmanager
    def use(cls, manager: LogManager) -> Generator[None, None, None]:
        """Bind a manager to the current execution context.

        Args:
            manager: The application manager providing native channels.

        Yields:
            Control while facade operations use the manager.
        """
        token = _ACTIVE_MANAGER.set(manager)
        try:
            yield
        finally:
            _ACTIVE_MANAGER.reset(token)

    @classmethod
    def manager(cls) -> LogManager:
        """Return the active manager for this execution context.

        Returns:
            The manager explicitly bound through :meth:`use`.

        Raises:
            LogContextError: If no manager is active.
        """
        manager = _ACTIVE_MANAGER.get()
        if manager is None:
            message = "Bind a LogManager with Log.use() before facade logging"
            raise LogContextError(message)
        return manager

    @classmethod
    def channel(cls, name: str | None = None) -> Logger:
        """Resolve a named or default logger from the active manager.

        Args:
            name: Optional configured channel name.

        Returns:
            The native Titanspan logger for that channel.
        """
        return cls.manager().channel(name)

    @classmethod
    def driver(cls, name: str | None = None) -> Logger:
        """Resolve a channel using Laravel-compatible driver terminology.

        Args:
            name: Optional channel name, defaulting to the selected channel.

        Returns:
            The native logger associated with the selected channel.
        """
        return cls.manager().driver(name)

    @classmethod
    def build(cls, configuration: Mapping[str, object]) -> Logger:
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
    ) -> Logger:
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
    ) -> StandardLogBridge:
        """Bridge one selected standard logger into a native channel.

        Args:
            logger_name: The explicitly selected stdlib logger name.
            channel: Optional Titanspan destination channel.

        Returns:
            A native bridge handle owned by the active manager.
        """
        return cls.manager().bridge_standard_logger(logger_name, channel)

    @classmethod
    def get_default_driver(cls) -> str:
        """Return the configured default channel name.

        Returns:
            The name currently selected as the manager default.
        """
        return cls.manager().get_default_driver()

    @classmethod
    def set_default_driver(cls, name: str) -> None:
        """Select a configured channel as the default destination.

        Args:
            name: Declared channel name to select.
        """
        cls.manager().set_default_driver(name)

    @classmethod
    def extend(
        cls,
        name: str,
        factory: Callable[[ChannelConfiguration], LogDriver],
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
    def get_channels(cls) -> Mapping[str, Logger]:
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
        fake_driver = MemoryLogDriver()
        channels = {
            name: _fake_configuration(channel)
            for name, channel in source.configuration.channels.items()
        }
        fake_manager = LogManager(
            LoggingConfiguration(
                default=source.get_default_driver(),
                channels=channels,
            ),
            drivers={"memory": lambda _: fake_driver},
        )
        fake = FakeLog(fake_driver)
        manager_token = _ACTIVE_MANAGER.set(fake_manager)
        fake_token = _ACTIVE_FAKE.set(fake)
        try:
            yield fake
        finally:
            _ACTIVE_FAKE.reset(fake_token)
            _ACTIVE_MANAGER.reset(manager_token)
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
        """Return the active fake for Laravel-inspired facade assertions.

        Raises:
            RuntimeError: If no fake scope is active.
        """
        fake = _ACTIVE_FAKE.get()
        if fake is None:
            message = "Use Log.fake() before logging assertions"
            raise LogContextError(message)
        return fake

    @classmethod
    def withContext(  # noqa: N802
        cls,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Add context using the Laravel-compatible method spelling.

        Prefer :meth:`with_context` in new Python code.

        Args:
            context: Optional mapping of structured values.
            **values: Additional values that override mapping keys.
        """
        cls.with_context(context, **values)

    @classmethod
    def shareContext(  # noqa: N802
        cls,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Share context using the Laravel-compatible method spelling.

        Prefer :meth:`share_context` in new Python code.

        Args:
            context: Optional mapping of structured values.
            **values: Additional values that override mapping keys.
        """
        cls.share_context(context, **values)

    @classmethod
    def withoutContext(cls, *keys: str) -> None:  # noqa: N802
        """Remove context values using Laravel-compatible spelling.

        Prefer :meth:`without_context` in new Python code.

        Args:
            *keys: Context keys to remove from the current execution.
        """
        cls.without_context(*keys)

    @classmethod
    def flushContext(cls) -> None:  # noqa: N802
        """Clear context using the Laravel-compatible method spelling.

        Prefer :meth:`flush_context` in new Python code.
        """
        cls.flush_context()

    @classmethod
    def getContext(cls) -> dict[str, object]:  # noqa: N802
        """Return context using the Laravel-compatible method spelling.

        Prefer :meth:`get_context` in new Python code.

        Returns:
            A detached mapping of active context values.
        """
        return cls.get_context()

    @classmethod
    def getDefaultDriver(cls) -> str:  # noqa: N802
        """Return the default channel with Laravel-compatible spelling.

        Returns:
            The name selected as the active default channel.
        """
        return cls.get_default_driver()

    @classmethod
    def setDefaultDriver(cls, name: str) -> None:  # noqa: N802
        """Select a default channel with Laravel-compatible spelling.

        Args:
            name: A declared channel name.
        """
        cls.set_default_driver(name)

    @classmethod
    def sharedContext(cls) -> dict[str, object]:  # noqa: N802
        """Return shared context with Laravel-compatible spelling.

        Returns:
            A detached mapping of active shared values.
        """
        return cls.shared_context()

    @classmethod
    def flushSharedContext(cls) -> None:  # noqa: N802
        """Clear shared context with Laravel-compatible spelling.

        Prefer :meth:`flush_shared_context` in new Python code.
        """
        cls.flush_shared_context()

    @classmethod
    def getChannels(cls) -> Mapping[str, Logger]:  # noqa: N802
        """Return resolved channels with Laravel-compatible spelling.

        Returns:
            A read-only snapshot of instantiated channel loggers.
        """
        return cls.get_channels()

    @classmethod
    def forgetChannel(cls, name: str | None = None) -> None:  # noqa: N802
        """Forget a channel with Laravel-compatible spelling.

        Args:
            name: Channel to close, or the default channel when omitted.
        """
        cls.forget_channel(name)

    @classmethod
    def forgetChannels(cls) -> None:  # noqa: N802
        """Forget every channel with Laravel-compatible spelling.

        The validated channel configuration remains available for reuse.
        """
        cls.forget_channels()

    @classmethod
    def assertLogged(  # noqa: N802
        cls,
        level: LogLevel | str | int | None = None,
        message: str | None = None,
        *,
        channel: str | None = None,
        context: Mapping[str, object] | None = None,
        predicate: Callable[[LogRecord], bool] | None = None,
    ) -> LogRecord:
        """Assert a matching record with Laravel-compatible spelling.

        Args:
            level: Optional severity filter.
            message: Optional exact message.
            channel: Optional channel name.
            context: Required structured context values.
            predicate: Optional record predicate.

        Returns:
            The first matching record.
        """
        return cls.assert_logged(
            level,
            message,
            channel=channel,
            context=context,
            predicate=predicate,
        )

    @classmethod
    def assertNotLogged(  # noqa: N802
        cls,
        level: LogLevel | str | int | None = None,
        message: str | None = None,
        *,
        channel: str | None = None,
        context: Mapping[str, object] | None = None,
        predicate: Callable[[LogRecord], bool] | None = None,
    ) -> None:
        """Assert no matching record with Laravel-compatible spelling.

        Args:
            level: Optional severity filter.
            message: Optional exact message.
            channel: Optional channel name.
            context: Required structured context values.
            predicate: Optional record predicate.
        """
        cls.assert_not_logged(
            level,
            message,
            channel=channel,
            context=context,
            predicate=predicate,
        )

    @classmethod
    def assertLoggedTimes(  # noqa: N802
        cls,
        count: int,
        level: LogLevel | str | int | None = None,
        message: str | None = None,
        *,
        channel: str | None = None,
        context: Mapping[str, object] | None = None,
        predicate: Callable[[LogRecord], bool] | None = None,
    ) -> None:
        """Assert a matching record count with Laravel-style spelling.

        Args:
            count: Expected number of matching records.
            level: Optional severity filter.
            message: Optional exact message.
            channel: Optional channel name.
            context: Required structured context values.
            predicate: Optional record predicate.
        """
        cls.assert_logged_times(
            count,
            level,
            message,
            channel=channel,
            context=context,
            predicate=predicate,
        )

    @classmethod
    def assertNothingLogged(cls) -> None:  # noqa: N802
        """Assert no records were captured with Laravel-style spelling.

        Prefer :meth:`assert_nothing_logged` in new Python code.
        """
        cls.assert_nothing_logged()


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
