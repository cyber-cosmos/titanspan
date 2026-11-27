"""Define native Queue and Bus dispatch boundaries.

The contracts accept registered job objects and return backend-independent
dispatch receipts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Self, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime, timedelta

    from titanspan.contracts.queue.dispatch import DispatchReceipt
    from titanspan.contracts.queue.result import JobResultHandle


@runtime_checkable
class PendingDispatch(Protocol):
    """Describe a single-use builder for one job publication.

    Implementations must not dispatch from object finalization.
    """

    def on_connection(self, name: str) -> Self:
        """Select a configured connection before publication.

        Args:
            name: Registered connection name.

        Returns:
            This pending dispatch builder.
        """
        ...

    def on_queue(self, name: str) -> Self:
        """Select a queue supported by the selected backend.

        Args:
            name: Queue name configured by the application.

        Returns:
            This pending dispatch builder.
        """
        ...

    def delay(self, value: float | timedelta | datetime) -> Self:
        """Set a backend-supported delivery time.

        Args:
            value: Delay duration or absolute timezone-aware time.

        Returns:
            This pending dispatch builder.
        """
        ...

    async def dispatch_async(self) -> DispatchReceipt:
        """Publish or execute the configured job once.

        Returns:
            The accepted dispatch metadata.
        """
        ...

    def dispatch_sync(self) -> DispatchReceipt:
        """Execute only when the selected connection is synchronous.

        Returns:
            The completed dispatch metadata.
        """
        ...


@runtime_checkable
class QueueDispatcher(Protocol):
    """Describe the native application's canonical job dispatcher.

    A configured manager implements this contract and owns its broker
    adapters through the application lifecycle.
    """

    def dispatch(
        self,
        job: object,
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> PendingDispatch:
        """Build a single-use pending dispatch without publishing it.

        Args:
            job: Trusted registered job instance.
            connection: Optional named connection.
            queue: Optional queue name.
            delay: Optional backend-supported delivery time.

        Returns:
            A builder that publishes only after an explicit dispatch call.
        """
        ...

    async def dispatch_async(
        self,
        job: object,
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> DispatchReceipt:
        """Publish a job through an explicit asynchronous operation.

        Args:
            job: Trusted registered job instance.
            connection: Optional named connection.
            queue: Optional queue name.
            delay: Optional backend-supported delivery time.

        Returns:
            Publication metadata.
        """
        ...

    async def dispatch_many_async(
        self,
        jobs: Sequence[object],
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> tuple[DispatchReceipt, ...]:
        """Dispatch a bounded sequence in order through the shared pipeline.

        Args:
            jobs: Registered job instances in publication order.
            connection: Optional connection override for every job.
            queue: Optional queue override for every job.
            delay: Optional delivery time shared by every job.

        Returns:
            Receipts in the same order as ``jobs``.

        Raises:
            QueueConfigurationError: If a job or selection is invalid.
        """
        ...

    def dispatch_sync(
        self,
        job: object,
        *,
        connection: str | None = None,
        queue: str | None = None,
    ) -> DispatchReceipt:
        """Execute one job only through a synchronous connection.

        Args:
            job: Trusted registered job instance.
            connection: Optional named connection.
            queue: Optional queue name.

        Returns:
            Inline execution metadata.
        """
        ...

    def result_for(self, receipt: DispatchReceipt) -> JobResultHandle:
        """Create a result handle for supported queued work.

        Args:
            receipt: Receipt returned by this application's dispatcher.

        Returns:
            An asynchronous handle backed by the selected connection.
        """
        ...


@runtime_checkable
class ChainBuilder(Protocol):
    """Describe an ordered sequence of registered jobs.

    Queued continuation guarantees depend on durable backend behavior.
    """

    def prepend(self, job: object) -> Self:
        """Add one registered job before the current members.

        Args:
            job: Job instance validated by the owning Queue manager.

        Returns:
            This chain builder.
        """
        ...

    def append(self, job: object) -> Self:
        """Add one registered job after the current members.

        Args:
            job: Job instance validated by the owning Queue manager.

        Returns:
            This chain builder.
        """
        ...

    def on_connection(self, name: str) -> Self:
        """Select the default connection for jobs without overrides.

        Args:
            name: Registered connection name.

        Returns:
            This chain builder.
        """
        ...

    def on_queue(self, name: str) -> Self:
        """Select the default queue for jobs without overrides.

        Args:
            name: Queue name.

        Returns:
            This chain builder.
        """
        ...

    async def dispatch_async(self) -> DispatchReceipt:
        """Start the first job in the chain.

        Returns:
            The first job's dispatch receipt.
        """
        ...

    def dispatch_sync(self) -> DispatchReceipt:
        """Execute a chain through synchronous connections only.

        Returns:
            Receipt for the first executed job.
        """
        ...


@runtime_checkable
class BatchBuilder(Protocol):
    """Describe a batch whose state is owned by a configured repository.

    Implementations must state whether batch state is process-local or
    durable across worker processes.
    """

    def name(self, value: str) -> Self:
        """Set a safe human-readable batch name.

        Args:
            value: Batch label.

        Returns:
            This batch builder.
        """
        ...

    def on_connection(self, name: str) -> Self:
        """Select the connection used for every batch member.

        Args:
            name: Registered connection name.

        Returns:
            This batch builder.
        """
        ...

    def on_queue(self, name: str) -> Self:
        """Select the queue used for every batch member.

        Args:
            name: Logical queue name.

        Returns:
            This batch builder.
        """
        ...

    def allow_failures(self) -> Self:
        """Continue tracking after a job failure.

        Returns:
            This batch builder.
        """
        ...

    async def dispatch_async(self) -> BatchHandle:
        """Dispatch the batch and return its identifier.

        Returns:
            An application-local batch handle.
        """
        ...


@runtime_checkable
class BatchHandle(Protocol):
    """Describe an inspectable batch status snapshot.

    Durable status remains unavailable until an application selects a
    persistent batch repository.
    """

    @property
    def id(self) -> str:
        """Return the application-local batch identifier.
        """  # fmt: skip
        ...

    @property
    def name(self) -> str:
        """Return the batch display name.
        """  # fmt: skip
        ...

    @property
    def total_jobs(self) -> int:
        """Return the total batch job count.
        """  # fmt: skip
        ...

    @property
    def pending_jobs(self) -> int:
        """Return the number of jobs without terminal state.
        """  # fmt: skip
        ...

    @property
    def processed_jobs(self) -> int:
        """Return the number of completed jobs.
        """  # fmt: skip
        ...

    @property
    def failed_jobs(self) -> int:
        """Return the number of failed jobs.
        """  # fmt: skip
        ...

    @property
    def state(self) -> str:
        """Return the batch state name.
        """  # fmt: skip
        ...


@runtime_checkable
class BusDispatcher(QueueDispatcher, Protocol):
    """Describe orchestration helpers built on the canonical dispatcher.

    Bus does not own a second job registry or broker.
    """

    def chain(self, jobs: Sequence[object]) -> ChainBuilder:
        """Build an ordered sequence using this dispatch service.

        Args:
            jobs: Registered jobs in execution order.

        Returns:
            A chain builder sharing the canonical dispatcher.
        """
        ...

    def batch(self, jobs: Sequence[object]) -> BatchBuilder:
        """Build a batch using this dispatch service.

        Args:
            jobs: Registered jobs submitted as one batch.

        Returns:
            A batch builder sharing the canonical dispatcher.
        """
        ...


__all__ = [
    "BatchBuilder",
    "BusDispatcher",
    "ChainBuilder",
    "PendingDispatch",
    "QueueDispatcher",
]
