"""Define delivery outcomes shared by logging channels and drivers.

Statuses describe what the logging call can prove at its return boundary.
They do not imply durable or exactly-once delivery.
"""

from enum import StrEnum


class DeliveryStatus(StrEnum):
    """Describe the outcome observed when a log call returns.

    ``DELIVERED`` means a synchronous driver accepted the record. ``QUEUED``
    means a background driver accepted it into bounded memory. Neither status
    promises durable storage or exactly-once delivery.
    """

    DELIVERED = "delivered"
    QUEUED = "queued"
    DROPPED = "dropped"
    FALLBACK = "fallback"
    PARTIAL = "partial"
