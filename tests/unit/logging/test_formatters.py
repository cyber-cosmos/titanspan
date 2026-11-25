"""Verify native output formats preserve safe structured record data.

Formatters are tested directly and through real standard-library handlers in
the integration suite.
"""

import json

import pytest

from titanspan.logging import (
    ConsoleLogFormatter,
    JsonLogFormatter,
    LogLevel,
    LogRecord,
    TextLogFormatter,
)

pytestmark = pytest.mark.unit


def test_json_formatter_emits_native_record_schema() -> None:
    """Render each stable record field as a machine-readable JSON value.

    The formatter handles the mapping proxy used by immutable record context.
    """
    record = LogRecord.create(
        level=LogLevel.INFO,
        channel="workflows",
        message="node completed",
        context={"workflow_id": "wf-1", "duration_ms": 25},
    )

    rendered = json.loads(JsonLogFormatter().format(record))

    assert rendered["level"] == "info"
    assert rendered["channel"] == "workflows"
    assert rendered["context"] == {
        "workflow_id": "wf-1",
        "duration_ms": 25,
    }
    assert rendered["timestamp"].endswith("Z")


def test_text_formatters_keep_messages_on_one_physical_line() -> None:
    """Escape line breaks and controls before human-readable rendering.

    JSON formatting remains valid while text output cannot forge records.
    """
    record = LogRecord.create(
        level=LogLevel.WARNING,
        channel="security",
        message="blocked\nFAKE ERROR\x1b[31m",
        context={"cookie": "private", "result": ["ok", 3]},
    )

    text = TextLogFormatter().format(record)
    console = ConsoleLogFormatter(color=False).format(record)

    assert "\n" not in text
    assert "\x1b" not in text
    assert "FAKE ERROR" in text
    assert "[REDACTED]" in console
    assert "\n" not in console


def test_console_formatter_color_is_explicit_and_optional() -> None:
    """Emit ANSI color only when explicitly requested or detected.

    Captured stream output can disable color deterministically.
    """
    record = LogRecord.create(
        level=LogLevel.ERROR,
        channel="app",
        message="failed",
        context={},
    )

    plain = ConsoleLogFormatter(color=False).format(record)
    colored = ConsoleLogFormatter(color=True).format(record)

    assert "\x1b[" not in plain
    assert "\x1b[" in colored
