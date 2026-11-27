"""Expose native job chains through the active application dispatcher.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.contracts.queue import (
    BatchBuilder,
    BusDispatcher,
    ChainBuilder,
    DispatchReceipt,
    PendingDispatch,
)
from titanspan.facades.base import Facade
from titanspan.facades.queue import Queue

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime, timedelta

    from titanspan.queue.job import Job
    from titanspan.queue.manager import QueueFakeScope


class Bus(Facade[BusDispatcher]):
    """Resolve Bus orchestration through the canonical Queue manager.
    """  # fmt: skip

    service_contract = BusDispatcher

    @classmethod
    def dispatch(
        cls,
        job: Job,
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> PendingDispatch:
        """Build an explicit Bus dispatch through the canonical manager.

        Args:
            job: Registered job containing serializable application data.
            connection: Optional configured Queue connection.
            queue: Optional logical queue name.
            delay: Optional backend-supported delivery time.

        Returns:
            A pending dispatch that requires explicit publication.
        """
        return cls.resolve_service().dispatch(
            job,
            connection=connection,
            queue=queue,
            delay=delay,
        )

    @classmethod
    async def dispatch_async(
        cls,
        job: Job,
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> DispatchReceipt:
        """Publish a job through the canonical Bus dispatcher.

        Args:
            job: Registered job containing serializable application data.
            connection: Optional configured Queue connection.
            queue: Optional logical queue name.
            delay: Optional backend-supported delivery time.

        Returns:
            Metadata for the accepted dispatch.
        """
        return await cls.resolve_service().dispatch_async(
            job,
            connection=connection,
            queue=queue,
            delay=delay,
        )

    @classmethod
    def dispatch_sync(
        cls,
        job: Job,
        *,
        connection: str | None = None,
        queue: str | None = None,
    ) -> DispatchReceipt:
        """Execute a job through an explicitly synchronous connection.

        Args:
            job: Registered job containing serializable application data.
            connection: Optional configured sync connection.
            queue: Optional logical queue name.

        Returns:
            Metadata for completed execution.
        """
        return cls.resolve_service().dispatch_sync(
            job,
            connection=connection,
            queue=queue,
        )

    @classmethod
    def fake(cls) -> QueueFakeScope:
        """Record Bus dispatches through the same Queue manager fake.

        Returns:
            An execution-local fake scope shared with Queue and DI clients.
        """
        return Queue.fake()

    @classmethod
    def chain(cls, jobs: Sequence[Job]) -> ChainBuilder:
        """Build an ordered chain using the active application's dispatcher.

        Args:
            jobs: Registered jobs in execution order.

        Returns:
            A pending chain requiring explicit asynchronous dispatch.
        """
        return cls.resolve_service().chain(jobs)

    @classmethod
    def batch(cls, jobs: Sequence[Job]) -> BatchBuilder:
        """Build a batch through the canonical application dispatcher.

        Args:
            jobs: Registered jobs submitted as one batch.

        Returns:
            A pending batch builder.
        """
        return cls.resolve_service().batch(jobs)


__all__ = ["Bus"]
