"""Define optional async delivery for native logging drivers.

Drivers that implement this contract can await backpressure instead of
offloading their write path through a synchronous worker thread.
"""

from typing import Protocol, runtime_checkable

from titanspan.contracts.logging.delivery import DeliveryStatus


@runtime_checkable
class AsyncLogDriver[RecordT_contra](Protocol):
    """Extend a synchronous logging driver with async record delivery.

    The driver must also satisfy ``LogDriver`` for synchronous callers and
    resource management. Async methods must preserve cancellation semantics.
    """

    async def write_async(
        self,
        record: RecordT_contra,
    ) -> DeliveryStatus | None:
        """Deliver or enqueue one record without blocking its event loop.

        Args:
            record: A sanitized native log record.

        Returns:
            The outcome observed before this operation returns.

        Raises:
            Exception: A destination failure translated by the channel.
        """
        ...
