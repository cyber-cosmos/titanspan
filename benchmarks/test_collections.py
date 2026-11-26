"""Compare collection pipelines with equivalent Python operations.

Measurements are informational and use no shared-runner timing thresholds.
"""

from __future__ import annotations

import tracemalloc
from itertools import count
from typing import TYPE_CHECKING, Protocol, cast

import pytest

from titanspan.collections import collect, lazy

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from pytest_benchmark.fixture import BenchmarkFixture

_VALUES = tuple(range(10_000))
_PREFIX_SIZE = 20_000
_MEMORY_ROUNDS = 3


class _BenchmarkMemoryFixture(Protocol):
    """Describe the locked benchmark fixture calls used for memory reports.

    The plugin does not publish type information for these dynamic methods.
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
        """Run a fixed number of benchmark rounds.

        Args:
            target: The operation measured by the fixture.
            args: Arguments passed to the operation.
            rounds: The number of samples to collect.
            iterations: The target calls made in each sample.

        Returns:
            The target result from the final sample.
        """
        ...


def _native_eager_map() -> list[int]:
    """Map a fixed tuple with a Python list comprehension.

    Returns:
        The transformed values in source order.
    """
    return [value * 2 for value in _VALUES]


def _collection_eager_map() -> list[int]:
    """Map the same tuple through an eager Collection pipeline.

    Returns:
        The transformed values in source order.
    """
    return collect(_VALUES).map(lambda value: value * 2).all()


def _native_lazy_map() -> list[int]:
    """Materialize a Python generator expression over the fixed tuple.

    Returns:
        The transformed values in source order.
    """
    return list(_native_mapped_values())


def _native_mapped_values() -> Iterator[int]:
    """Yield mapped values with a native generator function.

    Yields:
        The doubled source values in order.
    """
    for value in _VALUES:
        yield value * 2


def _collection_lazy_map() -> list[int]:
    """Materialize the equivalent LazyCollection pipeline.

    Returns:
        The transformed values in source order.
    """
    return lazy(iter(_VALUES)).map(lambda value: value * 2).collect().all()


def _incremental_prefix_sum() -> int:
    """Sum a finite prefix from an unbounded iterator incrementally.

    Returns:
        The sum of the first ``_PREFIX_SIZE`` incremented integers.
    """
    return lazy(count()).map(lambda value: value + 1).take(_PREFIX_SIZE).sum()


def _materialized_prefix_count() -> int:
    """Materialize the same finite source prefix into a Collection.

    Returns:
        The number of materialized values.
    """
    return lazy(count()).take(_PREFIX_SIZE).collect().count()


def _peak_memory(operation: Callable[[], object]) -> int:
    """Measure peak traced memory while one operation runs.

    Args:
        operation: A zero-argument operation whose memory use is measured.

    Returns:
        The peak number of traced bytes.
    """
    # Start each sample independently so prior rounds do not affect its peak.
    tracemalloc.start()
    try:
        operation()
        _, peak_bytes = tracemalloc.get_traced_memory()
        return peak_bytes
    finally:
        tracemalloc.stop()


@pytest.mark.benchmark
def test_native_eager_map(benchmark: BenchmarkFixture) -> None:
    """Measure the native eager list-comprehension baseline.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    benchmark(_native_eager_map)


@pytest.mark.benchmark
def test_collection_eager_map(benchmark: BenchmarkFixture) -> None:
    """Measure an equivalent eager Collection transformation.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    benchmark(_collection_eager_map)


@pytest.mark.benchmark
def test_native_lazy_map(benchmark: BenchmarkFixture) -> None:
    """Measure the native generator-expression baseline.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    benchmark(_native_lazy_map)


@pytest.mark.benchmark
def test_collection_lazy_map(benchmark: BenchmarkFixture) -> None:
    """Measure an equivalent LazyCollection transformation.

    Args:
        benchmark: Fixture that repeats the prepared operation.
    """
    benchmark(_collection_lazy_map)


@pytest.mark.benchmark
def test_incremental_peak_memory(benchmark: BenchmarkFixture) -> None:
    """Report peak memory for incremental prefix processing.

    Args:
        benchmark: Fixture that repeats the memory measurement.
    """
    # Narrow the untyped plugin calls to the API verified for version 5.3.1.
    memory_benchmark = cast("_BenchmarkMemoryFixture", benchmark)
    peak_bytes = cast(
        "int",
        memory_benchmark.pedantic(
            _peak_memory,
            args=(_incremental_prefix_sum,),
            rounds=_MEMORY_ROUNDS,
            iterations=1,
        ),
    )
    memory_benchmark.extra_info["peak_bytes"] = peak_bytes
    assert peak_bytes > 0


@pytest.mark.benchmark
def test_materialization_peak_memory(benchmark: BenchmarkFixture) -> None:
    """Report peak memory for materializing the same finite prefix.

    Args:
        benchmark: Fixture that repeats the memory measurement.
    """
    # Narrow the untyped plugin calls to the API verified for version 5.3.1.
    memory_benchmark = cast("_BenchmarkMemoryFixture", benchmark)
    peak_bytes = cast(
        "int",
        memory_benchmark.pedantic(
            _peak_memory,
            args=(_materialized_prefix_count,),
            rounds=_MEMORY_ROUNDS,
            iterations=1,
        ),
    )
    memory_benchmark.extra_info["peak_bytes"] = peak_bytes
    assert peak_bytes > 0
