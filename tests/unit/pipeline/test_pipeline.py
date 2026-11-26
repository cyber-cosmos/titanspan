"""Verify ordered Pipeline stages and explicit execution paths.

The tests use native callables and the Titanspan container.
"""

from collections.abc import Awaitable, Callable

import anyio
import pytest

from titanspan.pipeline import (
    ContinuationStage,
    Pipeline,
    PipelineExecutionError,
    pipeline,
)

pytestmark = pytest.mark.unit
_PIPELINE_FAILURE = "pipeline stage failed"


def test_pipeline_runs_ordered_transforms_and_destination() -> None:
    """Pass one value through stages and then call a destination.

    Stage order and the final destination determine the returned value.
    """

    def triple(value: int) -> int:
        """Multiply the input by three for this ordered-stage check.

        Args:
            value: Integer input.

        Returns:
            The tripled integer.
        """
        return value * 3

    def label(value: int) -> str:
        """Render the integer as one item label.

        Args:
            value: Tripled integer.

        Returns:
            A stable label.
        """
        return f"item-{value}"

    result = (
        Pipeline[int, str]()
        .send(4)
        .through([triple, label])
        .then(lambda value: value.upper())
    )

    assert result == "ITEM-12"


def test_pipeline_adds_stages_immutably_and_includes_them_conditionally() -> (
    None
):
    """Retain the source builder while extending a derived pipeline.

    A false condition does not include any of its stages.
    """
    base = Pipeline[str, str]().send("ready")
    extended = base.pipe(str.upper).when(False, [str.lower])

    assert base.then_return() == "ready"
    assert extended.then_return() == "READY"


def test_pipeline_accepts_callable_objects_and_propagates_sync_errors() -> None:
    """Invoke callable stage objects and preserve stage exception identity.

    Pipeline does not wrap errors raised by application processing stages.
    """

    class AddSuffix:
        """Append a stable suffix through the instance call protocol.

        The instance is passed directly as a callable stage.
        """

        def __call__(self, value: str) -> str:
            """Add the suffix to one value.

            Args:
                value: Current pipeline value.

            Returns:
                The suffixed value.
            """
            return value + "-done"

    def fail(value: str) -> str:
        """Raise an error without changing it at the Pipeline boundary.

        Args:
            value: Value whose contents do not affect the failure.

        Raises:
            ValueError: The original processing error.
        """
        _ = value
        raise ValueError(_PIPELINE_FAILURE)

    result = (
        Pipeline[str, str]().send("work").through([AddSuffix()]).then_return()
    )

    assert result == "work-done"
    with pytest.raises(ValueError, match=_PIPELINE_FAILURE):
        Pipeline[str, str]().send("work").pipe(fail).then_return()


def test_pipeline_rejects_missing_input_and_sync_awaitables() -> None:
    """Require an input and explicit async execution for awaitable stages.

    Rejected coroutine results are closed to prevent un-awaited coroutine
    warnings.
    """

    async def uppercase(value: str) -> str:
        """Return uppercase text through an asynchronous stage.

        Args:
            value: Pipeline input.

        Returns:
            Uppercase text.
        """
        return value.upper()

    with pytest.raises(PipelineExecutionError):
        Pipeline[str, str]().then_return()

    with pytest.raises(PipelineExecutionError, match="awaitable"):
        Pipeline[str, str]().send("ready").through([uppercase]).then_return()

    with pytest.raises(ValueError, match="middleware"):
        ContinuationStage[str, str]()
    with pytest.raises(ValueError, match="method name"):
        Pipeline.stage_method(object(), "")
    with pytest.raises(PipelineExecutionError, match="callable"):
        (
            Pipeline[object, object]()
            .send(object())
            .through([object()])
            .then_return()
        )


def test_sync_pipeline_rejects_async_continuation_wrappers() -> None:
    """Require async execution when a stage owns an async continuation.

    Pipeline reports an explicit execution-mode mismatch before invocation.
    """

    async def surround(
        value: str,
        next_stage: Callable[[str], Awaitable[str]],
    ) -> str:
        """Invoke an async continuation for this mode check.

        Args:
            value: Current stage value.
            next_stage: Async callback for remaining stages.

        Returns:
            The downstream stage result.
        """
        return await next_stage(value)

    with pytest.raises(PipelineExecutionError, match="execution mode"):
        (
            Pipeline[str, str]()
            .send("ready")
            .through([Pipeline.middleware_async(surround)])
            .then_return()
        )


@pytest.mark.anyio
async def test_async_pipe_and_destination_use_async_path() -> None:
    """Infer an async transform output and resolve an async destination.

    No synchronous entrypoint creates an event loop or blocks for I/O.
    """

    async def stringify(value: int) -> str:
        """Render an integer after an async checkpoint.

        Args:
            value: Integer pipeline value.

        Returns:
            Decimal string representation.
        """
        await anyio.lowlevel.checkpoint()
        return str(value)

    async def destination(value: str) -> str:
        """Wrap a transformed value asynchronously.

        Args:
            value: String pipeline output.

        Returns:
            Wrapped value.
        """
        await anyio.lowlevel.checkpoint()
        return f"<{value}>"

    result = await (
        Pipeline[int, int]()
        .send(42)
        .pipe_async(stringify)
        .then_async(destination)
    )

    assert result == "<42>"

    sync_destination_result = await (
        Pipeline[int, int]().send(42).then_async(lambda value: str(value))
    )
    assert sync_destination_result == "42"

    class AsyncClassStage:
        """Transform values through a no-dependency async class stage.

        Pipeline constructs this class directly without a Container.
        """

        async def handle(self, value: str) -> str:
            """Uppercase text through the explicit async method.

            Args:
                value: Current pipeline text.

            Returns:
                Uppercase text.
            """
            await anyio.lowlevel.checkpoint()
            return value.upper()

    class_result = await (
        Pipeline[str, str]()
        .send("ready")
        .through([AsyncClassStage])
        .then_return_async()
    )
    assert class_result == "READY"


def test_pipeline_short_circuits_with_explicit_continuation() -> None:
    """Allow continuation middleware to transform or stop the pipeline.

    A middleware may return without invoking the next stage.
    """
    calls: list[str] = []

    def stop(
        value: str,
        next_stage: Callable[[str], str],
    ) -> str:
        """Return a short-circuit response without continuing.

        The function records that downstream processing did not start.
        """
        _ = next_stage
        return value + "-stopped"

    def downstream(value: str) -> str:
        """Record a continuation that the middleware intentionally skips.

        The return value makes accidental execution observable.
        """
        calls.append(value)
        return value + "-continued"

    result = (
        Pipeline[str, str]()
        .send("input")
        .through([Pipeline.middleware(stop), downstream])
        .then_return()
    )

    assert result == "input-stopped"
    assert calls == []

    def continue_with_transformed_value(
        value: str,
        next_stage: Callable[[str], str],
    ) -> str:
        """Transform the value before invoking the continuation.

        Args:
            value: Value entering middleware.
            next_stage: Callback for the remaining ordered stages.

        Returns:
            The transformed result from downstream stages.
        """
        return next_stage(value.upper())

    continued = (
        Pipeline[str, str]()
        .send("input")
        .through(
            [
                Pipeline.middleware(continue_with_transformed_value),
                downstream,
            ],
        )
        .then_return()
    )
    assert continued == "INPUT-continued"
    assert calls == ["INPUT"]


def test_pipeline_invokes_explicit_methods_and_class_stages() -> None:
    """Resolve no-argument classes and invoke selected stage methods.

    Class stages may expose a native `handle` method without being callable.
    """

    class Normalize:
        """Normalize one string through an explicit stage method.

        The public method is selected by the Pipeline builder.
        """

        def normalize(self, value: str) -> str:
            """Strip surrounding whitespace and lowercase the value.

            Args:
                value: Unnormalized pipeline value.

            Returns:
                The normalized value.
            """
            return value.strip().lower()

    result = (
        Pipeline[str, str]()
        .send(" READY ")
        .through(
            [Pipeline.stage_method(Normalize, "normalize")],
        )
        .then_return()
    )

    assert result == "ready"


@pytest.mark.anyio
async def test_async_pipeline_awaits_stages_and_continuations() -> None:
    """Await async transforms in order and preserve async middleware flow.

    Synchronous transformations remain valid in the same async execution.
    """
    seen: list[str] = []

    async def uppercase(value: str) -> str:
        """Uppercase a value after yielding to the async runtime.

        Args:
            value: Input text.

        Returns:
            Uppercase text.
        """
        await anyio.lowlevel.checkpoint()
        return value.upper()

    async def surround(
        value: str,
        next_stage: Callable[[str], Awaitable[str]],
    ) -> str:
        """Wrap the next stage with visible entry and exit behavior.

        Args:
            value: Input text.
            next_stage: Asynchronous continuation for remaining stages.

        Returns:
            Text transformed by downstream stages and the wrapper.
        """
        seen.append("before")
        result = await next_stage(value + "!")
        seen.append("after")
        return f"<{result}>"

    result = await (
        Pipeline[str, str]()
        .send("ready")
        .through(
            [
                uppercase,
                Pipeline.middleware_async(surround),
                str.strip,
            ],
        )
        .then_return_async()
    )

    assert result == "<READY!>"
    assert seen == ["before", "after"]


@pytest.mark.anyio
async def test_async_pipeline_rejects_sync_continuation_wrappers() -> None:
    """Require an async wrapper when running the asynchronous entrypoint.

    Sync middleware is not implicitly adapted to async execution.
    """

    def surround(
        value: str,
        next_stage: Callable[[str], str],
    ) -> str:
        """Return the sync middleware result for the incompatible path.

        Args:
            value: Current stage value.
            next_stage: Sync callback for remaining stages.

        Returns:
            The downstream stage result.
        """
        return next_stage(value)

    with pytest.raises(PipelineExecutionError, match="execution mode"):
        await (
            Pipeline[str, str]()
            .send("ready")
            .through([Pipeline.middleware(surround)])
            .then_return_async()
        )

    with pytest.raises(PipelineExecutionError, match="Send a value"):
        await Pipeline[str, str]().then_return_async()


@pytest.mark.anyio
async def test_async_pipeline_propagates_cancellation_and_cleans_up() -> None:
    """Propagate cancellation through the active stage without detaching it.

    The stage-owned finalizer completes before async execution exits.
    """
    started = anyio.Event()
    finalized = anyio.Event()

    async def wait_for_cancel(value: str) -> str:
        """Wait for cancellation and finalize stage-owned resources.

        Args:
            value: The value the stage does not transform.

        Returns:
            The original value if cancellation never occurs.
        """
        try:
            started.set()
            await anyio.sleep_forever()
        finally:
            finalized.set()
        return value

    async def run_pipeline() -> None:
        """Keep the pipeline within its owning cancellation scope.

        The task group owns and cancels this execution.
        """
        await (
            Pipeline[str, str]()
            .send("ready")
            .through([wait_for_cancel])
            .then_return_async()
        )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(run_pipeline)
        await started.wait()
        task_group.cancel_scope.cancel()

    assert finalized.is_set()


@pytest.mark.anyio
async def test_async_pipeline_propagates_stage_errors() -> None:
    """Propagate stage failures without wrapping application exceptions.

    Callers retain the exception type and message from the stage.
    """

    async def fail(value: str) -> str:
        """Raise one application error during async processing.

        Args:
            value: Input whose value is not needed by this failing stage.

        Raises:
            ValueError: The expected stage failure.
        """
        _ = value
        raise ValueError(_PIPELINE_FAILURE)

    with pytest.raises(ValueError, match=_PIPELINE_FAILURE):
        await (
            Pipeline[str, str]()
            .send("ready")
            .through([fail])
            .then_return_async()
        )


def test_pipeline_helper_starts_a_value_preserving_pipeline() -> None:
    """Create a pipeline from one value without an application service.

    The helper supports simple data-processing call sites.
    """
    assert pipeline("ready").pipe(str.upper).then_return() == "READY"
