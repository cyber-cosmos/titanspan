"""Fan a record out to named child channels in deterministic order.

Nested stacks are assembled and cycle-checked by ``LogManager`` before this
driver is constructed.
"""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import TYPE_CHECKING

from titanspan.logging.delivery import DeliveryStatus
from titanspan.logging.exceptions import LogDeliveryError

if TYPE_CHECKING:
    from titanspan.logging.channel import LogChannel
    from titanspan.logging.record import LogRecord


class StackLogDriver:
    """Deliver records to child channels without taking their ownership.

    Attributes:
        failures: Bounded diagnostic history of ignored child failures.

    The manager owns child channel lifecycles. This driver only coordinates
    deterministic delivery and records ignored failures for inspection.
    """

    def __init__(
        self,
        channels: tuple[LogChannel, ...],
        *,
        ignore_exceptions: bool,
    ) -> None:
        """Create an ordered channel stack.

        Args:
            channels: Resolved child channels in configured order.
            ignore_exceptions: Whether to continue after child failures.
        """
        self._channels = channels
        self._ignore_exceptions = ignore_exceptions
        self._failures: deque[str] = deque(maxlen=100)
        self._lock = Lock()

    @property
    def failures(self) -> tuple[str, ...]:
        """Return a bounded snapshot of ignored child failures.

        Each value names a channel and exception type without retaining the
        original exception or record payload.
        """
        with self._lock:
            return tuple(self._failures)

    @property
    def channels(self) -> tuple[LogChannel, ...]:
        """Return the child channels referenced by this stack.

        Returns:
            The stable child-channel sequence owned by the manager.
        """
        return self._channels

    def write(self, record: LogRecord) -> DeliveryStatus:
        """Send one record to each child channel in configuration order.

        Args:
            record: The parent channel's processed record.

        Raises:
            LogDeliveryError: If a child fails and errors are not ignored.
        """
        outcomes: list[DeliveryStatus] = []
        for channel in self._channels:
            try:
                outcomes.append(
                    channel.write(record.with_channel(channel.name))
                )
            except LogDeliveryError as error:
                if not self._ignore_exceptions:
                    raise
                outcomes.append(DeliveryStatus.PARTIAL)
                with self._lock:
                    self._failures.append(
                        f"{channel.name}:{type(error).__name__}",
                    )
        return _combine_outcomes(outcomes)

    def flush(self) -> None:
        """Flush all child channels in deterministic order.

        Raises:
            LogDeliveryError: If one child cannot be flushed.
        """
        for channel in self._channels:
            channel.flush()

    def close(self) -> None:
        """Leave child cleanup to the manager that owns those channels.

        Closing a stack never finalizes shared child destinations itself.
        """

    async def write_async(self, record: LogRecord) -> DeliveryStatus:
        """Await child channel delivery in configured order.

        Args:
            record: The parent channel's already processed record.

        Returns:
            The combined outcome from all child channels.

        Raises:
            LogDeliveryError: If a child fails and errors are not ignored.
        """
        outcomes: list[DeliveryStatus] = []
        for channel in self._channels:
            try:
                outcomes.append(
                    await channel.write_async(
                        record.with_channel(channel.name),
                    ),
                )
            except LogDeliveryError as error:
                if not self._ignore_exceptions:
                    raise
                outcomes.append(DeliveryStatus.PARTIAL)
                with self._lock:
                    self._failures.append(
                        f"{channel.name}:{type(error).__name__}",
                    )
        return _combine_outcomes(outcomes)


def _combine_outcomes(
    outcomes: list[DeliveryStatus],
) -> DeliveryStatus:
    """Summarize stack results without implying every sink succeeded.

    Args:
        outcomes: Child channel outcomes in delivery order.

    Returns:
        A single outcome or ``PARTIAL`` when children differ.
    """
    if not outcomes:
        return DeliveryStatus.DELIVERED
    if all(outcome is DeliveryStatus.QUEUED for outcome in outcomes):
        return DeliveryStatus.QUEUED
    if all(outcome is DeliveryStatus.DELIVERED for outcome in outcomes):
        return DeliveryStatus.DELIVERED
    if len(set(outcomes)) == 1:
        return outcomes[0]
    return DeliveryStatus.PARTIAL
