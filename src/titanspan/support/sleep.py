"""Build explicit synchronous or asynchronous sleep operations.

The fluent API follows Laravel's Support Sleep component. Python execution is
explicit rather than destructor-driven, and fake state is local to the active
execution context.
"""

from __future__ import annotations

import inspect
import math
import time
from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Self, TypeVar, cast

import anyio

from titanspan.support.macroable import Macroable

_T = TypeVar("_T")
type SleepFakeCallback = Callable[[timedelta], object]
type SleepWhileCallback = Callable[[], object]
type AsyncSleepWhileCallback = Callable[[], object | Awaitable[object]]
type SleepCondition = bool | Callable[[Sleep], object]
type AsyncSleepCondition = bool | Callable[[Sleep], object | Awaitable[object]]
_NO_DURATION_ERROR = "No duration specified."
_UNKNOWN_UNIT_ERROR = "Unknown duration unit."
_TIMESTAMP_TYPE_ERROR = "timestamp must be a datetime or Unix timestamp"
_TIMESTAMP_VALUE_ERROR = "timestamp must be finite and numeric"
_TIMESTAMP_TIMEZONE_ERROR = "timestamp and now must have compatible timezones"
_TIMESTAMP_NOW_TYPE_ERROR = "now must be a datetime or numeric timestamp"
_DATETIME_NOW_TYPE_ERROR = "now must be a datetime for datetime targets"
_DURATION_NUMBER_ERROR = "duration must be a finite number"
_DURATION_FINITE_ERROR = "duration must be finite"
_DURATION_PROPERTY_TYPE_ERROR = "duration must be datetime.timedelta"
_DURATION_OVERFLOW_ERROR = "duration exceeds datetime.timedelta limits"
_SLEEP_COUNT_ERROR = "expected sleep count must be a non-negative integer"
_FAKE_VALUE_TYPE_ERROR = "value must be a boolean"
_WHILE_CALLBACK_TYPE_ERROR = "while callback must be callable"
_MAX_DURATION_MICROSECONDS = (
    timedelta.max.days * 86_400 + timedelta.max.seconds
) * 1_000_000 + timedelta.max.microseconds
_ASYNC_CALLBACK_ERROR = (
    "synchronous sleep callbacks must not return awaitables; "
    "use sleep_async() or then_async()"
)


def _new_durations() -> list[timedelta]:
    """Create an independent record of fake sleep durations.

    Returns:
        A fresh list for one fake execution context.
    """
    return []


def _new_fake_callbacks() -> list[SleepFakeCallback]:
    """Create an independent callback registry for fake sleeps.

    Returns:
        A fresh callback list for one fake execution context.
    """
    return []


@dataclass(slots=True)
class _FakeState:
    """Hold fake settings and observations for one execution context.

    Attributes:
        enabled: Whether sleep operations should be recorded instead of run.
        durations: The ordered durations recorded by fake operations.
        callbacks: Callbacks invoked after recording a fake duration.
    """

    enabled: bool = False
    durations: list[timedelta] = field(default_factory=_new_durations)
    callbacks: list[SleepFakeCallback] = field(
        default_factory=_new_fake_callbacks
    )


_FAKE_STATE: ContextVar[_FakeState | None] = ContextVar(
    "titanspan_sleep_fake_state",
    default=None,
)


def _fake_state() -> _FakeState:
    """Return or create the fake state for the current context.

    Returns:
        Mutable fake controls scoped to this execution context.
    """
    state = _FAKE_STATE.get()
    if state is None:
        # A context-local holder prevents one test's fake from changing
        # the behavior of unrelated applications or concurrent requests.
        state = _FakeState()
        _FAKE_STATE.set(state)
    return state


class _SleepMeta(type):
    """Expose fake callback controls through class-level properties.

    The properties resolve their values from the currently active context
    so callers can use Laravel's static-style testing API without sharing
    a process-global mutable callback registry.
    """

    @property
    def fake_sleep_callbacks(cls) -> list[SleepFakeCallback]:
        """Return callbacks registered for the active fake context.

        Returns:
            The mutable callback list used by fake sleep operations.
        """
        return _fake_state().callbacks

    @fake_sleep_callbacks.setter
    def fake_sleep_callbacks(cls, callbacks: list[SleepFakeCallback]) -> None:
        """Replace the active context's fake callback list.

        Args:
            callbacks: The replacement callback collection.
        """
        _fake_state().callbacks = list(callbacks)

    @property
    def fakeSleepCallbacks(cls) -> list[SleepFakeCallback]:
        """Expose Laravel's camelCase callback property.

        Returns:
            The mutable callback list used by fake sleep operations.
        """
        return _fake_state().callbacks

    @fakeSleepCallbacks.setter
    def fakeSleepCallbacks(cls, callbacks: list[SleepFakeCallback]) -> None:
        """Replace callbacks through the Laravel-compatible property.

        Args:
            callbacks: The replacement callback collection.
        """
        _fake_state().callbacks = list(callbacks)


class Sleep(Macroable, metaclass=_SleepMeta):
    """Represent a duration and explicitly execute a sleep operation.

    Build durations with ``for_`` and a unit method, then call ``sleep_sync``
    or await ``sleep_async``. A `timedelta` may be passed directly to the
    constructor. Fake recordings and callbacks live in a `ContextVar` rather
    than process-global mutable state.

    Attributes:
        duration: A replaceable duration rounded to whole microseconds.
        while_callback: A replaceable predicate that repeats the operation.

    Notes:
        Python does not sleep from ``__del__``. Explicit execution prevents
        garbage collection from blocking or unexpectedly suspending callers.
    """

    def __init__(self, duration: int | float | timedelta) -> None:
        """Create a duration builder from a number or Python timedelta.

        Args:
            duration: A numeric amount awaiting a unit, or a complete duration.

        Raises:
            TypeError: If the duration is boolean or has an unsupported type.
            ValueError: If a numeric duration is not finite.
        """
        self._duration_microseconds = 0
        self._pending: int | float | None = None
        self._while_callback: (
            SleepWhileCallback | AsyncSleepWhileCallback | None
        ) = None
        self._should_sleep = True
        self._already_slept = False
        if isinstance(duration, timedelta):
            self._duration_microseconds = max(
                0,
                self._timedelta_microseconds(duration),
            )
            return
        self._validate_number(duration)
        self._pending = duration

    @property
    def duration(self) -> timedelta:
        """Return the completed duration at Python's microsecond precision.

        Returns:
            The immutable duration value.
        """
        return timedelta(microseconds=self._duration_microseconds)

    @duration.setter
    def duration(self, duration: timedelta) -> None:
        """Replace the completed duration using an immutable timedelta.

        Args:
            duration: The replacement duration value.

        Raises:
            TypeError: If the replacement is not a `timedelta`.
        """
        duration = self._require_timedelta(duration)
        self._duration_microseconds = max(
            0,
            self._timedelta_microseconds(duration),
        )

    @property
    def while_callback(
        self,
    ) -> SleepWhileCallback | AsyncSleepWhileCallback | None:
        """Expose the predicate that repeats this operation.

        Returns:
            The configured predicate, or ``None`` for a single sleep.
        """
        return self._while_callback

    @while_callback.setter
    def while_callback(
        self,
        callback: SleepWhileCallback | AsyncSleepWhileCallback | None,
    ) -> None:
        """Replace or clear the predicate used for repeated waits.

        Args:
            callback: A callable predicate or ``None`` to clear it.

        Raises:
            TypeError: If the replacement is not callable or ``None``.
        """
        if callback is not None and not callable(callback):
            raise TypeError(_WHILE_CALLBACK_TYPE_ERROR)
        self._while_callback = callback

    @classmethod
    def for_(cls, duration: int | float | timedelta) -> Self:
        """Create a builder for a duration that will receive a unit.

        Args:
            duration: A number awaiting a unit or a Python timedelta.

        Returns:
            A builder of the concrete class.
        """
        return cls(duration)

    @classmethod
    def until(
        cls,
        timestamp: datetime | int | float | str,
        *,
        now: datetime | int | float | None = None,
    ) -> Self:
        """Create a builder for the time remaining until a target.

        Args:
            timestamp: An absolute datetime or Unix timestamp.
            now: Optional current time for deterministic tests.

        Returns:
            A complete duration builder, clamped to zero when in the past.

        Raises:
            TypeError: If the target or injected clock has an unsupported type.
            ValueError: If a numeric timestamp cannot be parsed or is
                non-finite.
        """
        if isinstance(timestamp, datetime):
            current = cls._datetime_now(timestamp, now)
            try:
                remaining = timestamp - current
            except TypeError as error:
                raise ValueError(_TIMESTAMP_TIMEZONE_ERROR) from error
            return cls(max(timedelta(0), remaining))

        return cls._from_timestamp(timestamp, now)

    @classmethod
    def _from_timestamp(
        cls,
        timestamp: int | float | str,
        now: datetime | int | float | None,
    ) -> Self:
        """Build a duration from a numeric Unix timestamp.

        Args:
            timestamp: A numeric timestamp or its string representation.
            now: An optional injected current time.

        Returns:
            A completed duration builder clamped to zero in the past.

        Raises:
            TypeError: If ``timestamp`` or ``now`` has an invalid type.
            ValueError: If either timestamp is non-finite or malformed.
        """
        # Convert only after rejecting bool: Python considers bool an int,
        # while a boolean is not a meaningful Unix timestamp here.
        if isinstance(timestamp, bool):
            raise TypeError(_TIMESTAMP_TYPE_ERROR)
        try:
            target_timestamp = float(timestamp)
        except (OverflowError, TypeError, ValueError) as error:
            raise ValueError(_TIMESTAMP_VALUE_ERROR) from error
        if not math.isfinite(target_timestamp):
            raise ValueError(_TIMESTAMP_VALUE_ERROR)
        current_timestamp = cls._resolve_timestamp_now(now)
        return cls(max(0.0, target_timestamp - current_timestamp)).seconds()

    @staticmethod
    def _resolve_timestamp_now(
        now: datetime | int | float | None,
    ) -> float:
        """Resolve an injected or system clock as a Unix timestamp.

        Args:
            now: An optional datetime or numeric timestamp.

        Returns:
            The current time as finite seconds since the Unix epoch.

        Raises:
            TypeError: If an injected clock has an unsupported type.
            ValueError: If the injected numeric clock is non-finite.
        """
        if isinstance(now, datetime):
            return now.timestamp()
        if now is None:
            return time.time()
        if type(now) is int or type(now) is float:
            try:
                current_timestamp = float(now)
            except OverflowError as error:
                raise ValueError(_TIMESTAMP_VALUE_ERROR) from error
            if not math.isfinite(current_timestamp):
                raise ValueError(_TIMESTAMP_VALUE_ERROR)
            return current_timestamp
        raise TypeError(_TIMESTAMP_NOW_TYPE_ERROR)

    @classmethod
    def usleep(cls, duration: int) -> Self:
        """Create a completed microsecond-duration builder.

        Args:
            duration: The number of microseconds.

        Returns:
            A builder ready for explicit execution.
        """
        return cls(duration).microseconds()

    @classmethod
    def sleep(cls, duration: int | float) -> Self:
        """Create a completed second-duration builder.

        Args:
            duration: The number of seconds.

        Returns:
            A builder ready for explicit execution.
        """
        return cls(duration).seconds()

    def minutes(self) -> Self:
        """Add the pending value as minutes to the current duration.

        Returns:
            This builder for fluent chaining.
        """
        return self._add_pending(60_000_000)

    def minute(self) -> Self:
        """Add the pending value as minutes using the singular alias.

        Returns:
            This builder for fluent chaining.
        """
        return self.minutes()

    def seconds(self) -> Self:
        """Add the pending value as seconds to the current duration.

        Returns:
            This builder for fluent chaining.
        """
        return self._add_pending(1_000_000)

    def second(self) -> Self:
        """Add the pending value as seconds using the singular alias.

        Returns:
            This builder for fluent chaining.
        """
        return self.seconds()

    def milliseconds(self) -> Self:
        """Add the pending value as milliseconds to the duration.

        Returns:
            This builder for fluent chaining.
        """
        return self._add_pending(1_000)

    def millisecond(self) -> Self:
        """Add the pending value as milliseconds using the singular alias.

        Returns:
            This builder for fluent chaining.
        """
        return self.milliseconds()

    def microseconds(self) -> Self:
        """Add the pending value as microseconds to the duration.

        Returns:
            This builder for fluent chaining.
        """
        return self._add_pending(1)

    def microsecond(self) -> Self:
        """Add the pending value as microseconds using the singular alias.

        Returns:
            This builder for fluent chaining.
        """
        return self.microseconds()

    def and_(self, duration: int | float) -> Self:
        """Set the next amount to add, adapting reserved word ``and``.

        Args:
            duration: A finite number awaiting a unit method.

        Returns:
            This builder for fluent chaining.

        Raises:
            TypeError: If the duration is boolean or not numeric.
            ValueError: If the duration is not finite.
        """
        self._validate_number(duration)
        self._pending = duration
        return self

    def while_(self, callback: SleepWhileCallback) -> Self:
        """Repeat the duration while a predicate returns true.

        Args:
            callback: A synchronous zero-argument continuation predicate.

        Returns:
            This builder for fluent chaining.
        """
        if not callable(callback):
            raise TypeError(_WHILE_CALLBACK_TYPE_ERROR)
        self.while_callback = callback
        return self

    def while_async(self, callback: AsyncSleepWhileCallback) -> Self:
        """Repeat asynchronous sleeps while an async predicate is true.

        Args:
            callback: A predicate that may return an awaitable value.

        Returns:
            This builder for fluent chaining.
        """
        if not callable(callback):
            raise TypeError(_WHILE_CALLBACK_TYPE_ERROR)
        self.while_callback = callback
        return self

    def when(self, condition: SleepCondition) -> Self:
        """Execute only when a boolean or builder-aware callback is true.

        Args:
            condition: A boolean or callback evaluated with this builder.

        Returns:
            This builder for fluent chaining.
        """
        outcome = condition(self) if callable(condition) else condition
        self._reject_awaitable(outcome)
        self._should_sleep = bool(outcome)
        return self

    def unless(self, condition: SleepCondition) -> Self:
        """Execute unless a boolean or builder-aware callback is true.

        Args:
            condition: A boolean or callback evaluated with this builder.

        Returns:
            This builder for fluent chaining.
        """
        outcome = condition(self) if callable(condition) else condition
        self._reject_awaitable(outcome)
        self._should_sleep = not bool(outcome)
        return self

    async def when_async(self, condition: AsyncSleepCondition) -> Self:
        """Set the condition after resolving an optional async callback.

        Args:
            condition: A boolean or callback that may return an awaitable.

        Returns:
            This builder with execution enabled or disabled.
        """
        outcome = condition(self) if callable(condition) else condition
        if inspect.isawaitable(outcome):
            outcome = await cast("Awaitable[object]", outcome)
        self._should_sleep = bool(outcome)
        return self

    async def unless_async(self, condition: AsyncSleepCondition) -> Self:
        """Set the inverse condition after resolving an async callback.

        Args:
            condition: A boolean or callback that may return an awaitable.

        Returns:
            This builder with execution enabled or disabled.
        """
        outcome = condition(self) if callable(condition) else condition
        if inspect.isawaitable(outcome):
            outcome = await cast("Awaitable[object]", outcome)
        self._should_sleep = not bool(outcome)
        return self

    def then(self, callback: Callable[[], _T]) -> _T:
        """Sleep synchronously and then return a callback's result.

        Args:
            callback: A zero-argument synchronous callback.

        Returns:
            The callback result.

        Raises:
            TypeError: If the callback returns an awaitable.
        """
        self.sleep_sync()
        result = callback()
        self._reject_awaitable(result)
        return result

    async def then_async(
        self,
        callback: Callable[[], Awaitable[_T]],
    ) -> _T:
        """Await a sleep and then await the callback result.

        Args:
            callback: A zero-argument asynchronous callback.

        Returns:
            The awaited callback result.
        """
        await self.sleep_async()
        return await callback()

    def sleep_sync(self) -> None:
        """Run this duration synchronously, if its conditions allow it.

        Raises:
            RuntimeError: If a numeric duration has no unit.
            TypeError: If a fake callback returns an awaitable.

        Notes:
            This is Titanspan's explicit execution method. No sleep occurs
            merely because a builder is created or discarded.
        """
        if self._already_slept or not self._should_sleep:
            return
        self._ensure_complete()
        duration = self.duration
        try:
            # Laravel's fake branch records one operation without evaluating
            # the real-wait repetition predicate.
            if self._record_fake_sync(duration):
                return
            while_callback = self._while_callback
            if while_callback is None:
                if duration > timedelta(0):
                    time.sleep(duration.total_seconds())
                return
            while self._invoke_while_callback(while_callback):
                if duration > timedelta(0):
                    time.sleep(duration.total_seconds())
        finally:
            # A canceled or interrupted wait cannot be resumed safely on a
            # later call because its elapsed portion is unknown.
            self._already_slept = True

    async def sleep_async(self) -> None:
        """Run this duration through AnyIO without blocking the event loop.

        Raises:
            RuntimeError: If a numeric duration has no unit.
        """
        if self._already_slept or not self._should_sleep:
            return
        self._ensure_complete()
        duration = self.duration
        try:
            # Keep fake behavior aligned with the synchronous path and avoid
            # invoking user repetition code when no real wait will occur.
            if await self._record_fake_async(duration):
                return
            while_callback = self._while_callback
            if while_callback is None:
                await anyio.sleep(duration.total_seconds())
                return
            # The predicate is the upstream repeat condition, not an event.
            should_repeat = await self._invoke_while_callback_async(
                while_callback
            )
            while should_repeat:
                await anyio.sleep(duration.total_seconds())
                should_repeat = await self._invoke_while_callback_async(
                    while_callback
                )
        finally:
            # Preserve cancellation semantics and prevent accidental replay
            # of a wait that may already have elapsed partially.
            self._already_slept = True

    @classmethod
    def fake(
        cls,
        value: bool = True,
    ) -> None:
        """Enable or disable fake sleeps in the active execution context.

        Args:
            value: Whether to record sleeps instead of waiting.

        Raises:
            TypeError: If ``value`` is not a boolean.
        """
        if type(value) is not bool:
            raise TypeError(_FAKE_VALUE_TYPE_ERROR)
        _FAKE_STATE.set(_FakeState(enabled=value))

    @classmethod
    def when_faking_sleep(cls, callback: SleepFakeCallback) -> None:
        """Register a callback for every fake sleep in this context.

        Args:
            callback: A synchronous callback receiving the recorded duration.
        """
        _fake_state().callbacks.append(callback)

    @classmethod
    def assert_slept(
        cls,
        expected: timedelta | Sleep | Callable[[timedelta], bool],
        times: int = 1,
    ) -> None:
        """Assert a duration or predicate matched a requested count.

        Args:
            expected: A duration, Sleep builder, or duration predicate.
            times: Number of matching recorded sleeps required.

        Raises:
            AssertionError: If the number of matching durations differs.
            ValueError: If ``times`` is not a non-negative integer.
        """
        cls._validate_assertion_count(times)
        durations = _fake_state().durations
        if isinstance(expected, Sleep):
            expected_duration = expected.duration
            matches = (duration == expected_duration for duration in durations)
        elif isinstance(expected, timedelta):
            matches = (duration == expected for duration in durations)
        else:
            matches = (expected(duration) for duration in durations)
        count = sum(matches)
        if count != times:
            message = f"Expected sleep match {times} times but found {count}."
            raise AssertionError(message)

    @classmethod
    def assert_slept_times(cls, expected: int) -> None:
        """Assert the total number of recorded fake sleep operations.

        Args:
            expected: Required number of sleeps.

        Raises:
            AssertionError: If the recorded count differs.
            ValueError: If ``expected`` is not a non-negative integer.
        """
        cls._validate_assertion_count(expected)
        actual = len(_fake_state().durations)
        if actual != expected:
            message = f"Expected [{expected}] sleeps but found [{actual}]."
            raise AssertionError(message)

    @classmethod
    def assert_sequence(
        cls,
        sequence: Sequence[timedelta | Sleep | None],
    ) -> None:
        """Compare fake recordings with an ordered duration sequence.

        Args:
            sequence: Expected durations; ``None`` skips one comparison.

        Raises:
            AssertionError: If counts or comparable durations differ.

        Notes:
            Expected Sleep builders are marked non-executing even when the
            assertion fails, matching Laravel's test helper cleanup behavior.
        """
        state = _fake_state()
        expected_count = len(sequence)
        actual_count = len(state.durations)
        try:
            if expected_count != actual_count:
                message = (
                    f"Expected [{expected_count}] sleeps but found "
                    f"[{actual_count}]."
                )
                raise AssertionError(message)
            for expected, actual in zip(sequence, state.durations, strict=True):
                if expected is None:
                    continue
                expected_duration = (
                    expected.duration
                    if isinstance(expected, Sleep)
                    else expected
                )
                if expected_duration != actual:
                    message = (
                        "Expected sleep duration of "
                        f"[{expected_duration}] but actually slept for "
                        f"[{actual}]."
                    )
                    raise AssertionError(message)
        finally:
            for expected in sequence:
                if isinstance(expected, Sleep):
                    expected._should_not_sleep()  # noqa: SLF001

    @classmethod
    def assert_never_slept(cls) -> None:
        """Assert that no fake sleep operation was recorded.

        Raises:
            AssertionError: If one or more sleeps were recorded.
        """
        cls.assert_slept_times(0)

    @classmethod
    def assert_insomniac(cls) -> None:
        """Assert that recorded sleeps all had zero duration.

        Raises:
            AssertionError: If any recorded duration was positive.
        """
        for duration in _fake_state().durations:
            if duration > timedelta(0):
                message = f"Unexpected sleep duration of [{duration}] found."
                raise AssertionError(message)

    def _add_pending(self, unit_microseconds: int) -> Self:
        """Consume a pending value into the completed duration.

        Args:
            unit_microseconds: Microseconds represented by one unit.

        Returns:
            This builder after adding the pending amount.

        Raises:
            RuntimeError: If no numeric amount is pending.
        """
        if self._pending is None:
            self._should_sleep = False
            raise RuntimeError(_NO_DURATION_ERROR)
        # Integers stay exact; float values truncate at Python's supported
        # microsecond resolution, matching the upstream smallest unit.
        amount = max(0, self._pending)
        microseconds = amount * unit_microseconds
        if isinstance(microseconds, float) and not math.isfinite(microseconds):
            raise OverflowError(_DURATION_OVERFLOW_ERROR)
        additional = int(microseconds)
        if (
            additional
            > _MAX_DURATION_MICROSECONDS - self._duration_microseconds
        ):
            raise OverflowError(_DURATION_OVERFLOW_ERROR)
        self._duration_microseconds += additional
        self._pending = None
        return self

    def _invoke_while_callback(
        self,
        callback: SleepWhileCallback | AsyncSleepWhileCallback,
    ) -> bool:
        """Evaluate the configured synchronous repetition predicate.

        Args:
            callback: The predicate captured for this execution.

        Returns:
            Whether the current sleep operation should repeat.

        Raises:
            TypeError: If the callback returns an awaitable.
        """
        result = callback()
        self._reject_awaitable(result)
        return bool(result)

    async def _invoke_while_callback_async(
        self,
        callback: SleepWhileCallback | AsyncSleepWhileCallback,
    ) -> bool:
        """Evaluate a repetition predicate in the async execution path.

        Args:
            callback: The predicate captured for this execution.

        Returns:
            Whether the current sleep operation should repeat.
        """
        result = callback()
        if inspect.isawaitable(result):
            result = await cast("Awaitable[object]", result)
        return bool(result)

    def _ensure_complete(self) -> None:
        """Reject execution before a numeric duration receives a unit.

        Raises:
            RuntimeError: If an amount remains pending.
        """
        if self._pending is not None:
            raise RuntimeError(_UNKNOWN_UNIT_ERROR)

    def _record_fake_sync(self, duration: timedelta) -> bool:
        """Record and notify synchronous fake callbacks when enabled.

        Args:
            duration: The completed operation duration.

        Returns:
            Whether faking intercepted the operation.

        Raises:
            TypeError: If a fake callback returns an awaitable.
        """
        state = _fake_state()
        if not state.enabled:
            return False
        state.durations.append(duration)
        callbacks = tuple(state.callbacks)
        for callback in callbacks:
            result = callback(duration)
            self._reject_awaitable(result)
        return True

    async def _record_fake_async(self, duration: timedelta) -> bool:
        """Record and notify fake callbacks in asynchronous execution.

        Args:
            duration: The completed operation duration.

        Returns:
            Whether faking intercepted the operation.
        """
        state = _fake_state()
        if not state.enabled:
            return False
        # Snapshot before awaiting callbacks so registrations during a
        # callback affect only later fake sleeps.
        state.durations.append(duration)
        callbacks = tuple(state.callbacks)
        for callback in callbacks:
            result = callback(duration)
            if inspect.isawaitable(result):
                await cast("Awaitable[object]", result)
        return True

    def _should_not_sleep(self) -> Self:
        """Mark an expected builder as assertion-only data.

        Returns:
            This builder with execution disabled.
        """
        self._should_sleep = False
        return self

    @staticmethod
    def _datetime_now(
        timestamp: datetime,
        now: datetime | int | float | None,
    ) -> datetime:
        """Resolve a current datetime compatible with a target's timezone.

        Args:
            timestamp: The target datetime.
            now: An optional injected current datetime.

        Returns:
            A datetime in the target's timezone mode.

        Raises:
            TypeError: If ``now`` has an unsupported type.
        """
        if isinstance(now, datetime):
            return now
        if now is not None:
            raise TypeError(_DATETIME_NOW_TYPE_ERROR)
        return datetime.now(timestamp.tzinfo)

    @staticmethod
    def _timedelta_microseconds(duration: timedelta) -> int:
        """Convert timedelta fields to exact integer microseconds.

        Args:
            duration: A Python duration value.

        Returns:
            The signed microsecond count.
        """
        return (
            duration.days * 86_400_000_000
            + duration.seconds * 1_000_000
            + duration.microseconds
        )

    @staticmethod
    def _require_timedelta(duration: object) -> timedelta:
        """Validate an assigned duration before converting it.

        Args:
            duration: The value assigned to the public property.

        Returns:
            The validated `timedelta` value.

        Raises:
            TypeError: If the assigned value is not a `timedelta`.
        """
        if not isinstance(duration, timedelta):
            raise TypeError(_DURATION_PROPERTY_TYPE_ERROR)
        return duration

    @staticmethod
    def _validate_number(duration: object) -> None:
        """Require a finite non-boolean integer or floating-point amount.

        Args:
            duration: The numeric value to validate.

        Raises:
            TypeError: If the value is boolean or not numeric.
            ValueError: If the numeric value is infinite or NaN.
        """
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise TypeError(_DURATION_NUMBER_ERROR)
        if isinstance(duration, float) and not math.isfinite(duration):
            raise ValueError(_DURATION_FINITE_ERROR)

    @staticmethod
    def _validate_assertion_count(count: int) -> None:
        """Validate non-negative integer counts for fake assertions.

        Args:
            count: The expected number of matching sleeps.

        Raises:
            ValueError: If the count is boolean, non-integer, or negative.
        """
        if type(count) is not int or count < 0:
            raise ValueError(_SLEEP_COUNT_ERROR)

    @staticmethod
    def _reject_awaitable(result: object) -> None:
        """Reject accidental async work from synchronous callbacks.

        Args:
            result: The returned value to inspect.

        Raises:
            TypeError: If the value must be awaited.
        """
        if not inspect.isawaitable(result):
            return
        if inspect.iscoroutine(result):
            result.close()
        raise TypeError(_ASYNC_CALLBACK_ERROR)

    whenFakingSleep = when_faking_sleep
    assertSlept = assert_slept
    assertSleptTimes = assert_slept_times
    assertSequence = assert_sequence
    assertNeverSlept = assert_never_slept
    assertInsomniac = assert_insomniac
