"""Verify minimum-duration execution and async cancellation behavior.

The tests replace clocks and wait operations rather than depending on wall
clock timing or arbitrary sleeps.
"""

from __future__ import annotations

from typing import cast

import anyio
import pytest

import titanspan.support.timebox as timebox_module
from titanspan.support import Timebox


@pytest.mark.unit
def test_call_runs_callback_and_waits_for_remaining_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return the callback result after waiting for a remaining duration.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    box = Timebox()
    clock = iter([0, 2_000_000])
    sleeps: list[float] = []
    monkeypatch.setattr(box, "_now_ns", lambda: next(clock))
    monkeypatch.setattr(box, "_sleep", sleeps.append)

    result = box.call(lambda active: active is box, 10_000)

    assert result is True
    assert sleeps == [0.008]


@pytest.mark.unit
def test_call_waits_for_minimum_even_when_callback_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve callback errors while waiting for the minimum duration.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    box = Timebox()
    clock = iter([0, 1_000_000])
    sleeps: list[float] = []
    monkeypatch.setattr(box, "_now_ns", lambda: next(clock))
    monkeypatch.setattr(box, "_sleep", sleeps.append)

    error_message = "timebox callback failed"

    def fail(_box: Timebox) -> None:
        """Raise the sentinel callback failure.

        Raises:
            LookupError: Always.
        """
        raise LookupError(error_message)

    with pytest.raises(LookupError, match=error_message):
        box.call(fail, 5_000)

    assert sleeps == [0.004]


@pytest.mark.unit
def test_return_early_and_dont_return_early_control_waiting() -> None:
    """Expose fluent controls for skipping or reinstating the minimum wait.

    Returns:
        None.
    """
    box = Timebox()

    assert box.return_early() is box
    assert box.early_return is True
    assert box.earlyReturn is True
    assert box.dont_return_early() is box
    assert box.early_return is False
    box.earlyReturn = True
    assert box.early_return is True
    assert box.returnEarly() is box
    assert box.dontReturnEarly() is box


@pytest.mark.unit
def test_call_rejects_negative_durations() -> None:
    """Reject negative minimum durations before invoking callbacks.

    Returns:
        None.
    """
    called = False

    def callback(_box: Timebox) -> None:
        """Mark the callback if invalid input reaches it.

        Returns:
            None.
        """
        nonlocal called
        called = True

    with pytest.raises(ValueError, match="microseconds"):
        Timebox().call(callback, -1)

    assert called is False


@pytest.mark.unit
def test_call_can_return_early_without_reading_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Honor early-return requests without performing another clock read.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    box = Timebox()
    clock = iter([0])
    sleeps: list[float] = []
    monkeypatch.setattr(box, "_now_ns", lambda: next(clock))
    monkeypatch.setattr(box, "_sleep", sleeps.append)

    result = box.call(lambda active: active.return_early(), 10_000)

    assert result is box
    assert sleeps == []


@pytest.mark.unit
def test_call_skips_sleep_when_callback_exceeds_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avoid sleeping after an operation already exceeded its minimum.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    box = Timebox()
    clock = iter([0, 8_000_000])
    sleeps: list[float] = []
    monkeypatch.setattr(box, "_now_ns", lambda: next(clock))
    monkeypatch.setattr(box, "_sleep", sleeps.append)

    assert box.call(lambda _active: "done", 5_000) == "done"
    assert sleeps == []


@pytest.mark.unit
def test_call_delegates_remaining_time_to_standard_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the blocking sleep adapter only in the synchronous call path.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    box = Timebox()
    clock = iter([0, 0])
    waits: list[float] = []
    monkeypatch.setattr(box, "_now_ns", lambda: next(clock))
    monkeypatch.setattr(timebox_module.time, "sleep", waits.append)

    assert box.call(lambda _active: "done", 2_000) == "done"
    assert waits == [0.002]


@pytest.mark.unit
def test_call_rejects_awaitable_results() -> None:
    """Close a coroutine returned through the synchronous timebox API.

    Returns:
        None.
    """

    async def callback(_box: Timebox) -> str:
        """Return an awaitable that the synchronous API must reject.

        Returns:
            A stable result.
        """
        return "not awaited"

    def callback_with_object_return(box: Timebox) -> object:
        """Return the coroutine as an opaque object for runtime validation.

        Args:
            box: The active timebox passed to the async callback.

        Returns:
            The coroutine object without awaiting it.
        """
        return callback(box)

    with pytest.raises(TypeError, match="call_async"):
        Timebox().call(callback_with_object_return, 0)


@pytest.mark.unit
@pytest.mark.parametrize("duration", [True])
def test_call_rejects_boolean_durations(duration: int) -> None:
    """Reject booleans instead of treating them as integer durations.

    Args:
        duration: The boolean duration passed to the API.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="microseconds"):
        Timebox().call(lambda _box: None, duration)


@pytest.mark.unit
@pytest.mark.parametrize("duration", [1.5, "10"])
def test_call_rejects_non_integer_durations(duration: object) -> None:
    """Require timebox durations to be whole microsecond counts.

    Args:
        duration: The invalid duration to supply.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="microseconds"):
        Timebox().call(lambda _box: None, cast("int", duration))


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_async_awaits_callback_and_remaining_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Await async callbacks and the remaining non-blocking wait.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    box = Timebox()
    clock = iter([0, 3_000_000])
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        """Record the requested non-blocking delay.

        Args:
            seconds: The requested wait duration.

        Returns:
            None.
        """
        waits.append(seconds)

    monkeypatch.setattr(box, "_now_ns", lambda: next(clock))
    monkeypatch.setattr(box, "_sleep_async", sleep)

    async def callback(active: Timebox) -> str:
        """Return a result after confirming the active box identity.

        Args:
            active: The timebox passed to the operation.

        Returns:
            A stable completion result.
        """
        assert active is box
        return "done"

    result = await box.call_async(callback, 10_000)

    assert result == "done"
    assert waits == [0.007]


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_async_does_not_block_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Propagate callback cancellation without waiting for the minimum.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    box = Timebox()
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        """Record asynchronous waits if cancellation reaches that stage.

        Args:
            seconds: The requested wait duration.

        Returns:
            None.
        """
        waits.append(seconds)

    monkeypatch.setattr(box, "_sleep_async", sleep)
    cancellation_error = anyio.get_cancelled_exc_class()

    async def cancel(_box: Timebox) -> None:
        """Raise the active backend's cancellation signal.

        Raises:
            cancellation_error: Always.
        """
        raise cancellation_error()

    with pytest.raises(cancellation_error):
        await box.call_async(cancel, 10_000)

    assert waits == []


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_async_waits_after_ordinary_callback_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enforce the minimum after ordinary errors before propagating them.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    box = Timebox()
    clock = iter([0, 4_000_000])
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        """Record the requested non-blocking delay.

        Args:
            seconds: The requested wait duration.

        Returns:
            None.
        """
        waits.append(seconds)

    monkeypatch.setattr(box, "_now_ns", lambda: next(clock))
    monkeypatch.setattr(box, "_sleep_async", sleep)
    error_message = "async timebox callback failed"

    async def fail(_box: Timebox) -> None:
        """Raise the sentinel callback error.

        Raises:
            LookupError: Always.
        """
        raise LookupError(error_message)

    with pytest.raises(LookupError, match=error_message):
        await box.call_async(fail, 10_000)

    assert waits == [0.006]


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_async_honors_early_return_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skip the asynchronous remainder when the callback opts out.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    box = Timebox()
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        """Record unexpected wait requests.

        Args:
            seconds: The requested wait duration.

        Returns:
            None.
        """
        waits.append(seconds)

    monkeypatch.setattr(box, "_sleep_async", sleep)

    async def callback(active: Timebox) -> None:
        """Request early completion from the active timebox.

        Args:
            active: The timebox passed to the callback.

        Returns:
            None.
        """
        active.return_early()

    await box.call_async(callback, 10_000)

    assert waits == []


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_async_skips_sleep_when_minimum_has_elapsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avoid an async wait when the callback already exceeded its minimum.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    box = Timebox()
    clock = iter([0, 2_000_000])
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        """Record unexpected async waits.

        Args:
            seconds: The requested wait duration.

        Returns:
            None.
        """
        waits.append(seconds)

    monkeypatch.setattr(box, "_now_ns", lambda: next(clock))
    monkeypatch.setattr(box, "_sleep_async", sleep)

    async def callback(_box: Timebox) -> str:
        """Return after the fake clock exceeds the minimum duration.

        Returns:
            A stable result.
        """
        return "done"

    assert await box.call_async(callback, 1_000) == "done"
    assert waits == []


@pytest.mark.unit
@pytest.mark.anyio
async def test_sleep_async_delegates_to_anyio_without_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delegate the delay to AnyIO's awaitable sleep operation.

    Args:
        monkeypatch: Pytest's attribute replacement fixture.

    Returns:
        None.
    """
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        """Record a requested asynchronous delay.

        Args:
            seconds: The requested wait duration.

        Returns:
            None.
        """
        waits.append(seconds)

    monkeypatch.setattr(timebox_module.anyio, "sleep", sleep)
    box = Timebox()
    clock = iter([0, 0])
    monkeypatch.setattr(box, "_now_ns", lambda: next(clock))

    async def callback(_box: Timebox) -> None:
        """Complete immediately so the minimum remainder is delegated.

        Returns:
            None.
        """

    await box.call_async(callback, 250_000)

    assert waits == [0.25]
