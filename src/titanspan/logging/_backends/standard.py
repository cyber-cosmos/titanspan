"""Adapt native records to Python's standard logging handlers.

This module owns handler construction and delivery details. Application code
receives Titanspan drivers and never has to configure handler instances.
"""

import logging

from titanspan.logging.contracts.log_formatter import LogFormatter
from titanspan.logging.level import to_python_level
from titanspan.logging.record import LogRecord


class StandardHandlerBackend:
    """Write formatted native records through one standard handler.

    The handler owns serialization and destination I/O. A fresh standard
    record is created per call so no application state is retained by it.
    """

    def __init__(
        self,
        handler: logging.Handler,
        formatter: LogFormatter,
    ) -> None:
        """Attach a Titanspan formatter to an owned standard handler.

        Args:
            handler: A standard-library stream, file, or syslog handler.
            formatter: A native formatter that renders Titanspan records.
        """
        self._handler = handler
        self._formatter = formatter
        self._handler.setLevel(logging.NOTSET)
        self._handler.setFormatter(logging.Formatter("%(message)s"))

    def write(self, record: LogRecord) -> None:
        """Format and deliver one native record.

        Args:
            record: A bounded Titanspan record.

        Raises:
            OSError: If the destination cannot accept the formatted message.
        """
        rendered = self._formatter.format(record)
        standard_record = logging.LogRecord(
            name=f"titanspan.{record.channel}",
            level=to_python_level(record.level),
            pathname="",
            lineno=0,
            msg=rendered,
            args=(),
            exc_info=None,
        )
        # SyslogHandler derives RFC priority from this field. Keeping the
        # native name avoids collapsing adjacent severities into CRITICAL.
        standard_record.levelname = record.level.value
        self._handler.handle(standard_record)

    def flush(self) -> None:
        """Flush buffered handler output.

        File and stream handlers expose their underlying stream's flush
        behavior through the standard handler interface.
        """
        self._handler.flush()

    def close(self) -> None:
        """Close the owned handler and any destination resources.

        Standard stream handlers do not close process-owned stdout or stderr;
        file handlers close only the file they opened.
        """
        self._handler.close()
