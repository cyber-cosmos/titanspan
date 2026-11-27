"""Measure native Queue inline dispatch through real application services.

The results are informational. Each sample dispatches a fixed batch through
the sync connection and includes application startup and shutdown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import anyio
import pytest

from titanspan import Application
from titanspan.queue import Job, QueueManager, QueueServiceProvider

if TYPE_CHECKING:
    from collections.abc import Callable

_BATCH_SIZE = 32
_BENCHMARK_ROUNDS = 5
_WARMUP_ROUNDS = 1
_NOT_EXECUTED_ERROR = "The inline Queue job did not execute."


class _BenchmarkFixture(Protocol):
    """Describe the typed pytest-benchmark surface used in this file.

    The installed plugin does not publish complete type information.
    """

    extra_info: dict[str, object]

    def pedantic(
        self,
        target: Callable[[], int],
        *,
        rounds: int,
        warmup_rounds: int,
        iterations: int,
        setup: Callable[[], None],
        teardown: Callable[[], None],
    ) -> int:
        """Measure repeated operations with setup outside timed samples.

        Args:
            target: Batch operation executed during a measured sample.
            rounds: Number of measured samples.
            warmup_rounds: Number of discarded warm-up samples.
            iterations: Number of calls per sample.
            setup: Prepare state before each sample.
            teardown: Release state after each sample.

        Returns:
            Result from the final operation.
        """
        ...


class _Sink:
    """Provide a concrete dependency for injected job handlers.

    The benchmark measures the real Container resolution path.
    """

    def consume(self, value: int) -> int:
        """Return the dispatched value without unrelated work.

        Args:
            value: Job data supplied to the application handler.

        Returns:
            The same value for benchmark validation.
        """
        return value


@dataclass
class _PlainJob(Job):
    """Carry one integer through the inline dispatch path.

    This job has no injected application services.
    """

    value: int

    def handle(self) -> int:
        """Return the payload through a synchronous handler.

        Returns:
            The integer stored in the job payload.
        """
        return self.value


@dataclass
class _InjectedJob(Job):
    """Resolve one application service during synchronous execution.

    The Container constructs ``_Sink`` within each job scope.
    """

    value: int

    def handle(self, sink: _Sink) -> int:
        """Pass the job value through the injected application service.

        Args:
            sink: Concrete dependency resolved by the native Container.

        Returns:
            The value returned by the injected service.
        """
        return sink.consume(self.value)


def _application(job_type: type[Job]) -> Application:
    """Create a fresh application with one trusted Queue job.

    Args:
        job_type: Job type registered before application startup.

    Returns:
        An unstarted application using Queue's inline connection.
    """
    return Application(
        config={"app": {"name": "queue-benchmark"}},
        service_providers=(QueueServiceProvider(jobs=(job_type,)),),
    )


async def _dispatch_batch(
    application: Application,
    jobs: tuple[Job, ...],
) -> int:
    """Execute one fixed job batch through the native application graph.

    Args:
        application: Fresh application used for this benchmark sample.
        jobs: Preconstructed job payloads excluded from timed setup.

    Returns:
        Number of jobs accepted and executed by the inline driver.
    """
    async with application:
        manager = application.container.make(QueueManager)
        for job in jobs:
            receipt = await manager.dispatch_async(
                job,
                connection="sync",
            )
            if receipt.state != "executed":
                raise AssertionError(_NOT_EXECUTED_ERROR)
    return len(jobs)


def _run_batch(
    application: Application,
    jobs: tuple[Job, ...],
) -> int:
    """Run one benchmark batch with a managed AnyIO event loop.

    Args:
        application: Fresh application used for this benchmark sample.
        jobs: Preconstructed job payloads.

    Returns:
        Number of jobs completed by the inline connection.
    """
    return anyio.run(_dispatch_batch, application, jobs)


@pytest.mark.benchmark
def test_sync_connection_inline_dispatch(
    benchmark: _BenchmarkFixture,
) -> None:
    """Measure payload dispatch without application handler injection.

    Each sample processes 32 jobs through a real application and sync driver.
    Startup, shutdown, and AnyIO loop setup remain part of the measured path.

    Args:
        benchmark: Fixture that records latency across independent samples.
    """
    jobs = tuple(_PlainJob(value) for value in range(_BATCH_SIZE))
    applications: list[Application] = []

    def setup() -> None:
        """Create the application before the timed batch starts.

        Application construction stays outside each timed sample.
        """
        applications[:] = [_application(_PlainJob)]

    def operation() -> int:
        """Dispatch the prepared batch through a fresh application.

        The application lifecycle and AnyIO runtime remain timed.
        """
        return _run_batch(applications[0], jobs)

    def teardown() -> None:
        """Drop the application reference after native shutdown.

        Queue resources are finalized by the application lifecycle.
        """
        applications.clear()

    benchmark.extra_info.update(
        {
            "jobs_per_sample": _BATCH_SIZE,
            "driver": "sync",
            "handler": "sync without injected services",
            "application_lifecycle_included": True,
        }
    )
    assert (
        benchmark.pedantic(
            operation,
            rounds=_BENCHMARK_ROUNDS,
            warmup_rounds=_WARMUP_ROUNDS,
            iterations=1,
            setup=setup,
            teardown=teardown,
        )
        == _BATCH_SIZE
    )


@pytest.mark.benchmark
def test_sync_connection_injected_handler(
    benchmark: _BenchmarkFixture,
) -> None:
    """Measure handler execution with a concrete Container dependency.

    Each sample resolves QueueManager and injects ``_Sink`` into every job.

    Args:
        benchmark: Fixture that records latency across independent samples.
    """
    jobs = tuple(_InjectedJob(value) for value in range(_BATCH_SIZE))
    applications: list[Application] = []

    def setup() -> None:
        """Create the application before the timed batch starts.

        Application construction stays outside each timed sample.
        """
        applications[:] = [_application(_InjectedJob)]

    def operation() -> int:
        """Run jobs and resolve each handler dependency.

        The application lifecycle and AnyIO runtime remain timed.
        """
        return _run_batch(applications[0], jobs)

    def teardown() -> None:
        """Drop the application reference after native shutdown.

        Queue resources are finalized by the application lifecycle.
        """
        applications.clear()

    benchmark.extra_info.update(
        {
            "jobs_per_sample": _BATCH_SIZE,
            "driver": "sync",
            "handler": "sync with Container-injected _Sink",
            "application_lifecycle_included": True,
        }
    )
    assert (
        benchmark.pedantic(
            operation,
            rounds=_BENCHMARK_ROUNDS,
            warmup_rounds=_WARMUP_ROUNDS,
            iterations=1,
            setup=setup,
            teardown=teardown,
        )
        == _BATCH_SIZE
    )
