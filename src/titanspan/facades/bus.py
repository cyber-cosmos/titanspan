"""Expose native job chains through the active application dispatcher.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.contracts.queue import (
    BatchBuilder,
    BusDispatcher,
    ChainBuilder,
    DispatchReceipt,
    JobResultHandle,
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
    def dispatch_if(
        cls,
        condition: bool,
        job: Job,
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> PendingDispatch | None:
        """Build a pending dispatch only when the condition is true.

        Args:
            condition: Whether to create the pending operation.
            job: Registered job instance.
            connection: Optional configured Queue connection.
            queue: Optional logical Queue name.
            delay: Optional backend-supported delivery time.

        Returns:
            A pending operation, or ``None`` when the condition is false.
        """
        return cls.resolve_service().dispatch_if(
            condition,
            job,
            connection=connection,
            queue=queue,
            delay=delay,
        )

    @classmethod
    def dispatch_unless(
        cls,
        condition: bool,
        job: Job,
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> PendingDispatch | None:
        """Build a pending dispatch only when the condition is false.

        Args:
            condition: Whether to skip pending operation creation.
            job: Registered job instance.
            connection: Optional configured Queue connection.
            queue: Optional logical Queue name.
            delay: Optional backend-supported delivery time.

        Returns:
            A pending operation, or ``None`` when the condition is true.
        """
        return cls.resolve_service().dispatch_unless(
            condition,
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
    async def dispatch_after_commit_async(
        cls,
        job: Job,
        *,
        database: str | None = None,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> None:
        """Defer Bus publication through the Database transaction outcome.

        Args:
            job: Registered job containing serializable application data.
            database: Database connection whose transaction owns dispatch.
            connection: Optional configured Queue connection.
            queue: Optional logical queue name.
            delay: Optional backend-supported delivery time.
        """
        await cls.resolve_service().dispatch_after_commit_async(
            job,
            database=database,
            connection=connection,
            queue=queue,
            delay=delay,
        )

    @classmethod
    async def dispatch_many_async(
        cls,
        jobs: Sequence[Job],
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> tuple[DispatchReceipt, ...]:
        """Dispatch registered jobs in order through the active Bus.

        Args:
            jobs: Registered job instances in publication order.
            connection: Optional connection override for every job.
            queue: Optional queue override for every job.
            delay: Optional delivery time shared by every job.

        Returns:
            Dispatch receipts in input order.
        """
        return await cls.resolve_service().dispatch_many_async(
            jobs,
            connection=connection,
            queue=queue,
            delay=delay,
        )

    @classmethod
    async def dispatch_if_async(
        cls,
        condition: bool,
        job: Job,
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> DispatchReceipt | None:
        """Dispatch asynchronously only when the condition is true.

        Args:
            condition: Whether to perform the dispatch.
            job: Registered job instance.
            connection: Optional configured Queue connection.
            queue: Optional logical Queue name.
            delay: Optional backend-supported delivery time.

        Returns:
            A dispatch receipt, or ``None`` when the condition is false.
        """
        return await cls.resolve_service().dispatch_if_async(
            condition,
            job,
            connection=connection,
            queue=queue,
            delay=delay,
        )

    @classmethod
    async def dispatch_unless_async(
        cls,
        condition: bool,
        job: Job,
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> DispatchReceipt | None:
        """Dispatch asynchronously only when the condition is false.

        Args:
            condition: Whether to skip the dispatch.
            job: Registered job instance.
            connection: Optional configured Queue connection.
            queue: Optional logical Queue name.
            delay: Optional backend-supported delivery time.

        Returns:
            A dispatch receipt, or ``None`` when the condition is true.
        """
        return await cls.resolve_service().dispatch_unless_async(
            condition,
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
    def result_for(cls, receipt: DispatchReceipt) -> JobResultHandle:
        """Create a result handle through the canonical Queue service.

        Args:
            receipt: Receipt returned by this application's Bus dispatcher.

        Returns:
            A cancellable asynchronous result handle.
        """
        return cls.resolve_service().result_for(receipt)

    @classmethod
    def fake(
        cls,
        only: Sequence[type[Job]] | None = None,
    ) -> QueueFakeScope:
        """Record Bus dispatches through the same Queue manager fake.

        Args:
            only: Optional registered job classes to intercept. Other
                single-job dispatches use their configured connection.

        Returns:
            An execution-local fake scope shared with Queue and DI clients.
        """
        return Queue.fake(only=only)

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
