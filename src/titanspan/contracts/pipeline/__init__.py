"""Define typed stage boundaries for ordered Pipeline execution.

Concrete stage resolution and execution remain owned by Pipeline.
"""

from collections.abc import Awaitable, Callable

type PipelineContinuation[InputT, OutputT] = Callable[
    [InputT],
    OutputT,
]
type AsyncPipelineContinuation[InputT, OutputT] = Callable[
    [InputT],
    Awaitable[OutputT],
]
type PipelineMiddlewareHandler[InputT, OutputT] = Callable[
    [InputT, PipelineContinuation[InputT, OutputT]],
    OutputT,
]
type AsyncPipelineMiddlewareHandler[InputT, OutputT] = Callable[
    [InputT, AsyncPipelineContinuation[InputT, OutputT]],
    Awaitable[OutputT],
]


__all__ = [
    "AsyncPipelineContinuation",
    "AsyncPipelineMiddlewareHandler",
    "PipelineContinuation",
    "PipelineMiddlewareHandler",
]
