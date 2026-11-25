"""Measure synchronous and asynchronous container resolution.

The benchmarks are informational and do not enforce shared-runner timing
thresholds.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from titanspan.container import Container

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

_ASYNC_BATCH_SIZE = 64


class ResolutionService:
    """Represent a small unregistered service for resolution benchmarks.

    Keeping construction trivial makes the measurement focus on container
    overhead instead of application work.
    """


@pytest.mark.benchmark
def test_sync_resolution(benchmark: BenchmarkFixture) -> None:
    """Measure synchronous transient resolution on a prepared container.

    Args:
        benchmark: Fixture that measures a repeatable synchronous operation.
    """
    container = Container()
    container.bind(ResolutionService)
    try:
        # Exclude introspection and provider setup from warm resolution timing.
        container.make(ResolutionService)
        benchmark(container.make, ResolutionService)
    finally:
        with asyncio.Runner() as runner:
            runner.run(container.aclose())


@pytest.mark.benchmark
def test_sync_cached_resolution(benchmark: BenchmarkFixture) -> None:
    """Measure synchronous retrieval of an initialized singleton.

    Args:
        benchmark: Fixture that measures a repeatable synchronous operation.
    """
    container = Container()
    container.singleton(ResolutionService)
    container.make(ResolutionService)
    try:
        benchmark(container.make, ResolutionService)
    finally:
        with asyncio.Runner() as runner:
            runner.run(container.aclose())


@pytest.mark.benchmark
def test_async_resolution(benchmark: BenchmarkFixture) -> None:
    """Measure async transient resolution without recreating the event loop.

    Args:
        benchmark: Fixture that measures a repeatable synchronous wrapper.

    Notes:
        A persistent runner keeps each batch on one event loop and amortizes
        loop startup across the measured resolution operations.
    """
    runner = asyncio.Runner()
    container = Container()
    container.bind(ResolutionService)

    async def resolve_batch() -> None:
        """Resolve a fixed batch of transient service instances.

        The batch allows the synchronous benchmark fixture to measure awaited
        resolutions on one persistent runner without returning a coroutine.
        """
        for _ in range(_ASYNC_BATCH_SIZE):
            await container.make_async(ResolutionService)

    def run_batch() -> None:
        """Run one asynchronous batch on the persistent benchmark loop.

        The coroutine is awaited before the wrapper returns to the fixture.
        """
        runner.run(resolve_batch())

    try:
        # Exclude graph composition and loop startup from each timed batch.
        runner.run(container.make_async(ResolutionService))
        benchmark(run_batch)
    finally:
        runner.run(container.aclose())
        runner.close()


@pytest.mark.benchmark
def test_async_cached_resolution(benchmark: BenchmarkFixture) -> None:
    """Measure async retrieval of an initialized singleton in batches.

    Args:
        benchmark: Fixture that measures a repeatable synchronous wrapper.

    Notes:
        Setup and warm-up happen before timing; the runner stays open until
        all benchmark iterations have completed.
    """
    runner = asyncio.Runner()
    container = Container()
    container.singleton(ResolutionService)

    async def warm_and_resolve_batch() -> None:
        """Warm the singleton and resolve it repeatedly in one loop.

        Setup warms the service before the timed batch, which reuses the cache.
        """
        for _ in range(_ASYNC_BATCH_SIZE):
            await container.make_async(ResolutionService)

    def run_batch() -> None:
        """Run one cached asynchronous resolution batch.

        The coroutine finishes on its owning loop before the measurement
        proceeds to the next sample.
        """
        runner.run(warm_and_resolve_batch())

    try:
        runner.run(container.make_async(ResolutionService))
        benchmark(run_batch)
    finally:
        runner.run(container.aclose())
        runner.close()
