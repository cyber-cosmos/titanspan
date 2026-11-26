"""Provide Titanspan-owned text, console, and JSON formatters.

Each formatter handles native records directly and does not depend on a
backend-specific event dictionary or record class.
"""

import json
import sys
from typing import TextIO

from titanspan.contracts.logging import LogFormatter
from titanspan.logging.configuration import ChannelConfiguration
from titanspan.logging.record import LogRecord


class JsonLogFormatter:
    """Render one native record as a stable JSON object.

    Context values have already passed through the bounded record normalizer,
    so output never falls back to arbitrary application object formatting.
    """

    def format(self, record: LogRecord) -> str:
        """Encode one record as a UTF-8-compatible JSON string.

        Args:
            record: A normalized Titanspan record.

        Returns:
            A compact, deterministic JSON object.
        """
        return json.dumps(
            record.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


class TextLogFormatter:
    """Render records as plain, single-line text with structured context.

    The formatter escapes context and exception data as JSON so nested values
    remain unambiguous and message newlines cannot forge records.
    """

    def format(self, record: LogRecord) -> str:
        """Render a readable text record.

        Args:
            record: A normalized Titanspan record.

        Returns:
            One log line without a trailing newline.
        """
        prefix = (
            f"{record.timestamp.isoformat()} "
            f"{record.level.value.upper()} "
            f"[{record.channel}] {record.message}"
        )
        if record.context:
            prefix += " " + _json(record.to_dict()["context"])
        if record.exception is not None:
            prefix += " exception=" + _json(dict(record.exception))
        return prefix


class ConsoleLogFormatter:
    """Render concise console messages with optional terminal colors.

    Attributes:
        color: Whether ANSI sequences are emitted for severity labels.

    Notes:
        Color detection is limited to the selected stream and can be disabled
        explicitly for captured output and non-interactive processes.
    """

    def __init__(
        self,
        *,
        color: bool | None = None,
        stream: TextIO | None = None,
    ) -> None:
        """Create a formatter with optional stream-aware color detection.

        Args:
            color: Explicit color setting, or ``None`` to detect a TTY.
            stream: Stream used for default TTY detection.
        """
        target = stream or sys.stderr
        self.color = target.isatty() if color is None else color

    def format(self, record: LogRecord) -> str:
        """Render the message, channel, and optional structured fields.

        Args:
            record: A normalized Titanspan record.

        Returns:
            A concise single-line console representation.
        """
        label = record.level.value.upper()
        if self.color:
            label = f"{_COLORS[record.level.value]}{label}\033[0m"
        rendered = f"{label} [{record.channel}] {record.message}"
        if record.context:
            rendered += " " + _json(record.to_dict()["context"])
        if record.exception is not None:
            rendered += " exception=" + _json(dict(record.exception))
        return rendered


_COLORS: dict[str, str] = {
    "emergency": "\033[1;31m",
    "alert": "\033[1;31m",
    "critical": "\033[1;31m",
    "error": "\033[31m",
    "warning": "\033[33m",
    "notice": "\033[36m",
    "info": "\033[32m",
    "debug": "\033[90m",
}


def create_formatter(
    configuration: ChannelConfiguration,
) -> LogFormatter[LogRecord]:
    """Create a native formatter from validated channel settings.

    Args:
        configuration: The destination's validated formatter options.

    Returns:
        A Titanspan formatter selected by the channel configuration.
    """
    if configuration.formatter == "json":
        return JsonLogFormatter()
    if configuration.formatter == "text":
        return TextLogFormatter()
    return ConsoleLogFormatter(color=configuration.color)


def _json(value: object) -> str:
    """Encode a pre-normalized value for human-readable text output.

    Args:
        value: A normalized context or exception mapping.

    Returns:
        Deterministic JSON text without evaluating custom objects.
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
