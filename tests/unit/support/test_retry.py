"""Verify bounded retry helpers and their cancellation semantics.

The tests cover attempt numbering, per-attempt delays, retry predicates,
exception propagation, validation, and asynchronous cancellation.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, cast

import anyio
import pytest

from titanspan.support import helpers as support_helpers
from titanspan.support import retry, retry_async
from titanspan.support.exceptions import (
    InvalidRetryConfigurationError,
    InvalidRetryConfigurationTypeError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

EXPECTED_ATTEMPTS = 3
FIRST_DELAY_SECONDS = 0.01
SECOND_DELAY_SECONDS = 0.02


class TemporaryFailureError(Exception):
    """Represent a retryable failure without relying on message contents.

    This dedicated exception keeps retry behavior assertions separate from
    exception string formatting.
    """


@pytest.mark.unit
def test_retry_passes_attempt_number_and_returns_success() -> None:
    """Retry until success and pass one-based attempt numbers.

    Returns:
        None.
    """
    attempts: list[int] = []

    def operation(attempt: int) -> str:
        """Fail twice before returning a successful value.

        Args:
            attempt: The current one-based attempt number.

        Returns:
            The successful result.

        Raises:
            TemporaryFailureError: While another retry remains.
        """
        attempts.append(attempt)
        if attempt < EXPECTED_ATTEMPTS:
            raise TemporaryFailureError
        return "complete"

    assert retry(EXPECTED_ATTEMPTS, operation) == "complete"
    assert attempts == [1, 2, 3]


@pytest.mark.unit
def test_retry_uses_backoff_schedule_and_callable_delays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use each sequence delay for the corresponding failed attempt.

    Args:
        monkeypatch: Pytest fixture for replacing the sleep boundary.

    Returns:
        None.
    """
    delays: list[float] = []
    monkeypatch.setattr(
        support_helpers,
        "_retry_sleep",
        delays.append,
    )

    def operation(attempt: int) -> str:
        """Fail once so the configured delay is observed.

        Args:
            attempt: The current one-based attempt number.

        Returns:
            The successful result.

        Raises:
            TemporaryFailureError: On the first attempt.
        """
        if attempt == 1:
            raise TemporaryFailureError
        return "complete"

    assert retry([10, 20], operation) == "complete"
    assert delays == [FIRST_DELAY_SECONDS]


@pytest.mark.unit
def test_retry_applies_scalar_delay_through_the_sync_sleep_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Convert scalar millisecond delays before calling the sleep function.

    Args:
        monkeypatch: Pytest fixture for replacing the standard sleep call.

    Returns:
        None.
    """
    delays: list[float] = []
    monkeypatch.setattr(support_helpers.time, "sleep", delays.append)

    def operation(attempt: int) -> str:
        """Fail once so the scalar delay is applied.

        Args:
            attempt: The current one-based attempt number.

        Returns:
            The successful result.

        Raises:
            TemporaryFailureError: On the first attempt.
        """
        if attempt == 1:
            raise TemporaryFailureError
        return "complete"

    assert retry(2, operation, sleep_milliseconds=10) == "complete"
    assert delays == [FIRST_DELAY_SECONDS]


@pytest.mark.unit
def test_retry_supports_dynamic_timedelta_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve a per-attempt duration from the raised exception.

    Args:
        monkeypatch: Pytest fixture for replacing the sleep boundary.

    Returns:
        None.
    """
    delays: list[float] = []
    monkeypatch.setattr(
        support_helpers,
        "_retry_sleep",
        delays.append,
    )

    def delay(attempt: int, error: Exception) -> timedelta:
        """Return a delay based on the retry number.

        Args:
            attempt: The failed attempt number.
            error: The exception raised by the operation.

        Returns:
            A duration in seconds.
        """
        assert isinstance(error, TemporaryFailureError)
        return timedelta(milliseconds=attempt * 10)

    def operation(attempt: int) -> str:
        """Raise once so the dynamic delay is evaluated.

        Args:
            attempt: The current one-based attempt number.

        Returns:
            The successful result.

        Raises:
            TemporaryFailureError: On the first attempt.
        """
        if attempt == 1:
            raise TemporaryFailureError
        return "complete"

    assert retry(2, operation, sleep_milliseconds=delay) == "complete"
    assert delays == [FIRST_DELAY_SECONDS]


@pytest.mark.unit
def test_retry_when_predicate_stops_and_preserves_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reraise the source exception when the predicate declines retry.

    Args:
        monkeypatch: Pytest fixture for replacing the sleep boundary.

    Returns:
        None.
    """
    predicate_calls: list[Exception] = []
    delays: list[float] = []
    monkeypatch.setattr(
        support_helpers,
        "_retry_sleep",
        delays.append,
    )

    def should_retry(error: Exception) -> bool:
        """Record the error and stop the retry loop.

        Args:
            error: The operation's failure.

        Returns:
            Whether the operation should be retried.
        """
        predicate_calls.append(error)
        return False

    failure = TemporaryFailureError()

    def operation(_attempt: int) -> str:
        """Always raise the same failure instance.

        Args:
            attempt: The current one-based attempt number.

        Returns:
            This operation never returns.

        Raises:
            TemporaryFailureError: The preserved source failure.
        """
        raise failure

    with pytest.raises(TemporaryFailureError) as raised:
        retry(
            4,
            operation,
            sleep_milliseconds=25,
            when=should_retry,
        )

    assert raised.value is failure
    assert len(predicate_calls) == 1
    assert delays == []


@pytest.mark.unit
def test_retry_runs_again_when_predicate_approves_exception() -> None:
    """Retry only the exceptions accepted by the supplied predicate.

    Returns:
        None.
    """
    attempts: list[int] = []
    predicate_errors: list[Exception] = []

    def should_retry(error: Exception) -> bool:
        """Record the operation failure and allow another attempt.

        Args:
            error: The operation's failure.

        Returns:
            Whether the operation should be retried.
        """
        predicate_errors.append(error)
        return True

    def operation(attempt: int) -> str:
        """Fail once before returning a result.

        Args:
            attempt: The current one-based attempt number.

        Returns:
            The successful result.

        Raises:
            TemporaryFailureError: On the first attempt.
        """
        attempts.append(attempt)
        if attempt == 1:
            raise TemporaryFailureError
        return "complete"

    assert retry(2, operation, when=should_retry) == "complete"
    assert attempts == [1, 2]
    assert len(predicate_errors) == 1


@pytest.mark.unit
def test_retry_does_not_call_predicate_after_final_attempt() -> None:
    """Avoid evaluating the retry predicate after attempts are exhausted.

    Returns:
        None.
    """
    predicate_calls: list[Exception] = []

    def should_retry(error: Exception) -> bool:
        """Record predicate evaluation and permit another attempt.

        Args:
            error: The operation's failure.

        Returns:
            Whether the operation should be retried.
        """
        predicate_calls.append(error)
        return True

    def operation(_attempt: int) -> str:
        """Always fail to exhaust the configured attempts.

        Args:
            attempt: The current one-based attempt number.

        Returns:
            This operation never returns.

        Raises:
            TemporaryFailureError: The operation's failure.
        """
        raise TemporaryFailureError

    with pytest.raises(TemporaryFailureError):
        retry(2, operation, when=should_retry)

    assert len(predicate_calls) == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    ("times", "error_type"),
    [
        (True, InvalidRetryConfigurationTypeError),
        (1.5, InvalidRetryConfigurationTypeError),
        ("3", InvalidRetryConfigurationTypeError),
        (b"3", InvalidRetryConfigurationTypeError),
        (["10"], InvalidRetryConfigurationTypeError),
        ([-1], InvalidRetryConfigurationError),
    ],
)
def test_retry_rejects_invalid_attempt_counts(
    times: object,
    error_type: type[Exception],
) -> None:
    """Reject invalid attempt counts and negative delay schedules.

    Args:
        times: The invalid attempt count or delay schedule.
        error_type: The expected validation exception class.

    Returns:
        None.
    """

    def callback(_attempt: int) -> str:
        """Return a fixed value without using retry input.

        Args:
            _attempt: The attempt number supplied by retry.

        Returns:
            An unused fixed value.
        """
        return "unused"

    retry_times = cast("int | Sequence[int]", times)

    with pytest.raises(error_type):
        retry(retry_times, callback)


@pytest.mark.unit
@pytest.mark.parametrize("times", [0, -1, []])
def test_retry_runs_once_for_empty_attempt_configuration(
    times: int | list[int],
) -> None:
    """Preserve the upstream first-call behavior for empty limits.

    Args:
        times: An attempt count or empty backoff schedule.

    Returns:
        None.
    """
    attempts: list[int] = []

    def operation(attempt: int) -> str:
        """Record the one permitted callback execution.

        Args:
            attempt: The current one-based attempt number.

        Returns:
            The successful result.
        """
        attempts.append(attempt)
        return "complete"

    assert retry(times, operation) == "complete"
    assert attempts == [1]


@pytest.mark.unit
def test_retry_rejects_async_callbacks_in_the_sync_api() -> None:
    """Close an awaitable instead of silently running it synchronously.

    Returns:
        None.
    """

    async def operation(attempt: int) -> str:
        """Return a coroutine that the synchronous API must reject.

        Args:
            attempt: The current one-based attempt number.

        Returns:
            A value that would be returned after awaiting.
        """
        return str(attempt)

    callback = cast("Callable[[int], object]", operation)

    with pytest.raises(TypeError, match="awaitable"):
        retry(3, callback)


@pytest.mark.unit
def test_retry_rejects_negative_dynamic_delays() -> None:
    """Reject a negative sleep duration when backoff is evaluated.

    Returns:
        None.
    """

    def operation(_attempt: int) -> str:
        """Fail to trigger delay validation.

        Returns:
            This operation never returns.

        Raises:
            TemporaryFailureError: The retryable operation failure.
        """
        raise TemporaryFailureError

    with pytest.raises(InvalidRetryConfigurationError):
        retry(2, operation, sleep_milliseconds=-1)


@pytest.mark.unit
@pytest.mark.parametrize("delay", [True, 1.5])
def test_retry_rejects_dynamic_delays_with_unsupported_types(
    delay: object,
) -> None:
    """Reject callback delay values outside the documented contract.

    Args:
        delay: A boolean or floating-point value that is not supported.

    Returns:
        None.
    """

    def operation(_attempt: int) -> str:
        """Fail to trigger delay validation.

        Returns:
            This operation never returns.

        Raises:
            TemporaryFailureError: The retryable operation failure.
        """
        raise TemporaryFailureError

    def invalid_delay(_attempt: int, _error: Exception) -> int:
        """Return an invalid runtime value to exercise validation.

        Args:
            _attempt: The failed attempt number.
            _error: The operation exception.

        Returns:
            An unsupported runtime value cast to the declared type.
        """
        return cast("int", delay)

    with pytest.raises(InvalidRetryConfigurationTypeError):
        retry(2, operation, sleep_milliseconds=invalid_delay)


@pytest.mark.unit
def test_retry_rejects_non_callable_predicate_before_invocation() -> None:
    """Validate synchronous retry predicates before invoking the operation.

    Returns:
        None.
    """
    callback = cast("Callable[[int], str]", str)
    predicate = cast("Callable[[Exception], bool]", object())

    with pytest.raises(InvalidRetryConfigurationTypeError):
        retry(2, callback, when=predicate)


@pytest.mark.unit
@pytest.mark.anyio
async def test_retry_async_rejects_non_callable_predicate() -> None:
    """Validate asynchronous retry predicates before invocation.

    Returns:
        None.
    """

    async def operation(attempt: int) -> str:
        """Return the attempt number as text.

        Args:
            attempt: The current attempt number.

        Returns:
            The attempt number formatted as text.
        """
        return str(attempt)

    predicate = cast("Callable[[Exception], bool]", object())

    with pytest.raises(InvalidRetryConfigurationTypeError):
        await retry_async(2, operation, when=predicate)


@pytest.mark.unit
@pytest.mark.anyio
async def test_retry_async_retries_and_uses_async_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry coroutine failures without blocking the event loop.

    Args:
        monkeypatch: Pytest fixture for replacing the async sleep boundary.

    Returns:
        None.
    """
    attempts: list[int] = []
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        """Record delay requests and yield control to the scheduler.

        Args:
            delay: The requested duration in seconds.

        Returns:
            None.
        """
        delays.append(delay)
        await anyio.lowlevel.checkpoint()

    monkeypatch.setattr(
        support_helpers.anyio,
        "sleep",
        fake_sleep,
    )

    async def operation(attempt: int) -> str:
        """Fail twice before returning a successful result.

        Args:
            attempt: The current one-based attempt number.

        Returns:
            The successful result.

        Raises:
            TemporaryFailureError: While another retry remains.
        """
        attempts.append(attempt)
        if attempt < EXPECTED_ATTEMPTS:
            raise TemporaryFailureError
        return "complete"

    assert (
        await retry_async(
            [10, 20],
            operation,
        )
        == "complete"
    )
    assert attempts == [1, 2, 3]
    assert delays == [FIRST_DELAY_SECONDS, SECOND_DELAY_SECONDS]


@pytest.mark.unit
@pytest.mark.anyio
async def test_retry_async_skips_sleep_for_zero_delay() -> None:
    """Retry immediately when the configured delay is zero.

    Returns:
        None.
    """
    attempts: list[int] = []

    async def operation(attempt: int) -> str:
        """Fail once before returning a successful value.

        Args:
            attempt: The current one-based attempt number.

        Returns:
            The successful result.

        Raises:
            TemporaryFailureError: On the first attempt.
        """
        attempts.append(attempt)
        if attempt == 1:
            raise TemporaryFailureError
        return "complete"

    assert await retry_async(2, operation) == "complete"
    assert attempts == [1, 2]


@pytest.mark.unit
@pytest.mark.anyio
async def test_retry_async_does_not_swallow_cancellation() -> None:
    """Propagate task cancellation without invoking retry policy.

    Returns:
        None.
    """
    attempts: list[int] = []

    async def operation(attempt: int) -> str:
        """Raise cancellation immediately.

        Args:
            attempt: The current one-based attempt number.

        Returns:
            This operation never returns.
        """
        attempts.append(attempt)
        raise asyncio.CancelledError

    callback = cast(
        "Callable[[int], Awaitable[str]]",
        operation,
    )

    with pytest.raises(asyncio.CancelledError):
        await retry_async(3, callback)

    assert attempts == [1]
