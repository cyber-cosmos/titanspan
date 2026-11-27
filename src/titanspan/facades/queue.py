"""Expose Queue operations through the active application Container.

Facade dispatch and injected QueueDispatcher references resolve the same
application-owned manager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.contracts.queue import (
    DispatchReceipt,
    JobResultHandle,
    PendingDispatch,
    QueueDispatcher,
)
from titanspan.facades.base import Facade
from titanspan.queue.manager import QueueFakeScope, QueueManager

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime, timedelta

    from titanspan.queue.job import Job


class Queue(Facade[QueueDispatcher]):
    """Resolve the canonical Queue dispatcher for the active application.
    """  # fmt: skip

    service_contract = QueueDispatcher

    @classmethod
    def manager(cls) -> QueueManager:
        """Return the manager shared by injected and facade consumers.
        """  # fmt: skip
        return cls.active_container().make(QueueManager)

    @classmethod
    def dispatch(
        cls,
        job: Job,
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> PendingDispatch:
        """Build a pending dispatch without relying on object finalization.

        Args:
            job: Registered job instance containing serializable data.
            connection: Optional configured connection name.
            queue: Optional logical queue name.
            delay: Optional backend-supported delivery time.

        Returns:
            A single-use builder requiring explicit dispatch.
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
            connection: Optional configured connection.
            queue: Optional logical queue.
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
            connection: Optional configured connection.
            queue: Optional logical queue.
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
        """Publish or execute one job through an explicit async operation.

        Args:
            job: Registered job instance containing serializable data.
            connection: Optional configured connection name.
            queue: Optional logical queue name.
            delay: Optional backend-supported delivery time.

        Returns:
            Queue receipt describing publication or inline completion.
        """
        return await cls.resolve_service().dispatch_async(
            job,
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
        """Dispatch registered jobs in order through the active application.

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
            connection: Optional configured connection.
            queue: Optional logical queue.
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
            connection: Optional configured connection.
            queue: Optional logical queue.
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
        """Run one job through the synchronous connection only.

        Args:
            job: Registered job instance containing serializable data.
            connection: Optional configured sync connection name.
            queue: Optional logical queue name.

        Returns:
            Receipt for inline execution.
        """
        return cls.resolve_service().dispatch_sync(
            job,
            connection=connection,
            queue=queue,
        )

    @classmethod
    def result_for(cls, receipt: DispatchReceipt) -> JobResultHandle:
        """Create a handle for retained results on supported backends.

        Args:
            receipt: Receipt returned by this application's Queue service.

        Returns:
            A cancellable asynchronous result handle.
        """
        return cls.resolve_service().result_for(receipt)

    @classmethod
    def fake(
        cls,
        only: Sequence[type[Job]] | None = None,
    ) -> QueueFakeScope:
        """Replace broker effects with an execution-local dispatch recorder.

        Args:
            only: Optional registered job classes to intercept. Other
                single-job dispatches use their configured connection.

        Returns:
            A sync and async fake scope with Queue assertions.
        """
        return cls.manager().fake(only=only)

    @classmethod
    async def work_async(
        cls,
        *,
        connection: str | None = None,
        queue: str | None = None,
        concurrency: int | None = None,
        prefetch: int | None = None,
    ) -> None:
        """Run a bounded Taskiq worker until cancellation or shutdown.

        Args:
            connection: Configured Taskiq connection to consume.
            queue: Logical queue consumed by this worker.
            concurrency: Maximum active asynchronous job handlers.
            prefetch: Additional messages allowed beyond active capacity.
        """
        await cls.manager().work_async(
            connection=connection,
            queue=queue,
            concurrency=concurrency,
            prefetch=prefetch,
        )


__all__ = ["Queue"]
