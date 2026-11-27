"""Build ordered Queue job chains with explicit asynchronous dispatch.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from titanspan.queue.exceptions import (
    QueueConfigurationError,
    QueueDispatchError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from titanspan.contracts.queue import DispatchReceipt
    from titanspan.queue.job import Job
    from titanspan.queue.manager import QueueManager


class PendingChain:
    """Configure and explicitly publish a sequence of registered jobs.
    """  # fmt: skip

    def __init__(
        self,
        manager: QueueManager,
        jobs: Sequence[Job],
        *,
        connection: str | None = None,
        queue: str | None = None,
    ) -> None:
        """Create a chain without publishing any jobs.

        Args:
            manager: Canonical application-owned queue manager.
            jobs: Ordered registered jobs to execute sequentially.
            connection: Optional connection shared by the chain.
            queue: Optional queue shared by the chain.
        """
        if not jobs:
            msg = "A job chain must contain at least one job."
            raise QueueConfigurationError(msg)
        self._manager = manager
        self._jobs = tuple(jobs)
        self._connection = connection
        self._queue = queue
        self._used = False

    def on_connection(self, name: str) -> Self:
        """Select one configured connection for the chain.

        Args:
            name: Registered queue connection name.

        Returns:
            This pending chain.
        """
        self._ensure_pending()
        self._manager.connection_configuration(name)
        self._connection = name
        return self

    def prepend(self, job: object) -> Self:
        """Add one trusted job before the current chain members.

        Args:
            job: Registered job instance to execute first.

        Returns:
            This pending chain.
        """
        self._ensure_pending()
        self._jobs = self._manager.validate_chain_members((job, *self._jobs))
        return self

    def append(self, job: object) -> Self:
        """Add one trusted job after the current chain members.

        Args:
            job: Registered job instance to execute last.

        Returns:
            This pending chain.
        """
        self._ensure_pending()
        self._jobs = self._manager.validate_chain_members((*self._jobs, job))
        return self

    def on_queue(self, name: str) -> Self:
        """Select the queue for members without a per-job override.

        Args:
            name: Application queue name.

        Returns:
            This pending chain.
        """
        self._ensure_pending()
        self._manager.validate_queue_name(name)
        self._queue = name
        return self

    async def dispatch_async(self) -> DispatchReceipt:
        """Publish the first job and preserve ordered continuation metadata.

        Returns:
            Receipt for the first job in the chain.
        """
        self._ensure_pending()
        self._used = True
        return await self._manager.dispatch_chain_async(
            self._jobs,
            connection=self._connection,
            queue=self._queue,
        )

    def _ensure_pending(self) -> None:
        """Reject mutation or publication after the chain is consumed.

        Raises:
            QueueDispatchError: If this builder already attempted publication.
        """
        if self._used:
            msg = "A pending job chain can be dispatched only once."
            raise QueueDispatchError(msg)

    _manager: QueueManager
    _jobs: tuple[Job, ...]
    _connection: str | None
    _queue: str | None


__all__ = ["PendingChain"]
