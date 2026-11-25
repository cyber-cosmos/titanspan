"""Exercise the facade as the application-facing logging entry point.

Facade tests bind an application manager explicitly and observe native
records, context scopes, fake assertions, and lifecycle operations.
"""

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

from titanspan.facades import Log
from titanspan.logging import (
    ChannelConfiguration,
    LogLevel,
    LogManager,
    MemoryLogDriver,
)

pytestmark = pytest.mark.unit
_EXCEPTION_MESSAGE = "captured facade exception"

if TYPE_CHECKING:
    from collections.abc import Mapping


def _facade_manager() -> tuple[LogManager, list[MemoryLogDriver]]:
    """Create a manager with separately owned memory destinations.

    Returns:
        A manager and its per-channel observable drivers.
    """
    drivers: list[MemoryLogDriver] = []

    def create_driver(_: ChannelConfiguration) -> MemoryLogDriver:
        """Return a unique in-memory sink for a channel.

        Returns:
            A newly allocated test driver.
        """
        driver = MemoryLogDriver()
        drivers.append(driver)
        return driver

    channels: Mapping[str, Mapping[str, object]] = {
        name: {"driver": "memory"}
        for name in ("default", "worker", "first", "second")
    }
    manager = LogManager(
        {"channels": channels},
        drivers={"memory": create_driver},
    )
    return manager, drivers


@pytest.fixture
def active_manager() -> Iterator[tuple[LogManager, list[MemoryLogDriver]]]:
    """Bind an isolated manager for the duration of one facade test.

    Yields:
        The bound manager and all separately owned memory destinations.
    """
    manager, drivers = _facade_manager()
    try:
        with Log.use(manager):
            yield manager, drivers
    finally:
        manager.close()


def test_facade_resolves_channels_builds_stacks_and_bridges_records(
    active_manager: tuple[LogManager, list[MemoryLogDriver]],
) -> None:
    """Resolve destinations and route native and standard records.

    The facade must keep manager-owned logger identity across its aliases.
    """
    manager, drivers = active_manager
    default_logger = Log.channel()
    assert Log.manager() is manager
    assert Log.driver() is default_logger
    worker_logger = Log.driver("worker")
    assert worker_logger is manager.channel("worker")

    Log.set_default_driver("worker")
    assert Log.get_default_driver() == "worker"
    Log.setDefaultDriver("default")
    assert Log.getDefaultDriver() == "default"
    Log.log(LogLevel.NOTICE, "facade log", origin="facade")
    Log.exception(
        "facade exception",
        exception=ValueError(_EXCEPTION_MESSAGE),
    )
    assert Log.get_channels()["default"] is default_logger
    assert Log.getChannels()["default"] is default_logger

    built = Log.build({"driver": "memory", "name": "on-demand"})
    with built:
        built.info("built logger")
    stacked = Log.stack(["first", "second"], channel="fanout")
    stacked.info("stacked logger")
    bridge = Log.bridge_standard_logger(
        "titanspan.tests.facade-contract",
    )
    logging.getLogger("titanspan.tests.facade-contract").warning(
        "bridged record",
    )
    bridge.close()

    assert [record.message for record in drivers[0].records] == [
        "facade log",
        "facade exception",
        "bridged record",
    ]
    assert drivers[1].records == ()
    assert drivers[3].records[0].channel == "first"
    assert drivers[4].records[0].channel == "second"


def test_facade_context_fakes_and_cache_lifecycle(
    active_manager: tuple[LogManager, list[MemoryLogDriver]],
) -> None:
    """Restore context and expose compatibility assertion aliases.

    Fake assertions must observe records written through the active manager.
    """
    manager, _ = active_manager
    Log.with_context(request_id="request-1")
    Log.share_context(tenant_id="tenant-1")
    assert Log.get_context() == {
        "request_id": "request-1",
        "tenant_id": "tenant-1",
    }
    Log.withContext(trace_id="trace-1")
    assert Log.getContext()["trace_id"] == "trace-1"
    Log.without_context("trace_id")
    Log.withoutContext("request_id")
    assert Log.get_context() == {"tenant_id": "tenant-1"}
    Log.flush_shared_context()
    Log.flushContext()
    Log.flushSharedContext()
    assert Log.shared_context() == {}

    with Log.context(workflow_id="workflow-1"):
        Log.info("temporary context")
        assert Log.get_context() == {"workflow_id": "workflow-1"}
    assert Log.get_context() == {}

    Log.forget_channel("worker")
    Log.forgetChannel("first")
    Log.forget_channels()
    Log.forgetChannels()
    assert Log.get_channels() == {}
    Log.channel().info("fresh channel")
    Log.flush()

    with Log.fake() as fake:
        Log.assert_nothing_logged()
        Log.assertNothingLogged()
        Log.info("captured", test_case="facade")
        record = Log.assert_logged(
            "info",
            "captured",
            context={"test_case": "facade"},
        )
        assert record.message == "captured"
        assert Log.assertLogged("info", "captured") is record
        Log.assert_logged_times(1, "info", "captured")
        Log.assertLoggedTimes(1, "info", "captured")
        Log.assert_not_logged("error")
        Log.assertNotLogged("error")
        assert fake.driver.records == (record,)

    Log.flush()
    assert manager.get_channels()


def test_facade_rejects_assertions_outside_a_fake_scope() -> None:
    """Require a fake scope before using capture assertions.

    Calling an assertion without an active fake fails explicitly.
    """
    manager, _ = _facade_manager()

    with Log.use(manager), pytest.raises(RuntimeError):
        Log.assert_nothing_logged()

    manager.close()


@pytest.mark.anyio
async def test_facade_async_flush_and_close_methods_are_available() -> None:
    """Expose explicit asynchronous lifecycle and exception operations.

    Callers await completion instead of relying on unmanaged tasks.
    """
    manager, _ = _facade_manager()

    with Log.use(manager):
        await Log.log_async("info", "async record")
        await Log.exception_async(
            "async exception record",
            exception=ValueError(_EXCEPTION_MESSAGE),
        )
        await Log.flush_async()
        await Log.close_async()

    with pytest.raises(RuntimeError):
        manager.channel()
