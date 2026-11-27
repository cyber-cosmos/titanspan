"""Verify small Queue contract and facade boundaries.
"""  # fmt: skip

from dataclasses import dataclass
from datetime import UTC, datetime
from math import nan
from uuid import uuid4

import anyio
import pytest

from titanspan.config import Repository
from titanspan.contracts.queue import JobContext, PendingDispatch
from titanspan.facades.bus import Bus
from titanspan.facades.queue import Queue
from titanspan.foundation import Application
from titanspan.queue import (
    Job,
    QueueCapabilityError,
    QueueConfigurationError,
    QueueManager,
    QueueServiceProvider,
)
from titanspan.queue.chain import PendingChain
from titanspan.queue.configuration import (
    QueueConfiguration,
    QueueConnectionConfiguration,
)

pytestmark = pytest.mark.unit


@dataclass
class _FacadeJob(Job):
    """Return its payload through the application-owned dispatcher.
    """  # fmt: skip

    value: str

    def handle(self) -> str:
        """Return the value supplied by the test.

        Returns:
            Job data used to confirm facade dispatch.
        """
        return self.value


def _application() -> Application:
    """Build one application with the native synchronous Queue driver.

    Returns:
        An unstarted application with one trusted job type.
    """
    return Application(
        config={
            "app": {"name": f"queue-facade-{uuid4().hex}"},
            "queue": {
                "default_connection": "sync",
                "connections": {"sync": {"driver": "sync"}},
            },
        },
        service_providers=(QueueServiceProvider(jobs=(_FacadeJob,)),),
    )


def test_job_context_copies_caller_metadata() -> None:
    """Keep handler metadata stable after the caller changes its mapping.
    """  # fmt: skip
    metadata: dict[str, str | int | float | bool] = {"attempt": 1}
    context = JobContext(
        job_id="job-1",
        job_name="jobs.example",
        connection="sync",
        queue="default",
        attempt=1,
        max_attempts=1,
        dispatched_at=datetime.now(UTC),
        metadata=metadata,
    )

    metadata["attempt"] = 2

    assert context.metadata == {"attempt": 1}


def test_connection_and_non_finite_interval_are_rejected() -> None:
    """Reject invalid driver identifiers and non-finite delay polling.
    """  # fmt: skip
    with pytest.raises(QueueConfigurationError, match="driver name"):
        QueueConnectionConfiguration("bad driver")

    repository = Repository(
        {"queue": {"schedule_poll_interval": nan}},
    )
    with pytest.raises(QueueConfigurationError, match="finite number"):
        QueueConfiguration.from_repository(repository)


def test_empty_pending_chain_is_rejected() -> None:
    """Reject a chain that has no executable first member.
    """  # fmt: skip
    application = Application()
    manager = QueueManager(container=application.container)

    with pytest.raises(QueueConfigurationError, match="at least one"):
        PendingChain(manager, ())


@pytest.mark.anyio
async def test_queue_and_bus_facades_delegate_sync_operations() -> None:
    """Route sync dispatch and result checks through the active app.
    """  # fmt: skip
    application = _application()

    async with application:
        manager = application.container.make(QueueManager)
        queue_receipt = await anyio.to_thread.run_sync(
            Queue.dispatch_sync,
            _FacadeJob("queue"),
        )
        bus_receipt = await anyio.to_thread.run_sync(
            Bus.dispatch_sync,
            _FacadeJob("bus"),
        )
        queue_pending = Queue.dispatch(_FacadeJob("queue-pending"))
        bus_pending = Bus.dispatch(_FacadeJob("bus-pending"))
        assert Queue.manager() is manager
        assert Queue.resolve_service() is manager
        assert Bus.resolve_service() is manager

        with pytest.raises(QueueCapabilityError, match="Only queued"):
            Queue.result_for(queue_receipt)
        with pytest.raises(QueueCapabilityError, match="Only queued"):
            Bus.result_for(bus_receipt)

    assert queue_receipt.result == "queue"
    assert bus_receipt.result == "bus"
    assert isinstance(queue_pending, PendingDispatch)
    assert isinstance(bus_pending, PendingDispatch)


@pytest.mark.anyio
async def test_queue_facade_rejects_worker_for_sync_connection() -> None:
    """Route worker startup through the active app-owned manager.
    """  # fmt: skip
    application = _application()

    async with application:
        with pytest.raises(QueueCapabilityError, match="provide a worker"):
            await Queue.work_async(connection="sync")
