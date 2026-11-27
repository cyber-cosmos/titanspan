"""Verify Queue uses the canonical application service graph.

The integration executes registered jobs through the production Container.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import ClassVar
from uuid import uuid4

import anyio
import pytest

from titanspan.container import Scope
from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.events import EventDispatcher
from titanspan.contracts.queue import (
    BatchHandle,
    BusDispatcher,
    DispatchReceipt,
    JobNext,
    QueueDispatcher,
    SyncJobNext,
)
from titanspan.facades.bus import Bus
from titanspan.facades.queue import Queue
from titanspan.foundation import Application
from titanspan.queue import (
    Job,
    JobContext,
    JobDispatching,
    JobRetried,
    QueueCapabilityError,
    QueueConfigurationError,
    QueueError,
    QueueManager,
    QueueServiceProvider,
)
from titanspan.queue.events import JobProcessing, QueueEvent

pytestmark = [pytest.mark.integration, pytest.mark.architecture]
_FIRST_ATTEMPT = 1
_SECOND_ATTEMPT = 2
_EXPECTED_FACADE_DISPATCHES = 2
_EXPECTED_CHAIN_JOBS = 2
_EXPECTED_FAKE_EXECUTIONS = 2
_EXPECTED_APPLICATIONS = 2
_OVERSIZED_CHAIN_LENGTH = 257


class _JobRecord:
    """Store execution metadata for the enclosing integration test.

    The test inspects values after each job scope closes.
    """

    def __init__(self) -> None:
        """Create an empty record owned by one application.

        The test observes the injected service identity.
        """
        self.values: list[tuple[str, str, object]] = []
        self.middleware_events: list[str] = []
        self.max_attempts: list[int] = []


class _ChainDestinationRecord:
    """Record the connection and queue used by each chain member.
    """  # fmt: skip

    def __init__(self) -> None:
        """Create an empty destination observation list.
        """  # fmt: skip
        self.destinations: list[tuple[str, str, str]] = []


class _JobDependency:
    """Identify one job-owned dependency instance.

    Separate job scopes must resolve separate instances.
    """

    def __init__(self) -> None:
        """Create a token for the current job scope.

        The enclosing test compares these tokens across jobs.
        """
        self.token = object()


class _SyncChainRecord:
    """Keep the order and chain metadata observed by synchronous jobs.

    The integration test checks one chain ID across isolated job scopes.
    """

    def __init__(self) -> None:
        """Create an empty observation list for one application.
        """  # fmt: skip
        self.jobs: list[tuple[str, str | None, object]] = []


class _SyncChainProvider:
    """Register one application-owned sync-chain observation service.
    """  # fmt: skip

    def __init__(self, record: _SyncChainRecord) -> None:
        """Retain the test-owned record for application registration.

        Args:
            record: Shared observation target for the test application.
        """
        self._record = record

    def register(self, container: ServiceRegistry) -> None:
        """Bind the observation target as an application singleton.

        Args:
            container: Canonical application service registry.
        """
        container.instance(_SyncChainRecord, self._record)
        container.scoped(_JobDependency, scope=Scope.JOB)


@dataclass
class _SyncChainJob(Job):
    """Record ordered execution and shared chain identity.
    """  # fmt: skip

    label: str

    def handle(
        self,
        record: _SyncChainRecord,
        dependency: _JobDependency,
        context: JobContext,
    ) -> None:
        """Record this job's label and active chain identifier.

        Args:
            record: Application-owned observation service.
            dependency: Dependency owned by the active job scope.
            context: Current job's native execution metadata.
        """
        record.jobs.append((self.label, context.chain_id, dependency.token))


@dataclass
class _AsyncChainJob(Job):
    """Represent a job that requires asynchronous execution.
    """  # fmt: skip

    label: str

    async def handle(self) -> None:
        """Complete one asynchronous test job without side effects.
        """  # fmt: skip
        _ = self.label


class _AsyncChainMiddleware:
    """Declare middleware that requires async job execution.
    """  # fmt: skip

    async def handle(
        self,
        context: JobContext,
        next_handler: JobNext,
    ) -> object:
        """Continue one async stage after retaining its metadata.

        Args:
            context: Metadata for this job attempt.
            next_handler: Asynchronous continuation.

        Returns:
            The value returned by the next stage.
        """
        _ = context
        return await next_handler()


@dataclass
class _AsyncMiddlewareChainJob(Job):
    """Represent a sync handler wrapped by async-only middleware.
    """  # fmt: skip

    label: str
    middleware = (_AsyncChainMiddleware,)

    def handle(
        self,
        record: _SyncChainRecord,
        context: JobContext,
    ) -> None:
        """Record execution if sync-chain preflight misses middleware.

        Args:
            record: Application-owned observation service.
            context: Current job's native execution metadata.
        """
        record.jobs.append((self.label, context.chain_id, object()))


@dataclass
class _TimedSyncChainJob(Job):
    """Represent a sync handler with an unsupported timeout policy.
    """  # fmt: skip

    label: str
    timeout: ClassVar[float | None] = 1.0

    def handle(
        self,
        record: _SyncChainRecord,
        context: JobContext,
    ) -> None:
        """Record execution if preflight ignores the timeout.

        Args:
            record: Application-owned observation service.
            context: Current job's native execution metadata.
        """
        record.jobs.append((self.label, context.chain_id, object()))


class _ChainDestinationProvider:
    """Register one destination observation in the native Container.
    """  # fmt: skip

    def __init__(self, record: _ChainDestinationRecord) -> None:
        """Retain the test-owned observation service.
        """  # fmt: skip
        self._record = record

    def register(self, container: ServiceRegistry) -> None:
        """Bind the destination observer as an application singleton.

        Args:
            container: Canonical application service registry.
        """
        container.instance(_ChainDestinationRecord, self._record)


@dataclass
class _FirstDestinationJob(Job):
    """Select one per-job queue within a configured chain.
    """  # fmt: skip

    label: str
    queue: ClassVar[str | None] = "first-job"

    def handle(
        self,
        record: _ChainDestinationRecord,
        context: JobContext,
    ) -> None:
        """Record the resolved connection and queue.

        Args:
            record: Application-owned destination observer.
            context: Current job's resolved dispatch metadata.
        """
        record.destinations.append(
            (self.label, context.connection, context.queue)
        )


@dataclass
class _DefaultDestinationJob(Job):
    """Use chain-wide destination defaults when no job override exists.
    """  # fmt: skip

    label: str

    def handle(
        self,
        record: _ChainDestinationRecord,
        context: JobContext,
    ) -> None:
        """Record the resolved connection and queue.

        Args:
            record: Application-owned destination observer.
            context: Current job's resolved dispatch metadata.
        """
        record.destinations.append(
            (self.label, context.connection, context.queue)
        )


@dataclass
class _LastDestinationJob(Job):
    """Select both per-job connection and queue inside a chain.
    """  # fmt: skip

    label: str
    connection: ClassVar[str | None] = "secondary"
    queue: ClassVar[str | None] = "last-job"

    def handle(
        self,
        record: _ChainDestinationRecord,
        context: JobContext,
    ) -> None:
        """Record the resolved connection and queue.

        Args:
            record: Application-owned destination observer.
            context: Current job's resolved dispatch metadata.
        """
        record.destinations.append(
            (self.label, context.connection, context.queue)
        )


class _ExecutionGate:
    """Coordinate concurrent jobs with deterministic synchronization.

    The gate records each job-owned dependency before releasing work.
    """

    def __init__(self, target: int) -> None:
        """Create a barrier for the expected number of active jobs.

        Args:
            target: Number of job handlers that must enter before release.
        """
        self.target = target
        self.entered = anyio.Event()
        self.release = anyio.Event()
        self.lock = anyio.Lock()
        self.dependencies: list[object] = []


@dataclass
class _ConcurrentJob(Job):
    """Wait at a gate while retaining one job-scoped dependency.

    Concurrent dispatch tests use this job to verify scope isolation.
    """

    index: int

    async def handle(
        self,
        gate: _ExecutionGate,
        dependency: _JobDependency,
    ) -> None:
        """Wait until every concurrent job enters its own scope.

        Args:
            gate: Shared synchronization owned by the application.
            dependency: Scope-owned dependency for this execution.
        """
        async with gate.lock:
            gate.dependencies.append(dependency.token)
            if len(gate.dependencies) == gate.target:
                gate.entered.set()
        await gate.release.wait()


@dataclass
class _RecordJob(Job):
    """Record a payload, injected scope dependency, and job metadata.

    The integration exercises serialization-safe class declarations.
    """

    value: str

    async def handle(
        self,
        record: _JobRecord,
        dependency: _JobDependency,
        context: JobContext,
    ) -> None:
        """Record injected services while the job scope remains active.

        Args:
            record: Application singleton shared by all job executions.
            dependency: Job-scoped value owned by the current execution.
            context: Metadata for the current job message.
        """
        record.values.append(
            (self.value, context.job_id, dependency.token),
        )
        record.max_attempts.append(context.max_attempts)


@dataclass
class _FailingJob(Job):
    """Raise one deterministic application error for batch accounting.
    """  # fmt: skip

    def handle(self) -> None:
        """Raise a known failure without external input.
        """  # fmt: skip
        message = "expected batch test failure"
        raise RuntimeError(message)


@dataclass
class _SyncRecordingMiddleware:
    """Record synchronous middleware around an inline job handler.
    """  # fmt: skip

    def __init__(self, record: _JobRecord) -> None:
        """Retain the application-owned observation service.

        Args:
            record: Application service used by the test assertion.
        """
        self._record = record

    def handle(
        self,
        context: JobContext,
        next_handler: SyncJobNext,
    ) -> object:
        """Run the next stage and record its position in the job scope.

        Args:
            context: Metadata for the current inline job attempt.
            next_handler: Synchronous continuation for the next stage.

        Returns:
            The handler result.
        """
        self._record.middleware_events.append(f"before:{context.attempt}")
        result = next_handler()
        self._record.middleware_events.append("after")
        return result


@dataclass
class _SyncRecordJob(Job):
    """Record an injected application service from sync job execution.

    This class exercises the Container's synchronous worker-thread path.
    """

    value: str
    middleware = (_SyncRecordingMiddleware,)

    def handle(
        self,
        record: _JobRecord,
        dependency: _JobDependency,
    ) -> None:
        """Record payload and the current job-owned dependency.

        Args:
            record: Application singleton used to observe execution.
            dependency: Dependency owned by this job scope.
        """
        record.values.append((self.value, "sync", dependency.token))


class _RecordingJobMiddleware:
    """Record middleware order through a dependency-injected service.
    """  # fmt: skip

    def __init__(self, record: _JobRecord) -> None:
        """Retain the application-owned observation service.

        Args:
            record: Application service used by the test assertion.
        """
        self._record = record

    async def handle(
        self,
        context: JobContext,
        next_handler: JobNext,
    ) -> object:
        """Wrap one handler and record its job identifier.

        Args:
            context: Metadata for the active job attempt.
            next_handler: Continuation to the next middleware or handler.

        Returns:
            The wrapped job result.
        """
        self._record.middleware_events.append(
            f"before:{context.attempt}",
        )
        result = await next_handler()
        self._record.middleware_events.append("after")
        return result


class _GlobalRecordingMiddleware:
    """Record global Queue middleware around each job attempt.
    """  # fmt: skip

    def __init__(self, record: _JobRecord) -> None:
        """Retain the application-owned observation service.

        Args:
            record: Application service used by the test assertion.
        """
        self._record = record

    async def handle(
        self,
        context: JobContext,
        next_handler: JobNext,
    ) -> object:
        """Wrap one job and record outer middleware ordering.

        Args:
            context: Metadata for the active job attempt.
            next_handler: Continuation to job-specific middleware or handler.

        Returns:
            The wrapped job result.
        """
        _ = context
        self._record.middleware_events.append("global-before")
        result = await next_handler()
        self._record.middleware_events.append("global-after")
        return result


class _GlobalSyncRecordingMiddleware:
    """Record application middleware around synchronous job execution.
    """  # fmt: skip

    def __init__(self, record: _JobRecord) -> None:
        """Retain the application-owned observation service.

        Args:
            record: Application service used by the test assertion.
        """
        self._record = record

    def handle(
        self,
        context: JobContext,
        next_handler: SyncJobNext,
    ) -> object:
        """Wrap one synchronous job and record middleware order.

        Args:
            context: Metadata for the active job attempt.
            next_handler: Synchronous continuation to local middleware.

        Returns:
            The wrapped job result.
        """
        _ = context
        self._record.middleware_events.append("global-before")
        result = next_handler()
        self._record.middleware_events.append("global-after")
        return result


@dataclass
class _MiddlewareJob(Job):
    """Verify job middleware wraps a handler inside its execution scope.
    """  # fmt: skip

    value: str
    middleware = (_RecordingJobMiddleware,)

    async def handle(
        self,
        record: _JobRecord,
        context: JobContext,
    ) -> None:
        """Record successful execution between middleware stages.

        Args:
            record: Application-owned middleware observation service.
            context: Metadata for the active job attempt.
        """
        record.middleware_events.append(self.value)
        record.max_attempts.append(context.max_attempts)


@pytest.mark.anyio
async def test_job_middleware_wraps_handler_with_injected_dependencies() -> (
    None
):
    """Resolve middleware in the same job scope as its handler.

    The continuation must preserve middleware order around job execution.
    """
    record = _JobRecord()
    application = Application(
        config={
            "app": {"name": "queue-middleware"},
            "queue": {"default_tries": 3},
        },
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_MiddlewareJob,)),
        ),
    )

    original_middleware = _MiddlewareJob.middleware
    try:
        async with application:
            manager = application.container.make(QueueManager)
            _MiddlewareJob.middleware = ()
            await manager.dispatch_async(_MiddlewareJob("handler"))
    finally:
        _MiddlewareJob.middleware = original_middleware

    assert record.middleware_events == [
        "before:1",
        "handler",
        "after",
    ]
    assert record.max_attempts == [3]


@pytest.mark.anyio
async def test_provider_middleware_wraps_every_job() -> None:
    """Run provider middleware outside declared job middleware.

    Both layers resolve from the canonical Container inside each job scope.
    """
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-global-middleware"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(
                jobs=(_MiddlewareJob, _RecordJob),
                middleware=(_GlobalRecordingMiddleware,),
            ),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        await manager.dispatch_async(
            _MiddlewareJob("with-local"),
            connection="sync",
        )
        await manager.dispatch_async(
            _RecordJob("global-only"),
            connection="sync",
        )

    assert record.middleware_events == [
        "global-before",
        "before:1",
        "with-local",
        "after",
        "global-after",
        "global-before",
        "global-after",
    ]


@pytest.mark.anyio
async def test_provider_middleware_wraps_sync_jobs_in_worker_threads() -> None:
    """Resolve global sync middleware in the active worker thread scope.

    The provider declaration surrounds the job's own middleware instance.
    """
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-global-sync-middleware"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(
                jobs=(_SyncRecordJob,),
                middleware=(_GlobalSyncRecordingMiddleware,),
            ),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        receipt = await anyio.to_thread.run_sync(
            manager.dispatch_sync,
            _SyncRecordJob("sync-global"),
        )

    assert receipt.state == "executed"
    assert [value[0] for value in record.values] == ["sync-global"]
    assert record.middleware_events == [
        "global-before",
        "before:1",
        "after",
        "global-after",
    ]


class _QueueTestProvider:
    """Register application and job scope services for integration.

    The application owns the returned singleton and scoped dependencies.
    """

    def __init__(self, record: _JobRecord) -> None:
        """Retain the record instance used to verify singleton identity.

        Args:
            record: Application-owned test record.
        """
        self._record = record

    def register(self, container: ServiceRegistry) -> None:
        """Register the singleton and job-scoped test dependencies.

        Args:
            container: Canonical application registry.
        """
        container.instance(_JobRecord, self._record)
        container.scoped(_JobDependency, scope=Scope.JOB)


class _GateProvider:
    """Register shared synchronization and one job-owned dependency.

    The application owns the gate while the Container owns job instances.
    """

    def __init__(self, gate: _ExecutionGate) -> None:
        """Retain the gate used by concurrent job handlers.

        Args:
            gate: Application-owned barrier and dependency recorder.
        """
        self._gate = gate

    def register(self, container: ServiceRegistry) -> None:
        """Register the gate and scoped dependency in the native graph.

        Args:
            container: Canonical application service registry.
        """
        container.instance(_ExecutionGate, self._gate)
        container.scoped(_JobDependency, scope=Scope.JOB)


class _JobLifecycle:
    """Coordinate one cancelled job and record resource finalization.
    """  # fmt: skip

    def __init__(self) -> None:
        """Create synchronization events and an empty cleanup counter.
        """  # fmt: skip
        self.entered = anyio.Event()
        self.release = anyio.Event()
        self.finalizations = 0


class _OwnedJobResource:
    """Represent a resource owned by one job execution scope.
    """  # fmt: skip

    def __init__(self, lifecycle: _JobLifecycle) -> None:
        """Retain the application-owned lifecycle observer.

        Args:
            lifecycle: Shared cancellation and cleanup recorder.
        """
        self.lifecycle = lifecycle


class _JobResourceProvider:
    """Register a generator-owned resource in the native JOB scope.
    """  # fmt: skip

    def __init__(self, lifecycle: _JobLifecycle) -> None:
        """Retain state used to verify scope teardown.

        Args:
            lifecycle: Shared cancellation and cleanup recorder.
        """
        self._lifecycle = lifecycle

    def register(self, container: ServiceRegistry) -> None:
        """Bind a resource factory to the canonical JOB scope.

        Args:
            container: Native application service registry.
        """
        container.instance(_JobLifecycle, self._lifecycle)
        container.scoped(
            _OwnedJobResource,
            self.create,
            scope=Scope.JOB,
        )

    async def create(self) -> AsyncIterator[_OwnedJobResource]:
        """Yield a resource and record its deterministic finalization.

        Yields:
            One job-owned resource instance.
        """
        try:
            yield _OwnedJobResource(self._lifecycle)
        finally:
            self._lifecycle.finalizations += 1


@dataclass
class _WaitForCancellationJob(Job):
    """Hold a job resource until the owning task is cancelled.
    """  # fmt: skip

    async def handle(self, resource: _OwnedJobResource) -> None:
        """Wait while retaining the scoped resource.

        Args:
            resource: Resource whose lifetime must include the handler.
        """
        resource.lifecycle.entered.set()
        await resource.lifecycle.release.wait()


class _RedisRecord:
    """Observe a job consumed by the real Taskiq Redis worker.

    The completion event provides deterministic synchronization.
    """

    def __init__(self) -> None:
        """Create one worker-owned completion signal and result list.
        """  # fmt: skip
        self.done = anyio.Event()
        self.values: list[str] = []
        self.attempts = 0


@dataclass
class _RedisJob(Job):
    """Write a queue payload after Redis Streams delivers the task.

    The job validates worker boot, registry lookup, and Container injection.
    """

    value: str
    tries = 2
    backoff = 0

    async def handle(self, record: _RedisRecord) -> None:
        """Record the payload and notify the integration test.

        Args:
            record: Application-owned observation service.
        """
        record.attempts += 1
        if record.attempts == _FIRST_ATTEMPT:
            message = "synthetic first-attempt failure"
            raise RuntimeError(message)
        record.values.append(self.value)
        record.done.set()


class _RedisProvider:
    """Register the observer injected into Redis-delivered jobs.
    """  # fmt: skip

    def __init__(self, record: _RedisRecord) -> None:
        """Retain the test-owned observer instance.

        Args:
            record: Completion signal shared with the test.
        """
        self._record = record

    def register(self, container: ServiceRegistry) -> None:
        """Bind the observer as one application singleton.

        Args:
            container: Canonical application service registry.
        """
        container.instance(_RedisRecord, self._record)


class _ChainRecord:
    """Track continuation order in a real Redis worker.
    """  # fmt: skip

    def __init__(self) -> None:
        """Create a worker-owned result list and completion event.
        """  # fmt: skip
        self.done = anyio.Event()
        self.values: list[str] = []


class _ConnectionRecord:
    """Observe delivery to a selected named connection.
    """  # fmt: skip

    def __init__(self) -> None:
        """Create one completion signal for connection isolation.
        """  # fmt: skip
        self.done = anyio.Event()
        self.values: list[str] = []


@dataclass
class _ConnectionJob(Job):
    """Record the selected logical connection in the injected test service.
    """  # fmt: skip

    value: str

    async def handle(self, record: _ConnectionRecord) -> None:
        """Signal delivery from one connection-specific Redis stream.

        Args:
            record: Application-owned observation service.
        """
        record.values.append(self.value)
        record.done.set()


class _ConnectionProvider:
    """Bind the connection-isolation observation service.
    """  # fmt: skip

    def __init__(self, record: _ConnectionRecord) -> None:
        """Retain the service shared by the application and test.

        Args:
            record: Application-owned job observation service.
        """
        self._record = record

    def register(self, container: ServiceRegistry) -> None:
        """Register the application-owned observation service.

        Args:
            container: Canonical application service registry.
        """
        container.instance(_ConnectionRecord, self._record)


class _ChainProvider:
    """Register the observer for Redis chain integration jobs.
    """  # fmt: skip

    def __init__(self, record: _ChainRecord) -> None:
        """Retain the test-owned chain observer.

        Args:
            record: Application-owned sequence recorder.
        """
        self._record = record

    def register(self, container: ServiceRegistry) -> None:
        """Bind the observer through the native service graph.

        Args:
            container: Canonical application registry.
        """
        container.instance(_ChainRecord, self._record)


@dataclass
class _RedisChainJob(Job):
    """Record one continuation delivered through Redis Streams.
    """  # fmt: skip

    value: str

    async def handle(self, record: _ChainRecord) -> None:
        """Append one member and signal after the chain completes.

        Args:
            record: Application-owned chain result recorder.
        """
        record.values.append(self.value)
        if len(record.values) == _EXPECTED_CHAIN_JOBS:
            record.done.set()


@pytest.mark.anyio
async def test_default_provider_runs_jobs_through_the_canonical_container() -> (
    None
):
    """Share the facade, injected manager, and isolated job scopes.

    The default application provider registers Queue without a second graph.
    """
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-integration"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_RecordJob,)),
        ),
    )
    async with application:
        manager = application.container.make(QueueManager)
        dispatcher = application.container.make(QueueDispatcher)
        assert dispatcher is manager
        assert Queue.manager() is manager

        first = await Queue.dispatch_async(_RecordJob("first"))
        second = await manager.dispatch_async(_RecordJob("second"))

    assert first.job_id != second.job_id
    assert [value[0] for value in record.values] == ["first", "second"]
    assert record.values[0][2] is not record.values[1][2]
    assert record.max_attempts == [1, 1]


@pytest.mark.anyio
async def test_concurrent_inline_jobs_have_independent_job_scopes() -> None:
    """Run twenty inline jobs concurrently through the real Container.

    A barrier proves that jobs overlap before any handler can complete.
    """
    target = 20
    gate = _ExecutionGate(target)
    application = Application(
        config={"app": {"name": "queue-concurrent"}},
        service_providers=(
            _GateProvider(gate),
            QueueServiceProvider(jobs=(_ConcurrentJob,)),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        async with anyio.create_task_group() as task_group:
            for index in range(target):
                task_group.start_soon(
                    manager.dispatch_async,
                    _ConcurrentJob(index),
                )
            with anyio.fail_after(5):
                await gate.entered.wait()
            gate.release.set()

    assert len(gate.dependencies) == target
    assert len({id(value) for value in gate.dependencies}) == target


@pytest.mark.anyio
async def test_job_scope_resource_closes_after_handler_cancellation() -> None:
    """Finalize a scoped resource when cancellation interrupts a job.

    The cancellation signal is controlled by events rather than a delay.
    """
    lifecycle = _JobLifecycle()
    application = Application(
        config={"app": {"name": "queue-job-cancellation"}},
        service_providers=(
            _JobResourceProvider(lifecycle),
            QueueServiceProvider(jobs=(_WaitForCancellationJob,)),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(
                manager.dispatch_async,
                _WaitForCancellationJob(),
            )
            with anyio.fail_after(5):
                await lifecycle.entered.wait()
            task_group.cancel_scope.cancel()

    assert lifecycle.finalizations == 1


@pytest.mark.anyio
async def test_sync_worker_dispatch_uses_container() -> None:
    """Allow synchronous jobs from a worker without opening an event loop.

    The application context propagates through AnyIO's managed worker bridge.
    """
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-sync-worker"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_SyncRecordJob,)),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        receipt = await anyio.to_thread.run_sync(
            manager.dispatch_sync,
            _SyncRecordJob("from-worker"),
        )

    assert receipt.state == "executed"
    assert [value[0] for value in record.values] == ["from-worker"]
    assert record.middleware_events == ["before:1", "after"]


@pytest.mark.anyio
async def test_inline_dispatch_rejects_request_scope_before_events() -> None:
    """Reject an inline job before emitting dispatch metadata in a request.

    A JOB scope cannot nest inside the active HTTP request scope.
    """
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-inline-request"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_RecordJob,)),
        ),
    )
    emitted: list[JobDispatching] = []

    async with application:
        manager = application.container.make(QueueManager)
        events = application.container.make(EventDispatcher)
        events.listen(JobDispatching, emitted.append)

        async with application.execution_scope(Scope.REQUEST):
            with pytest.raises(QueueCapabilityError):
                await manager.dispatch_async(_RecordJob("rejected"))

    assert emitted == []
    assert record.values == []


@pytest.mark.anyio
async def test_queue_fake_intercepts_manager_and_facade_before_execution() -> (
    None
):
    """Use one application fake for injected and facade dispatch calls.

    The fake path records jobs without executing handlers or opening brokers.
    """
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-fake"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_RecordJob,)),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        dispatcher = application.container.make(QueueDispatcher)
        async with Queue.fake() as fake:
            first = await Queue.dispatch_async(_RecordJob("facade"))
            second = await dispatcher.dispatch_async(_RecordJob("injected"))
        assert manager is Queue.manager()
        assert fake.pushed_count(_RecordJob) == _EXPECTED_FACADE_DISPATCHES
        fake.assert_pushed_with(_RecordJob, value="facade")
        fake.assert_pushed_on("default")
        fake.assert_pushed_on_connection("sync")
        assert first.state == second.state == "queued"

    assert record.values == []


@pytest.mark.anyio
async def test_queue_fake_asserts_delayed_job_delivery_metadata() -> None:
    """Preserve delay metadata for assertions without contacting a broker.
    """  # fmt: skip
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-fake-delay"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_RecordJob,)),
        ),
    )

    async with application:
        async with Queue.fake() as fake:
            receipt = await Queue.dispatch(
                _RecordJob("delayed"),
                delay=60,
            ).dispatch_async()

        fake.assert_pushed_delayed(_RecordJob)
        assert receipt.available_at is not None


@pytest.mark.anyio
async def test_queue_fake_runs_recorded_job_through_native_scope() -> None:
    """Execute fake records concurrently through native DI and job scopes.

    The helper bypasses the broker but keeps handler resolution and scopes real.
    """
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-fake-run"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_RecordJob,)),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        async with manager.fake() as fake:
            receipts = [
                await manager.dispatch_async(_RecordJob("first")),
                await manager.dispatch_async(_RecordJob("second")),
            ]
            results: list[object] = []

            async def run_next() -> None:
                """Execute one claimed fake job and collect its result.
                """  # fmt: skip
                results.append(await fake.run_next_async())

            async with anyio.create_task_group() as task_group:
                task_group.start_soon(run_next)
                task_group.start_soon(run_next)

            assert results == [None, None]
            with pytest.raises(AssertionError):
                await fake.run_next_async()
        with pytest.raises(QueueError, match="scope closes"):
            await fake.run_next_async()

    assert [receipt.state for receipt in receipts] == ["queued", "queued"]
    assert {value[0] for value in record.values} == {"first", "second"}
    assert {value[1] for value in record.values} == {
        receipt.job_id for receipt in receipts
    }
    dependency_tokens = {value[2] for value in record.values}
    assert len(dependency_tokens) == _EXPECTED_FAKE_EXECUTIONS


@pytest.mark.anyio
async def test_nested_queue_fakes_restore_the_previous_recorder() -> None:
    """Route nested dispatches to the innermost active fake only.

    Exiting the nested fake restores the outer application-local recorder.
    """
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-fake-nested"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_RecordJob,)),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        with manager.fake() as outer_fake:
            await manager.dispatch_async(_RecordJob("outer-before"))
            with manager.fake() as inner_fake:
                await manager.dispatch_async(_RecordJob("inner"))
            await manager.dispatch_async(_RecordJob("outer-after"))

    assert [
        item.job.value
        for item in outer_fake.records
        if isinstance(item.job, _RecordJob)
    ] == [
        "outer-before",
        "outer-after",
    ]
    assert [
        item.job.value
        for item in inner_fake.records
        if isinstance(item.job, _RecordJob)
    ] == ["inner"]
    assert record.values == []


@pytest.mark.anyio
async def test_queue_fake_state_isolated_between_concurrent_applications() -> (
    None
):
    """Keep parallel application fakes and managers independent.

    Each task activates its own Application context and canonical Container.
    """
    first_record = _JobRecord()
    second_record = _JobRecord()
    first_application = Application(
        config={"app": {"name": "queue-parallel-fakes"}},
        service_providers=(
            _QueueTestProvider(first_record),
            QueueServiceProvider(jobs=(_RecordJob,)),
        ),
    )
    second_application = Application(
        config={"app": {"name": "queue-parallel-fakes"}},
        service_providers=(
            _QueueTestProvider(second_record),
            QueueServiceProvider(jobs=(_RecordJob,)),
        ),
    )
    results: list[tuple[int, tuple[str, ...]]] = []

    async def dispatch_in(application: Application, value: str) -> None:
        """Record one fake dispatch through its active application's manager.

        Args:
            application: Independent application under test.
            value: Payload used to identify this application's record.
        """
        async with application:
            manager = application.container.make(QueueManager)
            async with manager.fake() as fake:
                await application.container.make(
                    QueueDispatcher
                ).dispatch_async(_RecordJob(value))
            results.append(
                (
                    id(manager),
                    tuple(
                        item.job.value
                        for item in fake.records
                        if isinstance(item.job, _RecordJob)
                    ),
                )
            )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(dispatch_in, first_application, "first")
        task_group.start_soon(dispatch_in, second_application, "second")

    assert len(results) == _EXPECTED_APPLICATIONS
    assert len({manager_id for manager_id, _ in results}) == (
        _EXPECTED_APPLICATIONS
    )
    assert {values[0] for _, values in results} == {"first", "second"}
    assert first_record.values == []
    assert second_record.values == []


@pytest.mark.anyio
async def test_bus_fake_and_dispatch_share_the_canonical_queue_manager() -> (
    None
):
    """Expose dispatch and fake operations through the Bus facade.

    The Bus facade must use the same manager injected as QueueDispatcher.
    """
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-bus-fake"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_RecordJob,)),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        assert application.container.make(BusDispatcher) is manager
        with Bus.fake() as fake:
            receipt = await Bus.dispatch_async(_RecordJob("bus"))

        assert fake.pushed(_RecordJob)
        assert receipt.state == "queued"

    assert record.values == []


@pytest.mark.anyio
async def test_fake_rejects_dispatch_from_child_task_after_scope_exit() -> None:
    """Close a fake inherited by a child task before it can record late work.

    Late dispatch must fail without falling through to a real broker.
    """
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-fake-child"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_RecordJob,)),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        release = anyio.Event()
        finished = anyio.Event()
        failures: list[BaseException] = []

        async def dispatch_after_close() -> None:
            """Try inherited fake dispatch after its owner restores context.
            """  # fmt: skip
            await release.wait()
            try:
                await manager.dispatch_async(_RecordJob("late"))
            except QueueError as error:
                failures.append(error)
            finally:
                finished.set()

        async with anyio.create_task_group() as task_group:
            async with Queue.fake():
                task_group.start_soon(dispatch_after_close)
            release.set()
            with anyio.fail_after(5):
                await finished.wait()

    assert len(failures) == 1
    assert record.values == []


@pytest.mark.anyio
async def test_real_redis_stream_worker_executes_registered_job(
    queue_redis_port: int,
) -> None:
    """Publish and consume one job through Taskiq Redis Streams.

    The integration verifies an actual broker and worker lifecycle.
    """
    record = _RedisRecord()
    application_name = f"queue-redis-{uuid4().hex}"
    application = Application(
        config={
            "app": {"name": application_name},
            "queue": {
                "default_connection": "redis",
                "default_queue": "integration",
                "connections": {
                    "redis": {
                        "driver": "redis_stream",
                        "options": {
                            "url": f"redis://127.0.0.1:{queue_redis_port}/15"
                        },
                    }
                },
                "schedule_poll_interval": 0.1,
                "schedule_loop_interval": 0.1,
            },
        },
        service_providers=(
            _RedisProvider(record),
            QueueServiceProvider(jobs=(_RedisJob,)),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        dispatcher = application.container.make(EventDispatcher)
        emitted: list[QueueEvent] = []
        dispatcher.listen(QueueEvent, emitted.append)
        receipts: list[DispatchReceipt] = []

        async def run_worker() -> None:
            """Run the real Redis consumer until the test cancels it.
            """  # fmt: skip
            await manager.work_async(
                connection="redis",
                queue="integration",
                concurrency=2,
                prefetch=2,
            )

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_worker)
            receipts.append(
                await manager.dispatch_async(_RedisJob("redis-worker"))
            )
            with anyio.fail_after(15):
                await record.done.wait()
            task_group.cancel_scope.cancel()

    assert len(receipts) == 1
    assert receipts[0].state == "queued"
    assert record.attempts == _SECOND_ATTEMPT
    assert record.values == ["redis-worker"]
    retry_events = [event for event in emitted if isinstance(event, JobRetried)]
    assert len(retry_events) == 1
    assert retry_events[0].attempt == 1
    assert retry_events[0].job_id == receipts[0].job_id
    assert retry_events[0].connection == "redis"
    assert retry_events[0].queue == "integration"


@pytest.mark.anyio
async def test_bus_chain_executes_in_order() -> None:
    """Run every inline chain member in an isolated job scope.

    The facade and manager share the same registered jobs and dispatcher.
    """
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-chain"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_RecordJob,)),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        assert application.container.make(BusDispatcher) is manager
        assert Bus.resolve_service() is manager
        chain = Bus.chain([_RecordJob("second")])
        chain.prepend(_RecordJob("first")).append(_RecordJob("third"))
        receipt = await chain.dispatch_async()
        with pytest.raises(QueueError):
            await chain.dispatch_async()

    assert receipt.state == "executed"
    assert receipt.chain_id is not None
    assert [value[0] for value in record.values] == [
        "first",
        "second",
        "third",
    ]


@pytest.mark.anyio
async def test_bus_chain_dispatch_sync_executes_in_order_with_one_id() -> None:
    """Run a synchronous chain through separate native job scopes.

    The receipt and injected JobContext expose the same chain identifier.
    """
    record = _SyncChainRecord()
    application = Application(
        config={"app": {"name": "queue-sync-chain"}},
        service_providers=(
            _SyncChainProvider(record),
            QueueServiceProvider(jobs=(_SyncChainJob,)),
        ),
    )

    async with application:
        chain = Bus.chain([_SyncChainJob("first"), _SyncChainJob("second")])
        receipt = await anyio.to_thread.run_sync(chain.dispatch_sync)

    assert receipt.state == "executed"
    assert receipt.chain_id is not None
    assert [value[:2] for value in record.jobs] == [
        ("first", receipt.chain_id),
        ("second", receipt.chain_id),
    ]
    assert record.jobs[0][2] is not record.jobs[1][2]


@pytest.mark.anyio
async def test_sync_chain_preflights_all_handlers_before_running() -> None:
    """Reject async work before a sync chain performs its first side effect.

    A later async member cannot leave an earlier sync member partially run.
    """
    record = _SyncChainRecord()
    application = Application(
        config={"app": {"name": "queue-sync-chain-preflight"}},
        service_providers=(
            _SyncChainProvider(record),
            QueueServiceProvider(jobs=(_SyncChainJob, _AsyncChainJob)),
        ),
    )

    async with application:
        chain = Bus.chain([_SyncChainJob("first"), _AsyncChainJob("async")])
        with pytest.raises(QueueCapabilityError):
            await anyio.to_thread.run_sync(chain.dispatch_sync)

    assert record.jobs == []


@pytest.mark.anyio
async def test_sync_chain_preflights_async_middleware_before_running() -> None:
    """Reject async-only middleware before any earlier member executes.

    Middleware declarations are part of the sync chain's preflight policy.
    """
    record = _SyncChainRecord()
    application = Application(
        config={"app": {"name": "queue-sync-chain-middleware"}},
        service_providers=(
            _SyncChainProvider(record),
            QueueServiceProvider(
                jobs=(_SyncChainJob, _AsyncMiddlewareChainJob)
            ),
        ),
    )

    async with application:
        chain = Bus.chain(
            [
                _SyncChainJob("first"),
                _AsyncMiddlewareChainJob("async-middleware"),
            ]
        )
        with pytest.raises(QueueCapabilityError):
            await anyio.to_thread.run_sync(chain.dispatch_sync)

    assert record.jobs == []


@pytest.mark.anyio
async def test_sync_chain_preflights_unsupported_timeout_before_running() -> (
    None
):
    """Reject a handler timeout before any chain member can run.

    Python cannot safely stop a synchronous handler after it starts.
    """
    record = _SyncChainRecord()
    application = Application(
        config={"app": {"name": "queue-sync-chain-timeout"}},
        service_providers=(
            _SyncChainProvider(record),
            QueueServiceProvider(jobs=(_SyncChainJob, _TimedSyncChainJob)),
        ),
    )

    async with application:
        chain = Bus.chain(
            [_SyncChainJob("first"), _TimedSyncChainJob("timeout")]
        )
        with pytest.raises(QueueCapabilityError):
            await anyio.to_thread.run_sync(chain.dispatch_sync)

    assert record.jobs == []


@pytest.mark.anyio
async def test_sync_chain_fake_records_all_members_without_execution() -> None:
    """Record every sync chain member without resolving its handler.

    The inherited fake context intercepts worker-thread chain dispatch.
    """
    record = _SyncChainRecord()
    application = Application(
        config={"app": {"name": "queue-sync-chain-fake"}},
        service_providers=(
            _SyncChainProvider(record),
            QueueServiceProvider(jobs=(_SyncChainJob,)),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        with manager.fake() as fake:
            chain = Bus.chain([_SyncChainJob("first"), _SyncChainJob("second")])
            receipt = await anyio.to_thread.run_sync(chain.dispatch_sync)

    assert receipt.state == "queued"
    assert receipt.chain_id is not None
    assert len(fake.records) == _EXPECTED_CHAIN_JOBS
    assert all(
        record.receipt.chain_id == receipt.chain_id for record in fake.records
    )
    assert record.jobs == []


@pytest.mark.anyio
async def test_sync_chain_rejects_active_async_execution_context() -> None:
    """Reject sync chain execution on the event loop before any handler.

    Async callers must use the explicit asynchronous chain API.
    """
    record = _SyncChainRecord()
    application = Application(
        config={"app": {"name": "queue-sync-chain-async-boundary"}},
        service_providers=(
            _SyncChainProvider(record),
            QueueServiceProvider(jobs=(_SyncChainJob,)),
        ),
    )

    async with application:
        chain = Bus.chain([_SyncChainJob("first")])
        with pytest.raises(QueueCapabilityError):
            chain.dispatch_sync()

    assert record.jobs == []


@pytest.mark.anyio
async def test_sync_chain_rejects_non_sync_connection_before_running() -> None:
    """Reject a broker connection before a sync chain starts side effects.

    Preflight reads configuration without constructing the remote broker.
    """
    record = _SyncChainRecord()
    application = Application(
        config={
            "app": {"name": "queue-sync-chain-driver"},
            "queue": {
                "connections": {
                    "sync": {"driver": "sync"},
                    "remote": {
                        "driver": "redis_stream",
                        "options": {"url": "redis://127.0.0.1:6379/0"},
                    },
                },
            },
        },
        service_providers=(
            _SyncChainProvider(record),
            QueueServiceProvider(jobs=(_SyncChainJob,)),
        ),
    )

    async with application:
        chain = Bus.chain([_SyncChainJob("first")]).on_connection("remote")
        with pytest.raises(QueueCapabilityError):
            await anyio.to_thread.run_sync(chain.dispatch_sync)

    assert record.jobs == []


@pytest.mark.anyio
async def test_sync_chain_rejects_nested_execution_scope() -> None:
    """Reject synchronous chaining inside a request-owned service scope.

    The sync API does not create an unsupported nested job lifetime.
    """
    record = _SyncChainRecord()
    application = Application(
        config={"app": {"name": "queue-sync-chain-scope"}},
        service_providers=(
            _SyncChainProvider(record),
            QueueServiceProvider(jobs=(_SyncChainJob,)),
        ),
    )

    async with application:
        chain = Bus.chain([_SyncChainJob("first")])
        async with application.execution_scope(Scope.REQUEST):
            with pytest.raises(QueueCapabilityError):
                await anyio.to_thread.run_sync(chain.dispatch_sync)

    assert record.jobs == []


@pytest.mark.anyio
async def test_sync_chain_rejects_empty_and_oversized_manager_inputs() -> None:
    """Keep internal synchronous chain execution bounded and non-empty.

    Normal callers reach this boundary through the validated pending builder.
    """
    application = Application(
        config={"app": {"name": "queue-sync-chain-bounds"}},
        service_providers=(QueueServiceProvider(jobs=(_SyncChainJob,)),),
    )

    async with application:
        manager = application.container.make(QueueManager)
        invalid_chains = (
            (),
            tuple(
                _SyncChainJob(str(index))
                for index in range(_OVERSIZED_CHAIN_LENGTH)
            ),
        )
        for jobs in invalid_chains:
            with pytest.raises(QueueConfigurationError):
                manager.dispatch_chain_sync(
                    jobs,
                    connection=None,
                    queue=None,
                )


@pytest.mark.anyio
async def test_chain_destination_defaults_allow_per_job_overrides() -> None:
    """Preserve each job's destination inside shared chain configuration.
    """  # fmt: skip
    record = _ChainDestinationRecord()
    application = Application(
        config={
            "app": {"name": "queue-chain-destinations"},
            "queue": {
                "default_connection": "sync",
                "connections": {
                    "sync": {"driver": "sync"},
                    "secondary": {"driver": "sync"},
                },
            },
        },
        service_providers=(
            _ChainDestinationProvider(record),
            QueueServiceProvider(
                jobs=(
                    _FirstDestinationJob,
                    _DefaultDestinationJob,
                    _LastDestinationJob,
                )
            ),
        ),
    )

    async with application:
        receipt = (
            await Bus.chain(
                [
                    _FirstDestinationJob("first"),
                    _DefaultDestinationJob("middle"),
                    _LastDestinationJob("last"),
                ]
            )
            .on_connection("sync")
            .on_queue("chain-default")
            .dispatch_async()
        )

    assert receipt.connection == "sync"
    assert receipt.queue == "first-job"
    assert record.destinations == [
        ("first", "sync", "first-job"),
        ("middle", "sync", "chain-default"),
        ("last", "secondary", "last-job"),
    ]


@pytest.mark.anyio
async def test_bus_batch_records_success_and_allowed_failure_counts() -> None:
    """Retain local batch status without a competing batch repository.

    Inline jobs execute through separate native job scopes in order.
    """
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-batch"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_FailingJob, _RecordJob)),
        ),
    )

    async with application:
        batch = (
            await Bus.batch(
                [_FailingJob(), _RecordJob("completed")],
            )
            .name("Document batch")
            .allow_failures()
            .dispatch_async()
        )

    assert batch.name == "Document batch"
    assert batch.total_jobs == _EXPECTED_CHAIN_JOBS
    assert batch.pending_jobs == 0
    assert batch.processed_jobs == 1
    assert batch.failed_jobs == 1
    assert batch.state == "completed_with_failures"
    assert [value[0] for value in record.values] == ["completed"]


@pytest.mark.anyio
async def test_batch_history_evicts_old_status_and_retains_latest() -> None:
    """Bound completed batch snapshots without evicting active batches.

    A handle reports an unavailable status after its snapshot is evicted.
    """
    record = _JobRecord()
    application = Application(
        config={
            "app": {"name": "queue-batch-history"},
            "queue": {"batch_history_limit": 1},
        },
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_RecordJob,)),
        ),
    )

    async with application:
        first_batch = await Bus.batch([_RecordJob("first")]).dispatch_async()
        second_batch = await Bus.batch([_RecordJob("second")]).dispatch_async()

        with pytest.raises(QueueError, match="not available"):
            _ = first_batch.state

    assert second_batch.state == "completed"
    assert [value[0] for value in record.values] == ["first", "second"]


@pytest.mark.anyio
async def test_batch_history_rejects_new_batch_when_capacity_is_active() -> (
    None
):
    """Protect active local batches and reject admission at the configured cap.

    The limit applies before dispatch side effects occur.
    """
    gate = _ExecutionGate(target=1)
    application = Application(
        config={
            "app": {"name": "queue-batch-active-capacity"},
            "queue": {"batch_history_limit": 1},
        },
        service_providers=(
            _GateProvider(gate),
            QueueServiceProvider(jobs=(_ConcurrentJob,)),
        ),
    )

    async with application:
        batches: list[BatchHandle] = []

        async def run_first_batch() -> None:
            """Run one batch until the deterministic gate blocks it.
            """  # fmt: skip
            batches.append(
                await Bus.batch([_ConcurrentJob(0)]).dispatch_async()
            )

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_first_batch)
            await gate.entered.wait()
            try:
                with pytest.raises(QueueCapabilityError, match="capacity"):
                    await Bus.batch([_ConcurrentJob(1)]).dispatch_async()
            finally:
                gate.release.set()

    assert len(batches) == 1
    assert batches[0].state == "completed"
    assert gate.dependencies


@pytest.mark.anyio
async def test_bus_fake_records_batch_members_without_backend_access() -> None:
    """Use the canonical fake for every batch member and status snapshot.

    The selected broker is never constructed while the fake is active.
    """
    record = _JobRecord()
    application = Application(
        config={"app": {"name": "queue-batch-fake"}},
        service_providers=(
            _QueueTestProvider(record),
            QueueServiceProvider(jobs=(_RecordJob,)),
        ),
    )

    async with application:
        async with Queue.fake() as fake:
            batch = await Bus.batch(
                [_RecordJob("one"), _RecordJob("two")],
            ).dispatch_async()
        assert fake.pushed_count(_RecordJob) == _EXPECTED_CHAIN_JOBS
        assert {record.receipt.batch_id for record in fake.records} == {
            batch.id
        }
        fake.assert_pushed_batch(
            batch.id,
            (_RecordJob, _RecordJob),
        )
        with pytest.raises(AssertionError):
            fake.assert_pushed_batch(batch.id, (_RecordJob,))
        assert batch.state == "queued"
        assert batch.pending_jobs == _EXPECTED_CHAIN_JOBS

    assert record.values == []


@pytest.mark.anyio
async def test_redis_worker_continues_chain_after_successful_job(
    queue_redis_port: int,
) -> None:
    """Publish a continuation only after the preceding job succeeds.

    Both jobs run through one actual Redis Streams worker process.
    """
    record = _ChainRecord()
    application = Application(
        config={
            "app": {"name": f"queue-redis-chain-{uuid4().hex}"},
            "queue": {
                "default_connection": "redis",
                "connections": {
                    "redis": {
                        "driver": "redis_stream",
                        "options": {
                            "url": f"redis://127.0.0.1:{queue_redis_port}/15"
                        },
                    }
                },
            },
        },
        service_providers=(
            _ChainProvider(record),
            QueueServiceProvider(jobs=(_RedisChainJob,)),
        ),
    )
    receipts: list[DispatchReceipt] = []

    async with application:
        manager = application.container.make(QueueManager)

        async def run_worker() -> None:
            """Consume the chain until cancellation.
            """  # fmt: skip
            await manager.work_async(
                connection="redis",
                queue="chains",
                concurrency=2,
                prefetch=2,
            )

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_worker)
            receipts.append(
                await Bus.chain(
                    [_RedisChainJob("first"), _RedisChainJob("second")],
                )
                .on_connection("redis")
                .on_queue("chains")
                .dispatch_async()
            )
            with anyio.fail_after(15):
                await record.done.wait()
            task_group.cancel_scope.cancel()

    assert len(receipts) == 1
    assert receipts[0].state == "queued"
    assert receipts[0].chain_id is not None
    assert record.values == ["first", "second"]


@pytest.mark.anyio
async def test_redis_named_connections_do_not_consume_each_others_jobs(
    queue_redis_port: int,
) -> None:
    """Keep two named connections isolated on one Redis server.

    Each configured connection owns a distinct physical stream, even when
    both connections use the same Redis URL and logical queue name.
    """
    record = _ConnectionRecord()
    worker_ready = anyio.Event()
    wrong_connection_received_job = anyio.Event()
    redis_url = f"redis://127.0.0.1:{queue_redis_port}/15"
    application = Application(
        config={
            "app": {"name": f"queue-connections-{uuid4().hex}"},
            "queue": {
                "default_connection": "publisher",
                "connections": {
                    "publisher": {
                        "driver": "redis_stream",
                        "options": {"url": redis_url},
                    },
                    "consumer": {
                        "driver": "redis_stream",
                        "options": {"url": redis_url},
                    },
                },
            },
        },
        service_providers=(
            _ConnectionProvider(record),
            QueueServiceProvider(jobs=(_ConnectionJob,)),
        ),
    )

    async with application:
        manager = application.container.make(QueueManager)
        events = application.container.make(EventDispatcher)

        async def observe_worker(event: QueueEvent) -> None:
            """Signal after the consumer broker has started.

            Args:
                event: Metadata for a worker lifecycle event.
            """
            if (
                event.connection == "consumer"
                and event.job_name == "worker.startup"
            ):
                worker_ready.set()

        async def observe_processing(event: JobProcessing) -> None:
            """Signal when the wrong connection receives a job.

            Args:
                event: Metadata for one processing attempt.
            """
            if event.connection == "consumer":
                wrong_connection_received_job.set()

        events.listen(QueueEvent, observe_worker)
        events.listen(JobProcessing, observe_processing)

        async def run_consumer() -> None:
            """Consume the named connection until the test ends.
            """  # fmt: skip
            await manager.work_async(
                connection="consumer",
                queue="shared-name",
            )

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_consumer)
            with anyio.fail_after(15):
                await worker_ready.wait()
                await anyio.wait_all_tasks_blocked()
            await manager.dispatch_async(
                _ConnectionJob("publisher"),
                connection="publisher",
                queue="shared-name",
            )

            with anyio.move_on_after(0.3) as wait_scope:
                await wrong_connection_received_job.wait()
            assert wait_scope.cancel_called
            assert record.values == []

            async def run_publisher() -> None:
                """Consume the publisher connection's physical stream.
                """  # fmt: skip
                await manager.work_async(
                    connection="publisher",
                    queue="shared-name",
                )

            task_group.start_soon(run_publisher)
            with anyio.fail_after(15):
                await record.done.wait()
            task_group.cancel_scope.cancel()

    assert record.values == ["publisher"]
