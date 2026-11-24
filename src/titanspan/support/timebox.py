"""Run callbacks for at least a requested duration when they finish early.

Synchronous and asynchronous entry points are explicit. Async callbacks use
AnyIO's backend-neutral sleep and allow cancellation to interrupt the wait.
"""

from __future__ import annotations

import inspect
import time
from typing import TYPE_CHECKING, TypeVar

import anyio

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_T = TypeVar("_T")
_ASYNC_CALLBACK_ERROR = (
    "synchronous timebox callbacks must not return awaitables; "
    "use call_async() instead"
)
_DURATION_ERROR = "microseconds must be a non-negative integer"


class Timebox:
    """Enforce a minimum operation duration without imposing a deadline.

    The callback receives this instance and can opt into early return with
    :meth:`return_early`. Otherwise, a short operation waits for its remaining
    duration. A long operation is never interrupted by the timebox.

    Attributes:
        early_return: Whether a callback may skip the remaining wait.

    Notes:
        Async cancellation propagates immediately and does not wait out the
        remaining duration. This class does not provide timing-attack defense.
    """

    def __init__(self) -> None:
        """Initialize a timebox that does not allow early return.

        Notes:
            The same instance can be reused, but early-return state is
            mutable and should not be shared across concurrent operations.
        """
        self.early_return = False

    def call(
        self,
        callback: Callable[[Timebox], _T],
        microseconds: int,
    ) -> _T:
        """Run a synchronous callback and enforce its minimum duration.

        Args:
            callback: Operation receiving the active timebox instance.
            microseconds: Minimum duration to wait, in microseconds.

        Returns:
            The callback result.

        Raises:
            ValueError: If the requested duration is negative or boolean.
            TypeError: If the synchronous callback returns an awaitable.
            Exception: Any exception raised by the callback after the
                remaining minimum wait has elapsed.
        """
        self._validate_duration(microseconds)
        started = self._now_ns()
        try:
            result = callback(self)
            self._reject_awaitable(result)
        except Exception:
            self._wait_remaining(started, microseconds)
            raise
        self._wait_remaining(started, microseconds)
        return result

    async def call_async(
        self,
        callback: Callable[[Timebox], Awaitable[_T]],
        microseconds: int,
    ) -> _T:
        """Run an async callback without blocking the running event loop.

        Args:
            callback: Awaitable operation receiving the active timebox.
            microseconds: Minimum duration to wait, in microseconds.

        Returns:
            The awaited callback result.

        Raises:
            ValueError: If the requested duration is negative or boolean.
            Exception: Any ordinary exception raised by the callback after
                the remaining minimum wait has elapsed.

        Notes:
            Cancellation is a control-flow signal and propagates immediately;
            the timebox does not delay it to satisfy the minimum duration.
        """
        self._validate_duration(microseconds)
        started = self._now_ns()
        try:
            result = await callback(self)
        except Exception:
            await self._wait_remaining_async(started, microseconds)
            raise
        await self._wait_remaining_async(started, microseconds)
        return result

    def return_early(self) -> Timebox:
        """Allow the current callback to skip its remaining minimum wait.

        Returns:
            This timebox instance for fluent use.
        """
        self.early_return = True
        return self

    def dont_return_early(self) -> Timebox:
        """Require the current callback to honor its minimum duration.

        Returns:
            This timebox instance for fluent use.
        """
        self.early_return = False
        return self

    @property
    def earlyReturn(self) -> bool:
        """Expose the public Laravel-compatible early-return flag.

        Returns:
            Whether the current operation may finish before its minimum time.
        """
        return self.early_return

    @earlyReturn.setter
    def earlyReturn(self, value: bool) -> None:
        """Set whether the callback may skip the remaining minimum duration.

        Args:
            value: Whether early return is allowed.
        """
        self.early_return = value

    def _wait_remaining(self, started_ns: int, microseconds: int) -> None:
        """Wait synchronously for any remaining portion of the timebox.

        Args:
            started_ns: Monotonic timestamp captured before the callback.
            microseconds: Requested minimum duration.
        """
        if self.early_return:
            return
        remaining = self._remaining_microseconds(started_ns, microseconds)
        if remaining > 0:
            self._sleep(remaining / 1_000_000)

    async def _wait_remaining_async(
        self,
        started_ns: int,
        microseconds: int,
    ) -> None:
        """Wait asynchronously for any remaining timebox duration.

        Args:
            started_ns: Monotonic timestamp captured before the callback.
            microseconds: Requested minimum duration.
        """
        if self.early_return:
            return
        remaining = self._remaining_microseconds(started_ns, microseconds)
        if remaining > 0:
            await self._sleep_async(remaining / 1_000_000)

    def _remaining_microseconds(
        self,
        started_ns: int,
        microseconds: int,
    ) -> int:
        """Calculate a non-negative remainder using a monotonic clock.

        Args:
            started_ns: Monotonic timestamp captured before the callback.
            microseconds: Requested minimum duration.

        Returns:
            Remaining time rounded down to whole microseconds.
        """
        elapsed = (self._now_ns() - started_ns) // 1_000
        return max(0, microseconds - elapsed)

    def _now_ns(self) -> int:
        """Return a monotonic nanosecond timestamp for elapsed time.

        Returns:
            A monotonic high-resolution clock reading.
        """
        # Wall-clock adjustments must not change elapsed operation time.
        return time.monotonic_ns()

    def _sleep(self, seconds: float) -> None:
        """Wait synchronously for a positive remainder.

        Args:
            seconds: Remaining duration in seconds.
        """
        time.sleep(seconds)

    async def _sleep_async(self, seconds: float) -> None:
        """Wait asynchronously without blocking other tasks.

        Args:
            seconds: Remaining duration in seconds.
        """
        await anyio.sleep(seconds)

    @staticmethod
    def _validate_duration(microseconds: object) -> None:
        """Reject durations that cannot represent a valid minimum wait.

        Args:
            microseconds: The requested minimum timebox duration.

        Raises:
            ValueError: If the value is boolean, non-integer, or negative.
        """
        if (
            isinstance(microseconds, bool)
            or not isinstance(microseconds, int)
            or microseconds < 0
        ):
            raise ValueError(_DURATION_ERROR)

    @staticmethod
    def _reject_awaitable(result: object) -> None:
        """Prevent a sync callback from leaking an unawaited coroutine.

        Args:
            result: The value returned by the callback.

        Raises:
            TypeError: If the result must be awaited.
        """
        if not inspect.isawaitable(result):
            return
        if inspect.iscoroutine(result):
            result.close()
        raise TypeError(_ASYNC_CALLBACK_ERROR)

    returnEarly = return_early
    dontReturnEarly = dont_return_early


__all__ = ["Timebox"]
