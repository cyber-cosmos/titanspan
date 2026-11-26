"""Verify deterministic and probabilistic callback selection.

The tests isolate result factories in their active context so one test's
forced outcome cannot affect unrelated asynchronous execution.
"""

from __future__ import annotations

import asyncio
from contextvars import Context
from typing import TYPE_CHECKING, cast

import pytest

import titanspan.support.lottery as lottery_module
from titanspan.support import Lottery

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def reset_lottery_factory() -> Iterator[None]:
    """Reset the context-local result factory before and after each test.

    Yields:
        None after installing the normal randomized behavior.
    """
    Lottery.determine_result_normally()
    yield
    Lottery.determine_result_normally()


@pytest.mark.unit
def test_lottery_uses_callbacks_for_wins_losses_and_default_results() -> None:
    """Run the selected callback or return its boolean default.

    Returns:
        None.
    """
    Lottery.always_win()
    assert Lottery.odds(0, 1).winner(lambda: "won").choose() == "won"

    Lottery.always_lose()
    assert Lottery.odds(1, 1).loser(lambda: "lost").choose() == "lost"
    assert Lottery.odds(1, 1).choose() is False


@pytest.mark.unit
def test_lottery_is_callable_and_forwards_callback_arguments() -> None:
    """Support callback-style APIs and forward positional arguments.

    Returns:
        None.
    """
    Lottery.always_win()

    def combine(left: str, right: str) -> str:
        """Join the two callback arguments.

        Args:
            left: First string fragment.
            right: Second string fragment.

        Returns:
            The joined fragments.
        """
        return left + right

    lottery = Lottery.odds(1, 1).winner(combine)

    assert lottery("a", "b") == "ab"


@pytest.mark.unit
def test_choose_returns_a_list_when_count_is_supplied() -> None:
    """Return one result per requested independent draw.

    Returns:
        None.
    """
    Lottery.always_lose()

    assert Lottery.odds(1, 1).loser(lambda: "no").choose(3) == [
        "no",
        "no",
        "no",
    ]


@pytest.mark.unit
@pytest.mark.parametrize("times", [-1, True])
def test_choose_rejects_invalid_draw_counts(times: int) -> None:
    """Reject negative and boolean counts rather than silently coercing.

    Args:
        times: The invalid draw count.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="times"):
        Lottery.odds(1, 1).choose(times)


@pytest.mark.unit
@pytest.mark.parametrize("times", [1.5, "2"])
def test_choose_rejects_non_integer_draw_counts(times: object) -> None:
    """Reject values that cannot represent a whole number of draws.

    Args:
        times: The invalid draw count.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="times"):
        Lottery.odds(1, 1).choose(cast("int", times))


@pytest.mark.unit
def test_fix_consumes_a_deterministic_sequence_then_uses_fallback() -> None:
    """Use sequence outcomes in order and invoke fallback when exhausted.

    Returns:
        None.
    """
    fallback_calls: list[tuple[int | float, int | None]] = []

    def fallback(chances: int | float, out_of: int | None) -> bool:
        """Record the probability and select a deterministic fallback.

        Args:
            chances: The configured win count or probability.
            out_of: The optional opportunity count.

        Returns:
            Whether this fallback draw wins.
        """
        fallback_calls.append((chances, out_of))
        return False

    Lottery.fix([True, False], when_missing=fallback)
    lottery = Lottery.odds(1, 10).winner(lambda: "win").loser(lambda: "loss")

    assert lottery.choose(3) == ["win", "loss", "loss"]
    assert fallback_calls == [(1, 10)]


@pytest.mark.unit
def test_missing_sequence_mapping_index_uses_fallback_repeatedly() -> None:
    """Keep the cursor at a missing index while invoking fallback results.

    Returns:
        None.
    """
    fallback_calls: list[int] = []

    def fallback(_chances: int | float, _out_of: int | None) -> bool:
        """Count missing indexed values and report a loss.

        Args:
            _chances: Ignored probability.
            _out_of: Ignored opportunity count.

        Returns:
            A losing outcome.
        """
        fallback_calls.append(1)
        return False

    Lottery.fix({0: True}, when_missing=fallback)
    lottery = Lottery.odds(1, 4)

    assert lottery.choose() is True
    assert lottery.choose() is False
    assert lottery.choose() is False
    assert fallback_calls == [1, 1]


@pytest.mark.unit
def test_default_fallback_advances_past_sparse_sequence_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Advance sparse mapping cursors after default random fallbacks.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    random_draws: list[tuple[int | float, int | None]] = []

    def fallback(chances: int | float, out_of: int | None) -> bool:
        """Record one default draw and return a deterministic loss.

        Args:
            chances: The lottery numerator or probability.
            out_of: The optional denominator.

        Returns:
            A losing result.
        """
        random_draws.append((chances, out_of))
        return False

    monkeypatch.setattr(
        Lottery,
        "_normal_result",
        staticmethod(fallback),
    )
    Lottery.fix({0: True, 2: True})
    lottery = Lottery.odds(1, 4)

    assert [lottery.choose() for _ in range(3)] == [True, False, True]
    assert random_draws == [(1, 4)]


@pytest.mark.unit
def test_default_fallback_runs_after_sequence_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use randomized odds after all list outcomes have been consumed.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """

    def fallback(_chances: int | float, _out_of: int | None) -> bool:
        """Return a deterministic loss for exhausted outcomes.

        Args:
            _chances: Ignored test probability.
            _out_of: Ignored denominator.

        Returns:
            A losing result.
        """
        return False

    monkeypatch.setattr(Lottery, "_normal_result", staticmethod(fallback))
    Lottery.fix([True])

    assert Lottery.odds(1, 2).choose(2) == [True, False]


@pytest.mark.unit
def test_sequence_mapping_and_result_factory_are_supported() -> None:
    """Use indexed outcomes and a deterministic result factory.

    Returns:
        None.
    """
    Lottery.force_result_with_sequence({0: True, 1: False})
    lottery = Lottery.odds(0, 1)

    assert lottery.choose() is True
    assert lottery.choose() is False

    def force_loss(_chances: int | float, _out_of: int | None) -> bool:
        """Provide a deterministic losing result.

        Args:
            _chances: Ignored test probability.
            _out_of: Ignored opportunity count.

        Returns:
            A losing outcome.
        """
        return False

    Lottery.set_result_factory(force_loss)
    assert Lottery.odds(1, 1).choose() is False
    Lottery.determine_result_normally()


@pytest.mark.unit
def test_determine_result_normally_clears_forced_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clear the active override and use the configured result factory.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    Lottery.always_lose()

    def force_win(_chances: int | float, _out_of: int | None) -> bool:
        """Return a stable win after clearing the forced-loss factory.

        Args:
            _chances: Ignored test probability.
            _out_of: Ignored denominator.

        Returns:
            A winning result.
        """
        return True

    monkeypatch.setattr(
        Lottery,
        "_normal_result",
        staticmethod(force_win),
    )

    Lottery.determine_result_normally()

    assert Lottery.odds(0, 1).choose() is True


@pytest.mark.unit
def test_normal_probability_without_denominator_uses_unit_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use a unit-interval sample for probability-based outcomes.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """

    def zero_sample(_limit: int) -> int:
        """Return the lowest bounded integer for deterministic sampling.

        Args:
            _limit: The exclusive random upper bound.

        Returns:
            Zero, the lowest valid sample.
        """
        return 0

    monkeypatch.setattr(
        lottery_module.secrets,
        "randbelow",
        zero_sample,
    )

    assert Lottery.odds(0.0).choose() is True


@pytest.mark.unit
def test_forced_callback_overrides_are_restored_even_when_callback_fails() -> (
    None
):
    """Restore an outer context's result factory after a temporary override.

    Returns:
        None.
    """
    Lottery.always_lose()

    error_message = "forced callback failed"

    def fail() -> None:
        """Raise the sentinel failure inside an always-win callback.

        Raises:
            LookupError: Always.
        """
        raise LookupError(error_message)

    with pytest.raises(LookupError, match=error_message):
        Lottery.always_win(fail)

    assert Lottery.odds(1, 1).choose() is False


@pytest.mark.unit
def test_temporary_forced_result_restores_outer_factory() -> None:
    """Restore the outer context after a successful temporary result scope.

    Returns:
        None.
    """
    Lottery.always_lose()
    observed: list[object] = []

    def record() -> None:
        """Record a draw while the temporary result is active.

        Returns:
            None.
        """
        observed.append(Lottery.odds(0, 1).choose())

    Lottery.always_win(record)

    assert observed == [True]
    assert Lottery.odds(1, 1).choose() is False


@pytest.mark.unit
def test_result_factories_are_isolated_between_contexts() -> None:
    """Keep result factories local to the context that installs them.

    Returns:
        None.
    """
    Lottery.always_win()
    other_context = Context()
    other_result = other_context.run(lambda: Lottery.odds(1, 1).choose())

    assert other_result is True
    assert Lottery.odds(0, 1).choose() is True


@pytest.mark.unit
def test_invalid_odds_and_denominators_raise_value_errors() -> None:
    """Reject invalid probability inputs with stable Python exceptions.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="Float must not be greater than 1"):
        Lottery.odds(1.1)
    with pytest.raises(ValueError, match="out of"):
        Lottery.odds(1, 0)
    with pytest.raises(TypeError, match="out_of"):
        Lottery.odds(1, True)
    with pytest.raises(TypeError, match="chances"):
        Lottery.odds(True)


@pytest.mark.unit
@pytest.mark.parametrize("out_of", [1.5, "2"])
def test_odds_rejects_non_integer_denominators(out_of: object) -> None:
    """Reject denominators that cannot define integer opportunity counts.

    Args:
        out_of: The invalid denominator to supply.

    Returns:
        None.
    """
    with pytest.raises(TypeError, match="out_of"):
        Lottery.odds(1, cast("int", out_of))


@pytest.mark.unit
def test_odds_rejects_non_numeric_chances() -> None:
    """Require the chance value to be an integer or floating-point number.

    Returns:
        None.
    """
    with pytest.raises(TypeError, match="chances"):
        Lottery.odds(cast("int", "1"))


@pytest.mark.unit
@pytest.mark.anyio
async def test_choose_async_awaits_winner_and_loser_callbacks() -> None:
    """Await explicitly asynchronous callbacks and propagate their values.

    Returns:
        None.
    """
    Lottery.always_win()

    async def winner() -> str:
        """Return the selected async winner value.

        Returns:
            A stable winner result.
        """
        return "async win"

    assert await Lottery.odds(1, 1).winner(winner).choose_async() == (
        "async win"
    )


@pytest.mark.unit
@pytest.mark.anyio
async def test_choose_async_runs_callbacks_sequentially() -> None:
    """Return one awaited callback result for each requested draw.

    Returns:
        None.
    """
    Lottery.always_lose()
    expected_draws = 2
    calls = 0

    async def loser() -> str:
        """Increment the callback counter and return a stable result.

        Returns:
            The losing result.
        """
        nonlocal calls
        calls += 1
        return "async loss"

    results = await Lottery.odds(1, 1).loser(loser).choose_async(expected_draws)

    assert results == ["async loss"] * expected_draws
    assert calls == expected_draws


@pytest.mark.unit
@pytest.mark.anyio
async def test_choose_async_accepts_synchronous_callback_results() -> None:
    """Return ordinary values from callbacks through the explicit async API.

    Returns:
        None.
    """
    Lottery.always_win()

    assert await Lottery.odds(1, 1).winner(lambda: "sync").choose_async() == (
        "sync"
    )


@pytest.mark.unit
@pytest.mark.anyio
async def test_choose_async_returns_default_when_callbacks_are_unset() -> None:
    """Return the draw result when no callback is configured.

    Returns:
        None.
    """
    Lottery.always_win()

    assert await Lottery.odds(0, 1).choose_async() is True


@pytest.mark.unit
@pytest.mark.anyio
async def test_choose_async_propagates_cancellation() -> None:
    """Allow cancellation raised by an async callback to propagate.

    Returns:
        None.
    """
    Lottery.always_win()

    async def cancel() -> None:
        """Raise the cancellation exception immediately.

        Raises:
            asyncio.CancelledError: Always.
        """
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await Lottery.odds(1, 1).winner(cancel).choose_async()


@pytest.mark.unit
def test_sync_choose_rejects_awaitable_callbacks() -> None:
    """Reject an async callback passed to the synchronous invocation API.

    Returns:
        None.
    """
    Lottery.always_win()

    async def callback() -> str:
        """Provide a coroutine that must be explicitly awaited.

        Returns:
            A stable result.
        """
        return "not awaited"

    with pytest.raises(TypeError, match="choose_async"):
        Lottery.odds(1, 1).winner(callback).choose()
