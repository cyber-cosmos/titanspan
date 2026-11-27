"""Verify Queue delivery through the optional Taskiq RabbitMQ adapter.
"""  # fmt: skip

from dataclasses import dataclass
from uuid import uuid4

import anyio
import pytest

from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.events import EventDispatcher
from titanspan.contracts.queue import JobContext
from titanspan.foundation import Application
from titanspan.queue import Job, QueueManager, QueueServiceProvider
from titanspan.queue.events import QueueEvent

pytestmark = pytest.mark.integration
_QUEUE_NAME = "rabbitmq-delivery-integration"


class _RabbitObservation:
    """Record the payload and route of one RabbitMQ-delivered job.
    """  # fmt: skip

    def __init__(self) -> None:
        """Create a completion signal and empty delivery record.
        """  # fmt: skip
        self.completed = anyio.Event()
        self.deliveries: list[tuple[str, str, str]] = []


@dataclass
class _RabbitJob(Job):
    """Carry one serializable value through RabbitMQ delivery.
    """  # fmt: skip

    value: str

    async def handle(
        self,
        observation: _RabbitObservation,
        context: JobContext,
    ) -> None:
        """Record one execution through the native worker Container.

        Args:
            observation: Application-owned test recorder.
            context: Metadata for this job execution.
        """
        observation.deliveries.append(
            (self.value, context.connection, context.queue)
        )
        observation.completed.set()


class _RabbitProvider:
    """Register the RabbitMQ test observer in the native Container.
    """  # fmt: skip

    def __init__(self, observation: _RabbitObservation) -> None:
        """Retain the observer injected into the registered job.

        Args:
            observation: Application-owned delivery record.
        """
        self._observation = observation

    def register(self, container: ServiceRegistry) -> None:
        """Bind the observer to the canonical application registry.

        Args:
            container: Native service registry for the test application.
        """
        container.instance(_RabbitObservation, self._observation)


@pytest.mark.anyio
async def test_rabbitmq_worker_processes_registered_job(
    queue_rabbitmq_url: str,
) -> None:
    """Publish and execute a job through the actual Taskiq RabbitMQ broker.

    The test verifies real broker startup, delivery, and application cleanup.
    """
    observation = _RabbitObservation()
    application = Application(
        config={
            "app": {"name": f"queue-rabbitmq-{uuid4().hex}"},
            "queue": {
                "default_connection": "rabbitmq",
                "default_queue": _QUEUE_NAME,
                "connections": {
                    "rabbitmq": {
                        "driver": "rabbitmq",
                        "options": {
                            "url": queue_rabbitmq_url,
                            "prefetch": 1,
                        },
                    }
                },
            },
        },
        service_providers=(
            _RabbitProvider(observation),
            QueueServiceProvider(jobs=(_RabbitJob,)),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        events = application.container.make(EventDispatcher)
        worker_ready = anyio.Event()
        receipt = await manager.dispatch_async(_RabbitJob("delivered"))

        async def observe_worker(event: QueueEvent) -> None:
            """Signal after the Queue worker starts its broker.

            Args:
                event: Metadata-only worker lifecycle event.
            """
            if event.job_name == "worker.startup":
                worker_ready.set()

        events.listen(QueueEvent, observe_worker)

        async def run_worker() -> None:
            """Consume the configured durable queue until cancellation.
            """  # fmt: skip
            await manager.work_async(
                connection="rabbitmq",
                queue=_QUEUE_NAME,
                concurrency=1,
                prefetch=1,
            )

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_worker)
            with anyio.fail_after(20):
                await worker_ready.wait()
            with anyio.fail_after(20):
                await observation.completed.wait()
            task_group.cancel_scope.cancel()

    assert receipt.state == "queued"
    assert observation.deliveries == [("delivered", "rabbitmq", _QUEUE_NAME)]
