"""Define backend-independent queue result records and access contracts.
"""  # fmt: skip

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class JobResultSnapshot:
    """Describe one completed job without exposing backend exceptions.

    Attributes:
        job_id: Stable identifier assigned to the job.
        state: Whether the worker completed or failed the job.
        has_value: Whether the worker stored a JSON-compatible return value.
        value: Stored JSON-compatible return value when available.
        execution_time: Handler execution time in seconds.
    """

    job_id: str
    state: Literal["failed", "succeeded"]
    has_value: bool
    value: object | None
    execution_time: float


class JobResultHandle(Protocol):
    """Describe asynchronous access to one backend-owned job result.

    Result retention and availability depend on the selected backend.
    """

    @property
    def job_id(self) -> str:
        """Return the job identifier associated with this handle.
        """  # fmt: skip
        ...

    async def is_ready(self) -> bool:
        """Check whether the backend retains a completed job result.

        Returns:
            Whether the result is available now.
        """
        ...

    async def get_async(self) -> JobResultSnapshot:
        """Read a completed result without waiting.

        Returns:
            A safe result snapshot.

        Raises:
            RuntimeError: If the result is not available or has expired.
        """
        ...

    async def wait_async(
        self,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
        poll_interval: float = 0.1,
    ) -> JobResultSnapshot:
        """Wait for a result using cancellable asynchronous polling.

        Args:
            timeout: Optional maximum wait in seconds.
            poll_interval: Positive seconds between readiness checks.

        Returns:
            The completed result snapshot.

        Raises:
            RuntimeError: If the wait interval or timeout is invalid.
            TimeoutError: If the result does not become available in time.
        """
        ...


__all__ = ["JobResultHandle", "JobResultSnapshot"]
