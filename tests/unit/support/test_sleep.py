"""Verify Laravel-inspired sleep builders and context-local test fakes.

Tests replace real waiting with fakes unless they explicitly verify AnyIO
task scheduling in the integration suite.
"""

from __future__ import annotations

import asyncio
import math
from contextvars import Context
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import pytest

import titanspan.support.sleep as sleep_module
from titanspan.support import Sleep

EXPECTED_REPEAT_CALLBACKS = 3

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


@pytest.fixture(autouse=True)
def reset_sleep_fake() -> Iterator[None]:
    """Reset context-local fake state around every test.

    Yields:
        None after installing real sleep behavior.
    """
    Sleep.fake(False)
    yield
    Sleep.fake(False)


@pytest.mark.unit
def test_duration_builder_supports_all_units_and_chaining() -> None:
    """Accumulate minute, second, millisecond, and microsecond units.

    Returns:
        None.
    """
    sleep = (
        Sleep.for_(1.5)
        .minutes()
        .and_(3)
        .seconds()
        .and_(250)
        .milliseconds()
        .and_(500)
        .microseconds()
    )

    assert sleep.duration == timedelta(seconds=93, microseconds=250_500)


@pytest.mark.unit
def test_singular_units_and_static_factories_match_plural_units() -> None:
    """Expose singular aliases and factory shortcuts for duration units.

    Returns:
        None.
    """
    assert Sleep.for_(1).minute().duration == timedelta(minutes=1)
    assert Sleep.for_(1).second().duration == timedelta(seconds=1)
    assert Sleep.for_(1).millisecond().duration == timedelta(milliseconds=1)
    assert Sleep.for_(1).microsecond().duration == timedelta(microseconds=1)
    assert Sleep.sleep(3).duration == timedelta(seconds=3)
    assert Sleep.usleep(3).duration == timedelta(microseconds=3)


@pytest.mark.unit
def test_fractional_microseconds_truncate_to_python_time_resolution() -> None:
    """Keep CarbonInterval's truncation at the smallest supported unit.

    Returns:
        None.
    """
    assert Sleep.for_(1.9).microseconds().duration == timedelta(microseconds=1)


@pytest.mark.unit
@pytest.mark.parametrize("duration", [True, "1", math.inf, math.nan])
def test_constructor_rejects_unsupported_duration_values(
    duration: object,
) -> None:
    """Reject booleans, strings, and non-finite numeric durations.

    Args:
        duration: The invalid value to provide to the constructor.

    Returns:
        None.
    """
    with pytest.raises((TypeError, ValueError)):
        Sleep(cast("int", duration))


@pytest.mark.unit
def test_negative_duration_is_clamped_to_zero() -> None:
    """Preserve Laravel's non-blocking behavior for negative durations.

    Returns:
        None.
    """
    assert Sleep.for_(-1).seconds().duration == timedelta(0)


@pytest.mark.unit
def test_duration_overflow_is_reported_before_execution() -> None:
    """Report values that cannot be represented by timedelta.

    Returns:
        None.
    """
    with pytest.raises(OverflowError, match="timedelta limits"):
        Sleep.for_(10**30).seconds()
    with pytest.raises(OverflowError, match="timedelta limits"):
        Sleep.for_(1e308).minutes()


@pytest.mark.unit
def test_timestamp_factory_uses_an_injected_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compute numeric timestamp waits without consulting wall-clock time.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    monkeypatch.setattr(sleep_module.time, "time", lambda: 100.0)

    assert Sleep.until(103.25).duration == timedelta(
        seconds=3,
        microseconds=250_000,
    )
    assert Sleep.until("99.5").duration == timedelta(0)
    assert Sleep.until(103.25, now=100).duration == timedelta(
        seconds=3,
        microseconds=250_000,
    )
    assert Sleep.until(103.25, now=100.0).duration == timedelta(
        seconds=3,
        microseconds=250_000,
    )
    clock_datetime = datetime(1970, 1, 1, 0, 1, 40, tzinfo=UTC)
    assert Sleep.until(103.25, now=clock_datetime).duration == timedelta(
        seconds=3,
        microseconds=250_000,
    )


@pytest.mark.unit
def test_until_rejects_boolean_timestamps() -> None:
    """Reject booleans instead of treating them as integer timestamps.

    Returns:
        None.
    """
    with pytest.raises(TypeError, match="timestamp"):
        Sleep.until(True)


@pytest.mark.unit
@pytest.mark.parametrize(
    "timestamp",
    ["not-a-timestamp", math.inf, math.nan, 10**400],
)
def test_until_rejects_invalid_numeric_timestamps(timestamp: object) -> None:
    """Reject unparsable and out-of-range timestamp values.

    Args:
        timestamp: An invalid or non-finite target time.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="timestamp"):
        Sleep.until(cast("float", timestamp))


@pytest.mark.unit
@pytest.mark.parametrize("now", [True, "100", math.inf, 10**400])
def test_until_rejects_invalid_numeric_clocks(now: object) -> None:
    """Reject invalid, non-finite, and overflowing injected clocks.

    Args:
        now: An invalid injected Unix timestamp.

    Returns:
        None.
    """
    with pytest.raises((TypeError, ValueError)):
        Sleep.until(103.25, now=cast("int", now))


@pytest.mark.unit
def test_datetime_until_preserves_timezone_semantics() -> None:
    """Compute a wait from timezone-aware Python datetime values.

    Returns:
        None.
    """
    now = datetime(2026, 1, 1, tzinfo=UTC)
    target = datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC)

    assert Sleep.until(target, now=now).duration == timedelta(seconds=2)


@pytest.mark.unit
def test_datetime_until_rejects_mismatched_timezones() -> None:
    """Report naive and timezone-aware datetime subtraction errors.

    Returns:
        None.
    """
    aware_target = datetime(2026, 1, 1, tzinfo=UTC)
    naive_now = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)

    with pytest.raises(ValueError, match="compatible timezones"):
        Sleep.until(aware_target, now=naive_now)

    with pytest.raises(TypeError, match="datetime for datetime targets"):
        Sleep.until(aware_target, now=0.0)


@pytest.mark.unit
def test_datetime_until_uses_the_system_clock_when_not_injected() -> None:
    """Resolve a target datetime using its timezone-aware current clock.

    Returns:
        None.
    """
    target = datetime.now(UTC) + timedelta(days=1)

    assert Sleep.until(target).duration > timedelta(days=1) - timedelta(
        seconds=1
    )


@pytest.mark.unit
def test_unknown_duration_unit_raises_before_sleeping() -> None:
    """Reject execution when a numeric value has no declared unit.

    Returns:
        None.
    """
    with pytest.raises(RuntimeError, match="Unknown duration unit"):
        Sleep.for_(5).sleep_sync()


@pytest.mark.unit
def test_duration_accessors_raise_when_no_unit_was_set() -> None:
    """Reject a unit addition when no numeric duration is pending.

    Returns:
        None.
    """
    with pytest.raises(RuntimeError, match="No duration specified"):
        Sleep(timedelta(seconds=1)).seconds()


@pytest.mark.unit
def test_duration_builder_accepts_and_clamps_timedelta_instances() -> None:
    """Use timedelta inputs as completed durations and clamp negatives.

    Returns:
        None.
    """
    assert Sleep.for_(timedelta(seconds=2)).duration == timedelta(seconds=2)
    assert Sleep.for_(timedelta(seconds=-2)).duration == timedelta(0)


@pytest.mark.unit
def test_public_duration_and_repeat_properties_can_be_replaced() -> None:
    """Keep upstream public property mutation available in Python form.

    Returns:
        None.
    """
    sleep = Sleep.for_(1)
    sleep.duration = timedelta(seconds=2)
    assert sleep.seconds().duration == timedelta(seconds=3)

    def should_repeat() -> bool:
        """Provide a repeat callback for the public property.

        Returns:
            False to complete after one evaluation.
        """
        return False

    sleep.while_callback = should_repeat
    assert sleep.while_callback is should_repeat
    sleep.while_callback = None
    assert sleep.while_callback is None
    sleep.duration = timedelta(seconds=-1)
    assert sleep.duration == timedelta(0)

    with pytest.raises(TypeError, match=r"datetime\.timedelta"):
        sleep.duration = cast("timedelta", "1")
    with pytest.raises(TypeError, match="while callback"):
        sleep.while_callback = cast("Callable[[], object]", 1)


@pytest.mark.unit
def test_explicit_sleep_fake_records_duration_without_blocking() -> None:
    """Require explicit execution while letting tests capture fake sleeps.

    Returns:
        None.
    """
    Sleep.fake()
    sleep = Sleep.for_(5).seconds()

    sleep.sleep_sync()
    Sleep.assertSlept(lambda duration: duration == timedelta(seconds=5))
    Sleep.assertSleptTimes(1)
    Sleep.assertSequence([Sleep.for_(5).seconds()])


@pytest.mark.unit
def test_sleep_fake_aliases_and_callback_property_are_context_local() -> None:
    """Expose Laravel spellings while isolating independent contexts.

    Returns:
        None.
    """
    Sleep.fake()
    observed: list[timedelta] = []

    def record(duration: timedelta) -> None:
        """Capture each fake duration in the active test context.

        Args:
            duration: The duration recorded by a fake sleep.

        Returns:
            None.
        """
        observed.append(duration)

    Sleep.whenFakingSleep(record)
    Sleep.fakeSleepCallbacks.append(record)
    Sleep.for_(2).seconds().sleep_sync()

    assert observed == [timedelta(seconds=2), timedelta(seconds=2)]
    other_context = Context()
    assert other_context.run(lambda: Sleep.fake_sleep_callbacks) == []

    callbacks: list[Callable[[timedelta], object]] = [record]
    Sleep.fakeSleepCallbacks = callbacks
    assert Sleep.fake_sleep_callbacks == [record]
    Sleep.fake_sleep_callbacks = []
    assert Sleep.fakeSleepCallbacks == []


@pytest.mark.unit
def test_assertions_report_sleep_count_duration_and_insomniac_state() -> None:
    """Verify count, duration, zero-duration, and no-sleep assertions.

    Returns:
        None.
    """
    Sleep.fake()
    Sleep.assertNeverSlept()
    Sleep.assertInsomniac()
    Sleep.for_(0).seconds().sleep_sync()
    Sleep.assertInsomniac()
    Sleep.assertSleptTimes(1)
    Sleep.assert_slept(
        lambda duration: duration == timedelta(0),
        times=1,
    )
    Sleep.for_(1).seconds().sleep_sync()

    with pytest.raises(AssertionError, match="Unexpected sleep"):
        Sleep.assertInsomniac()


@pytest.mark.unit
def test_assert_slept_supports_durations_builders_and_mismatch_counts() -> None:
    """Match recorded values through the public assertion forms.

    Returns:
        None.
    """
    Sleep.fake()
    Sleep.for_(2).seconds().sleep_sync()

    Sleep.assert_slept(timedelta(seconds=2))
    Sleep.assert_slept(Sleep.for_(2).seconds())
    with pytest.raises(AssertionError, match="Expected sleep match"):
        Sleep.assert_slept(timedelta(seconds=2), times=2)


@pytest.mark.unit
def test_sleep_assertions_reject_invalid_counts() -> None:
    """Reject negative, boolean, and non-integer assertion counts.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="non-negative integer"):
        Sleep.assert_slept_times(-1)
    with pytest.raises(ValueError, match="non-negative integer"):
        Sleep.assert_slept_times(cast("int", True))
    with pytest.raises(ValueError, match="non-negative integer"):
        Sleep.assert_slept(Sleep.for_(0).seconds(), times=cast("int", 1.5))
    with pytest.raises(TypeError, match="boolean"):
        Sleep.fake(cast("bool", 1))
    with pytest.raises(AssertionError, match=r"Expected \[1\] sleeps"):
        Sleep.assertSleptTimes(1)


@pytest.mark.unit
def test_assert_sequence_checks_count_and_skips_none_entries() -> None:
    """Check sequence lengths and permit explicit skipped comparisons.

    Returns:
        None.
    """
    Sleep.fake()
    Sleep.for_(1).seconds().sleep_sync()
    Sleep.assert_sequence([None])

    expected = [Sleep.for_(1).seconds(), Sleep.for_(1).seconds()]
    with pytest.raises(AssertionError, match=r"Expected \[2\] sleeps"):
        Sleep.assert_sequence(expected)
    expected[0].sleep_sync()
    Sleep.assertSleptTimes(1)


@pytest.mark.unit
def test_assert_sequence_cleans_expected_builders_on_failure() -> None:
    """Avoid executing expected builders after a failed sequence check.

    Returns:
        None.
    """
    Sleep.fake()
    Sleep.for_(1).seconds().sleep_sync()
    expected = Sleep.for_(2).seconds()

    with pytest.raises(AssertionError, match="Expected sleep duration"):
        Sleep.assertSequence([expected])

    assert expected.sleep_sync() is None
    Sleep.assertSleptTimes(1)


@pytest.mark.unit
def test_while_callback_controls_repeat_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeat synchronous waits while the callback says to continue.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    waits: list[float] = []
    monkeypatch.setattr(sleep_module.time, "sleep", waits.append)
    outcomes = iter([True, True, False])
    sleep = Sleep.for_(1).milliseconds().while_(lambda: next(outcomes))

    sleep.sleep_sync()

    assert waits == [0.001, 0.001]
    assert sleep.while_callback is not None


@pytest.mark.unit
def test_zero_duration_and_false_repeat_predicate_never_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avoid calling the blocking sleep function for zero durations.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    waits: list[float] = []
    monkeypatch.setattr(sleep_module.time, "sleep", waits.append)

    Sleep.for_(0).seconds().sleep_sync()
    Sleep.for_(0).seconds().while_(lambda: False).sleep_sync()
    outcomes = iter([True, False])
    Sleep.for_(0).seconds().while_(lambda: next(outcomes)).sleep_sync()

    assert waits == []


@pytest.mark.unit
def test_while_builders_reject_non_callable_values() -> None:
    """Validate sync and async callback registrations at runtime.

    Returns:
        None.
    """
    invalid_callback = cast("Callable[[], object]", 1)

    with pytest.raises(TypeError, match="while callback"):
        Sleep.for_(1).milliseconds().while_(invalid_callback)
    with pytest.raises(TypeError, match="while callback"):
        Sleep.for_(1).milliseconds().while_async(invalid_callback)


@pytest.mark.unit
def test_fake_sleep_skips_while_callback_and_records_once() -> None:
    """Match Laravel fake semantics without executing repeat predicates.

    Returns:
        None.
    """
    Sleep.fake()
    while_called = False

    def should_repeat() -> bool:
        """Record whether the repeat predicate was invoked.

        Returns:
            False to prevent a repeated sleep if evaluated.
        """
        nonlocal while_called
        while_called = True
        return False

    Sleep.for_(1).milliseconds().while_(should_repeat).sleep_sync()

    assert not while_called
    Sleep.assertSleptTimes(1)


@pytest.mark.unit
def test_condition_methods_skip_or_enable_sleep() -> None:
    """Apply boolean and callback conditions before explicit execution.

    Returns:
        None.
    """
    Sleep.fake()
    Sleep.for_(1).second().when(False).sleep_sync()
    Sleep.for_(1).second().when(lambda _sleep: True).sleep_sync()
    Sleep.for_(1).second().unless(True).sleep_sync()
    Sleep.for_(1).second().unless(lambda _sleep: False).sleep_sync()

    Sleep.assertSleptTimes(2)


@pytest.mark.unit
def test_sync_condition_rejects_awaitable_callbacks() -> None:
    """Require async conditions to use an explicit async builder method.

    Returns:
        None.
    """

    async def condition(_sleep: Sleep) -> bool:
        """Return a condition value for the synchronous rejection test.

        Args:
            _sleep: The builder passed to a condition callback.

        Returns:
            A true condition result.
        """
        return True

    with pytest.raises(TypeError, match="use sleep_async"):
        Sleep.for_(0).seconds().when(condition)


@pytest.mark.unit
@pytest.mark.anyio
async def test_sync_condition_rejects_non_coroutine_awaitables() -> None:
    """Reject futures from sync conditions without taking ownership of them.

    Returns:
        None.
    """
    future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

    def condition(_sleep: Sleep) -> object:
        """Return the caller-owned future for rejection.

        Args:
            _sleep: The builder passed to a condition callback.

        Returns:
            The future that the synchronous condition must reject.
        """
        return future

    with pytest.raises(TypeError, match="use sleep_async"):
        Sleep.for_(0).seconds().when(condition)
    future.cancel()


@pytest.mark.unit
def test_then_executes_after_sync_sleep_and_does_not_sleep_twice() -> None:
    """Return the callback result after one explicit synchronous sleep.

    Returns:
        None.
    """
    Sleep.fake()
    sleep = Sleep.for_(1).second()

    assert sleep.then(lambda: "finished") == "finished"
    sleep.sleep_sync()
    Sleep.assertSleptTimes(1)


@pytest.mark.unit
def test_sync_sleep_uses_time_module_for_real_waits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delegate non-faked waits to the synchronous standard library.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    waits: list[float] = []
    monkeypatch.setattr(sleep_module.time, "sleep", waits.append)

    Sleep.for_(1.5).seconds().sleep_sync()

    assert waits == [1.5]


@pytest.mark.unit
@pytest.mark.anyio
async def test_async_sleep_uses_anyio_and_awaits_fake_callbacks() -> None:
    """Await AnyIO sleeps and fake callbacks without blocking the loop.

    Returns:
        None.
    """
    Sleep.fake()
    observed: list[timedelta] = []

    async def record(duration: timedelta) -> None:
        """Capture one fake asynchronous duration.

        Args:
            duration: The duration recorded by the fake sleep.

        Returns:
            None.
        """
        observed.append(duration)

    Sleep.when_faking_sleep(record)
    await Sleep.for_(3).milliseconds().sleep_async()

    assert observed == [timedelta(milliseconds=3)]
    Sleep.assert_slept_times(1)


@pytest.mark.unit
@pytest.mark.anyio
async def test_async_fake_sleep_invokes_synchronous_callbacks() -> None:
    """Invoke synchronous callback registrations during async fake waits.

    Returns:
        None.
    """
    Sleep.fake()
    observed: list[timedelta] = []

    def record(duration: timedelta) -> None:
        """Capture a fake duration without returning an awaitable.

        Args:
            duration: The duration recorded by the fake sleep.

        Returns:
            None.
        """
        observed.append(duration)

    Sleep.when_faking_sleep(record)
    await Sleep.for_(2).milliseconds().sleep_async()

    assert observed == [timedelta(milliseconds=2)]


@pytest.mark.unit
@pytest.mark.anyio
async def test_async_fake_sleep_skips_while_callback_and_records_once() -> None:
    """Keep async fake recording separate from real-wait predicates.

    Returns:
        None.
    """
    Sleep.fake()
    while_called = False

    async def should_repeat() -> bool:
        """Record whether the async predicate was evaluated.

        Returns:
            False to prevent a repeated sleep if evaluated.
        """
        nonlocal while_called
        while_called = True
        return False

    await Sleep.for_(1).milliseconds().while_async(should_repeat).sleep_async()

    assert not while_called
    Sleep.assert_slept_times(1)


@pytest.mark.unit
@pytest.mark.anyio
async def test_then_async_awaits_callback_after_sleep() -> None:
    """Await callback results from the explicit asynchronous chain.

    Returns:
        None.
    """
    Sleep.fake()

    async def callback() -> str:
        """Return a stable value after the fake wait.

        Returns:
            A callback result.
        """
        return "finished"

    result = await Sleep.for_(1).second().then_async(callback)

    assert result == "finished"
    Sleep.assert_slept_times(1)


@pytest.mark.unit
@pytest.mark.anyio
async def test_async_conditions_are_explicitly_awaited() -> None:
    """Await async condition callbacks before deciding whether to sleep.

    Returns:
        None.
    """
    Sleep.fake()

    async def condition(_sleep: Sleep) -> bool:
        """Return a false condition after an async boundary.

        Args:
            _sleep: The builder passed to a condition callback.

        Returns:
            A false condition result.
        """
        return False

    skipped = await Sleep.for_(1).seconds().when_async(condition)
    await skipped.sleep_async()

    executed = await Sleep.for_(1).seconds().unless_async(condition)
    await executed.sleep_async()

    direct = await Sleep.for_(1).seconds().when_async(True)
    await direct.sleep_async()
    direct_unless = await Sleep.for_(1).seconds().unless_async(False)
    await direct_unless.sleep_async()

    Sleep.assert_slept_times(3)


@pytest.mark.unit
@pytest.mark.anyio
async def test_async_while_callback_controls_repeat_count() -> None:
    """Await a repetition predicate between zero-duration AnyIO waits.

    Returns:
        None.
    """
    outcomes = iter([True, True, False])
    callback_calls = 0

    async def should_repeat() -> bool:
        """Return the next deterministic repetition result.

        Returns:
            Whether another fake sleep should be recorded.
        """
        nonlocal callback_calls
        callback_calls += 1
        return next(outcomes)

    await Sleep.for_(0).seconds().while_async(should_repeat).sleep_async()

    assert callback_calls == EXPECTED_REPEAT_CALLBACKS

    sync_outcomes = iter([False])
    await (
        Sleep.for_(0)
        .seconds()
        .while_(lambda: next(sync_outcomes))
        .sleep_async()
    )
