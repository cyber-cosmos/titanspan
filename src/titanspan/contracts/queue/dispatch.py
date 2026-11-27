"""Define immutable metadata returned by native queue dispatch operations.

The receipt identifies publication or inline completion without exposing a
Taskiq backend result object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
from typing import Literal


@dataclass(frozen=True, slots=True)
class DispatchReceipt:
    """Identify one accepted job dispatch.

    Attributes:
        job_id: Stable identifier assigned before publication.
        connection: Configured connection selected for the job.
        queue: Configured queue selected for the job.
        state: Whether work completed, was queued, or was intentionally
            discarded by a disabled connection.
        chain_id: Optional native chain identifier.
        batch_id: Optional native batch identifier.
        available_at: Optional requested delayed delivery time.
        result: Inline result when synchronous execution completed.
    """

    job_id: str
    connection: str
    queue: str
    state: Literal["discarded", "executed", "queued"]
    chain_id: str | None = None
    batch_id: str | None = None
    available_at: datetime | None = None
    result: object | None = None


__all__ = ["DispatchReceipt"]
