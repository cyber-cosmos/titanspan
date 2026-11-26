"""Run bounded asynchronous outgoing HTTP operations.

AnyIO owns task lifetime; completed responses transfer to the caller.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeVar, overload

import anyio

from titanspan.contracts.http import HttpClientResponse

_INVALID_CONCURRENCY_ERROR = "HTTP pool concurrency must be a positive integer."
_INVALID_TIMEOUT_ERROR = "HTTP pool timeout must be finite and positive."
_CLEANUP_ERROR_NOTE = "One or more HTTP responses failed to close."
_MISSING_POOL_RESULT_ERROR = "An HTTP pool result was not assigned."

type HttpRequestKey = str | int
type HttpPoolValue = HttpClientResponse | Exception
type HttpRequestFactory = Callable[[], Awaitable[HttpClientResponse]]
type HttpPoolInput = (
    Sequence[HttpPoolRequest] | Mapping[HttpRequestKey, HttpPoolRequest]
)
type HttpPoolOutput = (
    tuple[HttpPoolValue, ...] | Mapping[HttpRequestKey, HttpPoolValue]
)
_KeyT = TypeVar("_KeyT", str, int)


@dataclass(frozen=True, slots=True)
class HttpPoolRequest:
    """Describe one async HTTP operation and its optional time limit.

    Attributes:
        send: Zero-argument callback that performs one HTTP request.
        timeout: Optional request timeout in seconds.
    """

    send: HttpRequestFactory
    timeout: float | None = None

    def __post_init__(self) -> None:
        """Validate timeout settings before the pool starts.

        Raises:
            ValueError: If the configured timeout is not finite and positive.
        """
        if self.timeout is not None and (
            not math.isfinite(self.timeout) or self.timeout <= 0
        ):
            raise ValueError(_INVALID_TIMEOUT_ERROR)


class HttpRequestPool:
    """Execute named or indexed HTTP callbacks with bounded task fan-out.

    Workers take one input at a time from the finite request collection.
    Successful responses transfer to the caller unless fail-fast cleanup runs.
    """

    def __init__(self, max_concurrency: int) -> None:
        """Create a pool with a fixed maximum number of active operations.

        Args:
            max_concurrency: Maximum number of simultaneously active requests.

        Raises:
            ValueError: If the limit is not a positive integer.
        """
        if type(max_concurrency) is not int or max_concurrency < 1:
            raise ValueError(_INVALID_CONCURRENCY_ERROR)
        self._max_concurrency = max_concurrency

    @overload
    async def run(
        self,
        requests: Mapping[_KeyT, HttpPoolRequest],
        *,
        fail_fast: bool = True,
    ) -> Mapping[_KeyT, HttpPoolValue]:
        """Run named callbacks and preserve their key type.

        The returned mapping associates every value with its input key.
        """

    @overload
    async def run(
        self,
        requests: Sequence[HttpPoolRequest],
        *,
        fail_fast: bool = True,
    ) -> tuple[HttpPoolValue, ...]:
        """Run indexed callbacks and preserve their input order.

        Each tuple position corresponds to the same request position.
        """

    async def run(
        self,
        requests: HttpPoolInput,
        *,
        fail_fast: bool = True,
    ) -> HttpPoolOutput:
        """Run finite requests and preserve their input association.

        Args:
            requests: Ordered mapping for named results or sequence for
                position-indexed results.
            fail_fast: Cancel remaining work and raise the first failure when
                true; return exceptions beside successful results when false.

        Returns:
            A mapping with the original keys or an indexed result tuple.

        Raises:
            Exception: The first request failure in fail-fast mode.
            TypeError: If an input value is not an ``HttpPoolRequest``.
        """
        keys, tasks, is_mapping = _normalize_requests(requests)
        results: list[HttpClientResponse | None] = [None] * len(tasks)
        errors: list[Exception | None] = [None] * len(tasks)
        try:
            await _execute_workers(
                self._max_concurrency,
                tasks,
                results,
                errors,
                fail_fast,
            )
        except BaseException as error:
            cleanup_errors = await _close_responses(results)
            if cleanup_errors:
                error.add_note(_CLEANUP_ERROR_NOTE)
            raise
        failure = next(
            (error for error in errors if error is not None),
            None,
        )
        if fail_fast and failure is not None:
            cleanup_errors = await _close_responses(results)
            if cleanup_errors:
                failure.add_note(_CLEANUP_ERROR_NOTE)
            raise failure
        return _collect_results(keys, is_mapping, results, errors)

    _max_concurrency: int


def _normalize_requests(
    requests: HttpPoolInput,
) -> tuple[tuple[HttpRequestKey, ...], tuple[HttpPoolRequest, ...], bool]:
    """Preserve request association and validate each pool input.

    Args:
        requests: Mapping for named output or sequence for indexed output.

    Returns:
        Result keys, validated callbacks, and whether output is a mapping.

    Raises:
        TypeError: If a request entry is not an ``HttpPoolRequest``.
    """
    if isinstance(requests, Mapping):
        keys = tuple(requests)
        tasks = tuple(requests[key] for key in keys)
        return keys, tasks, True
    keys = tuple(range(len(requests)))
    tasks = tuple(requests)
    return keys, tasks, False


async def _execute_workers(
    max_concurrency: int,
    requests: Sequence[HttpPoolRequest],
    results: list[HttpClientResponse | None],
    errors: list[Exception | None],
    fail_fast: bool,
) -> None:
    """Run a bounded set of workers over the ordered request collection.

    Args:
        max_concurrency: Maximum active callbacks.
        requests: Validated immutable request callbacks.
        results: Mutable result slots associated with original inputs.
        errors: Mutable error slots associated with original inputs.
        fail_fast: Cancel sibling workers after the first request error.
    """
    indexes = iter(range(len(requests)))
    async with anyio.create_task_group() as task_group:
        worker_count = min(max_concurrency, len(requests))
        for worker_index in range(worker_count):
            task_group.start_soon(
                _pool_worker,
                requests,
                indexes,
                results,
                errors,
                task_group.cancel_scope,
                fail_fast,
                name=f"http-pool-worker-{worker_index}",
            )


async def _pool_worker(
    requests: Sequence[HttpPoolRequest],
    indexes: Iterator[int],
    results: list[HttpClientResponse | None],
    errors: list[Exception | None],
    cancel_scope: anyio.CancelScope,
    fail_fast: bool,
) -> None:
    """Execute assigned requests until input ends or fail-fast cancellation.

    Args:
        requests: Validated immutable request callbacks.
        indexes: Shared ordered iterator; no await occurs while advancing it.
        results: Mutable result slots associated with original inputs.
        errors: Mutable error slots associated with original inputs.
        cancel_scope: Task-group scope cancelled after a failure when enabled.
        fail_fast: Whether the first request exception cancels sibling work.
    """
    while (index := next(indexes, None)) is not None:
        task = requests[index]
        try:
            result = await _run_one(task)
        except Exception as error:
            errors[index] = error
            if fail_fast:
                cancel_scope.cancel()
        else:
            results[index] = result


async def _run_one(request: HttpPoolRequest) -> HttpClientResponse:
    """Run one request callback with its optional AnyIO deadline.

    Args:
        request: Callback and optional timeout selected by the caller.

    Returns:
        The native response transferred to the pool result.
    """
    if request.timeout is None:
        return await request.send()
    with anyio.fail_after(request.timeout):
        return await request.send()


def _collect_results(
    keys: Sequence[HttpRequestKey],
    is_mapping: bool,
    results: Sequence[HttpClientResponse | None],
    errors: Sequence[Exception | None],
) -> HttpPoolOutput:
    """Build result values while preserving the request association.

    Args:
        keys: Original mapping keys or generated sequence indices.
        is_mapping: Whether the caller supplied a mapping.
        results: Completed native responses.
        errors: Captured per-request exceptions.

    Returns:
        Mapping or tuple corresponding to the caller's input shape.

    Raises:
        RuntimeError: If a callback returned without assigning a result.
    """
    values: list[HttpPoolValue] = []
    for index, result in enumerate(results):
        error = errors[index]
        if error is not None:
            values.append(error)
        elif result is not None:
            values.append(result)
        else:
            raise RuntimeError(_MISSING_POOL_RESULT_ERROR)
    if is_mapping:
        return dict(zip(keys, values, strict=True))
    return tuple(values)


async def _close_responses(
    responses: Sequence[HttpClientResponse | None],
) -> tuple[Exception, ...]:
    """Close every successful response while shielding finalization.

    Args:
        responses: Responses completed before failure or cancellation.

    Returns:
        Cleanup errors collected after attempting every response.
    """
    failures: list[Exception] = []
    with anyio.CancelScope(shield=True):
        for response in responses:
            if response is None:
                continue
            try:
                await response.aclose()
            except Exception as error:
                failures.append(error)
    return tuple(failures)


__all__ = [
    "HttpPoolInput",
    "HttpPoolOutput",
    "HttpPoolRequest",
    "HttpPoolValue",
    "HttpRequestFactory",
    "HttpRequestKey",
    "HttpRequestPool",
]
