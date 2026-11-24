"""Measure the small application composition cost for reference.

The benchmark is informational and does not enforce unstable shared-runner
timing thresholds.
"""

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from titanspan import Application


@pytest.mark.benchmark
def test_application_construction(benchmark: BenchmarkFixture) -> None:
    """Measure construction through the public application entry point.

    Args:
        benchmark: pytest-benchmark fixture that repeats the constructor call.
    """
    benchmark(Application)
