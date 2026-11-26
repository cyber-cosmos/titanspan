"""Describe sanitized events emitted after native log delivery succeeds.

The event model belongs to Titanspan and does not expose backend-specific
record or event dictionary types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from titanspan.contracts.logging import DeliveryStatus

if TYPE_CHECKING:
    from titanspan.logging.record import LogRecord


@dataclass(frozen=True, slots=True)
class MessageLogged:
    """Represent one record accepted, queued, or dropped by a channel.

    Attributes:
        record: The immutable, redacted record processed by the channel.
        status: What the channel could establish when the call returned.

    Listeners run synchronously after the channel write returns. ``QUEUED``
    does not claim that a background destination has delivered the record.
    """

    record: LogRecord
    status: DeliveryStatus = DeliveryStatus.DELIVERED
