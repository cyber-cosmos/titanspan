"""Provide native access to backend-retained job results.

Taskiq owns remote result transport. Queue validates metadata and exposes
safe application-owned snapshots.
"""

from __future__ import annotations

from math import isfinite
from typing import TYPE_CHECKING

import anyio

from titanspan.queue.exceptions import (
    QueueResultError,
    QueueResultTimeoutError,
)

if TYPE_CHECKING:
    from titanspan.contracts.queue import DispatchReceipt, JobResultSnapshot
    from titanspan.queue.manager import QueueManager

_RESULT_TIMEOUT_ERROR = "The job result was not ready before the timeout."


class QueueResultHandle:
    """Read one job result through its application-owned manager.
    """  # fmt: skip

    def __init__(
        self,
        manager: QueueManager,
        receipt: DispatchReceipt,
    ) -> None:
        """Bind a result identifier to its selected connection and queue.

        Args:
            manager: Canonical manager that owns the selected backend.
            receipt: Dispatch metadata returned by the same application.
        """
        self._manager = manager
        self._receipt = receipt

    @property
    def job_id(self) -> str:
        """Return the job identifier associated with this handle.
        """  # fmt: skip
        return self._receipt.job_id

    async def is_ready(self) -> bool:
        """Check whether a retained result is ready to read.

        Returns:
            Whether the selected backend has a completed result.
        """
        return await self._manager.result_is_ready(self._receipt)

    async def get_async(self) -> JobResultSnapshot:
        """Read one completed result without waiting.

        Returns:
            A safe result snapshot.

        Raises:
            QueueResultError: If the result is pending or expired.
            QueueResultError: If the retained result is malformed.
        """
        return await self._manager.read_result(self._receipt)

    async def wait_async(
        self,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
        poll_interval: float = 0.1,
    ) -> JobResultSnapshot:
        """Wait for a retained result with cancellable AnyIO polling.

        Args:
            timeout: Optional maximum wait duration in seconds.
            poll_interval: Positive seconds between readiness checks.

        Returns:
            The completed result snapshot.

        Raises:
            QueueResultError: If timing options are invalid.
            QueueResultTimeoutError: If the result is not ready in time.
        """
        if not isfinite(poll_interval) or poll_interval <= 0:
            msg = "The result polling interval must be positive and finite."
            raise QueueResultError(msg)
        if timeout is not None and (not isfinite(timeout) or timeout < 0):
            msg = "The result timeout must be finite and non-negative."
            raise QueueResultError(msg)

        if timeout == 0:
            if await self.is_ready():
                return await self.get_async()
            raise QueueResultTimeoutError(_RESULT_TIMEOUT_ERROR)
        try:
            if timeout is None:
                return await self._wait_until_ready(poll_interval)
            with anyio.fail_after(timeout):
                return await self._wait_until_ready(poll_interval)
        except TimeoutError:
            raise QueueResultTimeoutError(_RESULT_TIMEOUT_ERROR) from None

    async def _wait_until_ready(
        self,
        poll_interval: float,
    ) -> JobResultSnapshot:
        """Poll until the backend retains a completed result.

        Args:
            poll_interval: Positive seconds between readiness checks.

        Returns:
            The completed result snapshot.
        """
        # Taskiq result backends expose polling but no readiness event.
        while not await self.is_ready():  # noqa: ASYNC110
            await anyio.sleep(poll_interval)
        return await self.get_async()

    _manager: QueueManager
    _receipt: DispatchReceipt


__all__ = ["QueueResultHandle"]
