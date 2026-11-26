"""Define the Titanspan log formatter contract.

Formatters receive native structured records and return one output string.
"""

from typing import Protocol


class LogFormatter[RecordT_contra](Protocol):
    """Render a Titanspan record for a single output destination.

    Formatters must not mutate records and should keep multiline data safe for
    the selected output format.
    """

    def format(self, record: RecordT_contra) -> str:
        """Render a record as one destination-ready string.

        Args:
            record: The sanitized native log record.

        Returns:
            A UTF-8 encodable string without a trailing record terminator.
        """
        ...
