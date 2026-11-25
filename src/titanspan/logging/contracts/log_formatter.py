"""Define the Titanspan log formatter contract.

Formatters receive native structured records and return one output string.
"""

from typing import Protocol

from titanspan.logging.record import LogRecord


class LogFormatter(Protocol):
    """Render a Titanspan record for a single output destination.

    Formatters must not mutate records and should keep multiline data safe for
    the selected output format.
    """

    def format(self, record: LogRecord) -> str:
        """Render a record as one destination-ready string.

        Args:
            record: The sanitized native log record.

        Returns:
            A UTF-8 encodable string without a trailing record terminator.
        """
        ...
