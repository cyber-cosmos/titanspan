"""Resolve named channels and own their logging resource lifecycles.

The manager follows Laravel's channel-oriented API while using validated
Titanspan configuration, typed driver factories, and context-local metadata.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from threading import RLock
from types import MappingProxyType
from typing import TYPE_CHECKING, TextIO, cast
from uuid import uuid4

import anyio

from titanspan.logging._backends.bridge import StandardLibraryBridgeBackend
from titanspan.logging.bridge import StandardLogBridge
from titanspan.logging.channel import LogChannel
from titanspan.logging.configuration import (
    ChannelConfiguration,
    LoggingConfiguration,
)
from titanspan.logging.contracts.log_customizer import LogCustomizer
from titanspan.logging.contracts.log_driver import LogDriver
from titanspan.logging.contracts.log_formatter import LogFormatter
from titanspan.logging.drivers import (
    BackgroundLogDriver,
    EmergencyLogDriver,
    MemoryLogDriver,
    NullLogDriver,
    StackLogDriver,
    StandardHandlerLogDriver,
    WebhookLogDriver,
    create_console_driver,
    create_daily_file_driver,
    create_monthly_file_driver,
    create_rotating_file_driver,
    create_single_file_driver,
    create_syslog_driver,
    webhook_options,
)
from titanspan.logging.exceptions import (
    LogChannelNotFoundError,
    LogConfigurationError,
    LogDeliveryError,
    LogLifecycleError,
)
from titanspan.logging.formatters import create_formatter
from titanspan.logging.logger import Logger
from titanspan.logging.processors import RedactionProcessor

if TYPE_CHECKING:
    from collections.abc import Sequence

    from titanspan.logging.contracts.log_processor import LogProcessor
    from titanspan.logging.level import LogLevel

DriverFactory = Callable[[ChannelConfiguration], LogDriver]
FormatterFactory = Callable[[ChannelConfiguration], LogFormatter]
CustomizerRegistry = Mapping[str, LogCustomizer]
_EMPTY_CONTEXT: Mapping[str, object] = MappingProxyType({})
_SYSLOG_ADDRESS_PARTS = 2
_BUILTIN_FORMATTERS = frozenset({"console", "text", "json"})


def _channel_depends_on(
    channel: LogChannel,
    target: LogChannel,
    visited: set[int] | None = None,
) -> bool:
    """Return whether a stack transitively references one target channel.

    Args:
        channel: Candidate stack whose references are inspected.
        target: Channel that is about to be purged.
        visited: Channel identities already checked during traversal.

    Returns:
        ``True`` if the candidate is or references the target channel.
    """
    if channel is target:
        return True
    inspected: set[int] = visited if visited is not None else set()
    if id(channel) in inspected:
        return False
    inspected.add(id(channel))
    driver: LogDriver = channel.driver
    if isinstance(driver, BackgroundLogDriver):
        driver = driver.inner_driver
    if not isinstance(driver, StackLogDriver):
        return False
    return any(
        _channel_depends_on(child, target, inspected)
        for child in driver.channels
    )


class LogManager:
    """Manage configured channels, custom drivers, and scoped context.

    Attributes:
        configuration: Validated application logging configuration.

    A manager caches declared channels, while ``build`` creates a separately
    owned on-demand channel. Context is isolated by Python execution context.
    """

    def __init__(
        self,
        configuration: (
            LoggingConfiguration | Mapping[str, object] | None
        ) = None,
        *,
        drivers: Mapping[str, DriverFactory] | None = None,
        formatters: Mapping[str, FormatterFactory] | None = None,
        customizers: CustomizerRegistry | None = None,
        processors: tuple[LogProcessor, ...] = (),
        emergency_stream: TextIO | None = None,
    ) -> None:
        """Validate configuration and register built-in plus custom drivers.

        Args:
            configuration: Native configuration model or mapping.
            drivers: Application-defined driver factories.
            formatters: Application-defined native formatter factories.
            customizers: Application-defined channel initialization hooks.
            processors: Processors applied before driver delivery.
            emergency_stream: Optional fallback stream for testing.

        Raises:
            LogConfigurationError: If channels, drivers, or stacks are invalid.
        """
        self.configuration = LoggingConfiguration.from_value(configuration)
        self._default_channel = self.configuration.default
        self._lock = RLock()
        self._context: ContextVar[Mapping[str, object]] = ContextVar(
            f"titanspan_log_context_{id(self)}",
            default=_EMPTY_CONTEXT,
        )
        self._shared_context: ContextVar[Mapping[str, object]] = ContextVar(
            f"titanspan_shared_log_context_{id(self)}",
            default=_EMPTY_CONTEXT,
        )
        self._processors = tuple(processors)
        self._emergency_stream_value = emergency_stream
        self._emergency = EmergencyLogDriver(emergency_stream)
        self._factories = self._builtin_factories()
        self._factories.update(drivers or {})
        self._formatters = dict(formatters or {})
        self._customizers = dict(customizers or {})
        self._channels: dict[str, Logger] = {}
        self._dynamic_channels: set[LogChannel] = set()
        self._bridges: dict[tuple[str, str], StandardLogBridge] = {}
        self._resolved_drivers: dict[str, str] = {}
        self._resolved_formatters: dict[str, str] = {}
        self._closed = False
        self._validate_configuration()

    def channel(self, name: str | None = None) -> Logger:
        """Resolve and cache a named or default channel.

        Args:
            name: A declared channel name, or ``None`` for the default.

        Returns:
            A Titanspan logger wrapper for the resolved channel.

        Raises:
            LogChannelNotFoundError: If the name is not declared.
            LogLifecycleError: If the manager has been closed.
        """
        if self._closed:
            msg = "The logging manager is closed"
            raise LogLifecycleError(msg)
        channel_name = self._default_channel if name is None else name
        with self._lock:
            existing = self._channels.get(channel_name)
            if existing is not None:
                return existing
            configuration = self.configuration.channels.get(channel_name)
            if configuration is None:
                raise LogChannelNotFoundError(channel_name)
            logger = self._create_logger(channel_name, configuration)
            self._channels[channel_name] = logger
            self._resolved_drivers[channel_name] = configuration.driver
            self._resolved_formatters[channel_name] = configuration.formatter
            return logger

    def driver(self, name: str | None = None) -> Logger:
        """Resolve a channel using Laravel-compatible manager terminology.

        Args:
            name: A declared channel name or the configured default.

        Returns:
            The cached native logger for that channel.
        """
        return self.channel(name)

    def log(
        self,
        level: LogLevel | str | int,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a record through the configured default channel.

        Args:
            level: Native level, supported name, or RFC severity number.
            message: The application message.
            context: Optional positional structured context.
            **values: Additional context overriding mapping values.
        """
        self.channel().log(level, message, context, **values)

    def emergency(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a system-unavailable message to the default channel.

        Args:
            message: The emergency message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.channel().emergency(message, context, **values)

    def alert(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an alert through the configured default channel.

        Args:
            message: The alert message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.channel().alert(message, context, **values)

    def critical(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a critical event through the default channel.

        Args:
            message: The critical message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.channel().critical(message, context, **values)

    def error(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write an error through the configured default channel.

        Args:
            message: The error message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.channel().error(message, context, **values)

    def warning(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a warning through the configured default channel.

        Args:
            message: The warning message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.channel().warning(message, context, **values)

    def notice(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write a notice through the configured default channel.

        Args:
            message: The notice message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.channel().notice(message, context, **values)

    def info(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write informational output through the default channel.

        Args:
            message: The informational message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.channel().info(message, context, **values)

    def debug(
        self,
        message: str,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Write diagnostic output through the default channel.

        Args:
            message: The diagnostic message.
            context: Optional structured context mapping.
            **values: Additional structured context values.
        """
        self.channel().debug(message, context, **values)

    def resolve(self, name: str | None = None) -> Logger:
        """Resolve a channel through an explicit manager method.

        Args:
            name: A declared channel name or the configured default.

        Returns:
            The cached native logger for that channel.
        """
        return self.channel(name)

    def build(self, configuration: Mapping[str, object]) -> Logger:
        """Build an independently owned on-demand logging channel.

        Args:
            configuration: One native channel configuration mapping.

        Returns:
            A logger that can be used as a context manager to close its driver.

        Raises:
            LogConfigurationError: If the channel options are invalid.
        """
        if self._closed:
            msg = "The logging manager is closed"
            raise LogLifecycleError(msg)
        try:
            channel_configuration = ChannelConfiguration.model_validate(
                configuration,
            )
        except ValueError as error:
            raise LogConfigurationError(str(error)) from error
        self._validate_driver(channel_configuration)
        name = channel_configuration.name or f"on-demand-{uuid4().hex}"
        logger = self._create_logger(
            name,
            channel_configuration,
            owns_channel=True,
        )
        self._dynamic_channels.add(logger.channel)
        return logger

    def bridge_standard_logger(
        self,
        logger_name: str,
        channel: str | None = None,
    ) -> StandardLogBridge:
        """Capture a selected standard logger through a native channel.

        Args:
            logger_name: Standard-library logger name to bridge explicitly.
            channel: Destination channel, or the manager's current default.

        Returns:
            An owned handle that removes only its installed handler on close.

        Raises:
            LogConfigurationError: If the selected logger name is invalid.
            LogChannelNotFoundError: If the channel is not configured.
        """
        if not logger_name or logger_name != logger_name.strip():
            message = "A standard logger name must be non-empty and trimmed"
            raise LogConfigurationError(message)
        channel_name = self._default_channel if channel is None else channel
        key = (logger_name, channel_name)
        with self._lock:
            existing = self._bridges.get(key)
            if existing is not None and not existing.closed:
                return existing
            self._bridges.pop(key, None)
            native_logger = self.channel(channel_name)
            backend = StandardLibraryBridgeBackend(
                logger_name,
                native_logger.channel,
                self._emergency.report_failure,
            )
            bridge = StandardLogBridge(
                logger_name,
                channel_name,
                backend.close,
            )
            self._bridges[key] = bridge
            return bridge

    def stack(
        self,
        channels: tuple[str, ...] | list[str],
        *,
        channel: str | None = None,
        ignore_exceptions: bool = False,
    ) -> Logger:
        """Build an on-demand stack from declared channel names.

        Args:
            channels: Child channel names in delivery order.
            channel: Optional name used for emitted records.
            ignore_exceptions: Continue after failed child channels.

        Returns:
            A separately owned logger whose stack does not own its children.
        """
        return self.build(
            {
                "driver": "stack",
                "channels": tuple(channels),
                "name": channel,
                "ignore_exceptions": ignore_exceptions,
            },
        )

    def extend(self, name: str, factory: DriverFactory) -> None:
        """Register or replace a named Titanspan driver factory.

        Args:
            name: The application-defined driver identifier.
            factory: A factory returning a native ``LogDriver``.

        Raises:
            LogConfigurationError: If the name is blank or already active.
        """
        if not name or name != name.strip():
            msg = "A driver name must be non-empty and trimmed"
            raise LogConfigurationError(
                msg,
            )
        with self._lock:
            if name in self._resolved_drivers.values():
                msg = f"Driver {name!r} is already used by a resolved channel"
                raise LogConfigurationError(
                    msg,
                )
            self._factories[name] = factory
            self._validate_configuration()

    def extend_formatter(
        self,
        name: str,
        factory: FormatterFactory,
    ) -> None:
        """Register a native formatter before a channel resolves it.

        Args:
            name: Non-empty identifier selected by channel configuration.
            factory: Factory returning a Titanspan ``LogFormatter``.

        Raises:
            LogConfigurationError: If a built-in or active formatter is reused.
        """
        if not name or name != name.strip():
            message = "A formatter name must be non-empty and trimmed"
            raise LogConfigurationError(message)
        with self._lock:
            if name in _BUILTIN_FORMATTERS:
                message = f"Formatter {name!r} is reserved"
                raise LogConfigurationError(message)
            if name in self._resolved_formatters.values():
                message = f"Formatter {name!r} is used by a resolved channel"
                raise LogConfigurationError(message)
            self._formatters[name] = factory
            self._validate_configuration()

    def get_default_driver(self) -> str:
        """Return the currently selected default channel name.

        Returns:
            The default channel identifier.
        """
        return self._default_channel

    def get_channels(self) -> Mapping[str, Logger]:
        """Return an immutable snapshot of channels resolved so far.

        Returns:
            A read-only mapping from configured names to native loggers.
        """
        return MappingProxyType(dict(self._channels))

    def shared_context(self) -> dict[str, object]:
        """Return a detached snapshot of execution-shared context values.

        Returns:
            Values visible across channels in this execution context.
        """
        return dict(self._shared_context.get())

    def forget_channel(self, name: str | None = None) -> None:
        """Close and remove one resolved channel from the manager cache.

        Args:
            name: Channel to forget, defaulting to the current channel.
        """
        channel_name = self._default_channel if name is None else name
        self.purge(channel_name)

    def get(self, name: str | None = None) -> Logger:
        """Resolve a logger using Laravel-compatible manager terminology.

        Args:
            name: A declared channel or the currently selected default.

        Returns:
            The cached Titanspan logger for that channel.
        """
        return self.channel(name)

    def set_default_driver(self, name: str) -> None:
        """Select a declared channel as the default destination.

        Args:
            name: A channel name in the validated configuration.

        Raises:
            LogChannelNotFoundError: If the selected channel is undeclared.
        """
        if name not in self.configuration.channels:
            raise LogChannelNotFoundError(name)
        self._default_channel = name

    def with_context(
        self, context: Mapping[str, object] | None = None, **values: object
    ) -> None:
        """Merge values into the current logger execution context.

        Values are copied before storage. Sensitive values remain within the
        current context and are redacted before a driver receives a record.
        """
        merged = dict(self._context.get())
        if context is not None:
            merged.update(context)
        merged.update(values)
        self._context.set(MappingProxyType(merged))

    def share_context(
        self, context: Mapping[str, object] | None = None, **values: object
    ) -> None:
        """Merge context shared by all channels in this execution context.

        Args:
            context: Optional positional mapping of shared values.
            **values: Keyword values that override mapping keys.
        """
        merged = dict(self._shared_context.get())
        if context is not None:
            merged.update(context)
        merged.update(values)
        self._shared_context.set(MappingProxyType(merged))

    def without_context(
        self,
        keys: str | Sequence[str] | None = None,
        *additional: str,
    ) -> None:
        """Remove selected keys from local and shared context mappings.

        Args:
            keys: Context key or keys to remove, or ``None`` to clear all.
            *additional: Additional context keys to remove.
        """
        if keys is None:
            removed = set(additional)
            clear_all = not additional
        elif isinstance(keys, str):
            removed = {keys, *additional}
            clear_all = False
        else:
            removed = {*keys, *additional}
            clear_all = False
        if clear_all:
            self._context.set(_EMPTY_CONTEXT)
            self._shared_context.set(_EMPTY_CONTEXT)
            return
        local = {
            key: value
            for key, value in self._context.get().items()
            if key not in removed
        }
        shared = {
            key: value
            for key, value in self._shared_context.get().items()
            if key not in removed
        }
        self._context.set(MappingProxyType(local))
        self._shared_context.set(MappingProxyType(shared))

    def get_context(self) -> dict[str, object]:
        """Return a detached merged snapshot of active context.

        Shared values are merged first and local values take precedence.
        """
        context = dict(self._shared_context.get())
        context.update(self._context.get())
        return context

    @contextmanager
    def context(self, **values: object) -> Generator[None, None, None]:
        """Temporarily bind values and restore context on scope exit.

        Args:
            **values: Values merged over the current execution context.

        Yields:
            Control while the values are active.
        """
        current = dict(self._context.get())
        current.update(values)
        token = self._context.set(MappingProxyType(current))
        try:
            yield
        finally:
            self._context.reset(token)

    def flush_context(self) -> None:
        """Clear local and shared values in the current execution context.

        The change is scoped to the current task or thread context.
        """
        self._context.set(_EMPTY_CONTEXT)
        self._shared_context.set(_EMPTY_CONTEXT)

    def flush_shared_context(self) -> None:
        """Clear shared values without changing logger-bound local values.

        Existing task-local values remain available to the active logger.
        """
        self._shared_context.set(_EMPTY_CONTEXT)

    def flush(self) -> None:
        """Flush all currently resolved channels.

        Raises:
            LogDeliveryError: If a channel cannot flush its destination.
        """
        channels = [
            logger.channel
            for logger in self._channels.values()
            if not logger.channel.closed
        ]
        channels.extend(
            channel for channel in self._dynamic_channels if not channel.closed
        )
        for channel in channels:
            channel.flush()

    async def flush_async(self) -> None:
        """Flush resolved channels without blocking the active event loop.

        Synchronous destination work runs in AnyIO's worker pool.
        """
        await anyio.to_thread.run_sync(
            self.flush,
            abandon_on_cancel=False,
        )

    def purge(self, name: str) -> None:
        """Close and forget one cached channel.

        Args:
            name: The declared channel to release.

        Raises:
            LogDeliveryError: If the channel or a dependent stack cannot close.
        """
        with self._lock:
            logger = self._channels.pop(name, None)
            self._resolved_drivers.pop(name, None)
            self._resolved_formatters.pop(name, None)
            target = logger.channel if logger is not None else None
            dependent = (
                self._remove_dependent_channels(target)
                if target is not None
                else ()
            )
            removed_names = {name, *(channel.name for channel in dependent)}
            bridges = self._detach_bridges(removed_names)
        for bridge in bridges:
            bridge.close()
        channels_to_close = (*dependent, *((target,) if target else ()))
        if channels_to_close:
            self._close_channels(channels_to_close)

    def _remove_dependent_channels(
        self,
        target: LogChannel,
    ) -> tuple[LogChannel, ...]:
        """Forget cached and dynamic stacks that reference one channel.

        Args:
            target: A channel whose resources are being released.

        Returns:
            Removed stack channels that must also be closed.
        """
        cached = tuple(
            (name, logger)
            for name, logger in self._channels.items()
            if _channel_depends_on(logger.channel, target)
        )
        dynamic = tuple(
            channel
            for channel in self._dynamic_channels
            if _channel_depends_on(channel, target)
        )
        for name, _ in cached:
            self._channels.pop(name, None)
            self._resolved_drivers.pop(name, None)
            self._resolved_formatters.pop(name, None)
        self._dynamic_channels.difference_update(dynamic)
        return (*tuple(logger.channel for _, logger in cached), *dynamic)

    def _detach_bridges(
        self,
        channel_names: set[str],
    ) -> tuple[StandardLogBridge, ...]:
        """Remove bridges owned by channels before their resources close.

        Args:
            channel_names: Names of channels being removed.

        Returns:
            Bridges that the caller must close outside the manager lock.
        """
        keys = tuple(key for key in self._bridges if key[1] in channel_names)
        return tuple(self._bridges.pop(key) for key in keys)

    def forget_channels(self) -> None:
        """Close every cached channel while preserving configuration.

        Existing logger references become closed; a later lookup creates a
        fresh channel with the same validated configuration.
        """
        with self._lock:
            loggers = tuple(self._channels.values())
            targets = tuple(logger.channel for logger in loggers)
            dependent_dynamic = tuple(
                channel
                for channel in self._dynamic_channels
                if any(
                    _channel_depends_on(channel, target) for target in targets
                )
            )
            self._dynamic_channels.difference_update(dependent_dynamic)
            self._channels.clear()
            self._resolved_drivers.clear()
            self._resolved_formatters.clear()
        channels = (*dependent_dynamic, *targets)
        self._close_channels(channels)

    def close(self) -> None:
        """Flush and close cached and on-demand channel resources.

        Cleanup is idempotent. All channels are attempted even if one
        destination fails during shutdown.
        """
        if self._closed:
            return
        self._closed = True
        channels = [logger.channel for logger in self._channels.values()]
        channels.extend(self._dynamic_channels)
        bridges = tuple(self._bridges.values())
        self._channels.clear()
        self._resolved_drivers.clear()
        self._resolved_formatters.clear()
        self._dynamic_channels.clear()
        self._bridges.clear()
        first_error: Exception | None = None
        for bridge in bridges:
            try:
                bridge.close()
            except Exception as error:
                if first_error is None:
                    first_error = error
        try:
            self._close_channels(tuple(channels))
        except Exception as error:
            if first_error is None:
                first_error = error
        if first_error is not None:
            channel_name = "manager"
            raise LogDeliveryError(
                channel_name,
                type(first_error).__name__,
            ) from first_error

    async def aclose(self) -> None:
        """Flush and close logging resources without blocking async callers.

        Cleanup runs in AnyIO's worker pool because synchronous handlers and
        queue joins may block while pending output is finalized.
        """
        await anyio.to_thread.run_sync(
            self.close,
            abandon_on_cancel=False,
        )

    def _close_channels(self, channels: tuple[LogChannel, ...]) -> None:
        """Attempt cleanup for each unique channel and report the first error.

        Args:
            channels: Channel objects whose ownership has ended.

        Raises:
            LogDeliveryError: If any channel resource could not be closed.
        """
        first_error: Exception | None = None
        seen: set[int] = set()
        unique: list[LogChannel] = []
        for channel in channels:
            if id(channel) in seen:
                continue
            seen.add(id(channel))
            unique.append(channel)
        unique_channels = tuple(
            channel for channel in unique if not channel.closed
        )
        for channel in unique_channels:
            try:
                channel.flush()
            except Exception as error:
                if first_error is None:
                    first_error = error
        for channel in unique_channels:
            try:
                channel.close()
            except Exception as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            msg = "manager"
            raise LogDeliveryError(
                msg,
                type(first_error).__name__,
            ) from first_error

    def _create_logger(
        self,
        name: str,
        configuration: ChannelConfiguration,
        *,
        owns_channel: bool = False,
    ) -> Logger:
        """Create a native channel and logger from validated settings.

        Args:
            name: The final channel name attached to records.
            configuration: Validated driver, formatter, and threshold values.
            owns_channel: Whether the logger owns this on-demand destination.

        Returns:
            A Titanspan logger using the manager's context provider.

        Notes:
            ``owns_channel`` is reserved for independently built destinations.
        """
        driver = self._create_driver(name, configuration)
        processors = (
            *self._processors,
            RedactionProcessor(configuration.sensitive_fields),
        )
        channel = LogChannel(
            name,
            driver,
            level=configuration.level,
            processors=processors,
            emergency_driver=self._emergency,
        )
        logger = Logger(
            channel,
            context_provider=self.get_context,
            owns_channel=owns_channel,
        )
        for customizer_name in configuration.tap:
            try:
                self._customizers[customizer_name].customize(logger)
            except Exception as error:
                try:
                    channel.close()
                except Exception as cleanup_error:
                    message = (
                        f"Channel customizer {customizer_name!r} failed with "
                        f"{type(error).__name__}; cleanup failed with "
                        f"{type(cleanup_error).__name__}"
                    )
                    raise LogConfigurationError(message) from error
                message = (
                    f"Channel customizer {customizer_name!r} failed with "
                    f"{type(error).__name__}"
                )
                raise LogConfigurationError(message) from error
        return logger

    def _create_driver(
        self,
        name: str,
        configuration: ChannelConfiguration,
    ) -> LogDriver:
        """Create a native driver, resolving stack children when needed.

        Args:
            name: The final channel name attached to records.
            configuration: Validated channel settings.

        Returns:
            A registered Titanspan driver.
        """
        if configuration.driver == "stack":
            children = tuple(
                self.channel(channel_name).channel
                for channel_name in configuration.channels
            )
            driver: LogDriver = StackLogDriver(
                children,
                ignore_exceptions=configuration.ignore_exceptions,
            )
        else:
            factory = self._factories[configuration.driver]
            driver = factory(configuration)
        if configuration.background:
            return BackgroundLogDriver(
                driver,
                channel=name,
                capacity=configuration.queue_capacity,
                overflow_policy=configuration.overflow_policy,
                wait_timeout=configuration.queue_wait_timeout,
                emergency=self._emergency,
            )
        return driver

    def _validate_configuration(self) -> None:
        """Validate defaults, driver names, stack references, and cycles.

        Raises:
            LogConfigurationError: If any configured relationship is invalid.
        """
        if self._default_channel not in self.configuration.channels:
            msg = f"Default channel {self._default_channel!r} is not configured"
            raise LogConfigurationError(
                msg,
            )
        for name, channel in self.configuration.channels.items():
            self._validate_driver(channel)
            if channel.driver == "stack":
                for child in channel.channels:
                    if child not in self.configuration.channels:
                        msg = (
                            f"Stack {name!r} references unknown channel "
                            f"{child!r}"
                        )
                        raise LogConfigurationError(
                            msg,
                        )
        self._validate_stack_cycles()

    def _validate_driver(self, configuration: ChannelConfiguration) -> None:
        """Validate driver availability and required destination fields.

        Args:
            configuration: Settings for one channel.

        Raises:
            LogConfigurationError: If a driver or required option is invalid.
        """
        if configuration.driver not in self._factories and (
            configuration.driver != "stack"
        ):
            msg = f"Unknown logging driver {configuration.driver!r}"
            raise LogConfigurationError(
                msg,
            )
        if configuration.driver in {"webhook", "slack"}:
            webhook_options(configuration.options)
        for customizer_name in configuration.tap:
            if customizer_name not in self._customizers:
                message = (
                    f"Unknown logging channel customizer {customizer_name!r}"
                )
                raise LogConfigurationError(message)
        if (
            configuration.driver in {"single", "daily", "monthly", "rotating"}
            and configuration.path is None
        ):
            msg = f"Driver {configuration.driver!r} requires a path"
            raise LogConfigurationError(
                msg,
            )
        if configuration.driver == "stack" and not configuration.channels:
            msg = "A stack requires at least one channel"
            raise LogConfigurationError(msg)
        if (
            configuration.formatter not in _BUILTIN_FORMATTERS
            and configuration.formatter not in self._formatters
        ):
            message = f"Unknown logging formatter {configuration.formatter!r}"
            raise LogConfigurationError(message)

    def _create_formatter(
        self,
        configuration: ChannelConfiguration,
    ) -> LogFormatter:
        """Create the selected native formatter from channel settings.

        Args:
            configuration: Validated formatter name and output options.

        Returns:
            The Titanspan formatter selected for the channel.
        """
        if configuration.formatter in _BUILTIN_FORMATTERS:
            return create_formatter(configuration)
        return self._formatters[configuration.formatter](configuration)

    def _validate_stack_cycles(self) -> None:
        """Reject recursive stack graphs before any driver is created.

        Raises:
            LogConfigurationError: If a stack reaches itself recursively.
        """
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            """Explore one channel while tracking active graph ancestors.

            Args:
                name: The configured channel being inspected.
            """
            if name in visiting:
                msg = f"Recursive channel stack detected at {name!r}"
                raise LogConfigurationError(
                    msg,
                )
            if name in visited:
                return
            configuration = self.configuration.channels[name]
            if configuration.driver == "stack":
                visiting.add(name)
                for child in configuration.channels:
                    visit(child)
                visiting.remove(name)
            visited.add(name)

        for channel_name in self.configuration.channels:
            visit(channel_name)

    def _builtin_factories(self) -> dict[str, DriverFactory]:
        """Create the supported built-in driver factory registry.

        Returns:
            Factories for local, file, syslog, memory, and null channels.
        """
        return {
            "console": self._console_driver,
            "stdout": self._stdout_driver,
            "stderr": self._stderr_driver,
            "errorlog": self._stderr_driver,
            "single": self._single_driver,
            "daily": self._daily_driver,
            "monthly": self._monthly_driver,
            "rotating": self._rotating_driver,
            "syslog": self._syslog_driver,
            "webhook": self._webhook_driver,
            "slack": self._slack_driver,
            "memory": self._memory_driver,
            "null": lambda _: NullLogDriver(),
            "emergency": lambda _: EmergencyLogDriver(
                self._emergency_stream_value,
            ),
        }

    def _console_driver(
        self,
        configuration: ChannelConfiguration,
    ) -> StandardHandlerLogDriver:
        """Create a console driver targeting standard error.

        Args:
            configuration: Validated channel formatter options.

        Returns:
            A line-buffered standard-error driver.
        """
        return create_console_driver(
            self._create_formatter(configuration),
            stream=sys.stderr,
        )

    def _stdout_driver(
        self,
        configuration: ChannelConfiguration,
    ) -> StandardHandlerLogDriver:
        """Create a stream driver targeting standard output.

        Args:
            configuration: Validated channel formatter options.

        Returns:
            A line-buffered standard-output driver.
        """
        return create_console_driver(
            self._create_formatter(configuration),
            stream=sys.stdout,
        )

    def _stderr_driver(
        self,
        configuration: ChannelConfiguration,
    ) -> StandardHandlerLogDriver:
        """Create a stream driver targeting standard error.

        Args:
            configuration: Validated channel formatter options.

        Returns:
            A line-buffered standard-error driver.
        """
        return create_console_driver(
            self._create_formatter(configuration),
            stream=sys.stderr,
        )

    def _single_driver(
        self,
        configuration: ChannelConfiguration,
    ) -> StandardHandlerLogDriver:
        """Create a single-file driver after validated path checking.

        Args:
            configuration: Validated path and formatter options.

        Returns:
            A file handler-backed driver.
        """
        if configuration.path is None:
            msg = "The single driver requires a path"
            raise LogConfigurationError(msg)
        return create_single_file_driver(
            self._create_formatter(configuration),
            configuration.path,
        )

    def _daily_driver(
        self,
        configuration: ChannelConfiguration,
    ) -> StandardHandlerLogDriver:
        """Create a midnight-rotating file driver.

        Args:
            configuration: Validated path and retention options.

        Returns:
            A UTC time-rotating file handler-backed driver.
        """
        if configuration.path is None:
            msg = "The daily driver requires a path"
            raise LogConfigurationError(msg)
        return create_daily_file_driver(
            self._create_formatter(configuration),
            configuration.path,
            configuration.days,
        )

    def _rotating_driver(
        self,
        configuration: ChannelConfiguration,
    ) -> StandardHandlerLogDriver:
        """Create a size-based rotating file driver.

        Args:
            configuration: Validated path and rotation options.

        Returns:
            A size-rotating file handler-backed driver.
        """
        if configuration.path is None:
            msg = "The rotating driver requires a path"
            raise LogConfigurationError(msg)
        return create_rotating_file_driver(
            self._create_formatter(configuration),
            configuration.path,
            configuration.max_bytes,
            configuration.backup_count,
        )

    def _monthly_driver(
        self,
        configuration: ChannelConfiguration,
    ) -> StandardHandlerLogDriver:
        """Create a calendar-month rotating file destination.

        Args:
            configuration: Validated path and monthly retention options.

        Returns:
            A standard-handler-backed native log driver.
        """
        if configuration.path is None:
            msg = "The monthly driver requires a path"
            raise LogConfigurationError(msg)
        return create_monthly_file_driver(
            self._create_formatter(configuration),
            configuration.path,
            configuration.max_files,
        )

    def _syslog_driver(
        self,
        configuration: ChannelConfiguration,
    ) -> StandardHandlerLogDriver:
        """Create a syslog driver using a configured local or remote address.

        Args:
            configuration: Validated formatter and address options.

        Returns:
            A syslog handler-backed driver.

        Raises:
            LogConfigurationError: If the optional address has an invalid type.
        """
        address_value = configuration.options.get("address")
        if address_value is None:
            address: str | tuple[str, int] = "/dev/log"
        elif isinstance(address_value, str):
            address = address_value
        elif isinstance(address_value, tuple):
            # The options mapping holds arbitrary values, so narrow its tuple
            # elements before validating their shape and runtime types.
            parts = cast("tuple[object, ...]", address_value)
            if len(parts) != _SYSLOG_ADDRESS_PARTS:
                msg = "Invalid syslog address option"
                raise LogConfigurationError(msg)
            host: object = parts[0]
            port: object = parts[1]
            if isinstance(host, str) and type(port) is int:
                address = (host, port)
            else:
                msg = "Invalid syslog address option"
                raise LogConfigurationError(msg)
        else:
            msg = "Invalid syslog address option"
            raise LogConfigurationError(msg)
        return create_syslog_driver(
            self._create_formatter(configuration),
            address,
        )

    def _memory_driver(
        self,
        configuration: ChannelConfiguration,
    ) -> MemoryLogDriver:
        """Create a bounded memory channel for testing and local inspection.

        Args:
            configuration: Validated options containing an optional capacity.

        Returns:
            A bounded native memory driver.
        """
        capacity = configuration.options.get("max_records", 1000)
        if (
            not isinstance(capacity, int)
            or isinstance(capacity, bool)
            or capacity < 1
        ):
            msg = "Memory driver max_records must be a positive integer"
            raise LogConfigurationError(
                msg,
            )
        return MemoryLogDriver(capacity)

    def _webhook_driver(
        self,
        configuration: ChannelConfiguration,
    ) -> WebhookLogDriver:
        """Create a structured HTTP webhook destination.

        Args:
            configuration: Validated native endpoint settings.

        Returns:
            A synchronous Titanspan webhook driver.
        """
        return WebhookLogDriver(
            webhook_options(configuration.options),
        )

    def _slack_driver(
        self,
        configuration: ChannelConfiguration,
    ) -> WebhookLogDriver:
        """Create a Slack-compatible text webhook destination.

        Args:
            configuration: Validated native endpoint settings.

        Returns:
            A Titanspan driver that posts a Slack ``text`` payload.
        """
        return WebhookLogDriver(
            webhook_options(configuration.options),
            style="slack",
        )

    def getDefaultDriver(self) -> str:  # noqa: N802
        """Return the configured default channel name.

        Returns:
            The name selected as the manager's default channel.
        """
        return self.get_default_driver()

    def setDefaultDriver(self, name: str) -> None:  # noqa: N802
        """Select a default channel using Laravel-compatible spelling.

        Args:
            name: A declared channel name.
        """
        self.set_default_driver(name)

    def withContext(  # noqa: N802
        self,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Merge values into local context using Laravel method spelling.

        Args:
            context: Optional positional structured mapping.
            **values: Context values overriding matching mapping keys.
        """
        self.with_context(context, **values)

    def shareContext(  # noqa: N802
        self,
        context: Mapping[str, object] | None = None,
        **values: object,
    ) -> None:
        """Merge values into shared context using Laravel method spelling.

        Args:
            context: Optional positional structured mapping.
            **values: Context values overriding matching mapping keys.
        """
        self.share_context(context, **values)

    def withoutContext(  # noqa: N802
        self,
        keys: str | Sequence[str] | None = None,
        *additional: str,
    ) -> None:
        """Remove selected values using Laravel-compatible spelling.

        Args:
            keys: Context key or keys to remove, or ``None`` to clear all.
            *additional: Additional context keys to remove.
        """
        self.without_context(keys, *additional)

    def getContext(self) -> dict[str, object]:  # noqa: N802
        """Return a context snapshot using Laravel-compatible spelling.

        Returns:
            A detached merged context mapping.
        """
        return self.get_context()

    def sharedContext(self) -> dict[str, object]:  # noqa: N802
        """Return shared values using the Laravel-compatible method name.

        Returns:
            A detached mapping of context shared across channels.
        """
        return self.shared_context()

    def getChannels(self) -> Mapping[str, Logger]:  # noqa: N802
        """Return cached channels using Laravel-compatible spelling.

        Returns:
            A read-only snapshot of resolved native loggers.
        """
        return self.get_channels()

    def forgetChannel(self, name: str | None = None) -> None:  # noqa: N802
        """Forget a resolved channel using Laravel-compatible spelling.

        Args:
            name: Channel to forget, defaulting to the selected channel.
        """
        self.forget_channel(name)

    def flushContext(self) -> None:  # noqa: N802
        """Clear active context using Laravel-compatible spelling.

        The operation remains isolated to the current execution context.
        """
        self.flush_context()

    def flushSharedContext(self) -> None:  # noqa: N802
        """Clear shared values using Laravel-compatible spelling.

        Local logger-bound values remain unchanged.
        """
        self.flush_shared_context()

    def forgetChannels(self) -> None:  # noqa: N802
        """Close cached channels using Laravel-compatible spelling.

        A later resolution creates fresh drivers from current configuration.
        """
        self.forget_channels()

    def forgetDriver(self, name: str) -> None:  # noqa: N802
        """Close one cached destination using Laravel-compatible spelling.

        Args:
            name: The configured channel to forget.
        """
        self.purge(name)

    def __enter__(self) -> LogManager:
        """Enter a manager resource scope.

        Returns:
            This active manager.

        Raises:
            LogLifecycleError: If the manager has already been closed.
        """
        if self._closed:
            msg = "The logging manager is closed"
            raise LogLifecycleError(msg)
        return self

    def __exit__(self, *_: object) -> None:
        """Close every channel owned by the manager on scope exit.

        Resources are finalized even when the scope exits due to an error.
        """
        self.close()
