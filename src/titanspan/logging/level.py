"""Define Titanspan logging levels and backend severity translation.

The public values follow RFC 5424 ordering. Private backend levels follow the
opposite threshold ordering used by Python's standard logging handlers.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from titanspan.logging.exceptions import InvalidLogLevelError


class LogLevel(StrEnum):
    """Name one of the eight standard syslog severity levels.

    Keep RFC severity values available through :attr:`severity` while exposing
    lowercase strings as stable configuration values.
    """

    EMERGENCY = "emergency"
    ALERT = "alert"
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    NOTICE = "notice"
    INFO = "info"
    DEBUG = "debug"

    @property
    def severity(self) -> int:
        """Return this level's RFC 5424 severity number.

        Returns:
            An integer from zero for emergency through seven for debug.
        """
        return _SEVERITY[self]

    @classmethod
    def parse(cls, value: LogLevel | str | int) -> LogLevel:
        """Parse a level name, an existing value, or an RFC severity number.

        Args:
            value: A case-insensitive level name or RFC severity number.

        Returns:
            The matching native severity member.

        Raises:
            ValueError: If the input is not one of the eight supported levels.
        """
        if isinstance(value, int) and not isinstance(value, bool):
            try:
                return _SEVERITY_NAMES[value]
            except KeyError as error:
                msg = f"Unsupported RFC 5424 severity: {value}"
                raise InvalidLogLevelError(
                    msg,
                ) from error
        if isinstance(value, str):
            try:
                return cls(value.casefold())
            except ValueError as error:
                msg = f"Unsupported log level: {value}"
                raise InvalidLogLevelError(
                    msg,
                ) from error
        msg = f"Unsupported log level value: {value!r}"
        raise InvalidLogLevelError(msg)


_SEVERITY: dict[LogLevel, int] = {
    LogLevel.EMERGENCY: 0,
    LogLevel.ALERT: 1,
    LogLevel.CRITICAL: 2,
    LogLevel.ERROR: 3,
    LogLevel.WARNING: 4,
    LogLevel.NOTICE: 5,
    LogLevel.INFO: 6,
    LogLevel.DEBUG: 7,
}
_SEVERITY_NAMES: dict[int, LogLevel] = {
    severity: level for level, severity in _SEVERITY.items()
}
_PYTHON_LEVELS: dict[LogLevel, int] = {
    LogLevel.EMERGENCY: logging.CRITICAL,
    LogLevel.ALERT: logging.CRITICAL,
    LogLevel.CRITICAL: logging.CRITICAL,
    LogLevel.ERROR: logging.ERROR,
    LogLevel.WARNING: logging.WARNING,
    LogLevel.NOTICE: logging.INFO,
    LogLevel.INFO: logging.INFO,
    LogLevel.DEBUG: logging.DEBUG,
}


def to_python_level(level: LogLevel | str | int) -> int:
    """Translate a Titanspan level to a standard-library level number.

    Args:
        level: A Titanspan name, enum member, or RFC severity number.

    Returns:
        A standard logging severity number suitable for handlers.

    Notes:
        Adjacent RFC levels share standard levels when Python has no native
        equivalent. The original Titanspan level stays in the structured
        record; no process-global level names are registered.
    """
    return _PYTHON_LEVELS[LogLevel.parse(level)]


def from_python_level(level: int) -> LogLevel:
    """Translate a standard-library level number into a native level.

    Args:
        level: A standard logging numeric severity.

    Returns:
        The closest Titanspan level, preserving standard threshold order.
    """
    if level >= logging.CRITICAL:
        return LogLevel.CRITICAL
    if level >= logging.ERROR:
        return LogLevel.ERROR
    if level >= logging.WARNING:
        return LogLevel.WARNING
    if level >= logging.INFO:
        return LogLevel.INFO
    return LogLevel.DEBUG
