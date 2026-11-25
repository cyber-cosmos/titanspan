"""Verify explicit bridging from Python logging into native channels.

Tests use named standard-library loggers and restore their mutable process
state so bridge lifecycle behavior is isolated from other tests.
"""

from __future__ import annotations

import logging
from io import StringIO
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from titanspan.logging import LogManager, MemoryLogDriver

if TYPE_CHECKING:
    from titanspan.logging.events import MessageLogged

pytestmark = pytest.mark.integration


def test_standard_bridge_preserves_logger_configuration_and_handlers() -> None:
    """Capture records without reconfiguring the source logger.

    Existing handlers still receive their normal formatted output.
    """
    logger_name = f"tests.bridge.{uuid4().hex}"
    standard_logger = logging.getLogger(logger_name)
    stream = StringIO()
    existing_handler = logging.StreamHandler(stream)
    old_handlers = tuple(standard_logger.handlers)
    old_level = standard_logger.level
    old_propagate = standard_logger.propagate
    sink = MemoryLogDriver()
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: sink},
    )

    try:
        standard_logger.handlers[:] = [existing_handler]
        standard_logger.setLevel(logging.WARNING)
        standard_logger.propagate = False
        bridge = manager.bridge_standard_logger(logger_name)
        standard_logger.warning("database unavailable")

        assert standard_logger.handlers[0] is existing_handler
        assert standard_logger.level == logging.WARNING
        assert standard_logger.propagate is False
        assert len(sink.records) == 1
        assert sink.records[0].message == "database unavailable"
        assert "database unavailable" in stream.getvalue()

        bridge.close()
        standard_logger.warning("after close")
        assert len(sink.records) == 1
        assert standard_logger.handlers == [existing_handler]
    finally:
        manager.close()
        existing_handler.close()
        standard_logger.handlers[:] = old_handlers
        standard_logger.setLevel(old_level)
        standard_logger.propagate = old_propagate


def test_standard_bridge_prevents_recursive_capture() -> None:
    """Avoid routing listener-created records back into the same channel.

    The recursion guard prevents duplicate delivery to the native sink.
    """
    logger_name = f"tests.bridge.recursive.{uuid4().hex}"
    standard_logger = logging.getLogger(logger_name)
    old_handlers = tuple(standard_logger.handlers)
    old_level = standard_logger.level
    old_propagate = standard_logger.propagate
    sink = MemoryLogDriver()
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: sink},
    )

    def emit_nested_record(event: MessageLogged) -> None:
        """Attempt a recursive standard-library log from a listener.

        Args:
            event: Native event emitted after the outer record is handled.
        """
        if event.record.message == "outer":
            standard_logger.warning("nested")

    try:
        standard_logger.handlers.clear()
        standard_logger.setLevel(logging.DEBUG)
        standard_logger.propagate = False
        manager.bridge_standard_logger(logger_name)
        manager.channel().listen(emit_nested_record)
        standard_logger.warning("outer")

        assert [record.message for record in sink.records] == ["outer"]
    finally:
        manager.close()
        standard_logger.handlers[:] = old_handlers
        standard_logger.setLevel(old_level)
        standard_logger.propagate = old_propagate
