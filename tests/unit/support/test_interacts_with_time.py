"""Verify time calculations and runtime formatting for Support mixins.

Cover epoch deadlines, timedelta conversion, time injection, and source
compatible method aliases.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import titanspan.support.interacts_with_time as time_module
from titanspan.support import InteractsWithTime

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
_NAIVE = _NOW.replace(tzinfo=None)
_POSITIVE_DELAY = 12
_NEGATIVE_DELAY = -3
_FUTURE_SECONDS = 10
_INTERVAL_SECONDS = 15
_NEGATIVE_INTERVAL = -2
_NEGATIVE_AVAILABILITY = -5
_MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000
_MILLISECONDS_PER_WEEK = _MILLISECONDS_PER_DAY * 7
_MILLISECONDS_PER_MONTH = _MILLISECONDS_PER_WEEK * 4
_MILLISECONDS_PER_YEAR = _MILLISECONDS_PER_MONTH * 12


class _FixedClock(InteractsWithTime):
    """Provide a deterministic aware datetime for time-dependent methods.

    Args:
        now: The fixed instant returned by the clock hook.
    """

    def __init__(self, now: datetime = _NOW) -> None:
        """Store a fixed point in time for deterministic assertions.

        Args:
            now: The fixed instant returned by the clock hook.
        """
        self.now = now

    def _now_datetime(self) -> datetime:
        """Return the fixed instant used by inherited calculations.

        Returns:
            The test clock's timezone-aware current instant.
        """
        return self.now


def test_seconds_until_preserves_integer_delays() -> None:
    """Return integer delays unchanged, including negative values.

    Integer delays are not clamped by the upstream trait.
    """
    clock = _FixedClock()

    assert clock.seconds_until(_POSITIVE_DELAY) == _POSITIVE_DELAY
    assert clock.seconds_until(_NEGATIVE_DELAY) == _NEGATIVE_DELAY


def test_seconds_until_clamps_past_datetime_to_zero() -> None:
    """Clamp expired datetime deadlines but retain future epoch seconds.

    This matches the upstream distinction between integer and date delays.
    """
    clock = _FixedClock()
    past = _NOW - timedelta(seconds=2)
    future = _NOW + timedelta(seconds=_FUTURE_SECONDS)

    assert clock.seconds_until(past) == 0
    assert clock.seconds_until(future) == _FUTURE_SECONDS


def test_parse_date_interval_uses_fixed_clock_for_timedeltas() -> None:
    """Convert durations into an absolute aware datetime using the clock.

    Integer inputs remain integer delays after parsing.
    """
    clock = _FixedClock()

    assert clock.parse_date_interval(timedelta(seconds=3)) == (
        _NOW + timedelta(seconds=3)
    )
    assert clock.parse_date_interval(_NEGATIVE_INTERVAL) == (_NEGATIVE_INTERVAL)
    assert clock.parse_date_interval(True) == 1


def test_parse_date_interval_rejects_unsupported_runtime_values() -> None:
    """Reject values outside the typed delay contract at runtime.

    This protects callers that receive values from untyped boundaries.
    """
    with pytest.raises(TypeError, match="delay must be"):
        _FixedClock().parse_date_interval(1.5)


def test_seconds_until_accepts_timedelta_deadlines() -> None:
    """Resolve timedelta inputs relative to the active clock instant.

    The resulting whole seconds are measured against the fixed clock.
    """
    assert (
        _FixedClock().seconds_until(timedelta(seconds=_INTERVAL_SECONDS))
        == _INTERVAL_SECONDS
    )


def test_available_at_adds_integer_and_timedelta_delays() -> None:
    """Return Unix deadlines for numeric and duration delays.

    Negative delays remain valid and identify earlier availability times.
    """
    clock = _FixedClock()
    now_timestamp = int(_NOW.timestamp())

    assert clock.available_at() == now_timestamp
    assert clock.available_at(20) == now_timestamp + 20
    assert (
        clock.available_at(_NEGATIVE_AVAILABILITY)
        == now_timestamp + _NEGATIVE_AVAILABILITY
    )
    assert clock.available_at(timedelta(seconds=8)) == now_timestamp + 8


def test_available_at_returns_datetime_timestamp_without_rebasing() -> None:
    """Preserve an absolute datetime rather than adding it to current time.

    Timestamp conversion discards sub-second precision at the API boundary.
    """
    deadline = _NOW + timedelta(days=1, microseconds=500)

    assert _FixedClock().available_at(deadline) == int(deadline.timestamp())


def test_current_time_aliases_return_the_clock_timestamp() -> None:
    """Expose the source-compatible method alias over the injected clock.

    Both method names return the same whole-second epoch value.
    """
    clock = _FixedClock()
    expected = int(_NOW.timestamp())

    assert clock.current_time() == expected
    assert clock.currentTime() == expected


def test_default_clock_returns_current_epoch_seconds() -> None:
    """Use the system clock when a subclass supplies no clock hook.

    The immediate before-and-after bounds avoid timing-sensitive sleeps.
    """
    before = int(time_module.time.time())
    current = InteractsWithTime().current_time()
    after = int(time_module.time.time())

    assert before <= current <= after


def test_time_methods_reject_naive_datetime_values() -> None:
    """Reject ambiguous local datetimes instead of guessing a timezone.

    Absolute dates must have an explicit offset before conversion to epoch
    seconds.
    """
    with pytest.raises(ValueError, match="timezone-aware"):
        _FixedClock().seconds_until(_NAIVE)

    with pytest.raises(ValueError, match="timezone-aware"):
        _FixedClock().available_at(_NAIVE)


@pytest.mark.parametrize(
    ("milliseconds", "expected"),
    [
        (0.1, "0.10ms"),
        (999.995, "1,000.00ms"),
        (1000.0, "1,000.00ms"),
        (1001.0, "1s"),
        (1999.0, "1s"),
        (2000.0, "2s"),
        (61_000.0, "1m 1s"),
        (3_661_000.0, "1h 1m 1s"),
        (_MILLISECONDS_PER_DAY, "1d"),
        (_MILLISECONDS_PER_WEEK, "1w"),
        (_MILLISECONDS_PER_MONTH, "1mo"),
        (_MILLISECONDS_PER_MONTH * 2, "2mos"),
        (_MILLISECONDS_PER_YEAR, "1y"),
    ],
)
def test_runtime_for_humans_formats_elapsed_milliseconds(
    milliseconds: float,
    expected: str,
) -> None:
    """Format short runtimes as milliseconds and longer values as units.

    Args:
        milliseconds: Elapsed time supplied as start and end timestamps.
        expected: The abbreviated human-readable runtime.
    """
    assert (
        _FixedClock().run_time_for_humans(
            0.0,
            milliseconds / 1000,
        )
        == expected
    )


def test_runtime_for_humans_uses_current_time_when_end_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the current wall-clock timestamp for an omitted end value.

    The patched wall clock makes the test independent of elapsed real time.
    """
    monkeypatch.setattr(time_module.time, "time", lambda: 10.5)

    assert _FixedClock().run_time_for_humans(10.0) == "500.00ms"


@pytest.mark.parametrize(
    ("start_time", "end_time"),
    [
        (float("nan"), 0.0),
        (0.0, float("inf")),
        (1e308, -1e308),
    ],
)
def test_runtime_for_humans_rejects_nonfinite_durations(
    start_time: float,
    end_time: float,
) -> None:
    """Reject timestamps whose subtraction yields a nonfinite duration.

    Args:
        start_time: The operation's starting Unix timestamp.
        end_time: The operation's ending Unix timestamp.
    """
    with pytest.raises(ValueError, match="finite duration"):
        _FixedClock().run_time_for_humans(start_time, end_time)


def test_camel_case_time_aliases_share_python_implementations() -> None:
    """Expose all source-compatible spellings on the mixin.

    Each alias returns the same value as its Python-named implementation.
    """
    clock = _FixedClock()

    assert clock.secondsUntil(4) == clock.seconds_until(4)
    assert clock.availableAt(4) == clock.available_at(4)
    assert clock.parseDateInterval(-1) == clock.parse_date_interval(-1)
    assert clock.runTimeForHumans(1.0, 1.5) == "500.00ms"
