"""Measure event dispatch overhead against direct Python calls.

The measurements are informational and use no shared-runner thresholds.
"""

from __future__ import annotations

import tracemalloc
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

import anyio
import pytest

from titanspan import Application
from titanspan.events import (
    ListenerRegistration,
    NativeEventDispatcher,
    inspect_events,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_benchmark.fixture import BenchmarkFixture

    from titanspan.events import DiscoveryEntry

_DISCOVERY_MODULES = ("tests.unit.events._discovery_fixture",)
_HIGH_VOLUME_CALLS = 500
_MEMORY_ROUNDS = 3


@dataclass(frozen=True, slots=True)
class BenchEvent:
    """Carry one stable integer through event dispatch benchmarks.

    The benchmark keeps real backend work inside the measured path.
    """

    value: int


class _Sink:
    """Provide a concrete constructor dependency for Container resolution.

    The benchmark keeps real backend work inside the measured path.
    """

    def record(self, value: int) -> int:
        """Return one dependency-injected value without extra work.

        Args:
            value: Integer carried by the benchmark event.

        Returns:
            The same value for comparison with direct invocation.
        """
        return value


class _ResolvedListener:
    """Resolve through the Application Container for each dispatch.

    The benchmark keeps real backend work inside the measured path.
    """

    def __init__(self, sink: _Sink) -> None:
        """Retain the dependency constructed by the Container.

        Args:
            sink: Service injected by the application Container.
        """
        self._sink = sink

    def handle(self, event: BenchEvent) -> int:
        """Return a value through the injected service.

        Args:
            event: Benchmark event passed by the dispatcher.

        Returns:
            The value returned by the injected service.
        """
        return self._sink.record(event.value)


class _MemoryBenchmark(Protocol):
    """Describe the locked benchmark fixture's memory measurement method.

    The benchmark keeps real backend work inside the measured path.
    """

    extra_info: dict[str, object]

    def pedantic(
        self,
        target: Callable[..., object],
        *,
        args: tuple[object, ...],
        rounds: int,
        iterations: int,
    ) -> object:
        """Measure a fixed number of operation samples.

        Args:
            target: Operation measured by the benchmark fixture.
            args: Values passed to the operation.
            rounds: Number of independent samples.
            iterations: Calls made during each sample.

        Returns:
            The operation result from the last sample.
        """
        ...


def _dispatch_direct(event: BenchEvent) -> int:
    """Represent equivalent work through a direct Python call.

    Args:
        event: Event value used by the direct baseline.

    Returns:
        The event value.
    """
    return event.value


def _dispatch_many(
    dispatcher: NativeEventDispatcher,
    event: BenchEvent,
) -> int:
    """Dispatch one event repeatedly to measure high-frequency overhead.

    Args:
        dispatcher: Dispatcher with one registered listener.
        event: Stable event value reused for each dispatch.

    Returns:
        Number of listener responses collected during the batch.
    """
    responses = 0
    for _ in range(_HIGH_VOLUME_CALLS):
        responses += len(dispatcher.dispatch(event))
    return responses


async def _dispatch_async(
    dispatcher: NativeEventDispatcher,
    event: BenchEvent,
) -> list[object]:
    """Await one explicit asynchronous dispatch operation.

    Args:
        dispatcher: Dispatcher with a synchronous listener.
        event: Event value used by the asynchronous benchmark.

    Returns:
        Listener responses in registration order.
    """
    return await dispatcher.dispatch_async(event)


def _run_async_dispatch(
    dispatcher: NativeEventDispatcher,
    event: BenchEvent,
) -> list[object]:
    """Run one dispatch with AnyIO's event-loop startup included.

    Args:
        dispatcher: Dispatcher measured by this benchmark.
        event: Event value sent through the asynchronous path.

    Returns:
        Listener responses in registration order.
    """
    return anyio.run(_dispatch_async, dispatcher, event)


def _peak_memory(operation: Callable[[], object]) -> int:
    """Measure peak traced allocations made by one operation.

    Args:
        operation: Zero-argument operation measured by this helper.

    Returns:
        Peak bytes recorded by `tracemalloc`.
    """
    tracemalloc.start()
    try:
        operation()
        _, peak_bytes = tracemalloc.get_traced_memory()
        return peak_bytes
    finally:
        tracemalloc.stop()


@pytest.mark.benchmark
def test_direct_call_baseline(benchmark: BenchmarkFixture) -> None:
    """Measure the equivalent direct function call.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    benchmark(_dispatch_direct, BenchEvent(1))


@pytest.mark.benchmark
def test_dispatch_without_listeners(benchmark: BenchmarkFixture) -> None:
    """Measure dispatch when no registration matches.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    dispatcher = NativeEventDispatcher()
    benchmark(dispatcher.dispatch, BenchEvent(1))


@pytest.mark.benchmark
def test_single_listener_dispatch(benchmark: BenchmarkFixture) -> None:
    """Measure one typed listener invocation.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    dispatcher = NativeEventDispatcher()
    dispatcher.listen(BenchEvent, _dispatch_direct)
    benchmark(dispatcher.dispatch, BenchEvent(1))


@pytest.mark.benchmark
def test_multiple_listener_dispatch(benchmark: BenchmarkFixture) -> None:
    """Measure five typed listener invocations in deterministic order.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    dispatcher = NativeEventDispatcher()
    for _ in range(5):
        dispatcher.listen(BenchEvent, _dispatch_direct)
    benchmark(dispatcher.dispatch, BenchEvent(1))


@pytest.mark.benchmark
def test_wildcard_listener_dispatch(benchmark: BenchmarkFixture) -> None:
    """Measure one named-event wildcard match.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    dispatcher = NativeEventDispatcher()

    def record(name: str, payload: object) -> str:
        """Return the event name for the wildcard benchmark.

        Args:
            name: Canonical named event delivered by the dispatcher.
            payload: Named payload passed to the wildcard listener.

        Returns:
            The canonical event name.
        """
        _ = payload
        return name

    dispatcher.listen("workflow.*", record)
    benchmark(dispatcher.dispatch, "workflow.completed", 1)


@pytest.mark.benchmark
def test_container_resolved_listener_dispatch(
    benchmark: BenchmarkFixture,
) -> None:
    """Measure listener construction and injection through Application.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    application = Application()
    dispatcher = application.make(NativeEventDispatcher)
    dispatcher.listen(BenchEvent, _ResolvedListener)

    try:
        with application.context():
            benchmark(dispatcher.dispatch, BenchEvent(1))
    finally:
        anyio.run(application.shutdown)


@pytest.mark.benchmark
def test_async_listener_dispatch(benchmark: BenchmarkFixture) -> None:
    """Measure explicit async dispatch, including AnyIO loop startup.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    dispatcher = NativeEventDispatcher()
    dispatcher.listen(BenchEvent, _dispatch_direct)
    benchmark(_run_async_dispatch, dispatcher, BenchEvent(1))


@pytest.mark.benchmark
def test_high_frequency_dispatch(benchmark: BenchmarkFixture) -> None:
    """Measure a bounded batch of repeated event dispatches.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    dispatcher = NativeEventDispatcher()
    dispatcher.listen(BenchEvent, _dispatch_direct)
    assert benchmark(_dispatch_many, dispatcher, BenchEvent(1)) == (
        _HIGH_VOLUME_CALLS
    )


@pytest.mark.benchmark
def test_registration_overhead(benchmark: BenchmarkFixture) -> None:
    """Measure the cost of adding one receiver to a new dispatcher.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    benchmark(_register_one_listener)


def _register_one_listener() -> ListenerRegistration:
    """Create a dispatcher and register one listener.

    Returns:
        Registration handle owned by the new dispatcher.
    """
    dispatcher = NativeEventDispatcher()
    return dispatcher.listen(BenchEvent, _dispatch_direct)


@pytest.mark.benchmark
def test_discovery_inspection_overhead(benchmark: BenchmarkFixture) -> None:
    """Measure deterministic inspection of a small trusted module.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    entries = cast(
        "tuple[DiscoveryEntry, ...]",
        benchmark(inspect_events, _DISCOVERY_MODULES),
    )
    assert entries


@pytest.mark.benchmark
def test_dispatch_peak_memory(benchmark: BenchmarkFixture) -> None:
    """Report peak allocations for a high-frequency dispatch batch.

    Args:
        benchmark: Fixture that repeats the memory measurement.
    """
    dispatcher = NativeEventDispatcher()
    dispatcher.listen(BenchEvent, _dispatch_direct)

    def dispatch_batch() -> int:
        """Run the measured dispatch batch with a fresh event value.

        The benchmark keeps real backend work inside the measured path.
        """
        return _dispatch_many(dispatcher, BenchEvent(1))

    memory_benchmark = cast("_MemoryBenchmark", benchmark)
    peak_bytes = cast(
        "int",
        memory_benchmark.pedantic(
            _peak_memory,
            args=(dispatch_batch,),
            rounds=_MEMORY_ROUNDS,
            iterations=1,
        ),
    )
    memory_benchmark.extra_info["peak_bytes"] = peak_bytes
    assert peak_bytes > 0
