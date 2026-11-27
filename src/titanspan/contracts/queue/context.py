"""Define immutable metadata available during one Queue job attempt."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class JobContext:
    """Describe one attempt while its native job scope remains active.

    Attributes:
        job_id: Stable job identifier used across backend retries.
        job_name: Trusted name from the application job catalog.
        connection: Connection used for this execution.
        queue: Queue used for this execution.
        attempt: Current one-based attempt number.
        max_attempts: Total attempts including the first attempt.
        dispatched_at: UTC time recorded in the safe message envelope.
        chain_id: Optional sequential chain identifier.
        batch_id: Optional batch identifier.
        metadata: Immutable, non-sensitive application metadata.
    """

    job_id: str
    job_name: str
    connection: str
    queue: str
    attempt: int
    max_attempts: int
    dispatched_at: datetime
    chain_id: str | None = None
    batch_id: str | None = None
    metadata: Mapping[str, str | int | float | bool] | None = None

    def __post_init__(self) -> None:
        """Freeze caller metadata before a handler can observe it."""
        if self.metadata is not None:
            object.__setattr__(
                self,
                "metadata",
                MappingProxyType(dict(self.metadata)),
            )


__all__ = ["JobContext"]
