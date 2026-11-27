"""Verify Redis worker execution and delayed Taskiq scheduling.
"""  # fmt: skip

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from multiprocessing import get_context
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from threading import get_ident
from typing import TYPE_CHECKING
from uuid import uuid4

import anyio
import pytest
from redis.asyncio import Redis

from titanspan.container import Scope
from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.events import EventDispatcher
from titanspan.contracts.foundation import ServiceProvider
from titanspan.facades.bus import Bus
from titanspan.facades.queue import Queue
from titanspan.foundation import Application
from titanspan.queue import Job, JobContext, QueueManager, QueueServiceProvider
from titanspan.queue.events import JobFailed, JobProcessed, QueueEvent

if TYPE_CHECKING:
    from titanspan.contracts.queue import DispatchReceipt, JobResultSnapshot

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]
_WORKER_QUEUE = "delivery-integration"
_CHAIN_FIRST_QUEUE = "chain-first"
_CHAIN_SECOND_QUEUE = "chain-second"
_EXPECTED_CHAIN_WORKERS = 2
_RECLAIM_IDLE_TIMEOUT_MS = 1_000
_RECLAIM_LOCK_TIMEOUT_SECONDS = 0.5


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


class _WorkerJobToken:
    """Identify one worker-owned Queue execution scope.
    """  # fmt: skip


class _WorkerConcurrencyGate:
    """Require multiple real worker jobs to overlap before completion.
    """  # fmt: skip

    def __init__(self, target: int) -> None:
        """Create a barrier for a fixed number of active worker jobs.

        Args:
            target: Number of jobs required to overlap.
        """
        self.target = target
        self.entered = anyio.Event()
        self.release = anyio.Event()
        self.completed = anyio.Event()
        self._lock = anyio.Lock()
        self.tokens: list[_WorkerJobToken] = []
        self.job_ids: list[str] = []
        self._completed_count = 0

    async def wait_for_release(
        self,
        token: _WorkerJobToken,
        context: JobContext,
    ) -> None:
        """Record one job scope and wait for the test to release both jobs.

        Args:
            token: Dependency owned by this worker job scope.
            context: Metadata for the current queued job.
        """
        async with self._lock:
            self.tokens.append(token)
            self.job_ids.append(context.job_id)
            if len(self.tokens) == self.target:
                self.entered.set()
        await self.release.wait()
        async with self._lock:
            self._completed_count += 1
            if self._completed_count == self.target:
                self.completed.set()


@dataclass
class _ConcurrentRedisJob(Job):
    """Wait until another real Redis worker job enters its scope.
    """  # fmt: skip

    index: int

    async def handle(
        self,
        gate: _WorkerConcurrencyGate,
        token: _WorkerJobToken,
        context: JobContext,
    ) -> None:
        """Prove concurrent execution through the configured worker.

        Args:
            gate: Application-owned barrier shared by active jobs.
            token: Job-scoped dependency owned by this execution.
            context: Metadata for the current job.
        """
        _ = self.index
        await gate.wait_for_release(token, context)


class _CrashRecoveryGate:
    """Coordinate a worker crash and a later Redis redelivery.
    """  # fmt: skip

    def __init__(
        self,
        started: Connection | None,
    ) -> None:
        """Retain an optional signal for deterministic worker termination.

        Args:
            started: Pipe that signals entry into the crashing worker.
        """
        self._started = started

    async def wait_for_release(self) -> None:
        """Block only the first worker until the test terminates it.
        """  # fmt: skip
        if self._started is None:
            return
        self._started.send_bytes(b"started")
        await anyio.Event().wait()


@dataclass
class _CrashRedeliveryJob(Job):
    """Block one delivery until its worker process is terminated.
    """  # fmt: skip

    async def handle(
        self,
        gate: _CrashRecoveryGate,
    ) -> None:
        """Block the crashing worker before acknowledgement.

        Args:
            gate: Cross-process crash synchronization.
        """
        await gate.wait_for_release()


class _TimeoutLifecycle:
    """Record handler entry and job resource finalization.
    """  # fmt: skip

    def __init__(self) -> None:
        """Create synchronization and cleanup state for one test job.
        """  # fmt: skip
        self.entered = anyio.Event()
        self.finalizations = 0


class _TimeoutResource:
    """Represent a resource owned by a timed Redis job scope.
    """  # fmt: skip


class _TimeoutProvider:
    """Register a job-scoped resource with a visible finalizer.
    """  # fmt: skip

    def __init__(self, lifecycle: _TimeoutLifecycle) -> None:
        """Retain the observer used by the asynchronous resource factory.

        Args:
            lifecycle: State used to verify scope cleanup after timeout.
        """
        self._lifecycle = lifecycle

    def register(self, container: ServiceRegistry) -> None:
        """Bind the observer and resource through the application Container.

        Args:
            container: Canonical application service registry.
        """
        container.instance(_TimeoutLifecycle, self._lifecycle)
        container.scoped(
            _TimeoutResource,
            self.create,
            scope=Scope.JOB,
        )

    async def create(self) -> AsyncIterator[_TimeoutResource]:
        """Yield a resource and record its single finalization.

        Yields:
            One job-owned resource instance.
        """
        try:
            yield _TimeoutResource()
        finally:
            self._lifecycle.finalizations += 1


@dataclass
class _TimedRedisJob(Job):
    """Wait indefinitely so the configured async timeout cancels the handler.
    """  # fmt: skip

    timeout = 0.05
    tries = 1

    async def handle(
        self,
        lifecycle: _TimeoutLifecycle,
        resource: _TimeoutResource,
    ) -> None:
        """Enter the handler and wait for Queue's timeout boundary.

        Args:
            lifecycle: Observer for handler entry.
            resource: Resource owned by the current JOB scope.
        """
        _ = resource
        lifecycle.entered.set()
        await anyio.Event().wait()


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
class _ResultJob(Job):
    """Return a JSON value that a Redis result handle can retrieve.
    """  # fmt: skip

    value: str

    def handle(self) -> dict[str, str]:
        """Return one bounded JSON result.
        """  # fmt: skip
        return {"value": self.value}


@dataclass
class _FailingResultJob(Job):
    """Fail once so result storage can expose status without the message.
    """  # fmt: skip

    tries = 1

    def handle(self) -> None:
        """Raise a secret-bearing error for the redaction assertion.
        """  # fmt: skip
        message = "synthetic-private-result-detail"
        raise RuntimeError(message)


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


class _WorkerConcurrencyProvider:
    """Register one shared gate and one dependency per job scope.
    """  # fmt: skip

    def __init__(self, gate: _WorkerConcurrencyGate) -> None:
        """Retain the barrier used by concurrent Redis jobs.

        Args:
            gate: Application-owned worker synchronization gate.
        """
        self._gate = gate

    def register(self, container: ServiceRegistry) -> None:
        """Register services through the canonical application Container.

        Args:
            container: Native application service registry.
        """
        container.instance(_WorkerConcurrencyGate, self._gate)
        container.scoped(_WorkerJobToken, scope=Scope.JOB)


class _CrashRecoveryProvider:
    """Register one process-shared Queue crash coordination gate.
    """  # fmt: skip

    def __init__(
        self,
        gate: _CrashRecoveryGate,
    ) -> None:
        """Retain process coordination for the crash test.

        Args:
            gate: Cross-process worker crash coordinator.
        """
        self._gate = gate

    def register(self, container: ServiceRegistry) -> None:
        """Bind the test coordinator through the native Container.

        Args:
            container: Canonical application service registry.
        """
        container.instance(_CrashRecoveryGate, self._gate)


def _application(
    port: int,
    observation: _JobObservation,
    jobs: tuple[type[Job], ...],
    providers: tuple[ServiceProvider, ...] = (),
    *,
    application_name: str | None = None,
    connection_options: Mapping[str, object] | None = None,
) -> Application:
    """Build one isolated application configured for its Redis fixture.

    Args:
        port: Local or CI Redis service port.
        observation: Application-owned job observation.
        jobs: Trusted job declarations registered before startup.
        providers: Additional trusted providers for integration fixtures.
        application_name: Shared name used by producer and worker processes.
        connection_options: Additional options for the Redis broker.

    Returns:
        A native Application with Queue's Redis connection configured.
    """
    return Application(
        config={
            "app": {
                "name": application_name or f"queue-delivery-{uuid4().hex}"
            },
            "queue": {
                "default_connection": "redis",
                "default_queue": _WORKER_QUEUE,
                "connections": {
                    "redis": {
                        "driver": "redis_stream",
                        "options": {
                            "url": f"redis://127.0.0.1:{port}/15",
                            **(connection_options or {}),
                        },
                    }
                },
                "schedule_poll_interval": 0.02,
                "schedule_loop_interval": 0.02,
            },
        },
        service_providers=(
            _ObservationProvider(observation),
            *providers,
            QueueServiceProvider(jobs=jobs),
        ),
    )


def _run_crash_worker_process(
    port: int,
    application_name: str,
    started: Connection,
) -> None:
    """Run a Queue worker in an independently terminable process.

    Args:
        port: Redis port used by the integration fixture.
        application_name: Namespace shared with the producer application.
        started: Pipe used to signal handler entry to the test process.
    """
    gate = _CrashRecoveryGate(started)
    anyio.run(
        _run_crash_worker,
        port,
        application_name,
        gate,
    )


async def _run_crash_worker(
    port: int,
    application_name: str,
    gate: _CrashRecoveryGate,
) -> None:
    """Run one Redis consumer until its process is terminated.

    Args:
        port: Redis port used by the integration fixture.
        application_name: Namespace shared with the producer application.
        gate: Cross-process synchronization for the active job.
    """
    application = _application(
        port,
        _JobObservation(),
        (_CrashRedeliveryJob,),
        (_CrashRecoveryProvider(gate),),
        application_name=application_name,
        connection_options={
            "idle_timeout_ms": _RECLAIM_IDLE_TIMEOUT_MS,
            "unacknowledged_lock_timeout_seconds": (
                _RECLAIM_LOCK_TIMEOUT_SECONDS
            ),
        },
    )
    async with application:
        manager = application.container.make(QueueManager)
        await manager.work_async(
            connection="redis",
            queue=_WORKER_QUEUE,
            concurrency=1,
            prefetch=1,
        )


async def _crash_worker_after_handler_start(
    process: BaseProcess,
    started: Connection,
) -> int:
    """Terminate a worker after it signals entry into the job handler.

    Args:
        process: Independently spawned Taskiq worker process.
        started: Pipe that receives the handler-entry signal.

    Returns:
        Exit status after forced worker termination.
    """
    did_start = False
    try:
        await anyio.to_thread.run_sync(process.start)
        did_start = True
        assert await anyio.to_thread.run_sync(started.poll, 15)
        signal = await anyio.to_thread.run_sync(started.recv_bytes)
        assert signal == b"started"
        await anyio.to_thread.run_sync(process.terminate)
        await anyio.to_thread.run_sync(process.join, 10)
        exit_code = process.exitcode
        assert exit_code is not None
        return exit_code
    finally:
        if did_start:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            process.close()


async def _wait_for_idle_pending_message(
    port: int,
    stream: str,
    group: str,
    minimum_idle_ms: int,
) -> None:
    """Wait until Redis reports an unacknowledged message as reclaimable.

    Args:
        port: Redis port used by the integration fixture.
        stream: Fully namespaced Redis Stream key.
        group: Taskiq consumer group associated with the application.
        minimum_idle_ms: Backend reclaim threshold in milliseconds.
    """
    client = Redis(host="127.0.0.1", port=port, db=15)
    poll_interval = anyio.Event()
    try:
        with anyio.fail_after(10):
            while True:
                pending = await client.xpending_range(
                    stream,
                    group,
                    min="-",
                    max="+",
                    count=1,
                    idle=minimum_idle_ms,
                )
                if pending:
                    break
                with anyio.move_on_after(0.01):
                    await poll_interval.wait()
    finally:
        await client.aclose()


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
async def test_redis_worker_runs_jobs_concurrently_in_isolated_scopes(
    queue_redis_port: int,
) -> None:
    """Require two Redis jobs to overlap in separate native JOB scopes.

    A barrier prevents success unless both worker slots run concurrently.
    """
    target = 2
    gate = _WorkerConcurrencyGate(target)
    application = _application(
        queue_redis_port,
        _JobObservation(),
        (_ConcurrentRedisJob,),
        (_WorkerConcurrencyProvider(gate),),
    )

    async with application:
        manager = application.container.make(QueueManager)

        async def run_worker() -> None:
            """Consume Queue work until the test cancels the worker.
            """  # fmt: skip
            await manager.work_async(
                connection="redis",
                queue=_WORKER_QUEUE,
                concurrency=target,
                prefetch=target,
            )

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_worker)
            for index in range(target):
                await manager.dispatch_async(_ConcurrentRedisJob(index))
            with anyio.fail_after(15):
                await gate.entered.wait()
            gate.release.set()
            with anyio.fail_after(15):
                await gate.completed.wait()
            task_group.cancel_scope.cancel()

    assert len(gate.job_ids) == target
    assert len(set(gate.job_ids)) == target
    assert len({id(token) for token in gate.tokens}) == target


@pytest.mark.anyio
async def test_redis_redelivers_unacknowledged_job_after_worker_crash(
    queue_redis_port: int,
) -> None:
    """Recover a Redis Streams message after its worker process is killed.

    The test terminates a real worker inside the handler before acknowledgement.
    """
    process_context = get_context("spawn")
    started_receive, started_send = process_context.Pipe(duplex=False)
    gate = _CrashRecoveryGate(None)
    application_name = f"queue-crash-{uuid4().hex}"
    application = _application(
        queue_redis_port,
        _JobObservation(),
        (_CrashRedeliveryJob,),
        (_CrashRecoveryProvider(gate),),
        application_name=application_name,
        connection_options={
            "idle_timeout_ms": _RECLAIM_IDLE_TIMEOUT_MS,
            "unacknowledged_lock_timeout_seconds": (
                _RECLAIM_LOCK_TIMEOUT_SECONDS
            ),
        },
    )
    process = process_context.Process(
        target=_run_crash_worker_process,
        args=(
            queue_redis_port,
            application_name,
            started_send,
        ),
    )
    result: JobResultSnapshot | None = None

    async with application:
        manager = application.container.make(QueueManager)
        receipt = await manager.dispatch_async(_CrashRedeliveryJob())
        try:
            exit_code = await _crash_worker_after_handler_start(
                process,
                started_receive,
            )
            assert exit_code != 0
            await _wait_for_idle_pending_message(
                queue_redis_port,
                f"{manager.configuration.namespace}:redis:{_WORKER_QUEUE}",
                f"{manager.configuration.namespace}-redis-{_WORKER_QUEUE}",
                _RECLAIM_IDLE_TIMEOUT_MS,
            )

            async def recover_message() -> None:
                """Consume new and pending messages after the worker crash.
                """  # fmt: skip
                await manager.work_async(
                    connection="redis",
                    queue=_WORKER_QUEUE,
                    concurrency=1,
                    prefetch=1,
                )

            async with anyio.create_task_group() as task_group:
                task_group.start_soon(recover_message)
                await manager.dispatch_async(_CrashRedeliveryJob())
                result = await manager.result_for(receipt).wait_async(
                    timeout=10,
                    poll_interval=0.01,
                )
                task_group.cancel_scope.cancel()
            assert result is not None
            assert result.state == "succeeded"
        finally:
            started_receive.close()
            started_send.close()


@pytest.mark.anyio
async def test_redis_job_timeout_finalizes_its_scope_before_failure_result(
    queue_redis_port: int,
) -> None:
    """Cancel a timed Redis job and finalize its scoped resource once.

    The test verifies the native timeout, event, result, and Container scope.
    """
    lifecycle = _TimeoutLifecycle()
    application = _application(
        queue_redis_port,
        _JobObservation(),
        (_TimedRedisJob,),
        (_TimeoutProvider(lifecycle),),
    )
    failures: list[JobFailed] = []
    receipt: DispatchReceipt | None = None
    result: JobResultSnapshot | None = None

    async with application:
        manager = application.container.make(QueueManager)
        events = application.container.make(EventDispatcher)
        events.listen(JobFailed, failures.append)

        async def run_worker() -> None:
            """Consume timed jobs until the test closes the worker.
            """  # fmt: skip
            await manager.work_async(
                connection="redis",
                queue=_WORKER_QUEUE,
                concurrency=1,
                prefetch=1,
            )

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_worker)
            receipt = await manager.dispatch_async(_TimedRedisJob())
            result = await manager.result_for(receipt).wait_async(
                timeout=10,
                poll_interval=0.01,
            )
            task_group.cancel_scope.cancel()

    assert receipt is not None
    assert result is not None
    assert result.state == "failed"
    assert lifecycle.entered.is_set()
    assert lifecycle.finalizations == 1
    assert len(failures) == 1
    assert failures[0].job_id == receipt.job_id
    assert failures[0].attempt == 1
    assert failures[0].exception_type == "TimeoutError"


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


@pytest.mark.anyio
async def test_redis_result_handle_returns_safe_success_payload(
    queue_redis_port: int,
) -> None:
    """Read a typed result through Taskiq's Redis result backend.

    The handle observes the same registered job and worker lifecycle.
    """
    observation = _JobObservation()
    application = _application(
        queue_redis_port,
        observation,
        (_ResultJob,),
    )
    result: JobResultSnapshot | None = None

    async with application:
        manager = application.container.make(QueueManager)
        events = application.container.make(EventDispatcher)
        ready = _register_worker_signals(events, observation)

        async def run_worker() -> None:
            """Consume one result-producing job until test cancellation.
            """  # fmt: skip
            await manager.work_async(
                connection="redis",
                queue=_WORKER_QUEUE,
                concurrency=1,
                prefetch=1,
            )

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_worker)
            with anyio.fail_after(10):
                await ready.wait()
            receipt = await manager.dispatch_async(_ResultJob("complete"))
            handle = Queue.result_for(receipt)
            assert handle.job_id == receipt.job_id
            result = await handle.wait_async(
                timeout=10,
                poll_interval=0.01,
            )
            assert await handle.wait_async(timeout=0) == result
            assert await handle.wait_async() == result
            task_group.cancel_scope.cancel()

    assert result is not None
    assert result.state == "succeeded"
    assert result.has_value is True
    assert result.value == {"value": "complete"}


@pytest.mark.anyio
async def test_redis_result_handle_reports_missing_and_zero_timeout(
    queue_redis_port: int,
) -> None:
    """Distinguish a pending result from an expired result record.

    A zero timeout checks readiness once without starting a polling delay.
    """
    observation = _JobObservation()
    application = _application(
        queue_redis_port,
        observation,
        (_ResultJob,),
    )

    async with application:
        manager = application.container.make(QueueManager)
        receipt = await manager.dispatch_async(_ResultJob("pending"))
        handle = manager.result_for(receipt)

        assert not await handle.is_ready()
        with pytest.raises(TimeoutError):
            await handle.wait_async(timeout=0)
        with pytest.raises(TimeoutError):
            await handle.wait_async(timeout=0.01, poll_interval=1)
        with pytest.raises(RuntimeError, match="result is unavailable"):
            await handle.get_async()


@pytest.mark.anyio
async def test_redis_result_handle_redacts_failure_details(
    queue_redis_port: int,
) -> None:
    """Expose failure state without persisting exception message text.

    Taskiq retains retry and acknowledgement ownership for the failed job.
    """
    observation = _JobObservation()
    application = _application(
        queue_redis_port,
        observation,
        (_FailingResultJob,),
    )
    result: JobResultSnapshot | None = None

    async with application:
        manager = application.container.make(QueueManager)
        events = application.container.make(EventDispatcher)
        ready = _register_worker_signals(events, observation)

        async def run_worker() -> None:
            """Consume one failing result job until test cancellation.
            """  # fmt: skip
            await manager.work_async(
                connection="redis",
                queue=_WORKER_QUEUE,
                concurrency=1,
                prefetch=1,
            )

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_worker)
            with anyio.fail_after(10):
                await ready.wait()
            receipt = await manager.dispatch_async(_FailingResultJob())
            handle = Bus.result_for(receipt)
            result = await handle.wait_async(
                timeout=10,
                poll_interval=0.01,
            )
            task_group.cancel_scope.cancel()

    assert result is not None
    assert result.state == "failed"
    assert result.has_value is False
    assert "synthetic-private-result-detail" not in repr(result)
