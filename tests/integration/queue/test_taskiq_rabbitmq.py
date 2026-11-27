"""Verify Queue delivery through the optional Taskiq RabbitMQ adapter.
"""  # fmt: skip

from __future__ import annotations

from dataclasses import dataclass
from multiprocessing import get_context
from typing import TYPE_CHECKING
from uuid import uuid4

import anyio
import pytest

from titanspan.contracts.events import EventDispatcher

# Container injection resolves this contract from handler annotations.
from titanspan.contracts.queue import JobContext  # noqa: TC001
from titanspan.foundation import Application
from titanspan.queue import Job, QueueManager, QueueServiceProvider
from titanspan.queue.events import QueueEvent

if TYPE_CHECKING:
    from multiprocessing.connection import Connection
    from multiprocessing.process import BaseProcess

    from titanspan.contracts.container import ServiceRegistry
    from titanspan.contracts.foundation import ServiceProvider

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


@dataclass
class _RabbitCrashControl:
    """Share worker mode and process signals with one test job.
    """  # fmt: skip

    signal: Connection
    crash_on_delivery: bool


@dataclass
class _RabbitCrashJob(Job):
    """Expose a delivery boundary for the RabbitMQ crash test.
    """  # fmt: skip

    value: str

    async def handle(self, control: _RabbitCrashControl) -> None:
        """Signal handler entry and optionally remain unacknowledged.

        Args:
            control: Process-owned crash mode and synchronization pipe.
        """
        if control.crash_on_delivery and self.value == "crash":
            control.signal.send_bytes(b"crash-started")
            await anyio.Event().wait()
        control.signal.send_bytes(f"completed:{self.value}".encode())


class _RabbitCrashProvider:
    """Register process-local crash control in a native worker application.
    """  # fmt: skip

    def __init__(self, control: _RabbitCrashControl) -> None:
        """Keep the process signal used by the injected job.

        Args:
            control: Process-local worker mode and synchronization pipe.
        """
        self._control = control

    def register(self, container: ServiceRegistry) -> None:
        """Bind test control through the application Container.

        Args:
            container: Native service registry for the worker process.
        """
        container.instance(_RabbitCrashControl, self._control)


def _rabbit_application(
    queue_rabbitmq_url: str,
    application_name: str,
    provider: _RabbitCrashProvider | None = None,
) -> Application:
    """Build a worker or publisher with one shared RabbitMQ namespace.

    Args:
        queue_rabbitmq_url: URL for the disposable RabbitMQ service.
        application_name: Shared trusted namespace for producer and workers.
        provider: Optional test control provider for worker execution.

    Returns:
        A lazy Titanspan application configured for RabbitMQ.
    """
    providers: list[ServiceProvider] = [
        QueueServiceProvider(jobs=(_RabbitCrashJob, _RabbitJob)),
    ]
    if provider is not None:
        providers.insert(0, provider)
    return Application(
        config={
            "app": {"name": application_name},
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
        service_providers=tuple(providers),
    )


def _run_rabbit_worker_process(
    queue_rabbitmq_url: str,
    application_name: str,
    signal: Connection,
    crash_on_delivery: bool,
) -> None:
    """Run one real Taskiq worker in a separately terminable process.

    Args:
        queue_rabbitmq_url: URL for the disposable RabbitMQ service.
        application_name: Shared trusted namespace for producer and workers.
        signal: Pipe used to report handler entry and completion.
        crash_on_delivery: Whether the worker should block before ack.
    """
    anyio.run(
        _run_rabbit_worker,
        queue_rabbitmq_url,
        application_name,
        signal,
        crash_on_delivery,
    )


async def _run_rabbit_worker(
    queue_rabbitmq_url: str,
    application_name: str,
    signal: Connection,
    crash_on_delivery: bool,
) -> None:
    """Consume one application queue until process termination.

    Args:
        queue_rabbitmq_url: URL for the disposable RabbitMQ service.
        application_name: Shared trusted namespace for producer and workers.
        signal: Pipe used to report handler entry and completion.
        crash_on_delivery: Whether the worker should block before ack.
    """
    control = _RabbitCrashControl(signal, crash_on_delivery)
    application = _rabbit_application(
        queue_rabbitmq_url,
        application_name,
        _RabbitCrashProvider(control),
    )
    async with application:
        manager = application.container.make(QueueManager)
        await manager.work_async(
            connection="rabbitmq",
            queue=_QUEUE_NAME,
            concurrency=1,
            prefetch=1,
        )


async def _wait_for_process_signal(
    process: BaseProcess,
    signal: Connection,
    expected: bytes,
) -> None:
    """Wait for one worker event and fail clearly if it exits first.

    Args:
        process: Worker expected to send the signal.
        signal: Receiving end of the worker pipe.
        expected: Exact message required from the job handler.
    """
    did_signal = await anyio.to_thread.run_sync(signal.poll, 20)
    if not did_signal:
        exit_code = process.exitcode
        msg = f"RabbitMQ worker did not signal; exit code was {exit_code}."
        raise AssertionError(msg)
    actual = await anyio.to_thread.run_sync(signal.recv_bytes)
    assert actual == expected


async def _terminate_worker(process: BaseProcess) -> int:
    """Terminate one worker and return its operating-system exit code.

    Args:
        process: Started worker process to terminate.

    Returns:
        The worker's exit code after termination.
    """
    await anyio.to_thread.run_sync(process.terminate)
    await anyio.to_thread.run_sync(process.join, 10)
    exit_code = process.exitcode
    assert exit_code is not None
    process.close()
    return exit_code


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


@pytest.mark.anyio
async def test_rabbitmq_redelivers_when_worker_dies_before_acknowledgement(
    queue_rabbitmq_url: str,
) -> None:
    """Redeliver an unacknowledged RabbitMQ job after worker termination.

    A sentinel job proves that the recovered delivery completed first.
    """
    process_context = get_context("spawn")
    crash_receive, crash_send = process_context.Pipe(duplex=False)
    replay_receive, replay_send = process_context.Pipe(duplex=False)
    application_name = f"queue-rabbitmq-crash-{uuid4().hex}"
    application = _rabbit_application(
        queue_rabbitmq_url,
        application_name,
    )
    process = process_context.Process(
        target=_run_rabbit_worker_process,
        args=(
            queue_rabbitmq_url,
            application_name,
            crash_send,
            True,
        ),
    )
    replay_process = process_context.Process(
        target=_run_rabbit_worker_process,
        args=(
            queue_rabbitmq_url,
            application_name,
            replay_send,
            False,
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        await manager.dispatch_async(_RabbitCrashJob("crash"))
        started = False
        replay_started = False
        try:
            await anyio.to_thread.run_sync(process.start)
            started = True
            await _wait_for_process_signal(
                process,
                crash_receive,
                b"crash-started",
            )
            first_exit_code = await _terminate_worker(process)
            assert first_exit_code != 0
            started = False

            await anyio.to_thread.run_sync(replay_process.start)
            replay_started = True
            await _wait_for_process_signal(
                replay_process,
                replay_receive,
                b"completed:crash",
            )
            await manager.dispatch_async(_RabbitCrashJob("sentinel"))
            await _wait_for_process_signal(
                replay_process,
                replay_receive,
                b"completed:sentinel",
            )
        finally:
            if started and process.is_alive():
                await _terminate_worker(process)
            if replay_started and replay_process.is_alive():
                await _terminate_worker(replay_process)
            crash_receive.close()
            crash_send.close()
            replay_receive.close()
            replay_send.close()
