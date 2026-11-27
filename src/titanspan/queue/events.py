"""Define metadata-only lifecycle events emitted by Queue.

Events omit payload values and exception messages by default.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class QueueEvent:
    """Identify one job event without retaining job payload data.

    Attributes:
        job_id: Identifier assigned before execution or publication.
        job_name: Trusted job type name from the application registry.
        connection: Selected native queue connection.
        queue: Selected logical queue name.
        occurred_at: UTC timestamp at event creation.
        chain_id: Optional native chain identifier.
        batch_id: Optional batch identifier.
    """

    job_id: str
    job_name: str
    connection: str
    queue: str
    occurred_at: datetime
    chain_id: str | None = None
    batch_id: str | None = None


@dataclass(frozen=True, slots=True)
class JobDispatching(QueueEvent):
    """Mark the start of one publication attempt.
    """  # fmt: skip


@dataclass(frozen=True, slots=True)
class JobDispatched(QueueEvent):
    """Mark a job accepted by an inline or broker connection.
    """  # fmt: skip


@dataclass(frozen=True, slots=True)
class JobProcessing(QueueEvent):
    """Mark the start of one worker attempt.

    Attributes:
        attempt: One-based current attempt number.
    """

    attempt: int = 1


@dataclass(frozen=True, slots=True)
class JobProcessed(QueueEvent):
    """Mark successful handler completion without exposing its result.
    """  # fmt: skip


@dataclass(frozen=True, slots=True)
class JobFailed(QueueEvent):
    """Mark failed handler execution without exposing exception text.

    Attributes:
        attempt: One-based current attempt number.
        exception_type: Fully qualified exception class name.
    """

    attempt: int = 1
    exception_type: str = "Exception"


__all__ = [
    "JobDispatched",
    "JobDispatching",
    "JobFailed",
    "JobProcessed",
    "JobProcessing",
    "QueueEvent",
]
