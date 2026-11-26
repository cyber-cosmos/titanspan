"""Run probability-based callbacks with context-local test controls.

The default draw uses cryptographically secure system randomness. Forced
results and deterministic sequences are local to the active context.
"""

from __future__ import annotations

import inspect
import secrets
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextvars import ContextVar, Token
from threading import Lock
from typing import Self, cast

type ResultFactory = Callable[[int | float, int | None], bool]
type _Callback = Callable[..., object]
type _Sequence = Sequence[bool] | Mapping[int, bool]
_FLOAT_CHANCE_ERROR = "Float must not be greater than 1."
_CHANCES_TYPE_ERROR = "chances must be an integer or float"
_OUT_OF_ERROR = 'Lottery "out of" value must be at least 1.'
_OUT_OF_TYPE_ERROR = "out_of must be an integer"
_TIMES_ERROR = "times must be a non-negative integer"
_ASYNC_CALLBACK_ERROR = (
    "synchronous lottery callbacks must not return awaitables; "
    "use choose_async() instead"
)
_RESULT_FACTORY: ContextVar[ResultFactory | None] = ContextVar(
    "titanspan_lottery_result_factory",
    default=None,
)


class Lottery:
    """Choose a winner or loser callback according to configured odds.

    A lottery can use fractional probability or integer chances out of a
    denominator. Test overrides are stored in a :class:`ContextVar`, keeping
    independent asynchronous execution contexts isolated.

    Notes:
        ``always_win(callback)`` and ``always_lose(callback)`` restore the
        outer factory after the callback, including when it raises.
    """

    def __init__(
        self,
        chances: int | float,
        out_of: int | None = None,
    ) -> None:
        """Create a lottery with a probability or numerator and denominator.

        Args:
            chances: A probability in ``[0, 1]`` or expected win count.
            out_of: The positive number of opportunities, if specified.

        Raises:
            TypeError: If ``chances`` is not numeric or ``out_of`` is not
                an integer.
            ValueError: If a floating probability exceeds one or the
                denominator is not positive.
        """
        Lottery._validate_odds_types(chances, out_of)
        if out_of is not None and out_of < 1:
            raise ValueError(_OUT_OF_ERROR)
        if out_of is None and isinstance(chances, float) and chances > 1:
            raise ValueError(_FLOAT_CHANCE_ERROR)
        self._chances = chances
        self._out_of = out_of
        self._winner: _Callback | None = None
        self._loser: _Callback | None = None

    @classmethod
    def odds(cls, chances: int | float, out_of: int | None = None) -> Self:
        """Create a lottery through a named factory method.

        Args:
            chances: A probability in ``[0, 1]`` or expected win count.
            out_of: The positive number of opportunities, if specified.

        Returns:
            A lottery instance of the concrete class.
        """
        return cls(chances, out_of)

    def winner(self, callback: _Callback) -> Self:
        """Set the callback to run when the lottery wins.

        Args:
            callback: A synchronous callback receiving invocation args.

        Returns:
            This lottery for fluent configuration.
        """
        self._winner = callback
        return self

    def loser(self, callback: _Callback) -> Self:
        """Set the callback to run when the lottery loses.

        Args:
            callback: A synchronous callback receiving invocation args.

        Returns:
            This lottery for fluent configuration.
        """
        self._loser = callback
        return self

    def __call__(self, *args: object) -> object:
        """Run one draw and forward arguments to the selected callback.

        Args:
            *args: Values passed to the selected winner or loser callback.

        Returns:
            The selected callback result or its default boolean.
        """
        return self._run_callback(args)

    def choose(self, times: int | None = None) -> object | list[object]:
        """Run one draw or return a list of repeated independent draws.

        Args:
            times: Number of draws; ``None`` requests one scalar result.

        Returns:
            One callback result or a list with ``times`` results.

        Raises:
            ValueError: If ``times`` is negative or boolean.
        """
        if times is None:
            return self._run_callback(())
        self._validate_times(times)
        return [self._run_callback(()) for _ in range(times)]

    async def choose_async(
        self,
        times: int | None = None,
    ) -> object | list[object]:
        """Run draws while explicitly awaiting asynchronous callbacks.

        Args:
            times: Number of draws; ``None`` requests one scalar result.

        Returns:
            One callback result or a list with ``times`` results.

        Raises:
            ValueError: If ``times`` is negative or boolean.

        Notes:
            Draws run sequentially so callback side effects preserve order.
            Cancellation and callback exceptions propagate to the caller.
        """
        if times is None:
            return await self._run_callback_async(())
        self._validate_times(times)
        return [await self._run_callback_async(()) for _ in range(times)]

    @staticmethod
    def always_win(callback: Callable[[], object] | None = None) -> None:
        """Force wins in this context or temporarily while a callback runs.

        Args:
            callback: Optional synchronous operation to run under the override.

        Raises:
            TypeError: If the callback returns an awaitable.
        """
        Lottery._set_forced_result(True, callback)

    @staticmethod
    def always_lose(callback: Callable[[], object] | None = None) -> None:
        """Force losses in this context or temporarily while a callback runs.

        Args:
            callback: Optional synchronous operation to run under the override.

        Raises:
            TypeError: If the callback returns an awaitable.
        """
        Lottery._set_forced_result(False, callback)

    @staticmethod
    def fix(
        sequence: _Sequence,
        when_missing: ResultFactory | None = None,
    ) -> None:
        """Install a deterministic sequence for draws in this context.

        Args:
            sequence: Outcomes indexed by their zero-based draw number.
            when_missing: Optional fallback for an absent sequence index.

        Notes:
            The sequence is copied so later caller mutations do not change
            the active test behavior.
        """
        Lottery.force_result_with_sequence(sequence, when_missing)

    @staticmethod
    def force_result_with_sequence(
        sequence: _Sequence,
        when_missing: ResultFactory | None = None,
    ) -> None:
        """Install deterministic draw outcomes in the active context.

        Args:
            sequence: Outcomes indexed by their zero-based draw number.
            when_missing: Optional result used when the sequence has no item.

        Notes:
            Without a fallback, missing entries use normal randomized odds.
            Missing mapping indexes do not advance the sequence cursor.
        """
        outcomes: _Sequence = (
            dict(sequence) if isinstance(sequence, Mapping) else tuple(sequence)
        )
        default_fallback = when_missing is None
        fallback = Lottery._normal_result if default_fallback else when_missing
        next_index = 0
        lock = Lock()

        def result_factory(chances: int | float, out_of: int | None) -> bool:
            """Read one outcome without sharing an unprotected cursor.

            Args:
                chances: The lottery's configured win count or probability.
                out_of: The optional number of opportunities.

            Returns:
                The next configured outcome or the fallback result.
            """
            nonlocal next_index
            # Keep caller-provided fallback work outside the cursor lock.
            with lock:
                if isinstance(outcomes, Mapping):
                    if next_index not in outcomes:
                        result = None
                        if default_fallback:
                            next_index += 1
                    else:
                        result = outcomes[next_index]
                        next_index += 1
                elif next_index < len(outcomes):
                    result = outcomes[next_index]
                    next_index += 1
                else:
                    result = None
                    if default_fallback:
                        next_index += 1
            if result is not None:
                return result
            return fallback(chances, out_of)

        _RESULT_FACTORY.set(result_factory)

    @staticmethod
    def set_result_factory(factory: ResultFactory | None) -> None:
        """Set or clear the result factory in the active execution context.

        Args:
            factory: A synchronous draw function, or ``None`` for normal odds.
        """
        _RESULT_FACTORY.set(factory)

    @staticmethod
    def determine_result_normally() -> None:
        """Clear forced results in the active execution context.

        Notes:
            Other contexts retain their own forced result factories.
        """
        _RESULT_FACTORY.set(None)

    @staticmethod
    def _normal_result(
        chances: int | float,
        out_of: int | None,
    ) -> bool:
        """Draw from system randomness without consulting test overrides.

        Args:
            chances: The configured win count or probability.
            out_of: The optional number of opportunities.

        Returns:
            Whether this draw wins.
        """
        if out_of is None:
            sample = secrets.randbelow(sys.maxsize + 1) / sys.maxsize
            return sample <= chances
        return secrets.randbelow(out_of) + 1 <= chances

    def _wins(self) -> bool:
        """Evaluate the active result factory for this lottery's odds.

        Returns:
            Whether the current draw wins.
        """
        result_factory = _RESULT_FACTORY.get()
        if result_factory is None:
            result_factory = Lottery._normal_result
        return result_factory(self._chances, self._out_of)

    def _run_callback(self, args: tuple[object, ...]) -> object:
        """Run the selected callback and reject hidden async execution.

        Args:
            args: Arguments passed to the selected callback.

        Returns:
            The callback result or its default boolean.

        Raises:
            TypeError: If a synchronous callback returns an awaitable.
        """
        won = self._wins()
        callback = self._winner if won else self._loser
        if callback is None:
            return won
        result = callback(*args)
        self._reject_awaitable(result)
        return result

    async def _run_callback_async(self, args: tuple[object, ...]) -> object:
        """Run the selected callback and await it when it is asynchronous.

        Args:
            args: Arguments passed to the selected callback.

        Returns:
            The callback result or its default boolean.
        """
        won = self._wins()
        callback = self._winner if won else self._loser
        if callback is None:
            return won
        result = callback(*args)
        if inspect.isawaitable(result):
            return await cast("Awaitable[object]", result)
        return result

    @staticmethod
    def _reject_awaitable(result: object) -> None:
        """Reject coroutine results passed through synchronous callbacks.

        Args:
            result: The value returned by a synchronous callback.

        Raises:
            TypeError: If the result must be awaited.
        """
        if not inspect.isawaitable(result):
            return
        if inspect.iscoroutine(result):
            result.close()
        raise TypeError(_ASYNC_CALLBACK_ERROR)

    @staticmethod
    def _validate_odds_types(chances: object, out_of: object | None) -> None:
        """Reject values outside the public numeric odds contract.

        Args:
            chances: A numeric probability or numerator.
            out_of: The optional integer opportunity count.

        Raises:
            TypeError: If either value has an unsupported type.
        """
        if isinstance(chances, bool) or not isinstance(chances, (int, float)):
            raise TypeError(_CHANCES_TYPE_ERROR)
        if out_of is not None and (
            isinstance(out_of, bool) or not isinstance(out_of, int)
        ):
            raise TypeError(_OUT_OF_TYPE_ERROR)

    @staticmethod
    def _validate_times(times: object) -> None:
        """Validate the number of repeated independent draws.

        Args:
            times: The requested number of results.

        Raises:
            ValueError: If ``times`` is not an integer or is negative.
        """
        if isinstance(times, bool) or not isinstance(times, int) or times < 0:
            raise ValueError(_TIMES_ERROR)

    @staticmethod
    def _set_forced_result(
        result: bool,
        callback: Callable[[], object] | None,
    ) -> None:
        """Set an outcome persistently or scope it around one callback.

        Args:
            result: The forced outcome to install.
            callback: The optional operation to run under the override.

        Raises:
            TypeError: If a synchronous callback returns an awaitable.
        """

        def factory_for_result(
            _chances: int | float,
            _out_of: int | None,
        ) -> bool:
            """Return the fixed outcome for any configured lottery odds.

            Args:
                _chances: Ignored configured probability.
                _out_of: Ignored opportunity count.

            Returns:
                The forced result.
            """
            return result

        factory: ResultFactory = factory_for_result
        if callback is None:
            _RESULT_FACTORY.set(factory)
            return
        token: Token[ResultFactory | None] = _RESULT_FACTORY.set(factory)
        try:
            callback_result = callback()
            Lottery._reject_awaitable(callback_result)
        finally:
            _RESULT_FACTORY.reset(token)


__all__ = ["Lottery", "ResultFactory"]
