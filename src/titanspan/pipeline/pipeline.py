"""Run ordered synchronous and asynchronous application stages.

Stages execute sequentially; the caller owns the supplied value and any
resources acquired by stage implementations.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from titanspan.pipeline.exceptions import PipelineExecutionError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable

    from titanspan.contracts.container import ServiceContainer
    from titanspan.contracts.pipeline import (
        AsyncPipelineMiddlewareHandler,
        PipelineMiddlewareHandler,
    )

_UNSET = object()
_VALUE_REQUIRED_ERROR = "Send a value before executing a pipeline."
_MIDDLEWARE_MODE_ERROR = (
    "Pipeline middleware requires a handler for the selected execution mode."
)
_SYNC_AWAITABLE_ERROR = (
    "A synchronous pipeline stage returned an awaitable. "
    "Use then_return_async or then_async."
)
_INVALID_STAGE_ERROR = (
    "Pipeline stages must be callable, expose handle, or use stage_method."
)
_INVALID_STAGE_METHOD_ERROR = "A pipeline stage method must be callable."
_EMPTY_STAGE_METHOD_ERROR = "A pipeline stage method name cannot be empty."
_EMPTY_MIDDLEWARE_ERROR = (
    "Pipeline middleware requires a sync or async handler."
)


@dataclass(frozen=True, slots=True)
class ContinuationStage[InputT, OutputT]:
    """Wrap sync and async continuation handlers for explicit middleware.

    Attributes:
        sync_handler: Optional sync handler receiving its continuation.
        async_handler: Optional async handler receiving its continuation.
    """

    sync_handler: PipelineMiddlewareHandler[InputT, OutputT] | None = None
    async_handler: AsyncPipelineMiddlewareHandler[InputT, OutputT] | None = None

    def __post_init__(self) -> None:
        """Require at least one supported execution handler.

        Raises:
            ValueError: If both handler variants are missing.
        """
        if self.sync_handler is None and self.async_handler is None:
            raise ValueError(_EMPTY_MIDDLEWARE_ERROR)


@dataclass(frozen=True, slots=True)
class StageMethod[InputT, OutputT]:
    """Select one explicit method on a stage object or resolved class.

    Attributes:
        stage: Instance or class resolved by the optional container.
        method: Public method invoked with the current pipeline value.
    """

    stage: object
    method: str

    def __post_init__(self) -> None:
        """Reject method selectors that cannot name a callable attribute.

        Raises:
            ValueError: If the method name is empty.
        """
        if not self.method:
            raise ValueError(_EMPTY_STAGE_METHOD_ERROR)


class Pipeline[InputT, OutputT]:
    """Build and execute an immutable ordered processing pipeline.

    A pipeline can be reused with its original input and stages. ``pipe``
    preserves type inference for one transform; ``through`` accepts a
    heterogeneous stage sequence under the declared output type.
    """

    __slots__ = ("_container", "_stages", "_value")

    def __init__(
        self,
        *,
        container: ServiceContainer | None = None,
        _stages: tuple[object, ...] = (),
        _value: object = _UNSET,
    ) -> None:
        """Create an empty pipeline with optional class-stage resolution.

        Args:
            container: Native container used to construct class stages.
            _stages: Existing immutable stage snapshot for fluent copies.
            _value: Existing input snapshot for fluent copies.
        """
        self._container = container
        self._stages = tuple(_stages)
        self._value = _value

    def send(self, value: InputT) -> Pipeline[InputT, OutputT]:
        """Set the value that enters the first stage.

        Args:
            value: Value supplied to the ordered stage sequence.

        Returns:
            A new pipeline builder with the same stage snapshot.
        """
        return self._copy(value=value)

    def through(
        self,
        stages: Iterable[object],
    ) -> Pipeline[InputT, OutputT]:
        """Append an ordered sequence of heterogeneous processing stages.

        Args:
            stages: Callables, stage instances, class stages, or wrappers.

        Returns:
            A new pipeline builder with the appended stage snapshot.
        """
        return self._copy(stages=(*self._stages, *tuple(stages)))

    def pipe[NextT](
        self,
        stage: Callable[[OutputT], NextT],
    ) -> Pipeline[InputT, NextT]:
        """Append one synchronous value transform with inferred output type.

        Args:
            stage: Callable that transforms the current output value.

        Returns:
            A builder whose output type is inferred from the transform.
        """
        return Pipeline(
            container=self._container,
            _stages=(*self._stages, stage),
            _value=self._value,
        )

    def pipe_async[NextT](
        self,
        stage: Callable[[OutputT], Awaitable[NextT]],
    ) -> Pipeline[InputT, NextT]:
        """Append one async transform with inferred output typing.

        Args:
            stage: Async callable that transforms the current output value.

        Returns:
            A builder whose output type is inferred from the transform.
        """
        return Pipeline(
            container=self._container,
            _stages=(*self._stages, stage),
            _value=self._value,
        )

    def when(
        self,
        condition: bool,
        stages: Iterable[object],
    ) -> Pipeline[InputT, OutputT]:
        """Append stages only when a construction-time condition is true.

        Args:
            condition: Boolean that controls whether the stages are included.
            stages: Ordered stages added when ``condition`` is true.

        Returns:
            A new builder with the selected stage sequence.
        """
        return self.through(stages) if condition else self

    @staticmethod
    def middleware[StageInputT, StageOutputT](
        handler: PipelineMiddlewareHandler[StageInputT, StageOutputT],
    ) -> ContinuationStage[StageInputT, StageOutputT]:
        """Wrap a synchronous stage that controls the continuation.

        Args:
            handler: Function receiving the current value and next stage.

        Returns:
            An explicit continuation stage.
        """
        return ContinuationStage(sync_handler=handler)

    @staticmethod
    def middleware_async[StageInputT, StageOutputT](
        handler: AsyncPipelineMiddlewareHandler[StageInputT, StageOutputT],
    ) -> ContinuationStage[StageInputT, StageOutputT]:
        """Wrap an asynchronous stage that controls the continuation.

        Args:
            handler: Async function receiving the value and next stage.

        Returns:
            An explicit asynchronous continuation stage.
        """
        return ContinuationStage(async_handler=handler)

    @staticmethod
    def stage_method(
        stage: object,
        method: str,
    ) -> StageMethod[object, object]:
        """Select a named method on an instance or container-resolved class.

        Args:
            stage: Stage instance or class to resolve during execution.
            method: Public sync or async method name.

        Returns:
            A typed method selector accepted by ``through``.
        """
        return StageMethod(stage, method)

    def then[ResultT](
        self,
        destination: Callable[[OutputT], ResultT],
    ) -> ResultT:
        """Run a synchronous final destination after all stages.

        Args:
            destination: Callback receiving the final transformed value.

        Returns:
            The callback result.

        Raises:
            PipelineExecutionError: If execution requires async operations.
        """
        value = self._run_sync()
        return cast("ResultT", _require_sync_result(destination(value)))

    def then_return(self) -> OutputT:
        """Run synchronously and return the final value.

        Returns:
            The value produced by the final stage.

        Raises:
            PipelineExecutionError: If the input is missing or async work is
                encountered.
        """
        return self._run_sync()

    async def then_async[ResultT](
        self,
        destination: Callable[[OutputT], ResultT | Awaitable[ResultT]],
    ) -> ResultT:
        """Run stages and a final destination through explicit async execution.

        Args:
            destination: Sync or async callback receiving the final value.

        Returns:
            The resolved callback result.

        Raises:
            PipelineExecutionError: If the pipeline input was not set.
        """
        value = await self._run_async()
        result = destination(value)
        if inspect.isawaitable(result):
            return await cast("Awaitable[ResultT]", result)
        return cast("ResultT", result)

    async def then_return_async(self) -> OutputT:
        """Run the ordered sequence with explicit async execution.

        Returns:
            The value produced by the final stage.

        Raises:
            PipelineExecutionError: If the pipeline input was not set.
        """
        return await self._run_async()

    def _copy(
        self,
        *,
        stages: tuple[object, ...] | None = None,
        value: object = _UNSET,
    ) -> Pipeline[InputT, OutputT]:
        """Create an independent builder sharing only caller-owned values.

        Args:
            stages: Optional replacement stage tuple.
            value: Optional replacement input value.

        Returns:
            A new pipeline builder preserving its generic boundary.
        """
        return Pipeline(
            container=self._container,
            _stages=self._stages if stages is None else stages,
            _value=self._value if value is _UNSET else value,
        )

    def _run_sync(self) -> OutputT:
        """Execute all stages without creating or blocking an event loop.

        Returns:
            The final pipeline value.

        Raises:
            PipelineExecutionError: If the input is missing or an async stage
                is encountered.
        """
        if self._value is _UNSET:
            raise PipelineExecutionError(_VALUE_REQUIRED_ERROR)
        result = _run_sync_stages(
            self._stages,
            start=0,
            value=self._value,
            container=self._container,
        )
        return cast("OutputT", result)

    async def _run_async(self) -> OutputT:
        """Execute stages sequentially while propagating cancellation.

        Returns:
            The final pipeline value.

        Raises:
            PipelineExecutionError: If the input is missing.
        """
        if self._value is _UNSET:
            raise PipelineExecutionError(_VALUE_REQUIRED_ERROR)
        result = await _run_async_stages(
            self._stages,
            start=0,
            value=self._value,
            container=self._container,
        )
        return cast("OutputT", result)

    _container: ServiceContainer | None
    _stages: tuple[object, ...]
    _value: object


def _run_sync_stages(
    stages: tuple[object, ...],
    *,
    start: int,
    value: object,
    container: ServiceContainer | None,
) -> object:
    """Run simple stages iteratively and middleware continuations recursively.

    Args:
        stages: Immutable stage sequence.
        start: First stage index in this segment.
        value: Value entering this segment.
        container: Optional stage resolver.

    Returns:
        The final value or middleware short-circuit result.
    """
    for index in range(start, len(stages)):
        stage = stages[index]
        if isinstance(stage, ContinuationStage):
            continuation = cast(
                "ContinuationStage[object, object]",
                stage,
            )
            handler = continuation.sync_handler
            if handler is None:
                raise PipelineExecutionError(_MIDDLEWARE_MODE_ERROR)

            def continue_sync(
                next_value: object,
                *,
                next_index: int = index + 1,
            ) -> object:
                """Run remaining stages for one continuation value.

                Args:
                    next_value: Value supplied by the current middleware.
                    next_index: Index of the first downstream stage.

                Returns:
                    The downstream pipeline value.
                """
                return _run_sync_stages(
                    stages,
                    start=next_index,
                    value=next_value,
                    container=container,
                )

            result = handler(value, continue_sync)
            return _require_sync_result(result)

        method = stage.method if isinstance(stage, StageMethod) else None
        selected_stage = (
            stage.stage if isinstance(stage, StageMethod) else stage
        )
        target = _resolve_stage_sync(selected_stage, container)
        callback = _stage_callable(target, method)
        value = _require_sync_result(callback(value))
    return value


async def _run_async_stages(
    stages: tuple[object, ...],
    *,
    start: int,
    value: object,
    container: ServiceContainer | None,
) -> object:
    """Run simple stages iteratively and async continuations sequentially.

    Args:
        stages: Immutable stage sequence.
        start: First stage index in this segment.
        value: Value entering this segment.
        container: Optional stage resolver.

    Returns:
        The final value or middleware short-circuit result.
    """
    for index in range(start, len(stages)):
        stage = stages[index]
        if isinstance(stage, ContinuationStage):
            continuation = cast(
                "ContinuationStage[object, object]",
                stage,
            )
            handler = continuation.async_handler
            if handler is None:
                raise PipelineExecutionError(_MIDDLEWARE_MODE_ERROR)

            async def continue_async(
                next_value: object,
                *,
                next_index: int = index + 1,
            ) -> object:
                """Run remaining stages for one continuation value.

                Args:
                    next_value: Value supplied by the current middleware.
                    next_index: Index of the first downstream stage.

                Returns:
                    The downstream pipeline value.
                """
                return await _run_async_stages(
                    stages,
                    start=next_index,
                    value=next_value,
                    container=container,
                )

            result = handler(value, continue_async)
            return await _resolve_async_result(result)

        method = stage.method if isinstance(stage, StageMethod) else None
        selected_stage = (
            stage.stage if isinstance(stage, StageMethod) else stage
        )
        target = await _resolve_stage_async(selected_stage, container)
        callback = _stage_callable(target, method)
        value = await _resolve_async_result(callback(value))
    return value


def _resolve_stage_sync(
    stage: object,
    container: ServiceContainer | None,
) -> object:
    """Resolve a class stage with sync-safe container construction.

    Args:
        stage: Class or already constructed stage object.
        container: Optional application container.

    Returns:
        A stage instance ready for invocation.
    """
    if not inspect.isclass(stage):
        return stage
    stage_class = stage
    if container is not None:
        return container.make(stage_class)
    return stage_class()


async def _resolve_stage_async(
    stage: object,
    container: ServiceContainer | None,
) -> object:
    """Resolve a class stage through the explicit async container boundary.

    Args:
        stage: Class or already constructed stage object.
        container: Optional application container.

    Returns:
        A stage instance ready for invocation.
    """
    if not inspect.isclass(stage):
        return stage
    stage_class = stage
    if container is not None:
        return await container.make_async(stage_class)
    return stage_class()


def _stage_callable(
    stage: object,
    method: str | None,
) -> Callable[[object], object]:
    """Select an explicit method, a stage handle, or a direct callable.

    Args:
        stage: Resolved stage object.
        method: Optional caller-selected stage method.

    Returns:
        One unary callback that processes the current value.

    Raises:
        PipelineExecutionError: If no callable stage operation exists.
    """
    selected: object | None
    if method is not None:
        selected = getattr(stage, method, None)
    else:
        selected = getattr(stage, "handle", None)
        if not callable(selected):
            selected = stage
    if not callable(selected):
        raise PipelineExecutionError(_INVALID_STAGE_ERROR)
    return cast("Callable[[object], object]", selected)


def _require_sync_result(result: object) -> object:
    """Reject awaitables without starting an event loop or leaking coroutines.

    Args:
        result: Callback result.

    Returns:
        The result when it is safe for synchronous execution.

    Raises:
        PipelineExecutionError: If the callback returned an awaitable.
    """
    if inspect.isawaitable(result):
        if inspect.iscoroutine(result):
            result.close()
        raise PipelineExecutionError(_SYNC_AWAITABLE_ERROR)
    return result


async def _resolve_async_result(result: object) -> object:
    """Await a stage result only during explicit asynchronous execution.

    Args:
        result: Direct value or awaitable returned by a stage.

    Returns:
        The resolved value.
    """
    if inspect.isawaitable(result):
        return await cast("Awaitable[object]", result)
    return result


__all__ = ["ContinuationStage", "Pipeline", "StageMethod"]
