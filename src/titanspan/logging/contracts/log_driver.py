"""Define the native synchronous logging driver contract.

Drivers own one output destination and must release resources they create.
"""

from typing import Protocol

from titanspan.logging.delivery import DeliveryStatus
from titanspan.logging.record import LogRecord


class LogDriver(Protocol):
    """Accept structured records and manage destination resources.

    Implementations may write to a stream, file, memory buffer, or composed
    set of child destinations. A driver must not mutate the supplied record.
    """

    def write(self, record: LogRecord) -> DeliveryStatus | None:
        """Deliver one immutable-by-convention native record.

        Args:
            record: Sanitized record whose context has already been copied.

        Returns:
            ``None`` for synchronous delivery or a native delivery status.

        Raises:
            Exception: A destination-specific failure that the channel wraps.
        """
        ...

    def flush(self) -> None:
        """Flush buffered output owned by this driver.

        Raise destination failures to the caller rather than silently
        reporting a successful flush.
        """
        ...

    def close(self) -> None:
        """Release resources created by this driver.

        The operation must be idempotent so manager shutdown is repeatable.
        """
        ...
