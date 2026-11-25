"""Verify native log level semantics and backend severity translation.

These tests protect the inversion between RFC severity ordering and the
standard logging module's threshold ordering.
"""

import logging

import pytest

from titanspan.logging import (
    InvalidLogLevelError,
    LogLevel,
    from_python_level,
    to_python_level,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("name", "severity"),
    [
        ("emergency", 0),
        ("alert", 1),
        ("critical", 2),
        ("error", 3),
        ("warning", 4),
        ("notice", 5),
        ("info", 6),
        ("debug", 7),
    ],
)
def test_log_levels_match_syslog_severity_values(
    name: str,
    severity: int,
) -> None:
    """Map all standard severity names to their RFC numeric values.

    Args:
        name: The canonical lowercase severity name.
        severity: The corresponding RFC severity number.
    """
    assert LogLevel.parse(name).severity == severity


def test_python_level_mapping_reverses_threshold_order() -> None:
    """Map more severe RFC levels to higher standard levels.

    Ensure the framework can use standard handler thresholds without
    registering process-global custom level names.
    """
    mapped = [to_python_level(level) for level in LogLevel]

    assert mapped == sorted(mapped, reverse=True)
    assert to_python_level(LogLevel.DEBUG) == logging.DEBUG
    assert to_python_level(LogLevel.INFO) == logging.INFO
    assert to_python_level(LogLevel.WARNING) == logging.WARNING
    assert to_python_level(LogLevel.ERROR) == logging.ERROR
    assert to_python_level(LogLevel.CRITICAL) == logging.CRITICAL


def test_level_parser_accepts_names_and_enum_values() -> None:
    """Accept documented names and existing enum values.

    Normalize case but reject values outside the supported RFC levels.
    """
    assert LogLevel.parse("WARNING") is LogLevel.WARNING
    assert LogLevel.parse(LogLevel.INFO) is LogLevel.INFO

    with pytest.raises(InvalidLogLevelError):
        LogLevel.parse("trace")


@pytest.mark.parametrize("value", [-1, 8, 999])
def test_level_parser_rejects_out_of_range_rfc_values(value: int) -> None:
    """Reject integers outside the registered RFC severity range.

    Args:
        value: Invalid integer severity supplied by application code.
    """
    with pytest.raises(InvalidLogLevelError):
        LogLevel.parse(value)


def test_level_parser_rejects_booleans_and_unsupported_runtime_types() -> None:
    """Reject booleans and values outside the accepted level types.

    Python's boolean subclassing of integers must not alter severity parsing.
    """
    with pytest.raises(InvalidLogLevelError):
        LogLevel.parse(True)
    with pytest.raises(InvalidLogLevelError):
        LogLevel.parse(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("python_level", "expected"),
    [
        (logging.CRITICAL, LogLevel.CRITICAL),
        (logging.ERROR, LogLevel.ERROR),
        (logging.WARNING, LogLevel.WARNING),
        (logging.INFO, LogLevel.INFO),
        (logging.DEBUG, LogLevel.DEBUG),
        (logging.NOTSET, LogLevel.DEBUG),
    ],
)
def test_python_levels_translate_to_native_severity(
    python_level: int,
    expected: LogLevel,
) -> None:
    """Map standard-library thresholds to Titanspan severity values.

    Args:
        python_level: Standard-library severity number.
        expected: Closest representable Titanspan level.
    """
    assert from_python_level(python_level) is expected
