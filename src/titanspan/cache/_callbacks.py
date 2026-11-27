"""Run supported cache callback shapes without blocking async callers.

AnyIO owns worker-thread execution and propagates the active context.
"""

from __future__ import annotations

from inspect import isawaitable, iscoroutinefunction
from typing import TYPE_CHECKING, cast

import anyio

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


async def invoke_async[ResultT](
    callback: Callable[[], ResultT | Awaitable[ResultT]],
) -> ResultT:
    """Run async callbacks on-loop and sync callbacks in an AnyIO worker.

    Args:
        callback: Zero-argument callback accepted by an async cache API.

    Returns:
        The callback result after awaiting any produced awaitable.
    """
    if _is_async_callable(callback):
        result = callback()
    else:
        result = await anyio.to_thread.run_sync(callback)
    if isawaitable(result):
        return await cast("Awaitable[ResultT]", result)
    return cast("ResultT", result)


def _is_async_callable(callback: Callable[..., object]) -> bool:
    """Recognize async functions and callable instances.
    """  # fmt: skip
    if iscoroutinefunction(callback):
        return True
    return iscoroutinefunction(callback.__call__)


__all__ = ["invoke_async"]
