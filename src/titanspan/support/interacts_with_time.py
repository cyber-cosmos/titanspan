"""Provide epoch deadline and elapsed-time helpers.

This mixin adapts Illuminate's InteractsWithTime trait to aware Python
datetimes and ``timedelta`` values without changing process-wide clocks.
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

type _Delay = datetime | timedelta | int
type _ParsedDelay = datetime | int
_TIMEZONE_ERROR = "datetime values must be timezone-aware"
_DELAY_TYPE_ERROR = "delay must be datetime, timedelta, or integer seconds"
_ELAPSED_TIME_ERROR = "start and end times must produce a finite duration"

_MILLISECONDS_PER_SECOND = 1_000
_SECONDS_PER_MINUTE = 60
_MINUTES_PER_HOUR = 60
_HOURS_PER_DAY = 24
_DAYS_PER_WEEK = 7
_WEEKS_PER_MONTH = 4
_MONTHS_PER_YEAR = 12

_MILLISECONDS_PER_MINUTE = _MILLISECONDS_PER_SECOND * _SECONDS_PER_MINUTE
_MILLISECONDS_PER_HOUR = _MILLISECONDS_PER_MINUTE * _MINUTES_PER_HOUR
_MILLISECONDS_PER_DAY = _MILLISECONDS_PER_HOUR * _HOURS_PER_DAY
_MILLISECONDS_PER_WEEK = _MILLISECONDS_PER_DAY * _DAYS_PER_WEEK
_MILLISECONDS_PER_MONTH = _MILLISECONDS_PER_WEEK * _WEEKS_PER_MONTH
_MILLISECONDS_PER_YEAR = _MILLISECONDS_PER_MONTH * _MONTHS_PER_YEAR


class InteractsWithTime:
    """Calculate relative deadlines and format elapsed wall-clock time.

    Use this mixin to convert integer delays or ``timedelta`` values to Unix
    timestamps. Subclasses can override :meth:`_now_datetime` to supply a
    deterministic clock for tests or application-specific time sources.

    Notes:
        Python ``timedelta`` has no calendar months or years. Longer
        human-readable durations use Carbon's default 4-week month and
        12-month year cascade. Naive datetimes are rejected because their
        Unix timestamp depends on the host's local timezone.
    """

    def seconds_until(self, delay: _Delay) -> int:
        """Return whole seconds until a datetime or the integer delay.

        Args:
            delay: An aware deadline, a duration, or integer seconds.

        Returns:
            Seconds remaining for an absolute datetime, clamped at zero;
            integer delays are returned unchanged.

        Raises:
            TypeError: If the delay is not a supported value.
            ValueError: If an absolute datetime is naive.
            OverflowError: If adding a duration exceeds datetime limits.
        """
        parsed = self.parse_date_interval(delay)
        if isinstance(parsed, datetime):
            remaining = math.floor(parsed.timestamp()) - self.current_time()
            return max(0, remaining)
        return parsed

    def available_at(self, delay: _Delay = 0) -> int:
        """Return the Unix timestamp when a delay becomes available.

        Args:
            delay: An aware absolute deadline, duration, or integer seconds.

        Returns:
            The whole-second Unix timestamp for the deadline.

        Raises:
            TypeError: If the delay is not a supported value.
            ValueError: If an absolute datetime is naive.
            OverflowError: If adding a duration exceeds datetime limits.
        """
        parsed = self.parse_date_interval(delay)
        if isinstance(parsed, datetime):
            return math.floor(parsed.timestamp())

        deadline = self._now_datetime() + timedelta(seconds=parsed)
        return math.floor(deadline.timestamp())

    def parse_date_interval(self, delay: object) -> _ParsedDelay:
        """Convert a duration to an absolute time while retaining other forms.

        Args:
            delay: An aware datetime, duration, or integer seconds.

        Returns:
            An aware datetime for durations, the original aware datetime, or
            integer seconds for numeric delays.

        Raises:
            TypeError: If the delay is not a supported value.
            ValueError: If a datetime is naive.
            OverflowError: If adding a duration exceeds datetime limits.
        """
        if isinstance(delay, datetime):
            self._require_aware(delay)
            return delay
        if isinstance(delay, timedelta):
            return self._now_datetime() + delay
        if isinstance(delay, int):
            return int(delay)
        raise TypeError(_DELAY_TYPE_ERROR)

    def current_time(self) -> int:
        """Return current wall-clock time as whole Unix seconds.

        Returns:
            The current epoch timestamp rounded down to a whole second.
        """
        return math.floor(self._now_datetime().timestamp())

    def run_time_for_humans(
        self,
        start_time: float,
        end_time: float | None = None,
    ) -> str:
        """Format elapsed wall-clock time in milliseconds or short units.

        Args:
            start_time: Start timestamp in Unix seconds.
            end_time: End timestamp in Unix seconds, or current time when
                omitted.

        Returns:
            Milliseconds with two decimal places for durations up to one
            second; otherwise, a space-separated short duration.

        Notes:
            This compatibility helper uses wall-clock timestamps like the
            upstream API. Use a monotonic clock for new elapsed-time measures.
        """
        end = time.time() if end_time is None else end_time
        milliseconds = (end - start_time) * _MILLISECONDS_PER_SECOND
        if not math.isfinite(milliseconds):
            raise ValueError(_ELAPSED_TIME_ERROR)
        if milliseconds > _MILLISECONDS_PER_SECOND:
            return _format_short_duration(milliseconds)
        return _format_milliseconds(milliseconds)

    def _now_datetime(self) -> datetime:
        """Return the current timezone-aware UTC instant.

        Returns:
            The current wall-clock value in UTC.

        Notes:
            Override this method in deterministic test or clock adapters.
        """
        return datetime.now(UTC)

    @staticmethod
    def _require_aware(value: datetime) -> None:
        """Reject datetimes whose Unix timestamps depend on host settings.

        Args:
            value: The datetime value to validate.

        Raises:
            ValueError: If the value does not contain a usable timezone.
        """
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(_TIMEZONE_ERROR)

    # Keep the original Illuminate method names as explicit aliases.
    secondsUntil = seconds_until
    availableAt = available_at
    parseDateInterval = parse_date_interval
    currentTime = current_time
    runTimeForHumans = run_time_for_humans


def _format_milliseconds(milliseconds: float) -> str:
    """Format short elapsed durations with PHP-like half-up rounding.

    Args:
        milliseconds: Elapsed duration in milliseconds.

    Returns:
        A grouped numeric value with exactly two fractional digits.
    """
    rounded = Decimal(str(milliseconds)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    return f"{rounded:,.2f}ms"


def _format_short_duration(milliseconds: float) -> str:
    """Cascade a positive duration into short Carbon-style time units.

    Args:
        milliseconds: A duration greater than one second.

    Returns:
        Non-zero years through seconds, joined by single spaces.

    Notes:
        Carbon's default cascade treats a month as four weeks and a year as
        twelve months. Millisecond remainders are omitted by its default
        minimum display unit of seconds.
    """
    remaining = math.floor(milliseconds)
    units = (
        ("y", _MILLISECONDS_PER_YEAR),
        ("mo", _MILLISECONDS_PER_MONTH),
        ("w", _MILLISECONDS_PER_WEEK),
        ("d", _MILLISECONDS_PER_DAY),
        ("h", _MILLISECONDS_PER_HOUR),
        ("m", _MILLISECONDS_PER_MINUTE),
        ("s", _MILLISECONDS_PER_SECOND),
    )
    parts: list[str] = []
    for symbol, unit_size in units:
        count, remaining = divmod(remaining, unit_size)
        if count:
            suffix = "s" if symbol == "mo" and count != 1 else ""
            parts.append(f"{count}{symbol}{suffix}")
    return " ".join(parts)


__all__ = ["InteractsWithTime"]
