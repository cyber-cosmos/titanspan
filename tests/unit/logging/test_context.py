"""Verify execution-local logging context and facade binding behavior.

These tests use explicit managers to prevent process-global logger state from
leaking between independent application and workflow executions.
"""

import anyio
import pytest

from titanspan.facades import Log
from titanspan.logging import LogManager, MemoryLogDriver
from titanspan.logging.exceptions import LogContextError

pytestmark = pytest.mark.unit
EXPECTED_CONCURRENT_REQUESTS = 2


def _manager_with_driver(
    driver: MemoryLogDriver,
) -> LogManager:
    """Create an isolated manager using a shared memory sink.

    Args:
        driver: The memory sink used to inspect delivered records.

    Returns:
        A manager with one default channel.
    """
    return LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: driver},
    )


def test_manager_context_restores_after_exception() -> None:
    """Restore prior context even when a scoped operation raises.

    Context cleanup uses token reset so nested scopes retain outer values.
    """
    driver = MemoryLogDriver()
    manager = _manager_with_driver(driver)
    manager.with_context(request_id="outer")

    def fail_in_inner_scope() -> None:
        """Raise after logging within a temporary context.

        The exception verifies that ContextVar tokens restore outer values.
        """
        with manager.context(request_id="inner"):
            manager.channel().info("inside")
            msg = "stop"
            raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="stop"):
        fail_in_inner_scope()

    manager.channel().info("outside")

    assert driver.records[0].context["request_id"] == "inner"
    assert driver.records[1].context["request_id"] == "outer"


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_context_is_isolated_between_concurrent_tasks() -> None:
    """Keep request context separate across concurrent async logging calls.

    Each child task receives its own explicit scope and async logging
    snapshots values before offloading destination I/O.
    """
    driver = MemoryLogDriver()
    manager = _manager_with_driver(driver)
    logger = manager.channel()

    async def write(request_id: str) -> None:
        """Log one message within an isolated request scope.

        Args:
            request_id: Identifier owned by the child execution.
        """
        with manager.context(request_id=request_id):
            await logger.info_async("request handled")

    # A task group owns both writes and cancels siblings if either fails.
    async with anyio.create_task_group() as group:
        group.start_soon(write, "request-a")
        group.start_soon(write, "request-b")

    request_ids = [record.context["request_id"] for record in driver.records]
    assert len(request_ids) == EXPECTED_CONCURRENT_REQUESTS
    assert "request-a" in request_ids
    assert "request-b" in request_ids


def test_shared_context_is_visible_to_every_channel_and_can_be_flushed() -> (
    None
):
    """Share metadata across manager channels within the active context.

    Flushing shared context removes only the values shared by channels.
    """
    driver = MemoryLogDriver()
    manager = LogManager(
        {
            "channels": {
                "default": {"driver": "memory"},
                "worker": {"driver": "memory"},
            },
        },
        drivers={"memory": lambda _: driver},
    )
    manager.share_context(tenant_id="tenant-a")
    manager.channel("default").info("web")
    manager.channel("worker").info("job")
    manager.flush_shared_context()
    manager.channel("worker").info("unscoped")

    assert driver.records[0].context["tenant_id"] == "tenant-a"
    assert driver.records[1].context["tenant_id"] == "tenant-a"
    assert "tenant_id" not in driver.records[2].context


def test_facade_requires_explicit_manager_binding() -> None:
    """Raise a clear error instead of resolving a process-global manager.

    Applications bind their own manager for the current execution context.
    """
    with pytest.raises(LogContextError):
        Log.info("not bound")


def test_facade_supports_contextual_logging_and_native_fake_assertions() -> (
    None
):
    """Bind a manager and swap its destinations within a fake scope.

    Fake assertions inspect native records and do not expose backend objects.
    """
    original_driver = MemoryLogDriver()
    manager = _manager_with_driver(original_driver)

    with Log.use(manager), Log.fake() as fake:
        Log.with_context(request_id="request-1")
        Log.info("completed", workflow_id="flow-1")
        captured = Log.assert_logged(
            "info",
            "completed",
            context={"request_id": "request-1"},
        )
        fake.assert_logged_times(1, "info", "completed")

    assert captured.context["workflow_id"] == "flow-1"
    assert original_driver.records == ()


@pytest.mark.anyio
async def test_facade_supports_explicit_async_logging() -> None:
    """Await facade writes without exposing the active manager directly.

    The resulting native record retains structured keyword context.
    """
    driver = MemoryLogDriver()
    manager = _manager_with_driver(driver)

    with Log.use(manager):
        await Log.info_async("workflow completed", workflow_id="flow-2")

    assert driver.records[0].message == "workflow completed"
    assert driver.records[0].context["workflow_id"] == "flow-2"


@pytest.mark.anyio
async def test_logger_async_exception_captures_active_exception() -> None:
    """Preserve exception diagnostics through the asynchronous API.

    The captured record stores safe exception metadata instead of live frames.
    """
    driver = MemoryLogDriver()
    manager = _manager_with_driver(driver)
    logger = manager.channel()

    def raise_failure() -> None:
        """Raise one deterministic error to establish exception context.

        The error is caught by the test before the async logging call.
        """
        message = "invalid workflow state"
        raise ValueError(message)

    try:
        raise_failure()
    except ValueError:
        await logger.exception_async("workflow failed")

    assert driver.records[0].level.value == "error"
    assert driver.records[0].exception is not None
    assert driver.records[0].exception["type"] == "ValueError"
