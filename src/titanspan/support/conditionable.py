"""Provide conditional fluent operations for support objects.

Synchronous callbacks remain synchronous. Explicit async variants await
async conditions and callbacks and preserve cancellation propagation.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Self, cast

from titanspan.support.exceptions import AsyncCallbackUsageError

type Condition[T] = object | Callable[[T], object]
type Callback[T] = Callable[[T, object], object]
type AsyncResult = object | Awaitable[object]
CONDITION_SOURCE = "condition"
CALLBACK_SOURCE = "callback"


def _resolve_sync[T](
    target: T,
    condition: object | Callable[[T], object],
) -> object:
    """Resolve a direct or callable condition without creating an event loop.

    Args:
        target: The object receiving the condition operation.
        condition: A value or a synchronous callback that computes one.

    Returns:
        The resolved condition value.

    Raises:
        TypeError: If the callback returns an awaitable.
    """
    result = condition(target) if callable(condition) else condition
    if inspect.isawaitable(result):
        if inspect.iscoroutine(result):
            result.close()
        raise AsyncCallbackUsageError(
            CONDITION_SOURCE,
            "when_async or unless_async",
        )
    return result


def _sync_result(result: object) -> object:
    """Reject accidental asynchronous callback results in sync methods.

    Args:
        result: The synchronous callback result.

    Returns:
        The original result when it is synchronous.

    Raises:
        TypeError: If the callback returned an awaitable.
    """
    if inspect.isawaitable(result):
        if inspect.iscoroutine(result):
            result.close()
        raise AsyncCallbackUsageError(
            CALLBACK_SOURCE,
            "when_async or unless_async",
        )
    return result


async def _resolve_async[T](
    target: T,
    condition: object | Callable[[T], object],
) -> object:
    """Resolve direct, synchronous, or asynchronous condition values.

    Args:
        target: The object receiving the condition operation.
        condition: A value or callback that may return an awaitable.

    Returns:
        The resolved condition value.
    """
    result = condition(target) if callable(condition) else condition
    if inspect.isawaitable(result):
        return await cast("Awaitable[object]", result)
    return result


async def _async_result(result: AsyncResult) -> object:
    """Await a callback result when required.

    Args:
        result: A direct value or awaitable callback result.

    Returns:
        The resolved callback result.
    """
    if inspect.isawaitable(result):
        return await cast("Awaitable[object]", result)
    return result


class Conditionable:
    """Apply callbacks when a direct or computed condition matches.

    The mixin provides ``when`` and ``unless`` methods and explicit
    asynchronous counterparts. Callback results replace the target unless
    they are ``None``, in which case fluent chaining continues with self.

    Notes:
        Laravel's higher-order proxy form (for example ``when().method``)
        is not part of this initial Python implementation.
    """

    def when(
        self,
        value: Condition[Self],
        callback: Callback[Self] | None = None,
        default: Callback[Self] | None = None,
    ) -> Self | object:
        """Run a callback when the resolved condition is truthy.

        Args:
            value: A condition or a callback receiving this instance.
            callback: The callback for a truthy condition.
            default: The callback for a false condition.

        Returns:
            The callback result, or this instance when no result is given.

        Raises:
            TypeError: If a condition or callback returns an awaitable.
        """
        resolved = _resolve_sync(self, value)
        selected = callback if resolved else default
        if selected is None:
            return self
        result = _sync_result(selected(self, resolved))
        return self if result is None else result

    def unless(
        self,
        value: Condition[Self],
        callback: Callback[Self] | None = None,
        default: Callback[Self] | None = None,
    ) -> Self | object:
        """Run a callback when the resolved condition is falsy.

        Args:
            value: A condition or a callback receiving this instance.
            callback: The callback for a false condition.
            default: The callback for a truthy condition.

        Returns:
            The callback result, or this instance when no result is given.

        Raises:
            TypeError: If a condition or callback returns an awaitable.
        """
        resolved = _resolve_sync(self, value)
        selected = default if resolved else callback
        if selected is None:
            return self
        result = _sync_result(selected(self, resolved))
        return self if result is None else result

    async def when_async(
        self,
        value: Condition[Self],
        callback: Callback[Self] | None = None,
        default: Callback[Self] | None = None,
    ) -> Self | object:
        """Run and await the callback selected by a truthy condition.

        Args:
            value: A value or callback that may produce an awaitable.
            callback: The callback for a truthy condition.
            default: The callback for a false condition.

        Returns:
            The resolved callback result, or this instance for ``None``.
        """
        resolved = await _resolve_async(self, value)
        selected = callback if resolved else default
        if selected is None:
            return self
        result = await _async_result(selected(self, resolved))
        return self if result is None else result

    async def unless_async(
        self,
        value: Condition[Self],
        callback: Callback[Self] | None = None,
        default: Callback[Self] | None = None,
    ) -> Self | object:
        """Run and await the callback selected by a falsy condition.

        Args:
            value: A value or callback that may produce an awaitable.
            callback: The callback for a false condition.
            default: The callback for a truthy condition.

        Returns:
            The resolved callback result, or this instance for ``None``.
        """
        resolved = await _resolve_async(self, value)
        selected = default if resolved else callback
        if selected is None:
            return self
        result = await _async_result(selected(self, resolved))
        return self if result is None else result

    whenAsync = when_async
    unlessAsync = unless_async


__all__ = ["Condition", "Conditionable"]
