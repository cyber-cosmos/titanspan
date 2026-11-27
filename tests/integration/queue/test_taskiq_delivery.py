"""Verify Redis worker execution and delayed Taskiq scheduling.
"""  # fmt: skip

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import get_ident
from typing import TYPE_CHECKING
from uuid import uuid4

import anyio
import pytest

from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.events import EventDispatcher
from titanspan.foundation import Application
from titanspan.queue import Job, JobContext, QueueManager, QueueServiceProvider
from titanspan.queue.events import JobProcessed, QueueEvent

if TYPE_CHECKING:
    from titanspan.contracts.queue import DispatchReceipt

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]
_WORKER_QUEUE = "delivery-integration"
_CHAIN_FIRST_QUEUE = "chain-first"
_CHAIN_SECOND_QUEUE = "chain-second"
_EXPECTED_CHAIN_WORKERS = 2


class _JobObservation:
    """Share worker observations with the integration test.
    """  # fmt: skip

    def __init__(self) -> None:
        """Create a completion signal and empty execution metadata.
        """  # fmt: skip
        self.completed = anyio.Event()
        self.started_at: datetime | None = None
        self.thread_id: int | None = None
        self.deliveries: list[tuple[str, str, str]] = []


@dataclass
class _SynchronousJob(Job):
    """Record the execution thread used by Taskiq's async worker.
    """  # fmt: skip

    def handle(self, observation: _JobObservation) -> None:
        """Record execution metadata from the synchronous handler thread.

        Args:
            observation: Application-owned test observation.
        """
        observation.started_at = datetime.now(UTC)
        observation.thread_id = get_ident()


@dataclass
class _DelayedJob(Job):
    """Record when the Redis schedule source releases one delayed job.
    """  # fmt: skip

    def handle(self, observation: _JobObservation) -> None:
        """Record the first execution time after scheduled delivery.

        Args:
            observation: Application-owned test observation.
        """
        observation.started_at = datetime.now(UTC)


@dataclass
class _FirstQueueJob(Job):
    """Run the first chain member on its declared Redis stream.
    """  # fmt: skip

    queue = _CHAIN_FIRST_QUEUE
    value: str

    async def handle(
        self,
        observation: _JobObservation,
        context: JobContext,
    ) -> None:
        """Record the first member's actual transport destination.

        Args:
            observation: Shared completion and delivery recorder.
            context: Native metadata for the active job attempt.
        """
        observation.deliveries.append(
            (self.value, context.connection, context.queue)
        )


@dataclass
class _SecondQueueJob(Job):
    """Run the next chain member on a job-specific Redis stream.
    """  # fmt: skip

    queue = _CHAIN_SECOND_QUEUE
    value: str

    async def handle(
        self,
        observation: _JobObservation,
        context: JobContext,
    ) -> None:
        """Record the override and complete the chain observation.

        Args:
            observation: Shared completion and delivery recorder.
            context: Native metadata for the active job attempt.
        """
        observation.deliveries.append(
            (self.value, context.connection, context.queue)
        )
        observation.completed.set()


class _ObservationProvider:
    """Register one observation object through the application Container.
    """  # fmt: skip

    def __init__(self, observation: _JobObservation) -> None:
        """Retain the service owned by the integration test.

        Args:
            observation: Service injected into each test job.
        """
        self._observation = observation

    def register(self, container: ServiceRegistry) -> None:
        """Bind the observation as an application-owned instance.

        Args:
            container: Canonical application service registry.
        """
        container.instance(_JobObservation, self._observation)


def _application(
    port: int,
    observation: _JobObservation,
    jobs: tuple[type[Job], ...],
) -> Application:
    """Build one isolated application configured for its Redis fixture.

    Args:
        port: Local or CI Redis service port.
        observation: Application-owned job observation.
        jobs: Trusted job declarations registered before startup.

    Returns:
        A native Application with Queue's Redis connection configured.
    """
    return Application(
        config={
            "app": {"name": f"queue-delivery-{uuid4().hex}"},
            "queue": {
                "default_connection": "redis",
                "default_queue": _WORKER_QUEUE,
                "connections": {
                    "redis": {
                        "driver": "redis_stream",
                        "options": {
                            "url": f"redis://127.0.0.1:{port}/15",
                        },
                    }
                },
                "schedule_poll_interval": 0.02,
                "schedule_loop_interval": 0.02,
            },
        },
        service_providers=(
            _ObservationProvider(observation),
            QueueServiceProvider(jobs=jobs),
        ),
    )


def _register_worker_signals(
    events: EventDispatcher,
    observation: _JobObservation,
) -> anyio.Event:
    """Register metadata listeners that synchronize worker lifecycle.

    Args:
        events: Canonical application-owned event dispatcher.
        observation: Shared job result used by the completion listener.

    Returns:
        An event set after the Queue worker announces startup.
    """
    ready = anyio.Event()

    async def observe_worker(event: QueueEvent) -> None:
        """Signal readiness and completion without reading job payloads.

        Args:
            event: Metadata-only Queue lifecycle event.
        """
        if event.job_name == "worker.startup":
            ready.set()
        if isinstance(event, JobProcessed):
            observation.completed.set()

    events.listen(QueueEvent, observe_worker)
    return ready


@pytest.mark.anyio
async def test_worker_executes_sync_handler_off_the_event_loop(
    queue_redis_port: int,
) -> None:
    """Run a synchronous job through a real Redis-backed Taskiq worker.

    The injected handler executes on a managed worker thread.
    """
    observation = _JobObservation()
    application = _application(
        queue_redis_port,
        observation,
        (_SynchronousJob,),
    )
    loop_thread = get_ident()

    async with application:
        manager = application.container.make(QueueManager)
        events = application.container.make(EventDispatcher)
        ready = _register_worker_signals(events, observation)

        async def run_worker() -> None:
            """Consume Redis messages until the test cancels the worker.
            """  # fmt: skip
            await manager.work_async(
                connection="redis",
                queue=_WORKER_QUEUE,
                concurrency=1,
                prefetch=1,
            )

        receipt: DispatchReceipt | None = None
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_worker)
            with anyio.fail_after(10):
                await ready.wait()
            receipt = await manager.dispatch_async(_SynchronousJob())
            with anyio.fail_after(10):
                await observation.completed.wait()
            task_group.cancel_scope.cancel()

    assert receipt is not None
    assert receipt.state == "queued"
    assert observation.thread_id is not None
    assert observation.thread_id != loop_thread
    assert observation.started_at is not None


@pytest.mark.anyio
async def test_redis_schedule_source_delivers_after_requested_time(
    queue_redis_port: int,
) -> None:
    """Publish a delayed job and verify its actual worker start time.

    The test uses Redis schedule storage and the native Taskiq scheduler.
    """
    observation = _JobObservation()
    application = _application(
        queue_redis_port,
        observation,
        (_DelayedJob,),
    )

    async with application:
        manager = application.container.make(QueueManager)
        events = application.container.make(EventDispatcher)
        ready = _register_worker_signals(events, observation)

        async def run_worker() -> None:
            """Consume Redis work and due schedules until cancellation.
            """  # fmt: skip
            await manager.work_async(
                connection="redis",
                queue=_WORKER_QUEUE,
                concurrency=1,
                prefetch=1,
            )

        receipt: DispatchReceipt | None = None
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_worker)
            with anyio.fail_after(10):
                await ready.wait()
            receipt = await manager.dispatch_async(
                _DelayedJob(),
                delay=0.5,
            )
            assert receipt.available_at is not None
            with anyio.fail_after(15):
                await observation.completed.wait()
            task_group.cancel_scope.cancel()

    assert receipt is not None
    assert receipt.state == "queued"
    assert receipt.available_at is not None
    assert observation.started_at is not None
    assert observation.started_at >= receipt.available_at


@pytest.mark.anyio
async def test_redis_chain_honors_per_job_queue_override(
    queue_redis_port: int,
) -> None:
    """Publish chain continuation to its job-specific Redis stream.

    Separate workers consume each destination through the Taskiq adapter.
    """
    observation = _JobObservation()
    application = _application(
        queue_redis_port,
        observation,
        (_FirstQueueJob, _SecondQueueJob),
    )

    async with application:
        manager = application.container.make(QueueManager)
        events = application.container.make(EventDispatcher)
        worker_queues: set[str] = set()
        workers_ready = anyio.Event()

        async def observe_startup(event: QueueEvent) -> None:
            """Signal after both queue-specific workers start.

            Args:
                event: Metadata-only Queue lifecycle event.
            """
            if event.job_name == "worker.startup":
                worker_queues.add(event.queue)
                if len(worker_queues) == _EXPECTED_CHAIN_WORKERS:
                    workers_ready.set()

        events.listen(QueueEvent, observe_startup)

        async def run_worker(queue: str) -> None:
            """Consume one declared Queue stream until cancellation.

            Args:
                queue: Logical Queue selected for this Taskiq worker.
            """
            await manager.work_async(
                connection="redis",
                queue=queue,
                concurrency=1,
                prefetch=1,
            )

        receipt: DispatchReceipt | None = None
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_worker, _CHAIN_FIRST_QUEUE)
            task_group.start_soon(run_worker, _CHAIN_SECOND_QUEUE)
            with anyio.fail_after(15):
                await workers_ready.wait()
            receipt = (
                await manager.chain(
                    [_FirstQueueJob("first"), _SecondQueueJob("second")]
                )
                .on_queue(_CHAIN_FIRST_QUEUE)
                .dispatch_async()
            )
            with anyio.fail_after(15):
                await observation.completed.wait()
            task_group.cancel_scope.cancel()

    assert receipt is not None
    assert receipt.state == "queued"
    assert receipt.queue == _CHAIN_FIRST_QUEUE
    assert observation.deliveries == [
        ("first", "redis", _CHAIN_FIRST_QUEUE),
        ("second", "redis", _CHAIN_SECOND_QUEUE),
    ]
