"""Measure synchronous and asynchronous callable execution durations.

Measurements use a monotonic high-resolution clock and are reported in
milliseconds. Results are observations, not stable performance guarantees.
"""

from __future__ import annotations

import gc
import inspect
import pprint
import sys
from collections.abc import Awaitable, Callable, Iterable, Mapping
from time import perf_counter_ns
from typing import TypeVar, cast, overload

from titanspan.support.macroable import Macroable

_T = TypeVar("_T")
_K = TypeVar("_K")
type _SyncOperation = Callable[[], object]
type _AsyncOperation = Callable[[], Awaitable[object]]
type _SyncTargets = (
    _SyncOperation | Mapping[object, _SyncOperation] | Iterable[_SyncOperation]
)
type _AsyncTargets = (
    _AsyncOperation
    | Mapping[object, _AsyncOperation]
    | Iterable[_AsyncOperation]
)
_ITERATION_ERROR = "iterations must be a positive integer"
_ASYNC_CALLBACK_ERROR = (
    "synchronous benchmark callbacks must not return awaitables; "
    "use measure_async() or value_async()"
)


class Benchmark(Macroable):
    """Measure callable execution while preserving input result shapes.

    A single callback produces one millisecond value. A mapping produces a
    mapping with its keys preserved, and another iterable produces a list.
    Async methods await each operation sequentially and never create tasks.

    Notes:
        Wall-clock measurements vary with the machine, scheduler, and
        workload. They are diagnostic values, not benchmark evidence.
    """

    @staticmethod
    @overload
    def measure(
        benchmarkables: Callable[[], _T],
        iterations: int = 1,
    ) -> float:
        """Measure one callback and return its average duration.

        Returns:
            Average elapsed time in milliseconds.
        """
        ...

    @staticmethod
    @overload
    def measure(
        benchmarkables: Mapping[_K, _SyncOperation],
        iterations: int = 1,
    ) -> dict[_K, float]:
        """Measure named callbacks and preserve their mapping keys.

        Returns:
            Average elapsed milliseconds for each input key.
        """
        ...

    @staticmethod
    @overload
    def measure(
        benchmarkables: Iterable[_SyncOperation],
        iterations: int = 1,
    ) -> list[float]:
        """Measure iterable callbacks and preserve their order.

        Returns:
            Average elapsed milliseconds in input order.
        """
        ...

    @staticmethod
    def measure(
        benchmarkables: (
            _SyncOperation
            | Mapping[_K, _SyncOperation]
            | Iterable[_SyncOperation]
        ),
        iterations: int = 1,
    ) -> float | dict[_K, float] | list[float]:
        """Measure one or more synchronous callbacks in milliseconds.

        Args:
            benchmarkables: One callback, a mapping of callbacks, or an
                iterable of callbacks.
            iterations: Number of repetitions for each callback.

        Returns:
            A float, a key-preserving mapping, or a list of average timings.

        Raises:
            TypeError: If a synchronous callback returns an awaitable.
            ValueError: If ``iterations`` is not a positive integer.
        """
        Benchmark._validate_iterations(iterations)
        if callable(benchmarkables):
            return Benchmark._average(benchmarkables, iterations)
        if isinstance(benchmarkables, Mapping):
            callbacks = cast(
                "Mapping[_K, _SyncOperation]",
                benchmarkables,
            )
            return {
                key: Benchmark._average(callback, iterations)
                for key, callback in callbacks.items()
            }
        callbacks = tuple(benchmarkables)
        return [
            Benchmark._average(callback, iterations) for callback in callbacks
        ]

    @staticmethod
    @overload
    async def measure_async(
        benchmarkables: Callable[[], Awaitable[_T]],
        iterations: int = 1,
    ) -> float:
        """Measure one asynchronous callback and average its duration.

        Returns:
            Average elapsed time in milliseconds.
        """
        ...

    @staticmethod
    @overload
    async def measure_async(
        benchmarkables: Mapping[_K, _AsyncOperation],
        iterations: int = 1,
    ) -> dict[_K, float]:
        """Measure named async callbacks and preserve mapping keys.

        Returns:
            Average elapsed milliseconds for each input key.
        """
        ...

    @staticmethod
    @overload
    async def measure_async(
        benchmarkables: Iterable[_AsyncOperation],
        iterations: int = 1,
    ) -> list[float]:
        """Measure iterable async callbacks and preserve their order.

        Returns:
            Average elapsed milliseconds in input order.
        """
        ...

    @staticmethod
    async def measure_async(
        benchmarkables: (
            _AsyncOperation
            | Mapping[_K, _AsyncOperation]
            | Iterable[_AsyncOperation]
        ),
        iterations: int = 1,
    ) -> float | dict[_K, float] | list[float]:
        """Measure asynchronous callbacks sequentially in milliseconds.

        Args:
            benchmarkables: One async callback, a callback mapping, or an
                iterable of async callbacks.
            iterations: Number of repetitions for each callback.

        Returns:
            A float, a key-preserving mapping, or a list of average timings.

        Raises:
            ValueError: If ``iterations`` is not a positive integer.
        """
        Benchmark._validate_iterations(iterations)
        if callable(benchmarkables):
            return await Benchmark._average_async(
                benchmarkables,
                iterations,
            )
        if isinstance(benchmarkables, Mapping):
            results: dict[_K, float] = {}
            callbacks = cast(
                "Mapping[_K, _AsyncOperation]",
                benchmarkables,
            )
            for key, callback in callbacks.items():
                results[key] = await Benchmark._average_async(
                    callback,
                    iterations,
                )
            return results
        return [
            await Benchmark._average_async(callback, iterations)
            for callback in benchmarkables
        ]

    @staticmethod
    def value(callback: Callable[[], _T]) -> tuple[_T, float]:
        """Return a callback result and its elapsed time in milliseconds.

        Args:
            callback: The synchronous operation to execute once.

        Returns:
            The operation result and elapsed milliseconds.

        Raises:
            TypeError: If the callback returns an awaitable.
        """
        # Keep cycle collection outside the callback's measured interval.
        gc.collect()
        started = perf_counter_ns()
        result = callback()
        Benchmark._reject_awaitable(result)
        elapsed = (perf_counter_ns() - started) / 1_000_000
        return result, elapsed

    @staticmethod
    async def value_async(
        callback: Callable[[], Awaitable[_T]],
    ) -> tuple[_T, float]:
        """Return an awaited callback result and elapsed milliseconds.

        Args:
            callback: The asynchronous operation to execute once.

        Returns:
            The operation result and elapsed milliseconds.
        """
        # Match Laravel's sample setup before starting the monotonic clock.
        gc.collect()
        started = perf_counter_ns()
        result = await callback()
        elapsed = (perf_counter_ns() - started) / 1_000_000
        return result, elapsed

    @staticmethod
    def dd(benchmarkables: _SyncTargets, iterations: int = 1) -> None:
        """Print formatted measurements and terminate with SystemExit.

        Args:
            benchmarkables: One callback, a mapping, or an iterable.
            iterations: Number of repetitions for each callback.

        Raises:
            SystemExit: Always, after writing measurements to standard output.
            TypeError: If a synchronous callback returns an awaitable.
            ValueError: If ``iterations`` is not a positive integer.
        """
        result = Benchmark.measure(benchmarkables, iterations)
        if isinstance(result, dict):
            formatted: object = {
                key: f"{elapsed:.3f}ms" for key, elapsed in result.items()
            }
        elif isinstance(result, list):
            formatted = [f"{elapsed:.3f}ms" for elapsed in result]
        else:
            formatted = f"{result:.3f}ms"
        sys.stdout.write(f"{pprint.pformat(formatted)}\n")
        raise SystemExit

    @staticmethod
    def _validate_iterations(iterations: object) -> None:
        """Reject iteration counts that cannot produce an average.

        Args:
            iterations: The requested callback repetition count.

        Raises:
            ValueError: If the value is not a positive integer.
        """
        if (
            isinstance(iterations, bool)
            or not isinstance(iterations, int)
            or iterations < 1
        ):
            raise ValueError(_ITERATION_ERROR)

    @staticmethod
    def _average(callback: _SyncOperation, iterations: int) -> float:
        """Run a callback repeatedly and calculate mean milliseconds.

        Args:
            callback: The synchronous operation to measure.
            iterations: The positive number of measurements.

        Returns:
            The arithmetic mean of elapsed milliseconds.

        Raises:
            TypeError: If the callback returns an awaitable.
        """
        samples: list[float] = []
        for _ in range(iterations):
            # Keep collection work out of the recorded duration.
            gc.collect()
            started = perf_counter_ns()
            result = callback()
            Benchmark._reject_awaitable(result)
            samples.append((perf_counter_ns() - started) / 1_000_000)
        return sum(samples) / len(samples)

    @staticmethod
    async def _average_async(
        callback: _AsyncOperation,
        iterations: int,
    ) -> float:
        """Await a callback repeatedly and calculate mean milliseconds.

        Args:
            callback: The asynchronous operation to measure.
            iterations: The positive number of measurements.

        Returns:
            The arithmetic mean of elapsed milliseconds.
        """
        samples: list[float] = []
        for _ in range(iterations):
            # Keep collection work out of the recorded duration.
            gc.collect()
            started = perf_counter_ns()
            await callback()
            samples.append((perf_counter_ns() - started) / 1_000_000)
        return sum(samples) / len(samples)

    @staticmethod
    def _reject_awaitable(result: object) -> None:
        """Prevent synchronous APIs from leaking unawaited operations.

        Args:
            result: The value returned by a synchronous callback.

        Raises:
            TypeError: If the value is awaitable.
        """
        if not inspect.isawaitable(result):
            return
        if inspect.iscoroutine(result):
            result.close()
        raise TypeError(_ASYNC_CALLBACK_ERROR)


__all__ = ["Benchmark"]
