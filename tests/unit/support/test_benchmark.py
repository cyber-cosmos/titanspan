"""Verify benchmark timing, result shapes, and async extensions.

Tests use deterministic callbacks and assert only stable timing properties.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from titanspan.support import Benchmark

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.unit
def test_measure_returns_milliseconds_for_a_single_callable() -> None:
    """Measure one callable and return a non-negative millisecond value.

    Returns:
        None.
    """
    result = Benchmark.measure(lambda: "done")

    assert isinstance(result, float)
    assert result >= 0


@pytest.mark.unit
def test_measure_preserves_mapping_keys_and_runs_each_iteration() -> None:
    """Measure each keyed operation for the requested iteration count.

    Returns:
        None.
    """
    repetitions = 3
    calls: dict[str, int] = {"fast": 0, "slow": 0}

    def record(name: str) -> Callable[[], None]:
        """Create a callback that increments its named counter.

        Args:
            name: The counter key to increment.

        Returns:
            A zero-argument benchmark callback.
        """

        def callback() -> None:
            """Record one execution of the selected operation.

            Returns:
                None.
            """
            calls[name] += 1

        return callback

    results = Benchmark.measure(
        {"fast": record("fast"), "slow": record("slow")},
        iterations=repetitions,
    )

    assert isinstance(results, dict)
    assert set(results) == {"fast", "slow"}
    assert all(isinstance(value, float) for value in results.values())
    assert calls == {"fast": repetitions, "slow": repetitions}


@pytest.mark.unit
def test_measure_supports_an_iterable_of_callbacks() -> None:
    """Return measurements in iterable order for multiple callbacks.

    Returns:
        None.
    """
    callbacks: list[Callable[[], int]] = [lambda: 1, lambda: 2]

    results = Benchmark.measure(callbacks)

    assert isinstance(results, list)
    assert len(results) == len(callbacks)
    assert all(value >= 0 for value in results)


@pytest.mark.unit
@pytest.mark.parametrize("iterations", [0, -1])
def test_measure_rejects_non_positive_iteration_counts(
    iterations: int,
) -> None:
    """Reject empty or negative measurement runs explicitly.

    Args:
        iterations: The invalid iteration count to supply.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="iterations"):
        Benchmark.measure(lambda: None, iterations=iterations)


@pytest.mark.unit
@pytest.mark.parametrize("iterations", [1.5, "2"])
def test_measure_rejects_non_integer_iteration_counts(
    iterations: object,
) -> None:
    """Reject values that cannot represent an exact repetition count.

    Args:
        iterations: The invalid repetition count to supply.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="iterations"):
        Benchmark.measure(lambda: None, iterations=cast("int", iterations))


@pytest.mark.unit
def test_measure_propagates_callback_errors() -> None:
    """Propagate callback errors without converting them into timings.

    Returns:
        None.
    """
    error_message = "benchmark callback failed"

    def fail() -> None:
        """Raise the sentinel failure used by this test.

        Raises:
            LookupError: Always, to verify error propagation.
        """
        raise LookupError(error_message)

    with pytest.raises(LookupError, match=error_message):
        Benchmark.measure(fail)


@pytest.mark.unit
def test_value_returns_callback_result_and_elapsed_time() -> None:
    """Return the operation result together with its elapsed milliseconds.

    Returns:
        None.
    """
    result, elapsed = Benchmark.value(lambda: {"answer": 42})

    assert result == {"answer": 42}
    assert isinstance(elapsed, float)
    assert elapsed >= 0


@pytest.mark.unit
def test_dd_prints_measurement_then_raises_system_exit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Preserve dump-and-die semantics without terminating test execution.

    Args:
        capsys: Pytest's captured output fixture.

    Returns:
        None.
    """
    with pytest.raises(SystemExit):
        Benchmark.dd(lambda: None)

    assert "ms" in capsys.readouterr().out


@pytest.mark.unit
def test_macro_registration_uses_explicit_typed_invocation() -> None:
    """Expose Macroable registration while avoiding dynamic attribute lookup.

    Returns:
        None.
    """
    Benchmark.flush_macros()
    Benchmark.macro("is_ready", lambda: True)

    assert Benchmark.has_macro("is_ready")
    assert Benchmark.invoke_macro("is_ready") is True
    Benchmark.flush_macros()


@pytest.mark.unit
@pytest.mark.anyio
async def test_measure_async_awaits_each_callback() -> None:
    """Measure asynchronous callbacks without blocking their event loop.

    Returns:
        None.
    """
    expected_calls = 2
    calls = 0

    async def callback() -> int:
        """Increment and return a stable async callback result.

        Returns:
            The current callback count.
        """
        nonlocal calls
        calls += 1
        return calls

    result = await Benchmark.measure_async(
        callback,
        iterations=expected_calls,
    )

    assert isinstance(result, float)
    assert result >= 0
    assert calls == expected_calls


@pytest.mark.unit
@pytest.mark.anyio
async def test_measure_async_preserves_mapping_results() -> None:
    """Measure named asynchronous operations in their mapping shape.

    Returns:
        None.
    """

    async def callback() -> None:
        """Provide an asynchronous no-op operation.

        Returns:
            None.
        """

    result = await Benchmark.measure_async({"task": callback})

    assert isinstance(result, dict)
    assert list(result) == ["task"]
    assert result["task"] >= 0


@pytest.mark.unit
@pytest.mark.anyio
async def test_measure_async_supports_iterable_callbacks() -> None:
    """Return timings in order for an iterable of async callbacks.

    Returns:
        None.
    """

    async def callback() -> None:
        """Provide a deterministic async operation.

        Returns:
            None.
        """

    result = await Benchmark.measure_async([callback])

    assert len(result) == 1
    assert result[0] >= 0


@pytest.mark.unit
@pytest.mark.anyio
async def test_value_async_returns_awaited_result_and_duration() -> None:
    """Return an async callback's result and its elapsed duration.

    Returns:
        None.
    """

    async def callback() -> str:
        """Return a stable async callback result.

        Returns:
            The benchmark result.
        """
        return "complete"

    result, elapsed = await Benchmark.value_async(callback)

    assert result == "complete"
    assert elapsed >= 0


@pytest.mark.unit
def test_dd_formats_mapping_and_list_measurements(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Format grouped measurement results before raising SystemExit.

    Args:
        capsys: Pytest's captured output fixture.

    Returns:
        None.
    """
    with pytest.raises(SystemExit):
        Benchmark.dd({"named": lambda: None})
    assert "named" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        Benchmark.dd([lambda: None])
    assert "ms" in capsys.readouterr().out


@pytest.mark.unit
def test_measure_rejects_awaitable_from_synchronous_callback() -> None:
    """Reject and close an async result passed to the sync API.

    Returns:
        None.
    """

    async def callback() -> None:
        """Provide a coroutine that must not be leaked.

        Returns:
            None.
        """

    with pytest.raises(TypeError, match="measure_async"):
        Benchmark.measure(callback)
