"""Verify native logging events and bound logger context behavior.

Events expose sanitized Titanspan records after successful sink delivery.
"""

from typing import TYPE_CHECKING

import pytest

from titanspan.logging import LogManager, MemoryLogDriver

if TYPE_CHECKING:
    from titanspan.logging.events import MessageLogged

pytestmark = pytest.mark.unit
SENSITIVE_TEST_VALUE = "token-value-for-redaction-test"
REDACTED_MARKER = "[REDACTED]"
EXPECTED_USER_ID = 7


def test_logger_notifies_listeners_with_a_native_delivered_record() -> None:
    """Notify listeners after the memory driver accepts a safe record.

    The event retains the framework record rather than backend event
    dictionaries or mutable exception objects.
    """
    driver = MemoryLogDriver()
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: driver},
    )
    events: list[MessageLogged] = []

    manager.channel().listen(events.append)
    manager.channel().info(
        "completed",
        context={"access_token": SENSITIVE_TEST_VALUE},
    )

    assert len(events) == 1
    assert events[0].record is driver.records[0]
    assert events[0].record.context["access_token"] == REDACTED_MARKER


def test_bound_logger_context_can_be_removed_without_mutating_parent() -> None:
    """Return a narrowed logger while preserving the original bound values.

    Bound logger changes remain local to the new wrapper and do not leak into
    concurrent or separately retained logger references.
    """
    driver = MemoryLogDriver()
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: driver},
    )
    logger = manager.channel().with_context(
        user_id=EXPECTED_USER_ID,
        request_id="req-1",
    )
    narrowed = logger.without_context("user_id")

    narrowed.info("narrowed")
    logger.info("original")

    assert "user_id" not in driver.records[0].context
    assert driver.records[1].context["user_id"] == EXPECTED_USER_ID
