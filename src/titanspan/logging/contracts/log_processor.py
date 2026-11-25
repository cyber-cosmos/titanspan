"""Define Titanspan-owned record processor contracts.

Processors enrich or transform a record before dispatch to any driver.
"""

from typing import Protocol

from titanspan.logging.record import LogRecord


class LogProcessor(Protocol):
    """Transform one native record before any output side effect.

    Processors run in configured order. They must not emit log messages from
    inside a transformation because that can cause recursive dispatch.
    """

    def process(self, record: LogRecord) -> LogRecord:
        """Return the processed record.

        Args:
            record: The record produced by the active logger call.

        Returns:
            A record ready for later processors and destination delivery.
        """
        ...
