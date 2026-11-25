"""Provide safe native processors for structured logging records.

Processors execute before the backend boundary so sensitive fields are not
copied into queues or sent to output drivers in plaintext.
"""

from collections.abc import Iterable

from titanspan.logging.contracts.log_processor import LogProcessor
from titanspan.logging.record import LogRecord


class RedactionProcessor:
    """Redact configured key fragments from nested record context.

    Attributes:
        sensitive_fields: Case-insensitive field fragments to redact.

    The default field set includes common credential names. Applications can
    add domain-specific field fragments without disabling those defaults.
    """

    def __init__(self, sensitive_fields: Iterable[str] = ()) -> None:
        """Create a redactor with default and application-specific fields.

        Args:
            sensitive_fields: Additional fragments such as ``medical_id``.
        """
        defaults = {
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
        }
        self.sensitive_fields = frozenset(
            defaults
            | {
                "".join(
                    character
                    for character in field.casefold()
                    if character.isalnum()
                )
                for field in sensitive_fields
            },
        )

    def process(self, record: LogRecord) -> LogRecord:
        """Return a record after applying the configured redaction policy.

        Args:
            record: A normalized Titanspan log record.

        Returns:
            A new record whose matching nested values are redacted.
        """
        return record.with_context(
            {},
            sensitive_fields=self.sensitive_fields,
        )


def process_record(
    record: LogRecord,
    processors: Iterable[LogProcessor],
) -> LogRecord:
    """Apply native processors in their declared order.

    Args:
        record: The newly constructed record.
        processors: Ordered native processor implementations.

    Returns:
        The record returned by the final processor.

    """
    current = record
    for processor in processors:
        current = processor.process(current)
    return current
