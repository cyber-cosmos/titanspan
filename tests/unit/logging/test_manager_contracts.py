"""Exercise channel management, validation, and resource contracts.

These tests use real in-memory drivers so public manager operations are
verified through the native channel and record lifecycle.
"""

from collections.abc import Mapping
from typing import TYPE_CHECKING

import pytest

from titanspan.facades import Log
from titanspan.logging import (
    ChannelConfiguration,
    LogChannelNotFoundError,
    LogConfigurationError,
    LogContextError,
    LogDeliveryError,
    Logger,
    LogLevel,
    LogLifecycleError,
    LogManager,
    MemoryLogDriver,
    MessageLogged,
)
from titanspan.logging.formatters import JsonLogFormatter

if TYPE_CHECKING:
    from titanspan.contracts.logging import LoggingManager, LogWriter

pytestmark = pytest.mark.unit
SCOPE_FAILURE_MESSAGE = "scope failed"
APPLICATION_FAILURE_MESSAGE = "application failed"
DRIVER_FAILURE_MESSAGE = "flush failed"
CUSTOMIZER_FAILURE_MESSAGE = "customization failed"


def _make_manager(
    driver: MemoryLogDriver | None = None,
    *,
    channels: Mapping[str, Mapping[str, object]] | None = None,
) -> tuple[LogManager, MemoryLogDriver]:
    """Build an isolated manager backed by one observable memory sink.

    Args:
        driver: Optional sink shared by every configured channel.
        channels: Optional native channel configurations.

    Returns:
        The manager and the sink receiving records.
    """
    selected_driver = driver or MemoryLogDriver()
    selected_channels = channels or {
        "default": {"driver": "memory"},
        "worker": {"driver": "memory"},
    }
    manager = LogManager(
        {"channels": selected_channels},
        drivers={"memory": lambda _: selected_driver},
    )
    return manager, selected_driver


def _unused_memory_driver_factory(
    _: ChannelConfiguration,
) -> MemoryLogDriver:
    """Return a typed callback for validation paths that reject registration.

    Args:
        _: Configuration ignored by tests that fail before factory use.

    Returns:
        A new in-memory driver if a future test path invokes the callback.
    """
    return MemoryLogDriver()


def _write_then_fail(manager: LogManager) -> None:
    """Write inside temporary context and raise to exercise restoration.

    Args:
        manager: Manager whose local context must be restored.
    """
    with manager.context(request_id="temporary"):
        manager.log("info", "within scope")
        raise RuntimeError(SCOPE_FAILURE_MESSAGE)


def _fail_inside_manager_scope(manager: LogManager) -> None:
    """Raise inside a manager context after writing one record.

    Args:
        manager: Manager whose resources must close during unwinding.
    """
    with manager as active_manager:
        assert active_manager is manager
        active_manager.info("before failure")
        raise ValueError(APPLICATION_FAILURE_MESSAGE)


def test_manager_context_and_channel_operations_share_state() -> None:
    """Keep context and cached channels on shared manager state.

    Each channel should observe the manager's current context.
    """
    drivers: list[MemoryLogDriver] = []

    def create_driver(_: ChannelConfiguration) -> MemoryLogDriver:
        """Create independently owned destinations for named channels.

        Returns:
            A fresh in-memory logging driver.
        """
        driver = MemoryLogDriver()
        drivers.append(driver)
        return driver

    manager = LogManager(
        {
            "channels": {
                "default": {"driver": "memory"},
                "worker": {"driver": "memory"},
            },
        },
        drivers={"memory": create_driver},
    )
    manager.with_context(
        {"request_id": "mapping", "remove": "local"},
        request_id="keyword",
        local_only=True,
    )
    manager.share_context(
        {"tenant_id": "mapping", "remove_shared": True},
        tenant_id="keyword",
    )
    manager.info("contextual")
    driver = drivers[0]

    assert driver.records[0].context == {
        "request_id": "keyword",
        "local_only": True,
        "remove": "local",
        "tenant_id": "keyword",
        "remove_shared": True,
    }
    assert manager.get_context() == {
        "request_id": "keyword",
        "local_only": True,
        "remove": "local",
        "tenant_id": "keyword",
        "remove_shared": True,
    }
    assert manager.shared_context() == {
        "tenant_id": "keyword",
        "remove_shared": True,
    }

    manager.without_context(
        ["local_only", "remove_shared", "remove"],
        "tenant_id",
    )
    assert manager.get_context() == {"request_id": "keyword"}
    manager.without_context(None, "request_id")
    assert manager.get_context() == {}

    manager.with_context(trace_id="trace-1")
    manager.share_context(tenant_id="tenant-1")
    manager.flush_shared_context()
    assert manager.get_context() == {"trace_id": "trace-1"}
    manager.flush_context()
    assert manager.shared_context() == {}

    default_logger = manager.channel()
    worker_logger = manager.channel("worker")
    assert manager.get_channels() == {
        "default": default_logger,
        "worker": worker_logger,
    }
    manager.set_default_channel("worker")
    assert manager.get_default_channel() == "worker"
    assert manager.channel() is worker_logger
    manager.forget_channel("worker")
    assert worker_logger.channel.closed
    manager.set_default_channel("default")
    manager.forget_channel()
    assert manager.get_channels() == {}
    manager.close()


def test_manager_writes_and_restores_context_after_failure() -> None:
    """Write records and restore context after raised errors.

    Temporary context must not leak into later logging operations.
    """
    manager, driver = _make_manager()
    manager.log("notice", "through log", context={"source": "direct"})

    with pytest.raises(RuntimeError, match=SCOPE_FAILURE_MESSAGE):
        _write_then_fail(manager)

    manager.log(LogLevel.INFO, "after scope")

    assert [record.message for record in driver.records] == [
        "through log",
        "within scope",
        "after scope",
    ]
    assert driver.records[1].context == {"request_id": "temporary"}
    assert driver.records[2].context == {}


def test_manager_rejects_unknown_default_and_invalid_stack_graphs() -> None:
    """Reject invalid channel references before opening destinations.

    Missing references and recursive stacks fail during configuration.
    """
    with pytest.raises(LogConfigurationError, match="Default channel"):
        LogManager(
            {
                "default": "missing",
                "channels": {"default": {"driver": "null"}},
            },
        )

    with pytest.raises(LogConfigurationError, match="unknown channel"):
        LogManager(
            {
                "channels": {
                    "default": {
                        "driver": "stack",
                        "channels": ["missing"],
                    },
                },
            },
        )

    with pytest.raises(LogConfigurationError, match="Recursive"):
        LogManager(
            {
                "channels": {
                    "default": {
                        "driver": "stack",
                        "channels": ["default"],
                    },
                },
            },
        )


def test_manager_extension_validation_and_resolved_driver_protection() -> None:
    """Validate extension names and protect active registrations.

    Resolved driver factories cannot be replaced underneath live channels.
    """
    manager, _ = _make_manager()
    manager_contract: LoggingManager = manager
    logger_contract: LogWriter = manager.channel()
    assert manager_contract.channel() is logger_contract

    with pytest.raises(LogConfigurationError, match="driver name"):
        manager.extend(" custom", _unused_memory_driver_factory)
    with pytest.raises(LogConfigurationError, match="formatter name"):
        manager.extend_formatter(" custom", lambda _: JsonLogFormatter())

    manager.channel()
    with pytest.raises(LogConfigurationError, match="already used"):
        manager.extend("memory", _unused_memory_driver_factory)
    with pytest.raises(LogConfigurationError, match="reserved"):
        manager.extend_formatter("json", lambda _: JsonLogFormatter())

    manager.close()


def test_dynamic_channel_validation_and_manager_closed_errors() -> None:
    """Reject malformed dynamic channels and post-shutdown operations.

    Lifecycle errors use Titanspan-owned exceptions at the public boundary.
    """
    manager, _ = _make_manager()

    with pytest.raises(LogConfigurationError):
        manager.build({"driver": "memory", "unsupported": True})
    with pytest.raises(LogConfigurationError, match="Unknown logging driver"):
        manager.build({"driver": "unknown"})

    manager.close()
    manager.close()
    with pytest.raises(LogLifecycleError):
        manager.channel()
    with pytest.raises(LogLifecycleError):
        manager.build({"driver": "memory"})
    with pytest.raises(LogLifecycleError):
        manager.__enter__()


def test_manager_context_manager_closes_on_exception() -> None:
    """Release manager-owned resources when a scope raises.

    The exception leaves the scope only after the driver is closed.
    """
    driver = MemoryLogDriver()
    manager, _ = _make_manager(driver)
    logger = manager.channel()

    with pytest.raises(ValueError, match=APPLICATION_FAILURE_MESSAGE):
        _fail_inside_manager_scope(manager)

    assert driver.records[0].message == "before failure"
    assert logger.channel.closed


class _FlushFailureDriver(MemoryLogDriver):
    """Fail manager flushing to exercise cleanup error translation.

    The inherited in-memory behavior remains available for write checks.
    """

    def flush(self) -> None:
        """Raise a deterministic destination failure during cleanup.

        The manager must still attempt to close this driver.
        """
        raise RuntimeError(DRIVER_FAILURE_MESSAGE)


def test_manager_shutdown_reports_driver_flush_errors() -> None:
    """Close after a flush failure and surface a native error.

    Resource release remains required even when flushing cannot complete.
    """
    driver = _FlushFailureDriver()
    manager, _ = _make_manager(driver)
    logger = manager.channel()

    with pytest.raises(LogDeliveryError, match="manager"):
        manager.close()

    assert logger.channel.closed


def test_manager_bridge_validation_cache_and_purge_lifecycle() -> None:
    """Validate bridge names and release cached handles during purge.

    Repeated requests for one logger reuse the same active bridge object.
    """
    manager, _ = _make_manager()
    with pytest.raises(LogConfigurationError, match="logger name"):
        manager.bridge_standard_logger(" padded ")

    first = manager.bridge_standard_logger("titanspan.test.manager")
    assert manager.bridge_standard_logger("titanspan.test.manager") is first
    manager.purge("default")
    assert first.closed
    manager.close()


def test_channel_customizers_run_once_and_receive_native_loggers() -> None:
    """Apply registered channel customizers once after channel creation.

    A customizer can use the native logger listener contract without backend
    handler or logger objects.
    """
    events: list[MessageLogged] = []

    class EventCustomizer:
        """Attach an event listener to a native channel logger.

        The manager calls this object only when it constructs a channel.
        """

        def __init__(self) -> None:
            """Initialize a count of logger customizations.

            The same cached channel must not invoke this object twice.
            """
            self.calls = 0

        def customize(self, logger: Logger) -> None:
            """Attach a listener and count this channel initialization.

            Args:
                logger: Native logger being initialized by the manager.
            """
            self.calls += 1
            logger.listen(events.append)

    customizer = EventCustomizer()
    manager = LogManager(
        {
            "channels": {
                "default": {
                    "driver": "memory",
                    "tap": ["events"],
                },
            },
        },
        customizers={"events": customizer},
    )
    logger = manager.channel()

    assert manager.channel() is logger
    assert customizer.calls == 1
    logger.info("customized")
    assert events[0].record.message == "customized"
    manager.close()


def test_failed_customizer_closes_unpublished_channel_resources() -> None:
    """Close driver resources when channel customization fails.

    A failed tap must not leave an uncached channel or sink behind.
    """
    driver = MemoryLogDriver()

    class FailedCustomizer:
        """Raise a stable error while configuring the new logger.

        The manager must close the unpublished channel after this failure.
        """

        def customize(self, logger: Logger) -> None:
            """Fail the tap after channel resources have been created.

            Args:
                logger: Native logger not returned to the caller.
            """
            del logger
            raise RuntimeError(CUSTOMIZER_FAILURE_MESSAGE)

    manager = LogManager(
        {
            "channels": {
                "default": {
                    "driver": "memory",
                    "tap": ["failure"],
                },
            },
        },
        drivers={"memory": lambda _: driver},
        customizers={"failure": FailedCustomizer()},
    )

    with pytest.raises(
        LogConfigurationError,
        match="Channel customizer 'failure' failed with RuntimeError",
    ):
        manager.channel()

    assert driver.closed
    manager.close()


def test_manager_rejects_unknown_channel_customizers() -> None:
    """Validate tap names before any channel driver is opened.

    Misspelled customization references must fail during manager setup.
    """
    with pytest.raises(LogConfigurationError, match="customizer"):
        LogManager(
            {
                "channels": {
                    "default": {
                        "driver": "null",
                        "tap": ["missing"],
                    },
                },
            },
        )


def test_manager_missing_channel_and_invalid_default_are_explicit() -> None:
    """Report unresolved channel names instead of selecting a fallback.

    A missing configured default is an explicit manager error.
    """
    manager, _ = _make_manager()

    with pytest.raises(LogChannelNotFoundError):
        manager.channel("absent")
    with pytest.raises(LogChannelNotFoundError):
        manager.set_default_channel("absent")

    manager.close()


def test_facade_lifecycle_errors_are_titanspan_owned() -> None:
    """Expose a native context error when no facade scope is bound.

    The facade does not use a global active manager as a fallback.
    """
    manager, _ = _make_manager()

    with Log.use(manager):
        assert Log.manager() is manager
    with pytest.raises(LogContextError):
        Log.manager()
    manager.close()
