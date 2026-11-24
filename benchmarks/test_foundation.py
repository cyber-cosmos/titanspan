"""Informational construction microbenchmark for the initial foundation."""

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from titanspan import Application


@pytest.mark.benchmark
def test_application_construction(benchmark: BenchmarkFixture) -> None:
    """Measure application construction without imposing a timing threshold."""
    benchmark(Application)
