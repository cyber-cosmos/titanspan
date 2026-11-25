"""Verify stack delivery ordering, partial failure, and native outcomes.

Stacks are exercised through real manager-created child channels so tests
cover channel processing and resource coordination together.
"""

from io import StringIO

import pytest

from titanspan.logging import (
    DeliveryStatus,
    LogDeliveryError,
    LogManager,
    MemoryLogDriver,
    MessageLogged,
    StackLogDriver,
)
from titanspan.logging.record import LogRecord

pytestmark = pytest.mark.unit
CHILD_FAILURE_MESSAGE = "child failed"


class _FailingDriver(MemoryLogDriver):
    """Raise predictable destination errors for one stack child.

    The sink provides deterministic failure behavior for fanout tests.
    """

    def write(self, record: LogRecord) -> None:
        """Reject a write to exercise stack failure policy.

        Args:
            record: The record that would otherwise be persisted.
        """
        del record
        raise RuntimeError(CHILD_FAILURE_MESSAGE)


def test_stack_ignores_child_failure_and_records_safe_diagnostic() -> None:
    """Continue fanout after a child failure and mark partial delivery.

    The failure diagnostic contains only the channel and exception type.
    """
    healthy = MemoryLogDriver()
    manager = LogManager(
        {
            "channels": {
                "default": {
                    "driver": "stack",
                    "channels": ["broken", "healthy"],
                    "ignore_exceptions": True,
                },
                "broken": {"driver": "broken"},
                "healthy": {"driver": "healthy"},
            },
        },
        drivers={
            "broken": lambda _: _FailingDriver(),
            "healthy": lambda _: healthy,
        },
        emergency_stream=StringIO(),
    )
    logger = manager.channel()
    events: list[MessageLogged] = []
    logger.listen(events.append)

    logger.info("fanout")

    stack_driver = logger.channel.driver
    assert isinstance(stack_driver, StackLogDriver)
    assert healthy.records[0].message == "fanout"
    assert healthy.records[0].channel == "healthy"
    assert stack_driver.failures == ("broken:LogDeliveryError",)
    assert events[0].status is DeliveryStatus.PARTIAL
    manager.close()


def test_stack_propagates_child_failure_when_not_configured_to_ignore() -> None:
    """Propagate child failures when the stack policy requires it.

    The caller receives a Titanspan delivery exception.
    """
    manager = LogManager(
        {
            "channels": {
                "default": {"driver": "stack", "channels": ["broken"]},
                "broken": {"driver": "broken"},
            },
        },
        drivers={"broken": lambda _: _FailingDriver()},
        emergency_stream=StringIO(),
    )
    logger = manager.channel()

    with pytest.raises(LogDeliveryError):
        logger.error("must reach caller")

    manager.close()


@pytest.mark.anyio
async def test_on_demand_stack_forwards_async_writes_in_order() -> None:
    """Await child deliveries in order and retain destination channels.

    Each child observes the same message under its own channel name.
    """
    first = MemoryLogDriver()
    second = MemoryLogDriver()
    drivers = iter((first, second))
    manager = LogManager(
        {
            "channels": {
                "default": {"driver": "null"},
                "first": {"driver": "memory"},
                "second": {"driver": "memory"},
            },
        },
        drivers={"memory": lambda _: next(drivers)},
    )
    logger = manager.stack(["first", "second"], channel="combined")

    await logger.info_async("async fanout")
    await manager.aclose()

    assert [record.channel for record in first.records] == ["first"]
    assert [record.channel for record in second.records] == ["second"]
    assert first.records[0].message == "async fanout"
    assert second.records[0].message == "async fanout"
