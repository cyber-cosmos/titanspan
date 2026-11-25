"""Represent sanitized structured logging events owned by Titanspan.

Only explicitly supported values are converted. Unknown application objects
are represented by type name rather than invoking arbitrary representations.
"""

from __future__ import annotations

import traceback
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import TYPE_CHECKING, cast
from uuid import UUID

from titanspan.logging.exceptions import InvalidLogContextError

if TYPE_CHECKING:
    from titanspan.logging.level import LogLevel

type LogValue = (
    str | int | float | bool | None | list["LogValue"] | dict[str, "LogValue"]
)

_MAX_DEPTH = 8
_MAX_ITEMS = 100
_MAX_TEXT_LENGTH = 16_384
_TRUNCATED = "[TRUNCATED]"
_REDACTED = "[REDACTED]"
DEFAULT_SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "secret",
        "token",
        "apikey",
        "authorization",
        "cookie",
        "privatekey",
        "accesstoken",
        "refreshtoken",
        "clientsecret",
    },
)


def _type_name(value: object) -> str:
    """Return a stable short name without invoking the object's repr.

    Args:
        value: An unsupported application value.

    Returns:
        A module-qualified class name suitable for safe diagnostics.
    """
    value_type = type(value)
    return f"<{value_type.__module__}.{value_type.__qualname__}>"


def _normalize_value(value: object, depth: int = 0) -> LogValue:
    """Convert supported values into bounded JSON-compatible structures.

    Args:
        value: The input value from application context.
        depth: Current recursive nesting depth.

    Returns:
        A copied primitive or bounded collection.

    Notes:
        The depth and item limits constrain recursive or oversized payloads.
    """
    if depth > _MAX_DEPTH:
        return _TRUNCATED
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and len(value) > _MAX_TEXT_LENGTH:
            return value[:_MAX_TEXT_LENGTH] + _TRUNCATED
        return value
    if isinstance(value, float):
        return value if isfinite(value) else str(value)
    return _normalize_complex_value(value, depth)


def _normalize_complex_value(value: object, depth: int) -> LogValue:
    """Normalize non-primitive values and bounded containers.

    Args:
        value: A non-primitive context value.
        depth: Current recursive nesting depth.

    Returns:
        A bounded JSON-compatible value or a safe type marker.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "Nested datetime values must be timezone-aware"
            raise InvalidLogContextError(
                msg,
            )
        return value.astimezone(UTC).isoformat()
    if isinstance(value, (date, UUID)):
        return value.isoformat() if isinstance(value, date) else str(value)
    if isinstance(value, Enum):
        enum_value: object = value.value
        return _normalize_value(enum_value, depth + 1)
    if isinstance(value, Mapping):
        # Runtime ABC checks erase generic arguments, so contain that boundary.
        mapping = cast("Mapping[object, object]", value)
        return _normalize_mapping(mapping, depth)
    if isinstance(value, (bytes, bytearray, memoryview)):
        size = value.nbytes if isinstance(value, memoryview) else len(value)
        return f"<bytes:{size}>"
    if isinstance(value, Sequence) and not isinstance(value, str):
        # Runtime ABC checks erase generic arguments, so contain that boundary.
        sequence = cast("Sequence[object]", value)
        return _normalize_sequence(sequence, depth)
    return _type_name(value)


def _normalize_mapping(
    value: Mapping[object, object],
    depth: int,
) -> dict[str, LogValue]:
    """Copy a bounded mapping while validating string keys.

    Args:
        value: A mapping whose keys must be strings.
        depth: Parent nesting depth.

    Returns:
        A plain dictionary with normalized values.

    Raises:
        InvalidLogContextError: If any context key is not a string.
    """
    normalized: dict[str, LogValue] = {}
    for index, key in enumerate(value):
        if index >= _MAX_ITEMS:
            normalized["_titanspan_truncated"] = True
            break
        if not isinstance(key, str):
            msg = "Log context mapping keys must be strings"
            raise InvalidLogContextError(
                msg,
            )
        item: object = value[key]
        normalized[key] = _normalize_value(item, depth + 1)
    return normalized


def _normalize_sequence(
    value: Sequence[object],
    depth: int,
) -> list[LogValue]:
    """Copy a bounded sequence without materializing an unbounded iterator.

    Args:
        value: A sized sequence excluding strings and byte buffers.
        depth: Parent nesting depth.

    Returns:
        Normalized values with a truncation marker when needed.
    """
    normalized: list[LogValue] = []
    item_count = min(len(value), _MAX_ITEMS)
    for index in range(item_count):
        item: object = value[index]
        normalized.append(_normalize_value(item, depth + 1))
    if len(value) > _MAX_ITEMS:
        normalized.append(_TRUNCATED)
    return normalized


def _normalized_key(key: str) -> str:
    """Normalize field names for default secret matching.

    Args:
        key: An input mapping key.

    Returns:
        Lowercase ASCII letters and digits only.
    """
    return "".join(
        character for character in key.casefold() if character.isalnum()
    )


def _redact_value(
    value: LogValue,
    sensitive_fields: frozenset[str],
) -> LogValue:
    """Recursively replace configured sensitive mapping values.

    Args:
        value: A normalized value.
        sensitive_fields: Names that must not leave the logger boundary.

    Returns:
        A copied value with matching fields redacted.
    """
    if isinstance(value, dict):
        redacted: dict[str, LogValue] = {}
        for key, item in value.items():
            normalized = _normalized_key(key)
            if any(field in normalized for field in sensitive_fields):
                redacted[key] = _REDACTED
            else:
                redacted[key] = _redact_value(item, sensitive_fields)
        return redacted
    if isinstance(value, list):
        return [_redact_value(item, sensitive_fields) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class LogRecord:
    """Describe one sanitized application log event.

    Attributes:
        timestamp: A timezone-aware UTC creation timestamp.
        level: The original Titanspan severity before backend translation.
        channel: The named output channel for this record.
        message: A bounded message with control characters escaped.
        context: A copied structured mapping with sensitive values redacted.
        exception: Optional bounded exception metadata without frame locals.
    """

    timestamp: datetime
    level: LogLevel
    channel: str
    message: str
    context: Mapping[str, LogValue]
    exception: Mapping[str, str] | None = None

    @classmethod
    def create(
        cls,
        *,
        level: LogLevel,
        channel: str,
        message: str,
        context: Mapping[str, object],
        exception: BaseException | None = None,
        sensitive_fields: frozenset[str] = DEFAULT_SENSITIVE_FIELDS,
    ) -> LogRecord:
        """Build a bounded, copied, redacted record.

        Args:
            level: The original RFC severity level.
            channel: The configured channel name.
            message: The developer-supplied message.
            context: Context assembled from active execution scopes.
            exception: An optional exception whose frames are not retained.
            sensitive_fields: Normalized names to redact recursively.

        Returns:
            A record whose structured values no longer alias caller mappings.

        Raises:
            InvalidLogContextError: If keys or nested datetimes are invalid.
        """
        copied = _normalize_value(context)
        if not isinstance(copied, dict):
            msg = "Log context must be a mapping"
            raise InvalidLogContextError(msg)
        redacted = _redact_value(copied, sensitive_fields)
        if not isinstance(redacted, dict):
            msg = "Log context must normalize to a mapping"
            raise InvalidLogContextError(
                msg,
            )
        exception_data = _exception_data(exception)
        safe_message = _sanitize_text(message)
        return cls(
            timestamp=datetime.now(UTC),
            level=level,
            channel=channel,
            message=safe_message,
            context=MappingProxyType(redacted),
            exception=(
                MappingProxyType(exception_data)
                if exception_data is not None
                else None
            ),
        )

    def with_channel(self, channel: str) -> LogRecord:
        """Return a copy routed to a child channel.

        Args:
            channel: The child destination name.

        Returns:
            A new record with the same timestamp, message, and context.
        """
        return LogRecord(
            timestamp=self.timestamp,
            level=self.level,
            channel=channel,
            message=self.message,
            context=self.context,
            exception=self.exception,
        )

    def with_context(
        self,
        context: Mapping[str, object],
        *,
        sensitive_fields: frozenset[str] = DEFAULT_SENSITIVE_FIELDS,
    ) -> LogRecord:
        """Return a record with merged and re-sanitized context.

        Args:
            context: New values that override existing context keys.
            sensitive_fields: Normalized field names to redact.

        Returns:
            A new record preserving the original timestamp and message.
        """
        merged: dict[str, object] = dict(self.context)
        merged.update(context)
        normalized = _normalize_value(merged)
        if not isinstance(normalized, dict):
            msg = "Log context must normalize to a mapping"
            raise InvalidLogContextError(
                msg,
            )
        redacted = _redact_value(normalized, sensitive_fields)
        if not isinstance(redacted, dict):
            msg = "Log context must normalize to a mapping"
            raise InvalidLogContextError(
                msg,
            )
        return LogRecord(
            timestamp=self.timestamp,
            level=self.level,
            channel=self.channel,
            message=self.message,
            context=MappingProxyType(redacted),
            exception=self.exception,
        )

    def to_dict(self) -> dict[str, object]:
        """Return a detached JSON-compatible representation.

        Returns:
            A plain dictionary using stable native field names and values.
        """
        result: dict[str, object] = {
            "timestamp": self.timestamp.isoformat().replace("+00:00", "Z"),
            "level": self.level.value,
            "channel": self.channel,
            "message": self.message,
            "context": _normalize_value(self.context),
        }
        if self.exception is not None:
            result["exception"] = dict(self.exception)
        return result


def _sanitize_text(value: str) -> str:
    """Bound text and escape control characters used for log injection.

    Args:
        value: A message or exception text.

    Returns:
        A single-line string with non-printing controls represented safely.
    """
    bounded = value[:_MAX_TEXT_LENGTH]
    if len(value) > _MAX_TEXT_LENGTH:
        bounded += _TRUNCATED
    return "".join(
        character
        if character.isprintable() and character not in "\r\n\x1b"
        else character.encode("unicode_escape").decode("ascii")
        for character in bounded
    )


def _exception_data(error: BaseException | None) -> dict[str, str] | None:
    """Capture bounded type and traceback text without live frame objects.

    Args:
        error: The exception to describe, if any.

    Returns:
        A small string mapping or ``None`` for no exception.
    """
    if error is None:
        return None
    rendered = "".join(traceback.format_exception(error))
    return {
        "type": type(error).__qualname__,
        "message": _sanitize_text(str(error)),
        "traceback": _sanitize_text(rendered),
    }
