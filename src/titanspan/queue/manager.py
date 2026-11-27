"""Coordinate native job dispatch with application-owned Taskiq brokers.

Taskiq owns transport and message consumption. Titanspan owns trusted job
registration, payload policy, dependency scopes, and application lifecycle.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from dataclasses import replace as replace_dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, NoReturn, Protocol, cast
from uuid import UUID, uuid4, uuid5

import anyio
from taskiq import (
    Context as TaskiqContext,
)
from taskiq import (
    SmartRetryMiddleware,
    TaskiqDepends,
    TaskiqMessage,
)
from taskiq.abc.broker import AsyncBroker
from taskiq.abc.middleware import TaskiqMiddleware
from taskiq.api import run_receiver_task, run_scheduler_task
from taskiq.scheduler.scheduler import TaskiqScheduler
from taskiq.serializers.json_serializer import JSONSerializer

from titanspan._application_context import (
    ActiveApplicationContext,
    active_application_context,
    bind_application_context,
)
from titanspan.container import Scope
from titanspan.contracts.queue import (
    BatchBuilder,
    BusDispatcher,
    ChainBuilder,
    DispatchReceipt,
    JobMiddlewareType,
)
from titanspan.pipeline import Pipeline
from titanspan.queue._backends.taskiq import create_taskiq_transport
from titanspan.queue._serialization import (
    DecodedJob,
    JobCodec,
    JobMessageMetadata,
)
from titanspan.queue.batch import (
    BatchHandle,
    BatchSnapshot,
    BatchState,
    PendingBatch,
)
from titanspan.queue.chain import PendingChain
from titanspan.queue.configuration import (
    QueueConfiguration,
    QueueConnectionConfiguration,
    is_valid_name,
)
from titanspan.queue.events import (
    JobDispatched,
    JobDispatching,
    JobFailed,
    JobProcessed,
    JobProcessing,
    QueueEvent,
)
from titanspan.queue.exceptions import (
    QueueCapabilityError,
    QueueConfigurationError,
    QueueDispatchError,
    QueueError,
    QueueSerializationError,
)
from titanspan.queue.job import Job, JobContext, validate_job_policy

if TYPE_CHECKING:
    from types import TracebackType

    from taskiq.abc.schedule_source import ScheduleSource
    from taskiq.kicker import AsyncKicker

    from titanspan.contracts.config import ConfigRepository
    from titanspan.contracts.container import ServiceContainer
    from titanspan.contracts.events import EventDispatcher
    from titanspan.contracts.logging import LogWriter
    from titanspan.foundation.application import Application

type QueueBrokerFactory = Callable[
    [QueueConnectionConfiguration, str, str],
    AsyncBroker,
]

_QUEUE_CLOSED_ERROR = "The Queue manager has already shut down."
_JOB_CONTEXT_ERROR = "A JobContext is only available during job execution."
_APPLICATION_CONTEXT_ERROR = (
    "Queue operations require the active application that owns this manager."
)
_SYNC_IN_ASYNC_ERROR = (
    "Synchronous Queue dispatch cannot run inside an async context; "
    "use dispatch_async."
)
_SCOPED_SYNC_ERROR = (
    "Synchronous dispatch cannot start a nested job scope. "
    "Use a queued connection or dispatch_async outside request scope."
)
_ASYNC_HANDLER_ERROR = (
    "The selected handler requires async execution; use dispatch_async."
)
_ASYNC_MIDDLEWARE_ERROR = (
    "Synchronous job middleware cannot wrap async execution. "
    "Use an async handle method."
)
_SYNC_MIDDLEWARE_ERROR = (
    "Asynchronous job middleware cannot run through dispatch_sync. "
    "Use an async connection."
)
_SYNC_TIMEOUT_ERROR = (
    "A synchronous Python handler cannot be safely preempted by a timeout."
)
_INVALID_JOB_ERROR = (
    "The registered job does not define a callable handle method."
)
_INVALID_RETRIES_ERROR = "The job retry policy is invalid."
_INVALID_BACKOFF_ERROR = (
    "The job backoff policy must contain non-negative values."
)
_NO_DELAY_SOURCE_ERROR = (
    "The selected queue backend has no durable scheduling source."
)
_TASK_NAME = "titanspan.queue.execute.v1"
_EXECUTION_MODE_ERROR = "Taskiq workers require the asyncio execution backend."
_QUEUE_FAKE_ERROR = "Queue fake assertions failed."
_MISSING_ATTRIBUTE = object()
_MAX_CHAIN_JOBS = 256
_TASKIQ_CONTEXT_DEPENDENCY = cast(
    "TaskiqContext",
    TaskiqDepends(),
)


class _TaskKicker(Protocol):
    """Describe the narrow public Taskiq kicker operations used by Queue.

    The concrete Taskiq type remains private to the adapter boundary.
    """

    def with_labels(self, **labels: str | float) -> _TaskKicker:
        """Return a kicker with transport and retry labels.
        """  # fmt: skip
        ...

    def with_task_id(self, task_id: str | None) -> _TaskKicker:
        """Return a kicker with an application-owned job identifier.
        """  # fmt: skip
        ...

    async def kiq(self, payload: str) -> object:
        """Publish one safe JSON string through Taskiq.
        """  # fmt: skip
        ...

    async def schedule_by_time(
        self,
        source: ScheduleSource,
        time: datetime,
        payload: str,
    ) -> object:
        """Store one delayed message through a Taskiq schedule source.
        """  # fmt: skip
        ...


class _RegisteredTask(Protocol):
    """Describe the registration object returned by Taskiq.

    A task is local to one application-owned broker.
    """

    def kicker(self) -> _TaskKicker:
        """Create a per-publication Taskiq kicker.
        """  # fmt: skip
        ...

    @property
    def task_name(self) -> str:
        """Return the registered Taskiq task name.
        """  # fmt: skip
        ...


@dataclass(slots=True)
class _TaskiqConnection:
    """Own one broker, task registration, and optional schedule source.

    The connection belongs to one QueueManager and one event loop.
    """

    broker: AsyncBroker
    task: _RegisteredTask
    physical_queue: str
    schedule_source: ScheduleSource | None = None
    started: bool = False
    source_started: bool = False
    closed: bool = False
    loop: asyncio.AbstractEventLoop | None = None
    start_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass(frozen=True, slots=True)
class QueueDispatchRecord:
    """Record one fake dispatch without rendering its payload by default.

    Attributes:
        job: Caller-owned job instance retained only by the fake scope.
        job_name: Registered identifier associated with the instance.
        receipt: Receipt returned to the caller.
    """

    job: Job = field(repr=False)
    job_name: str
    receipt: DispatchReceipt


class QueueFake:
    """Record Queue operations without creating or contacting a broker.

    Fakes are selected by the owning manager's execution-local ContextVar.
    """

    def __init__(self) -> None:
        """Create an isolated empty dispatch record.
        """  # fmt: skip
        self._records: list[QueueDispatchRecord] = []
        self._lock = threading.RLock()
        self._closed = False

    @property
    def records(self) -> tuple[QueueDispatchRecord, ...]:
        """Return a stable snapshot of recorded dispatch metadata.
        """  # fmt: skip
        with self._lock:
            return tuple(self._records)

    def record(
        self,
        job: Job,
        job_name: str,
        receipt: DispatchReceipt,
    ) -> None:
        """Retain one job reference inside this fake's lifetime.

        Args:
            job: Job object supplied by the application.
            job_name: Trusted registration name.
            receipt: Native metadata returned to dispatch callers.
        """
        with self._lock:
            if self._closed:
                msg = "A Queue fake cannot record after its scope closes."
                raise QueueError(msg)
            self._records.append(QueueDispatchRecord(job, job_name, receipt))

    def close_scope(self) -> None:
        """Reject inherited child-context writes after scope restoration.
        """  # fmt: skip
        with self._lock:
            self._closed = True

    def assert_pushed(self, job_type: type[object]) -> None:
        """Require at least one dispatch for a selected job type.

        Args:
            job_type: Job class expected in the fake record.

        Raises:
            AssertionError: If no matching dispatch exists.
        """
        if not self.pushed(job_type):
            raise AssertionError(_QUEUE_FAKE_ERROR)

    def assert_pushed_count(
        self,
        job_type: type[object],
        count: int,
    ) -> None:
        """Require an exact dispatch count for one job class.

        Args:
            job_type: Job class selected for counting.
            count: Expected number of matching dispatches.

        Raises:
            AssertionError: If the count differs.
        """
        actual = self.pushed_count(job_type)
        if actual != count:
            msg = f"Expected {count} dispatches, observed {actual}."
            raise AssertionError(msg)

    def assert_nothing_pushed(self) -> None:
        """Require that no dispatch was recorded.

        Raises:
            AssertionError: If the fake contains one or more dispatches.
        """
        if self.records:
            raise AssertionError(_QUEUE_FAKE_ERROR)

    def assert_pushed_on(self, queue: str) -> None:
        """Require one recorded dispatch to use the selected queue.

        Args:
            queue: Expected logical queue name.

        Raises:
            AssertionError: If no dispatch targets the selected queue.
        """
        if not any(record.receipt.queue == queue for record in self.records):
            raise AssertionError(_QUEUE_FAKE_ERROR)

    def assert_pushed_on_connection(self, connection: str) -> None:
        """Require at least one record for a configured connection.

        Args:
            connection: Expected connection name.

        Raises:
            AssertionError: If no recorded dispatch uses the connection.
        """
        if not any(
            record.receipt.connection == connection for record in self.records
        ):
            raise AssertionError(_QUEUE_FAKE_ERROR)

    def assert_pushed_with(
        self,
        job_type: type[object],
        **attributes: object,
    ) -> None:
        """Match one exact job type and selected payload attributes.

        Args:
            job_type: Exact class expected in the fake record.
            **attributes: Public job fields whose values must match.

        Raises:
            AssertionError: If no recorded job matches every field.
        """
        for record in self.records:
            if type(record.job) is not job_type:
                continue
            if all(
                getattr(record.job, name, _MISSING_ATTRIBUTE) == value
                for name, value in attributes.items()
            ):
                return
        raise AssertionError(_QUEUE_FAKE_ERROR)

    def assert_pushed_delayed(self, job_type: type[object]) -> None:
        """Require a delayed dispatch for the selected job class.

        Args:
            job_type: Exact class expected in the fake record.

        Raises:
            AssertionError: If no matching dispatch has a delivery time.
        """
        if not any(
            type(record.job) is job_type
            and record.receipt.available_at is not None
            for record in self.records
        ):
            raise AssertionError(_QUEUE_FAKE_ERROR)

    def pushed(self, job_type: type[object]) -> bool:
        """Check whether a job class was recorded.

        Args:
            job_type: Job class selected for inspection.

        Returns:
            Whether the fake recorded that exact class.
        """
        return self.pushed_count(job_type) > 0

    def pushed_count(self, job_type: type[object]) -> int:
        """Count records for one exact job class.

        Args:
            job_type: Job class selected for counting.

        Returns:
            Number of matching dispatch records.
        """
        return sum(type(record.job) is job_type for record in self.records)


class QueueFakeScope:
    """Select and restore one manager-owned fake in sync or async code.

    Nested scopes restore their preceding fake after all exit paths.
    """

    def __init__(self, manager: QueueManager) -> None:
        """Create a fake scope without activating it.

        Args:
            manager: Canonical application-owned Queue manager.
        """
        self._manager = manager
        self._fake = QueueFake()
        self._token: Token[QueueFake | None] | None = None
        self._entered = False

    def __enter__(self) -> QueueFake:
        """Activate the fake and return its assertion API.

        Returns:
            The fake selected for the current execution context.
        """
        if self._entered:
            msg = "A Queue fake scope cannot be re-entered."
            raise QueueError(msg)
        self._entered = True
        self._token = self._manager.activate_fake(self._fake)
        return self._fake

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Restore the preceding fake after normal or exceptional exit.

        Args:
            exception_type: Active exception class, if any.
            exception: Active exception, if any.
            traceback: Traceback associated with the active exception.
        """
        _ = exception_type, exception, traceback
        self._restore()

    async def __aenter__(self) -> QueueFake:
        """Activate the fake in an asynchronous context.

        Returns:
            The fake selected for the current task context.
        """
        return self.__enter__()

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Restore the preceding fake after asynchronous execution.

        Args:
            exception_type: Active exception class, if any.
            exception: Active exception, if any.
            traceback: Traceback associated with the active exception.
        """
        self.__exit__(exception_type, exception, traceback)

    def _restore(self) -> None:
        """Reset this context variable to its preceding value.
        """  # fmt: skip
        token = self._token
        if token is not None:
            self._manager.restore_fake(token)
            self._token = None
            self._fake.close_scope()

    _manager: QueueManager
    _fake: QueueFake
    _token: Token[QueueFake | None] | None
    _entered: bool


class PendingDispatch:
    """Build a single-use dispatch with explicit publication semantics.

    Fluent methods return new builders. Dispatch occurs only through an
    explicit ``dispatch_async`` or ``dispatch_sync`` call.
    """

    def __init__(
        self,
        manager: QueueManager,
        job: Job,
        *,
        connection: str,
        queue: str,
        delay_at: datetime | None = None,
    ) -> None:
        """Create one pending job without publishing it.

        Args:
            manager: Canonical application dispatcher.
            job: Registered job instance.
            connection: Selected connection name.
            queue: Selected logical queue name.
            delay_at: Optional UTC delivery time.
        """
        self._manager = manager
        self._job = job
        self._connection = connection
        self._queue = queue
        self._delay_at = delay_at
        self._used = False

    def on_connection(self, name: str) -> PendingDispatch:
        """Select a configured connection before publication.

        Args:
            name: Registered connection name.

        Returns:
            An independent pending builder.
        """
        self._ensure_pending()
        self._manager.connection_configuration(name)
        return self._copy(connection=name)

    def on_queue(self, name: str) -> PendingDispatch:
        """Select a logical queue name before publication.

        Args:
            name: Queue identifier accepted by the application.

        Returns:
            An independent pending builder.
        """
        self._ensure_pending()
        self._manager.validate_queue_name(name)
        return self._copy(queue=name)

    def delay(
        self,
        value: float | timedelta | datetime,
    ) -> PendingDispatch:
        """Set an explicit backend-supported delivery time.

        Args:
            value: Delay duration or an absolute timezone-aware time.

        Returns:
            An independent pending builder.

        Raises:
            QueueConfigurationError: If the duration or timestamp is invalid.
        """
        self._ensure_pending()
        delay_at = _normalize_delay(value)
        return self._copy(delay_at=delay_at)

    async def dispatch_async(self) -> DispatchReceipt:
        """Publish or execute the configured job once.

        Returns:
            The accepted dispatch metadata.

        Raises:
            QueueError: If this pending builder was already used.
        """
        self._ensure_pending()
        self._used = True
        return await self._manager.dispatch_effect_async(
            self._job,
            JobMessageMetadata(
                connection=self._connection,
                queue=self._queue,
                delay_at=self._delay_at,
            ),
        )

    def dispatch_sync(self) -> DispatchReceipt:
        """Execute the job only through a synchronous connection.

        Returns:
            Inline execution metadata.

        Raises:
            QueueError: If this builder was used or sync execution is unsafe.
        """
        self._ensure_pending()
        if self._delay_at is not None:
            msg = "A synchronous connection cannot schedule delayed jobs."
            raise QueueCapabilityError(msg)
        self._used = True
        return self._manager.dispatch_effect_sync(
            self._job,
            connection=self._connection,
            queue=self._queue,
        )

    def _copy(
        self,
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay_at: datetime | None = None,
    ) -> PendingDispatch:
        """Copy selected values without sharing publication state.

        Args:
            connection: Optional replacement connection.
            queue: Optional replacement queue.
            delay_at: Optional replacement delivery time.

        Returns:
            An independent pending builder.
        """
        return PendingDispatch(
            self._manager,
            self._job,
            connection=self._connection if connection is None else connection,
            queue=self._queue if queue is None else queue,
            delay_at=self._delay_at if delay_at is None else delay_at,
        )

    def _ensure_pending(self) -> None:
        """Reject mutation or publication after the builder was consumed.

        Raises:
            QueueError: If this builder has already dispatched.
        """
        if self._used:
            msg = "A pending job dispatch can be used only once."
            raise QueueDispatchError(msg)


class QueueManager(BusDispatcher):
    """Own one application's jobs, Taskiq brokers, and job scopes.

    Broker instances are created lazily after explicit dispatch or worker
    startup. They are finalized through the provider-owned application life.
    """

    def __init__(
        self,
        configuration: QueueConfiguration | None = None,
        *,
        container: ServiceContainer,
        drivers: Mapping[str, QueueBrokerFactory] | None = None,
        jobs: Sequence[type[Job]] = (),
        events: EventDispatcher | None = None,
        logger: LogWriter | None = None,
    ) -> None:
        """Create an application manager without opening broker connections.

        Args:
            configuration: Validated application Queue settings.
            container: Canonical Container used for handler injection.
            drivers: Trusted Taskiq broker factories keyed by driver name.
            jobs: Explicit trusted job classes available to workers.
            events: Application dispatcher for metadata-only lifecycle events.
            logger: Application logger used for observer diagnostics.
        """
        self._configuration = configuration or QueueConfiguration()
        self._container = container
        self._drivers = dict(drivers or {})
        self._events = events
        self._logger = logger
        self._codec = JobCodec(
            max_payload_bytes=self._configuration.max_payload_bytes,
            max_payload_depth=self._configuration.max_payload_depth,
        )
        self._job_middleware: dict[
            type[Job],
            tuple[JobMiddlewareType, ...],
        ] = {}
        self._brokers: dict[tuple[str, str], _TaskiqConnection] = {}
        self._batches: dict[str, BatchSnapshot] = {}
        self._lock = threading.RLock()
        self._job_context: ContextVar[JobContext | None] = ContextVar(
            f"titanspan_queue_job_context_{id(self)}",
            default=None,
        )
        self._fake: ContextVar[QueueFake | None] = ContextVar(
            f"titanspan_queue_fake_{id(self)}",
            default=None,
        )
        self._frozen = False
        self._closed = False
        self._validate_drivers()
        for job_type in jobs:
            self.register_job(job_type)

    @classmethod
    def from_repository(
        cls,
        repository: ConfigRepository,
        *,
        container: ServiceContainer,
        drivers: Mapping[str, QueueBrokerFactory] | None = None,
        jobs: Sequence[type[Job]] = (),
        events: EventDispatcher | None = None,
        logger: LogWriter | None = None,
    ) -> QueueManager:
        """Build an application manager from canonical Config settings.

        Args:
            repository: Application-owned configuration repository.
            container: Canonical Container used for job injection.
            drivers: Trusted custom Taskiq broker factories.
            jobs: Explicit trusted job classes.
            events: Application event dispatcher.
            logger: Application logger.

        Returns:
            A lazy manager that owns only selected backend instances.
        """
        return cls(
            QueueConfiguration.from_repository(repository),
            container=container,
            drivers=drivers,
            jobs=jobs,
            events=events,
            logger=logger,
        )

    @property
    def configuration(self) -> QueueConfiguration:
        """Return immutable Queue settings with redacted option display.
        """  # fmt: skip
        return self._configuration

    @property
    def job_names(self) -> tuple[str, ...]:
        """Return trusted registered job identifiers.
        """  # fmt: skip
        return self._codec.job_names

    @property
    def current_job_context(self) -> JobContext:
        """Return the active metadata for dependency injection.

        Raises:
            QueueError: If no job execution is active.
        """
        context = self._job_context.get()
        if context is None:
            raise QueueError(_JOB_CONTEXT_ERROR)
        return context

    def register_job(
        self,
        job_type: type[Job],
        *,
        name: str | None = None,
    ) -> str:
        """Register one trusted job class before application startup.

        Args:
            job_type: Dataclass or Pydantic subclass with a public handler.
            name: Optional stable identifier persisted in queue messages.

        Returns:
            The registered identifier.

        Raises:
            QueueConfigurationError: If registration is frozen or invalid.
        """
        if self._closed:
            raise QueueError(_QUEUE_CLOSED_ERROR)
        if self._frozen:
            msg = "Register Queue jobs before application startup."
            raise QueueConfigurationError(msg)
        try:
            validate_job_policy(job_type)
            registered_before = self._codec.is_registered(job_type)
            selected_name = self._codec.register(job_type, name)
            if not registered_before:
                self._job_middleware[job_type] = tuple(
                    job_type.middleware,
                )
        except (TypeError, ValueError, QueueSerializationError) as error:
            msg = "The trusted job declaration is invalid."
            raise QueueConfigurationError(msg) from error
        else:
            return selected_name

    def freeze(self) -> None:
        """Freeze job registration after provider startup.

        Future messages can resolve only classes in this stable registry.
        """
        self._frozen = True

    def connection_configuration(
        self,
        name: str,
    ) -> QueueConnectionConfiguration:
        """Return a configured connection declaration by name.

        Args:
            name: Connection selected by the caller or job class.

        Returns:
            Immutable backend settings.

        Raises:
            QueueConfigurationError: If no such connection exists.
        """
        try:
            return self._configuration.connection_configurations[name]
        except KeyError as error:
            msg = "The selected Queue connection is not configured."
            raise QueueConfigurationError(msg) from error

    def validate_queue_name(self, name: str) -> None:
        """Validate one logical queue name before broker access.

        Args:
            name: Application-controlled logical queue identifier.

        Raises:
            QueueConfigurationError: If the identifier is unsafe or empty.
        """
        if not is_valid_name(name):
            msg = "The selected queue name is invalid."
            raise QueueConfigurationError(msg)

    def dispatch(
        self,
        job: object,
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> PendingDispatch:
        """Build a pending dispatch without publishing a message.

        Args:
            job: Registered job instance containing serializable data.
            connection: Optional named connection.
            queue: Optional logical queue.
            delay: Optional backend-supported delay or timestamp.

        Returns:
            A single-use builder with explicit publication methods.
        """
        job_type = self._job_type(job)
        selected_connection = (
            connection
            or job_type.connection
            or self._configuration.default_connection
        )
        selected_queue = (
            queue or job_type.queue or self._configuration.default_queue
        )
        self.connection_configuration(selected_connection)
        self.validate_queue_name(selected_queue)
        pending = PendingDispatch(
            self,
            cast("Job", job),
            connection=selected_connection,
            queue=selected_queue,
        )
        return pending if delay is None else pending.delay(delay)

    def chain(self, jobs: Sequence[object]) -> ChainBuilder:
        """Create a Bus chain using this manager's trusted job catalog.

        Args:
            jobs: Registered jobs in the required execution order.

        Returns:
            A builder that publishes only after explicit dispatch.

        Raises:
            QueueConfigurationError: If the chain or a job is invalid.
        """
        job_values = self.validate_chain_members(jobs)
        return PendingChain(self, job_values)

    def validate_chain_members(
        self,
        jobs: Sequence[object],
    ) -> tuple[Job, ...]:
        """Validate registered jobs before adding them to a chain.

        Args:
            jobs: Candidate ordered chain members.

        Returns:
            Immutable registered job instances.

        Raises:
            QueueConfigurationError: If a job, destination, or limit is bad.
        """
        if not jobs or len(jobs) > _MAX_CHAIN_JOBS:
            msg = "A job chain must contain between 1 and 256 jobs."
            raise QueueConfigurationError(msg)
        job_values: list[Job] = []
        for job in jobs:
            job_type = self._job_type(job)
            connection = (
                job_type.connection or self._configuration.default_connection
            )
            queue = job_type.queue or self._configuration.default_queue
            self.connection_configuration(connection)
            self.validate_queue_name(queue)
            job_values.append(cast("Job", job))
        return tuple(job_values)

    def batch(self, jobs: Sequence[object]) -> BatchBuilder:
        """Create a bounded batch from jobs registered in this application.

        Args:
            jobs: Registered job instances to submit as one batch.

        Returns:
            A builder that requires explicit asynchronous dispatch.
        """
        job_values: list[Job] = []
        for job in jobs:
            self._job_type(job)
            job_values.append(cast("Job", job))
        return PendingBatch(self, job_values)

    def batch_status(self, batch_id: str) -> BatchSnapshot:
        """Return one process-local batch status snapshot.

        Args:
            batch_id: Identifier returned by a BatchHandle.

        Returns:
            Latest immutable status recorded by this application.

        Raises:
            QueueError: If this manager does not own the requested batch.
        """
        with self._lock:
            status = self._batches.get(batch_id)
        if status is None:
            msg = "The batch is not available in this application process."
            raise QueueError(msg)
        return status

    async def dispatch_batch_async(
        self,
        jobs: Sequence[Job],
        *,
        name: str,
        allow_failures: bool,
        connection: str | None,
        queue: str | None,
    ) -> BatchHandle:
        """Execute a local batch or record it inside a Queue fake.

        Distributed batch state requires a persistent repository. The native
        Database integration will provide that storage boundary.

        Args:
            jobs: Ordered registered job instances.
            name: Safe display label chosen by the caller.
            allow_failures: Whether remaining jobs run after a failure.
            connection: Optional configured Queue connection.
            queue: Optional logical queue name.

        Returns:
            A handle for status owned by this application process.

        Raises:
            QueueCapabilityError: If durable distributed state is required.
        """
        if not jobs:
            msg = "A batch must contain at least one job."
            raise QueueConfigurationError(msg)
        for job in jobs:
            self._job_type(job)
        selected_connection = (
            connection or self._configuration.default_connection
        )
        selected_queue = queue or self._configuration.default_queue
        configuration = self.connection_configuration(selected_connection)
        self.validate_queue_name(selected_queue)
        fake = self._fake.get()
        if configuration.driver not in {"sync", "null"} and fake is None:
            msg = (
                "Distributed batches require a persistent batch repository; "
                "use the native Database integration when available."
            )
            raise QueueCapabilityError(msg)
        batch_id = str(uuid4())
        status = BatchSnapshot(
            id=batch_id,
            name=name,
            total_jobs=len(jobs),
            pending_jobs=len(jobs),
            processed_jobs=0,
            failed_jobs=0,
            state="queued" if fake is not None else "running",
            allow_failures=allow_failures,
        )
        self._store_batch_status(status)
        if fake is not None:
            await self._record_batch_fake(
                jobs,
                batch_id=batch_id,
                connection=selected_connection,
                queue=selected_queue,
            )
            return BatchHandle(self, batch_id)
        if configuration.driver == "null":
            self._store_batch_status(
                replace_dataclass(
                    status,
                    pending_jobs=0,
                    state="discarded",
                )
            )
            return BatchHandle(self, batch_id)
        status = await self._execute_batch_inline(
            jobs,
            status,
            connection=selected_connection,
            queue=selected_queue,
        )
        return BatchHandle(self, status.id)

    async def _record_batch_fake(
        self,
        jobs: Sequence[Job],
        *,
        batch_id: str,
        connection: str,
        queue: str,
    ) -> None:
        """Record batch members without creating or contacting a broker.

        Args:
            jobs: Registered job instances retained by the active fake.
            batch_id: Identifier shared by all fake dispatch records.
            connection: Selected Queue connection.
            queue: Selected logical queue.
        """
        for job in jobs:
            await self.dispatch_effect_async(
                job,
                JobMessageMetadata(
                    connection=connection,
                    queue=queue,
                    batch_id=batch_id,
                ),
            )

    async def _execute_batch_inline(
        self,
        jobs: Sequence[Job],
        status: BatchSnapshot,
        *,
        connection: str,
        queue: str,
    ) -> BatchSnapshot:
        """Run a local batch sequentially and retain its terminal counts.

        Args:
            jobs: Registered jobs to run in order.
            status: Initial status snapshot.
            connection: Selected synchronous connection.
            queue: Selected logical queue.

        Returns:
            The final or interrupted status snapshot.
        """
        processed = 0
        failed = 0
        for job in jobs:
            try:
                await self.dispatch_effect_async(
                    job,
                    JobMessageMetadata(
                        connection=connection,
                        queue=queue,
                        batch_id=status.id,
                    ),
                )
            except BaseException as error:
                failed += 1
                cancelled = isinstance(
                    error,
                    anyio.get_cancelled_exc_class(),
                )
                state: BatchState = "cancelled" if cancelled else "failed"
                status = replace_dataclass(
                    status,
                    pending_jobs=len(jobs) - processed - failed,
                    processed_jobs=processed,
                    failed_jobs=failed,
                    state=state,
                )
                self._store_batch_status(status)
                if cancelled:
                    raise
                if not status.allow_failures:
                    return status
                continue
            processed += 1
            status = replace_dataclass(
                status,
                pending_jobs=len(jobs) - processed - failed,
                processed_jobs=processed,
                failed_jobs=failed,
                state="running",
            )
            self._store_batch_status(status)
        final_state: BatchState = (
            "completed_with_failures" if failed else "completed"
        )
        status = replace_dataclass(status, state=final_state)
        self._store_batch_status(status)
        return status

    def _store_batch_status(self, status: BatchSnapshot) -> None:
        """Publish one immutable batch snapshot to local readers.

        Args:
            status: Latest application-local status.
        """
        with self._lock:
            self._batches[status.id] = status

    async def dispatch_chain_async(
        self,
        jobs: Sequence[Job],
        *,
        connection: str | None,
        queue: str | None,
    ) -> DispatchReceipt:
        """Dispatch one chain with bounded, versioned continuation data.

        Args:
            jobs: Ordered registered jobs in the chain.
            connection: Selected chain connection.
            queue: Selected logical queue.

        Returns:
            Receipt for the first job.

        Raises:
            QueueConfigurationError: If a job or chain limit is invalid.
        """
        if not jobs or len(jobs) > _MAX_CHAIN_JOBS:
            msg = "A job chain must contain between 1 and 256 jobs."
            raise QueueConfigurationError(msg)
        first_type = type(jobs[0])
        selected_connection = (
            first_type.connection
            or connection
            or self._configuration.default_connection
        )
        selected_queue = (
            first_type.queue or queue or self._configuration.default_queue
        )
        self.connection_configuration(selected_connection)
        self.validate_queue_name(selected_queue)
        continuation_connection = (
            connection or self._configuration.default_connection
        )
        continuation_queue = queue or self._configuration.default_queue
        for job in jobs:
            job_type = self._job_type(job)
            self.connection_configuration(
                job_type.connection or continuation_connection
            )
            self.validate_queue_name(job_type.queue or continuation_queue)
        chain_id = str(uuid4())
        continuation = self._codec.encode_chain(
            jobs[1:],
            chain_id=chain_id,
            connection=continuation_connection,
            queue=continuation_queue,
            first_index=1,
        )
        job_id = str(uuid5(UUID(chain_id), "0"))
        return await self.dispatch_effect_async(
            jobs[0],
            JobMessageMetadata(
                connection=selected_connection,
                queue=selected_queue,
                chain_id=chain_id,
                job_id=job_id,
                continuation=continuation,
            ),
        )

    async def dispatch_async(
        self,
        job: object,
        *,
        connection: str | None = None,
        queue: str | None = None,
        delay: float | timedelta | datetime | None = None,
    ) -> DispatchReceipt:
        """Publish or inline one job through the explicit async boundary.

        Args:
            job: Registered job instance containing serializable data.
            connection: Optional named connection.
            queue: Optional logical queue.
            delay: Optional backend-supported delivery time.

        Returns:
            Publication or inline completion metadata.
        """
        pending = self.dispatch(
            job,
            connection=connection,
            queue=queue,
            delay=delay,
        )
        return await pending.dispatch_async()

    def dispatch_sync(
        self,
        job: object,
        *,
        connection: str | None = None,
        queue: str | None = None,
    ) -> DispatchReceipt:
        """Execute a job synchronously without creating an event loop.

        Args:
            job: Registered job instance containing serializable data.
            connection: Optional named connection.
            queue: Optional logical queue.

        Returns:
            Inline completion metadata.

        Raises:
            QueueCapabilityError: If sync execution is unsafe or unsupported.
        """
        pending = self.dispatch(
            job,
            connection=connection,
            queue=queue,
        )
        return pending.dispatch_sync()

    def fake(self) -> QueueFakeScope:
        """Select an execution-local fake for this canonical manager.

        Returns:
            A sync and async context manager that records dispatches.
        """
        return QueueFakeScope(self)

    async def work_async(
        self,
        *,
        connection: str | None = None,
        queue: str | None = None,
        concurrency: int | None = None,
        prefetch: int | None = None,
    ) -> None:
        """Run one bounded Taskiq worker until cancellation or failure.

        Args:
            connection: Selected Taskiq connection.
            queue: Logical queue consumed by this worker.
            concurrency: Maximum active asynchronous job handlers.
            prefetch: Additional backend messages allowed to wait.

        Raises:
            QueueCapabilityError: If the connection or execution backend is
                unsupported.
        """
        _ = self._require_asyncio_loop()
        self._require_application_context()
        selected_connection = (
            connection or self._configuration.default_connection
        )
        selected_queue = queue or self._configuration.default_queue
        self.validate_queue_name(selected_queue)
        state = self._taskiq_state(selected_connection, selected_queue)
        if state is None:
            msg = "The selected connection does not provide a worker."
            raise QueueCapabilityError(msg)
        if concurrency is not None and (
            type(concurrency) is not int or concurrency < 1
        ):
            msg = "Worker concurrency must be a positive integer."
            raise QueueConfigurationError(msg)
        selected_concurrency = (
            concurrency or self._configuration.worker_concurrency
        )
        selected_prefetch = (
            self._configuration.prefetch if prefetch is None else prefetch
        )
        if type(selected_prefetch) is not int or selected_prefetch < 0:
            msg = "Worker prefetch must be a non-negative integer."
            raise QueueConfigurationError(msg)
        await self._ensure_started(state)
        await self._emit_async(
            QueueEvent(
                job_id="worker",
                job_name="worker.startup",
                connection=selected_connection,
                queue=selected_queue,
                occurred_at=datetime.now(UTC),
            )
        )

        async def run_receiver() -> None:
            """Run the Taskiq receiver with configured concurrency bounds.

            Taskiq owns message consumption, acknowledgement, and worker
            scheduling. This adapter supplies its public receiver entrypoint.
            """
            await run_receiver_task(
                state.broker,
                sync_workers=1,
                max_async_tasks=selected_concurrency,
                max_prefetch=selected_prefetch,
                ack_time=None,
                run_startup=False,
            )

        async def run_scheduler() -> None:
            """Run Taskiq's scheduler for the configured durable source.

            The source is application-owned and closed by ``aclose``.
            """
            source = state.schedule_source
            if source is None:
                return
            # Taskiq's public runner starts each source before polling it.
            # Mark ownership first so application shutdown closes it even
            # when the runner is cancelled during its startup callback.
            state.source_started = True
            scheduler = TaskiqScheduler(state.broker, sources=[source])
            await run_scheduler_task(
                scheduler,
                run_startup=False,
                interval=timedelta(
                    seconds=self._configuration.schedule_poll_interval,
                ),
                loop_interval=timedelta(
                    seconds=self._configuration.schedule_loop_interval,
                ),
            )

        try:
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(run_receiver)
                if state.schedule_source is not None:
                    task_group.start_soon(run_scheduler)
        finally:
            await self._emit_async(
                QueueEvent(
                    job_id="worker",
                    job_name="worker.shutdown",
                    connection=selected_connection,
                    queue=selected_queue,
                    occurred_at=datetime.now(UTC),
                )
            )

    async def aclose(self) -> None:
        """Close every Taskiq broker and schedule source owned by this app.

        Cleanup continues after one backend raises. The first failure is
        re-raised after all owned resources have received shutdown.
        """
        if self._closed:
            return
        self._closed = True
        with self._lock:
            states = tuple(self._brokers.values())
        errors: list[BaseException] = []
        for state in states:
            try:
                await self._shutdown_state(state)
            except BaseException as error:
                errors.append(error)
        if errors:
            msg = "Queue resource cleanup failed."
            raise BaseExceptionGroup(
                msg,
                errors,
            )

    async def dispatch_effect_async(
        self,
        job: Job,
        metadata: JobMessageMetadata,
    ) -> DispatchReceipt:
        """Apply one finalized dispatch selection and perform its effect.

        Args:
            job: Registered serializable job instance.
            metadata: Final connection, queue, and continuation selection.

        Returns:
            Backend-independent dispatch metadata.
        """
        self._ensure_open()
        self._require_application_context()
        connection = metadata.connection
        queue = metadata.queue
        chain_id = metadata.chain_id
        batch_id = metadata.batch_id
        configuration = self.connection_configuration(connection)
        self.validate_queue_name(queue)
        encoded = self._codec.encode(job, metadata)
        decoded = self._codec.decode(encoded)
        job_id = str(decoded.envelope.job_id)
        fake = self._fake.get()
        if fake is not None:
            receipt = DispatchReceipt(
                job_id=job_id,
                connection=connection,
                queue=queue,
                state="queued",
                chain_id=chain_id,
                batch_id=batch_id,
                available_at=metadata.delay_at,
            )
            fake.record(job, decoded.envelope.job_type, receipt)
            return receipt

        if configuration.driver == "sync":
            application_context = self._require_application_context()
            if application_context.scope is not None:
                raise QueueCapabilityError(_SCOPED_SYNC_ERROR)

        await self._emit_async(
            JobDispatching(
                job_id=job_id,
                job_name=decoded.envelope.job_type,
                connection=connection,
                queue=queue,
                occurred_at=datetime.now(UTC),
                chain_id=chain_id,
                batch_id=batch_id,
            )
        )
        if configuration.driver == "null":
            return DispatchReceipt(
                job_id=job_id,
                connection=connection,
                queue=queue,
                state="discarded",
                chain_id=chain_id,
                batch_id=batch_id,
                available_at=metadata.delay_at,
            )
        if configuration.driver == "sync":
            return await self._dispatch_inline(decoded, metadata)
        return await self._dispatch_to_taskiq(
            job,
            encoded,
            decoded,
            metadata,
        )

    async def _dispatch_inline(
        self,
        decoded: DecodedJob,
        metadata: JobMessageMetadata,
    ) -> DispatchReceipt:
        """Execute a synchronous connection and its inline chain members.

        Args:
            decoded: Validated root job message.
            metadata: Final dispatch selection.

        Returns:
            Completion receipt for the root job.
        """
        if metadata.delay_at is not None:
            msg = "The sync connection cannot schedule delayed jobs."
            raise QueueCapabilityError(msg)
        connection = metadata.connection
        queue = metadata.queue
        chain_id = metadata.chain_id
        job_id = str(decoded.envelope.job_id)
        result = await self._execute_async(decoded, attempt=1)
        current = decoded
        while current.continuation:
            current = self._next_chain_job(current)
            await self._emit_async(
                JobDispatching(
                    job_id=str(current.envelope.job_id),
                    job_name=current.envelope.job_type,
                    connection=current.envelope.connection,
                    queue=current.envelope.queue,
                    occurred_at=datetime.now(UTC),
                    chain_id=chain_id,
                )
            )
            await self._execute_async(current, attempt=1)
        receipt = DispatchReceipt(
            job_id=job_id,
            connection=connection,
            queue=queue,
            state="executed",
            chain_id=chain_id,
            batch_id=metadata.batch_id,
            result=result,
        )
        await self._emit_dispatched_async(decoded, receipt)
        return receipt

    async def _dispatch_to_taskiq(
        self,
        job: Job,
        encoded: bytes,
        decoded: DecodedJob,
        metadata: JobMessageMetadata,
    ) -> DispatchReceipt:
        """Publish one encoded envelope through an owned Taskiq broker.

        Args:
            job: Registered job that configures retry behavior.
            encoded: Bounded JSON bytes produced by the trusted job codec.
            decoded: Validated message metadata for lifecycle events.
            metadata: Final connection, queue, and delay selection.

        Returns:
            Broker publication receipt.
        """
        connection = metadata.connection
        queue = metadata.queue
        chain_id = metadata.chain_id
        state = self._taskiq_state(connection, queue)
        if state is None:
            msg = "The selected queue connection has no Taskiq broker."
            raise QueueCapabilityError(msg)
        await self._ensure_started(state)
        if metadata.delay_at is not None and state.schedule_source is None:
            raise QueueCapabilityError(_NO_DELAY_SOURCE_ERROR)
        labels = self._retry_labels(job)
        labels["queue_name"] = state.physical_queue
        job_id = str(decoded.envelope.job_id)
        kicker = state.task.kicker().with_labels(**labels).with_task_id(job_id)
        payload_text = encoded.decode("utf-8")
        if metadata.delay_at is None:
            await self._publish_taskiq_message(
                state,
                job_id=job_id,
                payload=payload_text,
                labels=labels,
            )
        else:
            source = state.schedule_source
            if source is None:
                raise QueueCapabilityError(_NO_DELAY_SOURCE_ERROR)
            await kicker.schedule_by_time(
                source,
                metadata.delay_at,
                payload_text,
            )
        receipt = DispatchReceipt(
            job_id=job_id,
            connection=connection,
            queue=queue,
            state="queued",
            chain_id=chain_id,
            batch_id=metadata.batch_id,
            available_at=metadata.delay_at,
        )
        await self._emit_dispatched_async(decoded, receipt)
        return receipt

    async def _publish_taskiq_message(
        self,
        state: _TaskiqConnection,
        *,
        job_id: str,
        payload: str,
        labels: Mapping[str, str | int],
    ) -> None:
        """Publish without Taskiq's argument-value debug log.

        Taskiq's public kicker logs every argument at debug level. Queue
        payloads can contain private application data, so this adapter uses
        Taskiq's public message formatter and broker methods directly.
        Middleware hooks still run in the same order as ``AsyncKicker.kiq``.

        Args:
            state: Application-owned broker and registered task.
            job_id: Stable id assigned by the Queue envelope.
            payload: Safe JSON envelope text.
            labels: Validated retry and queue labels.

        Raises:
            QueueDispatchError: If the broker does not confirm publication.
        """
        message = TaskiqMessage(
            task_id=job_id,
            task_name=state.task.task_name,
            labels=dict(labels),
            args=[payload],
            kwargs={},
        )
        try:
            await _send_taskiq_message(
                state.broker,
                message,
                self._log_post_send_error,
            )
        except Exception as error:
            self._log_publication_error(job_id, error)
            msg = (
                "The broker did not confirm publication. The job may have "
                "been accepted; inspect its id before retrying."
            )
            raise QueueDispatchError(msg) from None

    def _log_post_send_error(self, error: Exception) -> None:
        """Log middleware failure after the broker accepted a message.

        Args:
            error: Observer error used only for its class name.
        """
        if self._logger is not None:
            self._logger.error(
                "A Taskiq post-send observer failed after publication.",
                exception_type=type(error).__name__,
            )

    def _log_publication_error(
        self,
        job_id: str,
        error: Exception,
    ) -> None:
        """Record safe publication diagnostics without message contents.

        Args:
            job_id: Non-secret identifier assigned before broker access.
            error: Backend error used only for its class name.
        """
        if self._logger is not None:
            self._logger.error(
                "A Queue broker did not confirm publication.",
                job_id=job_id,
                exception_type=type(error).__name__,
            )

    def dispatch_effect_sync(
        self,
        job: Job,
        *,
        connection: str,
        queue: str,
    ) -> DispatchReceipt:
        """Run one registered job with sync-safe dependencies and scope.

        Args:
            job: Registered data instance.
            connection: Selected connection name.
            queue: Selected logical queue.

        Returns:
            Inline execution receipt.

        Raises:
            QueueCapabilityError: If the active execution context is async,
                already scoped, or selects an asynchronous broker.
        """
        self._ensure_open()
        application_context = self._require_application_context()
        if application_context.scope is not None:
            raise QueueCapabilityError(_SCOPED_SYNC_ERROR)
        try:
            anyio.get_current_task()
        except anyio.NoEventLoopError:
            pass
        else:
            raise QueueCapabilityError(_SYNC_IN_ASYNC_ERROR)
        configuration = self.connection_configuration(connection)
        if configuration.driver != "sync":
            msg = "Synchronous dispatch requires the sync connection."
            raise QueueCapabilityError(msg)
        decoded = self._codec.decode(
            self._codec.encode(
                job,
                JobMessageMetadata(
                    connection=connection,
                    queue=queue,
                ),
            )
        )
        fake = self._fake.get()
        if fake is not None:
            receipt = DispatchReceipt(
                job_id=str(decoded.envelope.job_id),
                connection=connection,
                queue=queue,
                state="queued",
            )
            fake.record(job, decoded.envelope.job_type, receipt)
            return receipt
        handler = getattr(decoded.job, "handle", None)
        if not callable(handler):
            raise QueueConfigurationError(_INVALID_JOB_ERROR)
        if inspect.iscoroutinefunction(handler):
            raise QueueCapabilityError(_ASYNC_HANDLER_ERROR)
        if type(decoded.job).timeout is not None:
            raise QueueCapabilityError(_SYNC_TIMEOUT_ERROR)

        application = cast("Application", application_context.application)
        context = self._make_job_context(decoded, connection, queue, 1)
        with application.container.scope(Scope.JOB) as scope:
            token = self._job_context.set(context)
            try:
                with bind_application_context(
                    application, self._container, scope
                ):
                    result = self._execute_sync_pipeline(
                        handler,
                        decoded,
                        context,
                    )
            finally:
                self._job_context.reset(token)
        receipt = DispatchReceipt(
            job_id=str(decoded.envelope.job_id),
            connection=connection,
            queue=queue,
            state="executed",
            result=result,
        )
        self._emit_sync(
            JobDispatched(
                job_id=receipt.job_id,
                job_name=decoded.envelope.job_type,
                connection=connection,
                queue=queue,
                occurred_at=datetime.now(UTC),
            )
        )
        return receipt

    def _next_chain_job(self, current: DecodedJob) -> DecodedJob:
        """Build the next validated message from trusted continuation data.

        Args:
            current: Completed chain member with remaining continuation data.

        Returns:
            The next registered job and its remaining continuation.
        """
        selected = current.continuation[0]
        remaining = current.continuation[1:]
        envelope = current.envelope.model_copy(
            update={
                "job_id": selected.payload.job_id,
                "job_type": selected.payload.job_type,
                "payload_version": selected.payload.payload_version,
                "connection": (
                    selected.payload.connection or current.envelope.connection
                ),
                "queue": selected.payload.queue or current.envelope.queue,
                "payload": selected.payload.payload,
                "continuation": tuple(item.payload for item in remaining),
                "dispatched_at": datetime.now(UTC),
            }
        )
        return DecodedJob(
            envelope=envelope,
            job=selected.job,
            continuation=remaining,
        )

    async def _execute_async(
        self,
        decoded: DecodedJob,
        *,
        attempt: int,
    ) -> object:
        """Run one handler in a fresh native job scope.

        Args:
            decoded: Validated message and registered job instance.
            attempt: Current one-based Taskiq attempt number.

        Returns:
            Handler result for inline execution only.
        """
        self._ensure_open()
        application_context = self._require_application_context()

        application = cast("Application", application_context.application)
        job_context = self._make_job_context(
            decoded,
            decoded.envelope.connection,
            decoded.envelope.queue,
            attempt,
        )
        handler = getattr(decoded.job, "handle", None)
        if not callable(handler):
            raise QueueConfigurationError(_INVALID_JOB_ERROR)

        async with application.execution_scope(Scope.JOB):
            token = self._job_context.set(job_context)
            event = JobProcessing(
                job_id=job_context.job_id,
                job_name=job_context.job_name,
                connection=job_context.connection,
                queue=job_context.queue,
                occurred_at=datetime.now(UTC),
                chain_id=job_context.chain_id,
                batch_id=job_context.batch_id,
                attempt=job_context.attempt,
            )
            await self._emit_async(event)
            if not inspect.iscoroutinefunction(handler) and (
                type(decoded.job).timeout is not None
            ):
                raise QueueCapabilityError(_SYNC_TIMEOUT_ERROR)
            try:
                result = await self._execute_handler_pipeline(
                    handler,
                    decoded,
                    job_context,
                )
            except BaseException as error:
                if not isinstance(error, anyio.get_cancelled_exc_class()):
                    await self._emit_async(
                        JobFailed(
                            job_id=job_context.job_id,
                            job_name=job_context.job_name,
                            connection=job_context.connection,
                            queue=job_context.queue,
                            occurred_at=datetime.now(UTC),
                            chain_id=job_context.chain_id,
                            batch_id=job_context.batch_id,
                            attempt=job_context.attempt,
                            exception_type=type(error).__name__,
                        )
                    )
                raise
            else:
                await self._emit_async(
                    JobProcessed(
                        job_id=job_context.job_id,
                        job_name=job_context.job_name,
                        connection=job_context.connection,
                        queue=job_context.queue,
                        occurred_at=datetime.now(UTC),
                        chain_id=job_context.chain_id,
                        batch_id=job_context.batch_id,
                    )
                )
                return result
            finally:
                self._job_context.reset(token)

    async def _execute_handler_pipeline(
        self,
        handler: Callable[..., object],
        decoded: DecodedJob,
        job_context: JobContext,
    ) -> object:
        """Run trusted middleware and the handler inside the active JOB scope.

        Args:
            handler: Registered job handler selected from the decoded class.
            decoded: Validated job envelope and typed payload.
            job_context: Metadata for the active attempt.

        Returns:
            The handler result or a middleware short-circuit value.
        """

        async def invoke_handler(_: JobContext) -> object:
            """Invoke the job through the native Container.
            """  # fmt: skip
            if inspect.iscoroutinefunction(handler):
                timeout = type(decoded.job).timeout
                if timeout is None:
                    return await self._container.call_async(handler)
                with anyio.fail_after(float(timeout)):
                    return await self._container.call_async(handler)

            result = await anyio.to_thread.run_sync(
                self._container.call,
                handler,
            )
            if inspect.isawaitable(result):
                _raise_async_handler_error()
            return result

        stages: list[object] = []
        for middleware_type in self._middleware_for(decoded.job):

            async def run_middleware(
                context: JobContext,
                next_stage: Callable[
                    [JobContext],
                    Awaitable[object],
                ],
                *,
                selected_type: JobMiddlewareType = middleware_type,
            ) -> object:
                """Resolve one middleware in the active JOB scope.

                Args:
                    context: Immutable metadata for this job attempt.
                    next_stage: Pipeline continuation for the next stage.
                    selected_type: Trusted middleware class from the job type.

                Returns:
                    The middleware result or a short-circuit value.
                """
                instance = await self._container.make_async(selected_type)
                callback = getattr(instance, "handle", None)
                if not callable(callback):
                    msg = "Job middleware must define a callable handle method."
                    raise QueueConfigurationError(msg)
                if not inspect.iscoroutinefunction(callback):
                    raise QueueCapabilityError(_ASYNC_MIDDLEWARE_ERROR)
                return await self._container.call_async(
                    callback,
                    {
                        "context": context,
                        "next_handler": lambda: next_stage(context),
                    },
                )

            stages.append(Pipeline.middleware_async(run_middleware))
        stages.append(invoke_handler)
        pipeline = (
            Pipeline[JobContext, object](container=self._container)
            .send(job_context)
            .through(stages)
        )
        return await pipeline.then_return_async()

    def _execute_sync_pipeline(
        self,
        handler: Callable[..., object],
        decoded: DecodedJob,
        job_context: JobContext,
    ) -> object:
        """Run synchronous middleware and a handler in the current JOB scope.

        Args:
            handler: Registered synchronous job handler.
            decoded: Validated job payload and metadata.
            job_context: Metadata for the active attempt.

        Returns:
            The handler result or a middleware short-circuit value.

        Raises:
            QueueCapabilityError: If middleware requires async execution.
        """

        def invoke_handler(_: JobContext) -> object:
            """Resolve handler dependencies through the canonical Container.
            """  # fmt: skip
            result = self._container.call(handler)
            if inspect.isawaitable(result):
                _raise_async_handler_error()
            return result

        stages: list[object] = []
        for middleware_type in self._middleware_for(decoded.job):

            def run_middleware(
                context: JobContext,
                next_stage: Callable[[JobContext], object],
                *,
                selected_type: JobMiddlewareType = middleware_type,
            ) -> object:
                """Resolve and execute one synchronous middleware stage.
                """  # fmt: skip
                instance = self._container.make(selected_type)
                callback = getattr(instance, "handle", None)
                if not callable(callback):
                    msg = "Job middleware must define a callable handle method."
                    raise QueueConfigurationError(msg)
                if inspect.iscoroutinefunction(callback):
                    raise QueueCapabilityError(_SYNC_MIDDLEWARE_ERROR)
                result = self._container.call(
                    callback,
                    {
                        "context": context,
                        "next_handler": lambda: next_stage(context),
                    },
                )
                if inspect.isawaitable(result):
                    _raise_async_handler_error()
                return result

            stages.append(Pipeline.middleware(run_middleware))
        stages.append(invoke_handler)
        pipeline = (
            Pipeline[JobContext, object](container=self._container)
            .send(job_context)
            .through(stages)
        )
        return pipeline.then_return()

    async def execute_message(
        self,
        encoded: str,
        task_context: TaskiqContext,
    ) -> None:
        """Validate and execute one broker message without trusting labels.

        Args:
            encoded: Bounded JSON message passed by Taskiq.
            task_context: Taskiq metadata for retry accounting.

        Raises:
            QueueSerializationError: If the message is invalid.
            Exception: If the job fails and Taskiq should apply retry policy.
        """
        decoded = self._codec.decode(encoded)
        retries = task_context.message.labels.get("_retries", 0)
        if isinstance(retries, str) and retries.isdecimal():
            attempt = int(retries) + 1
        elif type(retries) is int and retries >= 0:
            attempt = retries + 1
        else:
            msg = "The job attempt metadata is invalid."
            raise QueueSerializationError(msg)
        await self._execute_async(decoded, attempt=attempt)
        if decoded.continuation:
            next_job = self._next_chain_job(decoded)
            await self.dispatch_effect_async(
                next_job.job,
                JobMessageMetadata(
                    connection=next_job.envelope.connection,
                    queue=next_job.envelope.queue,
                    delay_at=None,
                    chain_id=next_job.envelope.chain_id,
                    job_id=str(next_job.envelope.job_id),
                    continuation=tuple(
                        item.payload for item in next_job.continuation
                    ),
                ),
            )

    def _taskiq_state(
        self,
        connection_name: str,
        queue: str,
    ) -> _TaskiqConnection | None:
        """Create or return one broker state for a connection and queue.

        Args:
            connection_name: Configured Queue connection.
            queue: Logical queue selected by a worker or dispatch.

        Returns:
            One Taskiq connection state, or None for sync and null drivers.
        """
        configuration = self.connection_configuration(connection_name)
        if configuration.driver in {"sync", "null"}:
            return None
        key = (connection_name, queue)
        with self._lock:
            existing = self._brokers.get(key)
            if existing is not None:
                return existing
            if configuration.driver in {"redis_stream", "rabbitmq"}:
                broker, source = create_taskiq_transport(
                    configuration,
                    namespace=self._configuration.namespace,
                    connection_name=connection_name,
                    queue=queue,
                )
            else:
                factory = self._drivers.get(configuration.driver)
                if factory is None:
                    msg = "The selected Queue driver is not registered."
                    raise QueueConfigurationError(msg)
                physical = (
                    f"{self._configuration.namespace}:{connection_name}:{queue}"
                )
                broker = factory(configuration, connection_name, physical)
                source = None
                broker.with_serializer(JSONSerializer(ensure_ascii=False))
            if source is not None:
                retry_middleware = _QueueRetryMiddleware(
                    source,
                    logger=self._logger,
                )
            else:
                retry_middleware = _QueueRetryMiddleware(
                    None,
                    logger=self._logger,
                )
            broker.with_middlewares(retry_middleware)
            task = _register_task(broker, self, connection_name, queue)
            physical_queue = (
                f"{self._configuration.namespace}:{connection_name}:{queue}"
            )
            state = _TaskiqConnection(
                broker=broker,
                task=cast("_RegisteredTask", task),
                physical_queue=physical_queue,
                schedule_source=source,
            )
            self._brokers[key] = state
            return state

    async def _ensure_started(self, state: _TaskiqConnection) -> None:
        """Start a broker and source once on their owning asyncio loop.

        Args:
            state: Lazy connection state selected for one queue.

        Raises:
            QueueCapabilityError: If another event loop owns the connection.
        """
        loop = self._require_asyncio_loop()
        async with state.start_lock:
            if state.closed:
                raise QueueError(_QUEUE_CLOSED_ERROR)
            if state.started:
                if state.loop is not loop:
                    msg = "A Taskiq connection belongs to another event loop."
                    raise QueueCapabilityError(msg)
                return
            state.loop = loop
            try:
                await state.broker.startup()
                state.started = True
            except BaseException as startup_error:
                try:
                    await state.broker.shutdown()
                except BaseException as cleanup_error:
                    startup_error.add_note(
                        "Queue startup cleanup also failed with "
                        f"{type(cleanup_error).__name__}."
                    )
                state.started = False
                state.source_started = False
                state.loop = None
                raise

    async def _shutdown_state(self, state: _TaskiqConnection) -> None:
        """Finalize one broker and schedule source exactly once.

        Args:
            state: Connection state owned by this manager.

        Raises:
            BaseException: The first backend cleanup failure after both
                resources receive their shutdown call.
        """
        async with state.start_lock:
            if state.closed:
                return
            state.closed = True
            failures: list[BaseException] = []
            if state.source_started and state.schedule_source is not None:
                try:
                    await state.schedule_source.shutdown()
                except BaseException as error:
                    failures.append(error)
            if state.started:
                try:
                    await state.broker.shutdown()
                except BaseException as error:
                    failures.append(error)
            if failures:
                raise failures[0]

    async def _emit_async(self, event: object) -> None:
        """Dispatch metadata without letting observer errors alter job state.

        Args:
            event: Native Queue lifecycle event with no payload data.

        Raises:
            BaseException: Cancellation from an event listener propagates.
        """
        if self._events is None:
            return
        try:
            await self._events.dispatch_async(event)
        except BaseException as error:
            if isinstance(error, anyio.get_cancelled_exc_class()):
                raise
            self._log_observer_error(event, error)

    def _emit_sync(self, event: object) -> None:
        """Dispatch metadata while preserving sync operation outcomes.

        Args:
            event: Native Queue lifecycle event with no payload data.
        """
        if self._events is None:
            return
        try:
            self._events.dispatch(event)
        except Exception as error:
            self._log_observer_error(event, error)

    def _log_observer_error(self, event: object, error: BaseException) -> None:
        """Log safe exception classification without user-controlled text.

        Args:
            event: Queue event class that failed during observation.
            error: Listener error used only to identify its Python type.
        """
        if self._logger is not None:
            self._logger.error(
                "A Queue event listener failed.",
                event_type=type(event).__name__,
                exception_type=type(error).__name__,
            )

    async def _emit_dispatched_async(
        self,
        decoded: DecodedJob,
        receipt: DispatchReceipt,
    ) -> None:
        """Emit safe metadata after the dispatch side effect completes.

        Args:
            decoded: Validated message metadata.
            receipt: Successful inline or broker dispatch receipt.
        """
        await self._emit_async(
            JobDispatched(
                job_id=receipt.job_id,
                job_name=decoded.envelope.job_type,
                connection=receipt.connection,
                queue=receipt.queue,
                occurred_at=datetime.now(UTC),
                chain_id=receipt.chain_id,
                batch_id=decoded.envelope.batch_id,
            )
        )

    def _make_job_context(
        self,
        decoded: DecodedJob,
        connection: str,
        queue: str,
        attempt: int,
    ) -> JobContext:
        """Create metadata owned by one handler execution.

        Args:
            decoded: Validated message and payload.
            connection: Selected Queue connection.
            queue: Selected logical queue.
            attempt: Current one-based handler attempt.

        Returns:
            Immutable execution metadata.
        """
        return JobContext(
            job_id=str(decoded.envelope.job_id),
            job_name=decoded.envelope.job_type,
            connection=connection,
            queue=queue,
            attempt=attempt,
            max_attempts=self._effective_tries(type(decoded.job)),
            dispatched_at=decoded.envelope.dispatched_at,
            chain_id=decoded.envelope.chain_id,
            batch_id=decoded.envelope.batch_id,
        )

    def _effective_tries(self, job_type: type[Job]) -> int:
        """Select the job override or application retry default.

        Args:
            job_type: Registered job declaration.

        Returns:
            Total allowed handler attempts.
        """
        tries = job_type.tries
        return self._configuration.default_tries if tries is None else tries

    def _middleware_for(
        self,
        job: Job,
    ) -> tuple[JobMiddlewareType, ...]:
        """Return the immutable middleware snapshot captured at registration.

        Args:
            job: Decoded instance of a registered job class.

        Returns:
            Middleware declarations trusted during application bootstrap.

        Raises:
            QueueConfigurationError: If the class is outside the catalog.
        """
        try:
            return self._job_middleware[type(job)]
        except KeyError as error:
            msg = "The job middleware declaration is not registered."
            raise QueueConfigurationError(msg) from error

    def _retry_labels(self, job: Job) -> dict[str, str | int]:
        """Build Taskiq labels from validated native job retry declarations.

        Args:
            job: Registered job whose policy is included in the message.

        Returns:
            Scalar Taskiq labels with the backoff sequence encoded as JSON.
        """
        job_type = type(job)
        validate_job_policy(job_type)
        backoff = job_type.backoff
        if isinstance(backoff, tuple):
            values = backoff
        elif not isinstance(backoff, bool):
            values = (float(backoff),)
        else:
            raise QueueConfigurationError(_INVALID_BACKOFF_ERROR)
        if any(
            type(value) not in (int, float) or value < 0 for value in values
        ):
            raise QueueConfigurationError(_INVALID_BACKOFF_ERROR)
        selected = tuple(float(value) for value in values) or (0.0,)
        tries = self._effective_tries(job_type)
        return {
            "retry_on_error": "true" if tries > 1 else "false",
            "max_retries": tries,
            "titanspan_backoff": json.dumps(selected),
        }

    def _job_type(self, job: object) -> type[Job]:
        """Require a registered job instance before creating a builder.

        Args:
            job: Caller-supplied job value.

        Returns:
            The registered job class.

        Raises:
            QueueConfigurationError: If the value is not a registered job.
        """
        if not isinstance(job, Job):
            msg = "Queue dispatch requires a Job."
            raise QueueConfigurationError(msg)
        if not self._codec.is_registered(type(job)):
            msg = "The job class is not registered."
            raise QueueConfigurationError(msg)
        return type(job)

    def _require_application_context(self) -> ActiveApplicationContext:
        """Require this manager's active application and canonical Container.

        Returns:
            The verified active application context.

        Raises:
            QueueError: If no matching app context is active.
        """
        active = active_application_context()
        if active is None or active.container is not self._container:
            raise QueueError(_APPLICATION_CONTEXT_ERROR)
        return active

    def _require_asyncio_loop(self) -> asyncio.AbstractEventLoop:
        """Require Taskiq operations to run on an asyncio event loop.

        Returns:
            The current asyncio loop.

        Raises:
            QueueCapabilityError: If no asyncio loop is active.
        """
        try:
            return asyncio.get_running_loop()
        except RuntimeError as error:
            raise QueueCapabilityError(_EXECUTION_MODE_ERROR) from error

    def _ensure_open(self) -> None:
        """Reject new operations after application-owned shutdown begins.

        Raises:
            QueueError: If the manager has closed.
        """
        if self._closed:
            raise QueueError(_QUEUE_CLOSED_ERROR)

    def _validate_drivers(self) -> None:
        """Reject duplicate or conflicting trusted driver registrations.

        Raises:
            QueueConfigurationError: If a custom factory is invalid.
        """
        builtin = {"sync", "null", "redis_stream", "rabbitmq"}
        for name, factory in self._drivers.items():
            if (
                not name.isidentifier()
                or name in builtin
                or not callable(factory)
            ):
                msg = "A Queue driver registration is invalid."
                raise QueueConfigurationError(msg)

    def activate_fake(self, fake: QueueFake) -> Token[QueueFake | None]:
        """Activate one fake in this manager's execution context.

        Args:
            fake: New fake selected by a context manager.

        Returns:
            ContextVar token required for restoration.
        """
        return self._fake.set(fake)

    def restore_fake(self, token: Token[QueueFake | None]) -> None:
        """Restore the preceding fake after an execution-local replacement.

        Args:
            token: Token returned by this manager's fake selection.
        """
        self._fake.reset(token)

    _configuration: QueueConfiguration
    _container: ServiceContainer
    _drivers: dict[str, QueueBrokerFactory]
    _events: EventDispatcher | None
    _logger: LogWriter | None
    _codec: JobCodec
    _job_middleware: dict[type[Job], tuple[JobMiddlewareType, ...]]
    _brokers: dict[tuple[str, str], _TaskiqConnection]
    _lock: threading.RLock
    _job_context: ContextVar[JobContext | None]
    _fake: ContextVar[QueueFake | None]
    _frozen: bool
    _closed: bool


class _QueueRetryMiddleware(SmartRetryMiddleware):
    """Delegate retries to Taskiq using per-message native backoff values.

    The middleware changes only delay selection. Taskiq owns rescheduling,
    attempt labels, error delivery, and acknowledgement behavior.
    """

    def __init__(
        self,
        source: ScheduleSource | None,
        *,
        logger: LogWriter | None,
    ) -> None:
        """Configure retries with an optional durable schedule source.

        Args:
            source: Taskiq source used for delayed retry publication.
            logger: Application logger for safe middleware diagnostics.
        """
        super().__init__(
            default_retry_count=1,
            default_retry_label=False,
            schedule_source=source,
            types_of_exceptions=(Exception,),
        )
        self._logger = logger

    def make_delay(self, message: TaskiqMessage, retries: int) -> float:
        """Select a job-declared delay for the current retry count.

        Args:
            message: Original Taskiq message with JSON string labels.
            retries: One-based retry sequence number.

        Returns:
            Non-negative delay from the registered job declaration.
        """
        encoded = message.labels.get("titanspan_backoff", "[0]")
        try:
            values: object = (
                json.loads(encoded) if isinstance(encoded, str) else [0]
            )
        except (TypeError, ValueError):
            return 0.0
        if not isinstance(values, list) or not values:
            return 0.0
        values = cast("list[object]", values)
        index = min(max(retries - 1, 0), len(values) - 1)
        value = values[index]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0.0
        if value < 0:
            return 0.0
        return float(value)

    async def on_send(
        self,
        kicker: AsyncKicker[Any, Any],
        message: TaskiqMessage,
        delay: float,
    ) -> None:
        """Reschedule retries without logging serialized job arguments.

        Taskiq's default immediate retry path uses its debug-logging kicker.
        Queue keeps the retry engine but publishes through Taskiq's formatter
        and broker boundary to avoid logging the JSON payload.

        Args:
            kicker: Taskiq's retry publication configuration.
            message: Original safe task message.
            delay: Backoff selected by ``make_delay``.

        Raises:
            QueueCapabilityError: If a nonzero retry delay has no scheduler.
        """
        source = self.schedule_source
        if source is not None:
            when = datetime.now(UTC) + timedelta(seconds=delay)
            await kicker.schedule_by_time(
                source,
                when,
                *message.args,
                **message.kwargs,
            )
            return
        if delay > 0:
            msg = (
                "This Queue backend cannot apply delayed retry backoff. "
                "Configure a scheduling source or use zero backoff."
            )
            raise QueueCapabilityError(msg)
        labels = {
            name: value
            for name, value in kicker.labels.items()
            if name != "types_of_exceptions"
        }
        retry_message = TaskiqMessage(
            task_id=message.task_id,
            task_name=message.task_name,
            labels=labels,
            args=message.args,
            kwargs=message.kwargs,
        )
        await _send_taskiq_message(
            self.broker,
            retry_message,
            self._log_post_send_error,
        )

    def _log_post_send_error(self, error: Exception) -> None:
        """Record a safe error after Taskiq accepted a retry message.

        Args:
            error: Observer error used only for its class name.
        """
        if self._logger is not None:
            self._logger.error(
                "A Taskiq post-send observer failed after retry publication.",
                exception_type=type(error).__name__,
            )


async def _send_taskiq_message(
    broker: AsyncBroker,
    message: TaskiqMessage,
    on_post_error: Callable[[Exception], None],
) -> None:
    """Run Taskiq publication hooks without logging message arguments.

    Args:
        broker: Taskiq transport that owns message formatting and delivery.
        message: Safe Taskiq message containing the bounded JSON envelope.
        on_post_error: Safe logger used after confirmed broker publication.
    """
    for middleware in broker.middlewares:
        if middleware.__class__.pre_send is TaskiqMiddleware.pre_send:
            continue
        result = middleware.pre_send(message)
        if inspect.isawaitable(result):
            message = await result
        else:
            message = result
    await broker.kick(broker.formatter.dumps(message))
    for middleware in reversed(broker.middlewares):
        if middleware.__class__.post_send is TaskiqMiddleware.post_send:
            continue
        try:
            result = middleware.post_send(message)
            if inspect.isawaitable(result):
                await result
        except Exception as error:
            # Publication already succeeded. Observer failure must not cause
            # callers or Taskiq to publish this message again.
            on_post_error(error)


def _register_task(
    broker: AsyncBroker,
    manager: QueueManager,
    connection: str,
    queue: str,
) -> object:
    """Register one generic trusted-message handler on a local broker.

    Args:
        broker: Taskiq broker owned by the application manager.
        manager: Native dispatcher used to resolve registered job types.
        connection: Configured connection associated with the handler.
        queue: Logical queue associated with the handler.

    Returns:
        The Taskiq task registration used for publication.
    """

    async def execute(
        message: str,
        context: TaskiqContext = _TASKIQ_CONTEXT_DEPENDENCY,
    ) -> None:
        """Run one JSON envelope through the canonical app and Container.

        Args:
            message: Bounded job envelope received from Taskiq.
            context: Taskiq retry metadata supplied by its worker.
        """
        _ = connection, queue
        await manager.execute_message(message, context)

    return broker.register_task(execute, task_name=_TASK_NAME)


def _normalize_delay(
    value: float | timedelta | datetime,
) -> datetime:
    """Convert a public delay value to a UTC absolute timestamp.

    Args:
        value: Relative duration or timezone-aware timestamp.

    Returns:
        The delivery time in UTC.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "Delayed dispatch requires a timezone-aware timestamp."
            raise QueueConfigurationError(msg)
        return value.astimezone(UTC)
    seconds = value.total_seconds() if isinstance(value, timedelta) else value
    if type(seconds) not in (int, float) or seconds < 0:
        msg = "A queue delay must be a non-negative duration."
        raise QueueConfigurationError(msg)
    return datetime.now(UTC) + timedelta(seconds=seconds)


def _raise_async_handler_error() -> NoReturn:
    """Reject a synchronous handler that returned an awaitable.
    """  # fmt: skip
    raise QueueCapabilityError(_ASYNC_HANDLER_ERROR)


__all__ = [
    "PendingDispatch",
    "QueueBrokerFactory",
    "QueueDispatchRecord",
    "QueueFake",
    "QueueFakeScope",
    "QueueManager",
]
