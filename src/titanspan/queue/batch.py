"""Provide application-local Batch state for native Bus dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Self

from titanspan.queue.exceptions import QueueConfigurationError, QueueError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from titanspan.queue.job import Job
    from titanspan.queue.manager import QueueManager

BatchState = Literal[
    "queued",
    "running",
    "completed",
    "completed_with_failures",
    "failed",
    "cancelled",
    "discarded",
]
_MAX_BATCH_JOBS = 1000
_MAX_BATCH_NAME_LENGTH = 128
_CONTROL_CHARACTER_LIMIT = 32


@dataclass(frozen=True, slots=True)
class BatchSnapshot:
    """Describe a batch status snapshot owned by one application process.

    Attributes:
        id: Unique identifier assigned at dispatch.
        name: Safe display name selected by the caller.
        total_jobs: Number of jobs in the batch.
        pending_jobs: Jobs not yet completed or failed.
        processed_jobs: Jobs completed successfully.
        failed_jobs: Jobs that raised during inline execution.
        state: Current process-local status.
        allow_failures: Whether inline execution continued after a failure.
    """

    id: str
    name: str
    total_jobs: int
    pending_jobs: int
    processed_jobs: int
    failed_jobs: int
    state: BatchState
    allow_failures: bool


class BatchHandle:
    """Read status retained by the owning application's Queue manager."""

    def __init__(self, manager: QueueManager, batch_id: str) -> None:
        """Create a status handle without duplicating batch state.

        Args:
            manager: Application-owned Queue manager.
            batch_id: Identifier returned by batch dispatch.
        """
        self._manager = manager
        self.id = batch_id

    @property
    def snapshot(self) -> BatchSnapshot:
        """Return the latest in-process batch status snapshot."""
        return self._manager.batch_status(self.id)

    @property
    def name(self) -> str:
        """Return the display name selected for this batch."""
        return self.snapshot.name

    @property
    def total_jobs(self) -> int:
        """Return the number of submitted jobs."""
        return self.snapshot.total_jobs

    @property
    def pending_jobs(self) -> int:
        """Return the number of jobs without a terminal result."""
        return self.snapshot.pending_jobs

    @property
    def processed_jobs(self) -> int:
        """Return the number of successful jobs."""
        return self.snapshot.processed_jobs

    @property
    def failed_jobs(self) -> int:
        """Return the number of failed jobs."""
        return self.snapshot.failed_jobs

    @property
    def state(self) -> BatchState:
        """Return the current process-local batch state."""
        return self.snapshot.state

    _manager: QueueManager
    id: str


class PendingBatch:
    """Configure and explicitly submit a bounded batch of jobs."""

    def __init__(
        self,
        manager: QueueManager,
        jobs: Sequence[Job],
    ) -> None:
        """Create an unpublished batch with a bounded job count.

        Args:
            manager: Canonical Queue manager for the active application.
            jobs: Registered job instances to submit.

        Raises:
            QueueConfigurationError: If the batch is empty or too large.
        """
        if not jobs or len(jobs) > _MAX_BATCH_JOBS:
            msg = "A batch must contain between 1 and 1000 jobs."
            raise QueueConfigurationError(msg)
        self._manager = manager
        self._jobs = tuple(jobs)
        self._name = "Job batch"
        self._allows_failures = False
        self._connection: str | None = None
        self._queue: str | None = None
        self._used = False

    def name(self, value: str) -> Self:
        """Set a bounded display label without control characters.

        Args:
            value: Human-readable batch name.

        Returns:
            This batch builder.
        """
        self._ensure_pending()
        if (
            not value.strip()
            or len(value) > _MAX_BATCH_NAME_LENGTH
            or any(
                ord(character) < _CONTROL_CHARACTER_LIMIT for character in value
            )
        ):
            msg = "A batch name must be printable and at most 128 characters."
            raise QueueConfigurationError(msg)
        self._name = value
        return self

    def on_connection(self, name: str) -> Self:
        """Select one configured connection for this batch.

        Args:
            name: Registered Queue connection name.

        Returns:
            This batch builder.
        """
        self._ensure_pending()
        self._manager.connection_configuration(name)
        self._connection = name
        return self

    def on_queue(self, name: str) -> Self:
        """Select one logical queue for every batch member.

        Args:
            name: Application queue name.

        Returns:
            This batch builder.
        """
        self._ensure_pending()
        self._manager.validate_queue_name(name)
        self._queue = name
        return self

    def allow_failures(self) -> Self:
        """Continue inline processing after a job raises.

        Returns:
            This batch builder.
        """
        self._ensure_pending()
        self._allows_failures = True
        return self

    async def dispatch_async(self) -> BatchHandle:
        """Submit the batch through the application's Queue manager.

        Returns:
            A handle that reads process-local batch status.

        Raises:
            QueueError: If the batch was already submitted.
        """
        self._ensure_pending()
        self._used = True
        return await self._manager.dispatch_batch_async(
            self._jobs,
            name=self._name,
            allow_failures=self._allows_failures,
            connection=self._connection,
            queue=self._queue,
        )

    def _ensure_pending(self) -> None:
        """Reject changes after the one explicit dispatch operation."""
        if self._used:
            msg = "A batch builder can be dispatched only once."
            raise QueueError(msg)

    _manager: QueueManager
    _jobs: tuple[Job, ...]
    _name: str
    _allows_failures: bool
    _connection: str | None
    _queue: str | None
    _used: bool


__all__ = ["BatchHandle", "BatchSnapshot", "BatchState", "PendingBatch"]
