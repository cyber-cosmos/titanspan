"""Verify record normalization, redaction, and bounded rendering.

Tests use the public immutable record contract and hostile object values to
ensure logging does not invoke arbitrary representations.
"""

from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID

import pytest

from titanspan.logging import (
    InvalidLogContextError,
    LogLevel,
    LogRecord,
)

pytestmark = pytest.mark.unit
MAX_LOG_TEXT_LENGTH = 16_384
MAX_CONTEXT_ITEMS = 100
UNSAFE_REPR_MESSAGE = "unsafe representation was invoked"
REDACTED_VALUE = "[REDACTED]"


class _Status(StrEnum):
    """Represent a typed string value accepted in structured context.

    The record normalizer should preserve the enum's value, not its repr.
    """

    COMPLETE = "complete"


class _UnsafeRepresentation:
    """Expose a representation that normalization must never execute.

    The logger records a safe type marker for unsupported object instances.
    """

    def __repr__(self) -> str:
        """Fail if normalization attempts to inspect the object's contents.

        Returns:
            No value; this method always raises.
        """
        raise AssertionError(UNSAFE_REPR_MESSAGE)


def _record(
    context: dict[str, object] | None = None,
    *,
    message: str = "record",
    exception: BaseException | None = None,
) -> LogRecord:
    """Create a native record for normalization-focused assertions.

    Args:
        context: Optional structured values to normalize.
        message: The original log message.
        exception: Optional exception metadata to capture.

    Returns:
        A redacted and bounded Titanspan log record.
    """
    return LogRecord.create(
        level=LogLevel.INFO,
        channel="test",
        message=message,
        context=context or {},
        exception=exception,
    )


def test_record_normalizes_supported_values_and_nested_redaction() -> None:
    """Normalize supported scalar values and redact nested credentials.

    Unsupported objects become safe markers without evaluating their repr.
    """
    result = _record(
        {
            "date": date(2026, 11, 25),
            "timestamp": datetime(2026, 11, 25, tzinfo=UTC),
            "identifier": UUID("12345678-1234-5678-1234-567812345678"),
            "state": _Status.COMPLETE,
            "payload": b"private bytes",
            "nested": [
                {"api_key": "redacted-value"},  # pragma: allowlist secret
                _UnsafeRepresentation(),
            ],
        },
    )

    assert result.context["date"] == "2026-11-25"
    assert result.context["timestamp"] == "2026-11-25T00:00:00+00:00"
    assert (
        result.context["identifier"] == "12345678-1234-5678-1234-567812345678"
    )
    assert result.context["state"] == "complete"
    assert result.context["payload"] == "<bytes:13>"
    nested = result.context["nested"]
    assert isinstance(nested, list)
    assert nested[0] == {"api_key": REDACTED_VALUE}
    assert nested[1] == (
        f"<{_UnsafeRepresentation.__module__}._UnsafeRepresentation>"
    )


def test_record_rejects_naive_nested_datetimes() -> None:
    """Reject ambiguous timestamps before record serialization.

    Datetime values must carry timezone information to enter context.
    """
    with pytest.raises(InvalidLogContextError, match="timezone-aware"):
        _record({"timestamp": datetime.fromisoformat("2026-11-25")})


def test_record_bounds_depth_item_count_and_text() -> None:
    """Bound recursive structures and oversized log payloads.

    Truncation keeps serialization predictable for untrusted values.
    """
    nested: object = "bottom"
    for _ in range(10):
        nested = [nested]
    long_message = "m" * (MAX_LOG_TEXT_LENGTH + 1)
    many_values = list(range(MAX_CONTEXT_ITEMS + 1))

    result = _record(
        {"deep": nested, "many": many_values, "non_finite": float("inf")},
        message=long_message,
    )

    assert result.message.endswith("[TRUNCATED]")
    assert len(result.message) < MAX_LOG_TEXT_LENGTH * 2
    assert result.context["non_finite"] == "inf"
    many = result.context["many"]
    assert isinstance(many, list)
    assert many[-1] == "[TRUNCATED]"
    assert result.context["deep"] == [[[[[[[["[TRUNCATED]"]]]]]]]]


def test_record_escapes_control_characters_and_keeps_snapshot_detached() -> (
    None
):
    """Prevent forged multiline output and later caller mutation.

    Record construction snapshots and escapes values before delivery.
    """
    context: dict[str, object] = {
        "nested": {"items": ["original"]},
    }
    result = _record(
        context,
        message="line one\nline two\r\x1b",
    )
    context["nested"] = {"items": ["changed"]}

    assert result.message == r"line one\nline two\r\x1b"
    assert result.context["nested"] == {"items": ["original"]}
    timestamp = result.to_dict()["timestamp"]
    assert isinstance(timestamp, str)
    assert timestamp.endswith("Z")


def test_record_exception_is_bounded_and_survives_channel_copy() -> None:
    """Keep exception diagnostics and timestamp stable across routing.

    Channel copies preserve the captured metadata without retaining errors.
    """
    result = _record(
        {"access_token": "credential-marker"},
        exception=ValueError("processing failed"),
    )
    routed = result.with_channel("worker")
    mapping = result.to_dict()

    assert result.context["access_token"] == REDACTED_VALUE
    assert result.exception is not None
    assert result.exception["type"] == "ValueError"
    assert "processing failed" in result.exception["traceback"]
    assert routed.channel == "worker"
    assert routed.timestamp == result.timestamp
    assert mapping["exception"] == dict(result.exception)


def test_record_context_updates_reapply_sensitive_field_rules() -> None:
    """Reapply sensitive field rules to immutable context updates.

    The original record remains unchanged after a routed context merge.
    """
    original = _record({"status": "waiting"})
    updated = original.with_context(
        {
            "status": "complete",
            "client_secret": "marker",  # pragma: allowlist secret
        },
    )

    assert original.context == {"status": "waiting"}
    assert updated.context == {
        "status": "complete",
        "client_secret": "[REDACTED]",
    }
