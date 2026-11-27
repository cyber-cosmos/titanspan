"""Exercise Queue result delegation and bounded backend storage.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import anyio
import pytest
from taskiq.abc.result_backend import AsyncResultBackend
from taskiq.result import TaskiqResult

from titanspan.contracts.queue import (
    DispatchReceipt,
    JobResultSnapshot,
)
from titanspan.queue._backends.results import QueueTaskiqResultBackend
from titanspan.queue.exceptions import QueueResultTimeoutError
from titanspan.queue.results import QueueResultHandle

if TYPE_CHECKING:
    from titanspan.queue.manager import QueueManager

pytestmark = pytest.mark.unit


class _ResultBackend(AsyncResultBackend[object]):
    """Record backend lifecycle and result access calls.
    """  # fmt: skip

    def __init__(self) -> None:
        """Initialize an empty result store and lifecycle counters.
        """  # fmt: skip
        self.results: dict[str, TaskiqResult[object]] = {}
        self.started = False
        self.stopped = False
        self.readiness_calls: list[str] = []

    async def startup(self) -> None:
        """Record backend startup.
        """  # fmt: skip
        self.started = True

    async def shutdown(self) -> None:
        """Record backend shutdown.
        """  # fmt: skip
        self.stopped = True

    async def set_result(
        self,
        task_id: str,
        result: TaskiqResult[object],
    ) -> None:
        """Store a result submitted through the adapter.

        Args:
            task_id: Identifier assigned to the result.
            result: Safe result supplied by Queue.
        """
        self.results[task_id] = result

    async def is_result_ready(self, task_id: str) -> bool:
        """Report whether the selected identifier has a result.

        Args:
            task_id: Identifier to inspect.

        Returns:
            Whether a result exists for the identifier.
        """
        self.readiness_calls.append(task_id)
        return task_id in self.results

    async def get_result(
        self,
        task_id: str,
        with_logs: bool = False,
    ) -> TaskiqResult[object]:
        """Return a stored result.

        Args:
            task_id: Identifier to read.
            with_logs: Whether logs were requested.

        Returns:
            The stored Taskiq result.
        """
        _ = with_logs
        return self.results[task_id]


class _ResultManager:
    """Expose the result methods used by one native handle.
    """  # fmt: skip

    def __init__(self, ready_states: list[bool]) -> None:
        """Configure deterministic readiness responses.

        Args:
            ready_states: Readiness values returned in call order.
        """
        self.ready_states = ready_states
        self.ready_calls: list[DispatchReceipt] = []
        self.read_calls: list[DispatchReceipt] = []
        self.snapshot = JobResultSnapshot(
            job_id="job-1",
            state="succeeded",
            has_value=True,
            value={"answer": 42},
            execution_time=0.25,
        )

    async def result_is_ready(self, receipt: DispatchReceipt) -> bool:
        """Return the next readiness state for the selected receipt.

        Args:
            receipt: Receipt passed by the result handle.

        Returns:
            The next configured readiness value.
        """
        self.ready_calls.append(receipt)
        return self.ready_states.pop(0)

    async def read_result(self, receipt: DispatchReceipt) -> JobResultSnapshot:
        """Return the configured result snapshot.

        Args:
            receipt: Receipt passed by the result handle.

        Returns:
            The configured successful result.
        """
        self.read_calls.append(receipt)
        return self.snapshot


def _receipt() -> DispatchReceipt:
    """Create stable dispatch metadata for handle tests.

    Returns:
        One queued result receipt.
    """
    return DispatchReceipt(
        job_id="job-1",
        connection="redis",
        queue="default",
        state="queued",
    )


@pytest.mark.anyio
async def test_result_handle_delegates_ready_and_read_calls() -> None:
    """Pass the selected receipt to both canonical manager operations.
    """  # fmt: skip
    receipt = _receipt()
    manager = _ResultManager([True])
    handle = QueueResultHandle(cast("QueueManager", manager), receipt)

    assert await handle.is_ready()
    assert await handle.get_async() == manager.snapshot
    assert manager.ready_calls == [receipt]
    assert manager.read_calls == [receipt]


@pytest.mark.anyio
async def test_zero_timeout_reads_a_ready_result() -> None:
    """Allow zero-timeout checks to return results that are already ready.
    """  # fmt: skip
    receipt = _receipt()
    manager = _ResultManager([True])
    handle = QueueResultHandle(cast("QueueManager", manager), receipt)

    assert await handle.wait_async(timeout=0) == manager.snapshot
    assert manager.ready_calls == [receipt]
    assert manager.read_calls == [receipt]


@pytest.mark.anyio
async def test_wait_without_deadline_polls_until_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Continue cancellable polling until the backend reports readiness.
    """  # fmt: skip
    receipt = _receipt()
    manager = _ResultManager([False, True])
    handle = QueueResultHandle(cast("QueueManager", manager), receipt)
    intervals: list[float] = []

    async def record_sleep(interval: float) -> None:
        """Record the polling interval without delaying the test.

        Args:
            interval: Requested delay between result checks.
        """
        intervals.append(interval)

    monkeypatch.setattr(anyio, "sleep", record_sleep)

    assert await handle.wait_async(poll_interval=0.25) == manager.snapshot
    assert manager.ready_calls == [receipt, receipt]
    assert manager.read_calls == [receipt]
    assert intervals == [0.25]


@pytest.mark.anyio
async def test_result_backend_delegates_lifecycle_and_readiness() -> None:
    """Keep Taskiq responsible for backend lifecycle and result lookup.
    """  # fmt: skip
    backend = _ResultBackend()
    adapter = QueueTaskiqResultBackend(backend)

    await adapter.startup()
    assert backend.started
    assert not await adapter.is_result_ready("job-1")

    await adapter.set_result(
        "job-1",
        TaskiqResult[object](
            is_err=False,
            return_value={"has_value": True, "value": {"answer": 42}},
            execution_time=0.25,
            labels={"untrusted": "ignored"},
        ),
    )

    assert await adapter.is_result_ready("job-1")
    assert backend.readiness_calls == ["job-1", "job-1"]
    result = await adapter.get_result("job-1")
    assert result.return_value == {
        "has_value": True,
        "value": {"answer": 42},
    }
    assert result.labels == {}

    await adapter.shutdown()
    assert backend.stopped


@pytest.mark.anyio
async def test_zero_timeout_preserves_pending_result_timeout() -> None:
    """Raise the native timeout when the one readiness check is false.
    """  # fmt: skip
    manager = _ResultManager([False])
    handle = QueueResultHandle(cast("QueueManager", manager), _receipt())

    with pytest.raises(QueueResultTimeoutError):
        await handle.wait_async(timeout=0)


@pytest.mark.anyio
async def test_timed_wait_translates_deadline_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translate an expired cancellable wait into the native Queue error.
    """  # fmt: skip
    manager = _ResultManager([False])
    handle = QueueResultHandle(cast("QueueManager", manager), _receipt())

    async def expire_wait(interval: float) -> None:
        """Raise the timeout that an AnyIO deadline would produce.

        Args:
            interval: Requested polling delay, unused by this controlled case.
        """
        _ = interval
        raise TimeoutError

    monkeypatch.setattr(anyio, "sleep", expire_wait)

    with pytest.raises(QueueResultTimeoutError):
        await handle.wait_async(timeout=10, poll_interval=0.25)
