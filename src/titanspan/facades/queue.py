"""Expose Queue operations through the active application Container.

Facade dispatch and injected QueueDispatcher references resolve the same
application-owned manager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.contracts.queue import (
    DispatchReceipt,
    PendingDispatch,
    QueueDispatcher,
)
from titanspan.facades.base import Facade
from titanspan.queue.manager import QueueFakeScope, QueueManager

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from titanspan.queue.job import Job


class Queue(Facade[QueueDispatcher]):
    """Resolve the canonical Queue dispatcher for the active application."""

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
    def fake(cls) -> QueueFakeScope:
        """Replace broker effects with an execution-local dispatch recorder.

        Returns:
            A sync and async fake scope with Queue assertions.
        """
        return cls.manager().fake()

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
