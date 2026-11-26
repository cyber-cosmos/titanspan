"""Verify native logging methods and their shared record path.

These behavior-focused tests keep manager, logger, and facade entry points
delegating to the same native record path.
"""

from __future__ import annotations

import pytest

from titanspan.facades import Log
from titanspan.logging import (
    ChannelConfiguration,
    LogLevel,
    LogManager,
    MemoryLogDriver,
)

pytestmark = pytest.mark.unit
EXPECTED_LEVELS = tuple(LogLevel)
EXPECTED_CREATED_DRIVERS = 5


def _manager_with_memory(
    driver: MemoryLogDriver,
    channels: dict[str, dict[str, object]] | None = None,
) -> LogManager:
    """Create a manager whose channels share one isolated memory sink.

    Args:
        driver: Sink observed by public API assertions.
        channels: Optional native channel configuration mapping.

    Returns:
        A manager with a default memory channel.
    """
    selected_channels = channels or {
        "default": {"driver": "memory"},
    }
    return LogManager(
        {"channels": selected_channels},
        drivers={"memory": lambda _: driver},
    )


def test_logger_exposes_all_eight_synchronous_level_methods() -> None:
    """Route named severity methods through one record contract.

    Every supported RFC level retains its native Titanspan value.
    """
    driver = MemoryLogDriver()
    logger = _manager_with_memory(driver).channel()

    logger.emergency("emergency")
    logger.alert("alert")
    logger.critical("critical")
    logger.error("error")
    logger.warning("warning")
    logger.notice("notice")
    logger.info("info")
    logger.debug("debug")

    assert tuple(record.level for record in driver.records) == EXPECTED_LEVELS


@pytest.mark.anyio
async def test_logger_exposes_all_eight_asynchronous_level_methods() -> None:
    """Keep asynchronous severity methods explicit and typed.

    Awaited writes preserve the same levels as synchronous calls.
    """
    driver = MemoryLogDriver()
    logger = _manager_with_memory(driver).channel()

    await logger.emergency_async("emergency")
    await logger.alert_async("alert")
    await logger.critical_async("critical")
    await logger.error_async("error")
    await logger.warning_async("warning")
    await logger.notice_async("notice")
    await logger.info_async("info")
    await logger.debug_async("debug")

    assert tuple(record.level for record in driver.records) == EXPECTED_LEVELS


def test_manager_methods_share_channel_and_context_state() -> None:
    """Exercise manager conveniences, channels, and execution context.

    The facade and manager must share context and channel state.
    """
    driver = MemoryLogDriver()
    manager = _manager_with_memory(
        driver,
        {
            "default": {"driver": "memory"},
            "worker": {"driver": "memory"},
        },
    )

    manager.emergency("emergency")
    manager.alert("alert")
    manager.critical("critical")
    manager.error("error")
    manager.warning("warning")
    manager.notice("notice")
    manager.info("info")
    manager.debug("debug")
    manager.with_context(request_id="request-1")
    manager.share_context(tenant_id="tenant-1")
    manager.channel("worker").info("worker")

    assert (
        tuple(record.level for record in driver.records[:8]) == EXPECTED_LEVELS
    )
    assert driver.records[-1].context == {
        "request_id": "request-1",
        "tenant_id": "tenant-1",
    }
    assert manager.get_default_channel() == "default"
    assert manager.shared_context() == {"tenant_id": "tenant-1"}
    assert manager.get_channels()["default"] is manager.channel()
    manager.set_default_channel("worker")
    assert manager.get_default_channel() == "worker"
    assert manager.channel() is manager.channel("worker")


def test_manager_build_stack_extension_and_cache_lifecycle() -> None:
    """Build channels, register drivers, and release cached resources.

    Dynamic, stacked, and named channels keep distinct ownership rules.
    """
    created: list[MemoryLogDriver] = []

    def create_driver(_: ChannelConfiguration) -> MemoryLogDriver:
        """Return a distinct sink for each independently owned channel.

        Returns:
            A fresh in-memory driver instance.
        """
        driver = MemoryLogDriver()
        created.append(driver)
        return driver

    manager = LogManager(
        {
            "channels": {
                "default": {"driver": "memory"},
                "first": {"driver": "memory"},
                "second": {"driver": "memory"},
            },
        },
        drivers={"memory": create_driver},
    )
    manager.extend("local", create_driver)
    dynamic = manager.build({"driver": "local", "name": "dynamic"})
    with dynamic:
        dynamic.info("built")
    stack = manager.stack(["first", "second"], channel="fanout")
    stack.info("stacked")
    manager.forget_channel("first")
    first_again = manager.channel("first")
    assert first_again.channel.closed is False
    manager.forget_channels()
    fresh_default = manager.channel()

    assert dynamic.channel.closed is True
    assert fresh_default.channel.closed is False
    assert len(created) == EXPECTED_CREATED_DRIVERS
    manager.close()


def test_facade_levels_and_context_resolve_the_active_manager() -> None:
    """Resolve native facade operations from the explicitly bound manager.

    Log operations resolve only from the bound manager context.
    """
    driver = MemoryLogDriver()
    manager = _manager_with_memory(
        driver,
        {
            "default": {"driver": "memory"},
            "worker": {"driver": "memory"},
        },
    )

    with Log.use(manager):
        Log.emergency("emergency")
        Log.alert("alert")
        Log.critical("critical")
        Log.error("error")
        Log.warning("warning")
        Log.notice("notice")
        Log.info("info")
        Log.debug("debug")
        Log.with_context(request_id="request-2")
        Log.share_context(tenant_id="tenant-2")
        assert Log.get_context() == {
            "request_id": "request-2",
            "tenant_id": "tenant-2",
        }
        assert Log.shared_context() == {"tenant_id": "tenant-2"}
        assert Log.get_default_channel() == "default"
        assert "default" in Log.get_channels()
        Log.set_default_channel("worker")
        Log.channel().info("selected")
        Log.flush_shared_context()

    assert (
        tuple(record.level for record in driver.records[:8]) == EXPECTED_LEVELS
    )
    assert driver.records[-1].context == {
        "request_id": "request-2",
        "tenant_id": "tenant-2",
    }


@pytest.mark.anyio
async def test_facade_exposes_all_eight_asynchronous_level_methods() -> None:
    """Write every severity through explicitly awaited facade calls.

    The facade preserves the active manager's native level values.
    """
    driver = MemoryLogDriver()
    manager = _manager_with_memory(driver)

    with Log.use(manager):
        await Log.emergency_async("emergency")
        await Log.alert_async("alert")
        await Log.critical_async("critical")
        await Log.error_async("error")
        await Log.warning_async("warning")
        await Log.notice_async("notice")
        await Log.info_async("info")
        await Log.debug_async("debug")

    assert tuple(record.level for record in driver.records) == EXPECTED_LEVELS
