"""Verify safe Taskiq result retention and bounded handler values.
"""  # fmt: skip

from typing import cast

import pytest
from taskiq.abc.result_backend import AsyncResultBackend
from taskiq.result import TaskiqResult

from titanspan.contracts.queue import DispatchReceipt
from titanspan.foundation import Application
from titanspan.queue._backends.results import QueueTaskiqResultBackend
from titanspan.queue._serialization import JobCodec
from titanspan.queue.exceptions import QueueResultError
from titanspan.queue.manager import QueueManager
from titanspan.queue.results import QueueResultHandle
from titanspan.queue.service_provider import QueueServiceProvider

pytestmark = [pytest.mark.unit, pytest.mark.security, pytest.mark.regression]
_BACKEND_ERROR = "private backend detail"


class _MemoryResultBackend(AsyncResultBackend[object]):
    """Record Taskiq results passed through the native adapter.
    """  # fmt: skip

    def __init__(self) -> None:
        """Create an empty result store for adapter behavior tests.
        """  # fmt: skip
        self.results: dict[str, TaskiqResult[object]] = {}
        self.read_logs: list[bool] = []

    async def set_result(
        self,
        task_id: str,
        result: TaskiqResult[object],
    ) -> None:
        """Store one already-sanitized Taskiq result.

        Args:
            task_id: Result identifier.
            result: Safe result passed by Queue.
        """
        self.results[task_id] = result

    async def is_result_ready(self, task_id: str) -> bool:
        """Report whether this backend contains the selected result.

        Args:
            task_id: Result identifier.

        Returns:
            Whether the result exists.
        """
        return task_id in self.results

    async def get_result(
        self,
        task_id: str,
        with_logs: bool = False,
    ) -> TaskiqResult[object]:
        """Return a result and record the requested log behavior.

        Args:
            task_id: Result identifier.
            with_logs: Whether Taskiq was asked to include logs.

        Returns:
            Stored result for the selected identifier.
        """
        self.read_logs.append(with_logs)
        return self.results[task_id]

    results: dict[str, TaskiqResult[object]]
    read_logs: list[bool]


class _RawResultBackend:
    """Return deliberately malformed or unavailable result values.
    """  # fmt: skip

    def __init__(
        self,
        result: TaskiqResult[object],
        *,
        fail_readiness: bool = False,
    ) -> None:
        """Retain one result and an optional readiness failure mode.

        Args:
            result: Raw result supplied to QueueManager.
            fail_readiness: Whether readiness checks should raise.
        """
        self._result = result
        self._fail_readiness = fail_readiness

    async def is_result_ready(self, task_id: str) -> bool:
        """Return readiness or simulate a backend transport error.

        Args:
            task_id: Result identifier selected by the manager.

        Returns:
            Whether the selected result is ready.
        """
        _ = task_id
        if self._fail_readiness:
            raise OSError(_BACKEND_ERROR)
        return True

    async def get_result(
        self,
        task_id: str,
        with_logs: bool = False,
    ) -> TaskiqResult[object]:
        """Return the raw result without using the production sanitizer.

        Args:
            task_id: Result identifier selected by the manager.
            with_logs: Whether the caller requested backend logs.

        Returns:
            The selected raw Taskiq result.
        """
        _ = task_id, with_logs
        return self._result

    _fail_readiness: bool
    _result: TaskiqResult[object]


@pytest.mark.anyio
async def test_result_backend_redacts_failures() -> None:
    """Persist failure state without job values or worker diagnostics.

    Result records must not become an alternate exception logging channel.
    """
    backend = _MemoryResultBackend()
    adapter = QueueTaskiqResultBackend(backend)
    marker = "private-result-marker"
    result = TaskiqResult[object](
        is_err=True,
        log=marker,
        return_value={"has_value": True, "value": marker},
        execution_time=float("nan"),
        labels={"private": marker},
        error=RuntimeError(marker),
    )

    await adapter.set_result("failed-job", result)
    safe = backend.results["failed-job"]

    assert safe.is_err
    assert safe.log is None
    assert safe.return_value == {"has_value": False, "value": None}
    assert safe.execution_time == 0.0
    assert safe.labels == {}
    assert safe.error is not None
    assert marker not in str(safe.error)


@pytest.mark.anyio
async def test_result_backend_sanitizes_loaded_values_and_logs() -> None:
    """Revalidate backend records before exposing a result to callers.

    Storage content remains untrusted even when the broker is configured.
    """
    backend = _MemoryResultBackend()
    adapter = QueueTaskiqResultBackend(backend)
    marker = "private-result-marker"
    backend.results["untrusted-job"] = TaskiqResult[object](
        is_err=False,
        log=marker,
        return_value={"has_value": True, "value": object()},
        execution_time=0.25,
        labels={"private": marker},
    )

    safe = await adapter.get_result("untrusted-job", with_logs=True)

    assert safe.return_value == {"has_value": False, "value": None}
    assert safe.log is None
    assert safe.labels == {}
    assert backend.read_logs == [False]


def test_job_codec_omits_unsupported_result_values() -> None:
    """Keep unsupported handler returns from making completed jobs retry.
    """  # fmt: skip
    codec = JobCodec(max_payload_bytes=128)

    assert codec.encode_result(object()) == {
        "has_value": False,
        "value": None,
    }


def test_job_codec_preserves_bounded_json_result_values() -> None:
    """Retain JSON results within the configured message bounds.
    """  # fmt: skip
    codec = JobCodec(max_payload_bytes=128)
    value = {"items": [1, False, None, "document"]}

    assert codec.encode_result(value) == {
        "has_value": True,
        "value": value,
    }


def test_job_codec_omits_oversized_result_values() -> None:
    """Keep large handler returns from exceeding the configured result bound.
    """  # fmt: skip
    codec = JobCodec(max_payload_bytes=8)

    assert codec.encode_result("too large") == {
        "has_value": False,
        "value": None,
    }


@pytest.mark.anyio
async def test_result_adapter_rejects_non_mapping_backend_payloads() -> None:
    """Omit malformed top-level results without exposing backend objects.
    """  # fmt: skip
    backend = _MemoryResultBackend()
    adapter = QueueTaskiqResultBackend(backend)
    result = TaskiqResult[object](
        is_err=False,
        log=None,
        return_value=object(),
        execution_time=0.0,
        labels={},
    )
    backend.results["invalid-job"] = result

    safe = await adapter.get_result("invalid-job")

    assert safe.return_value == {"has_value": False, "value": None}


@pytest.mark.parametrize(
    "value",
    [
        {"other": "field"},
        {"has_value": 1, "value": "not-a-bool"},
        {"has_value": False, "value": None},
        {"has_value": True, "value": "x" * 1_000_001},
    ],
)
@pytest.mark.anyio
async def test_result_backend_omits_invalid_or_oversized_values(
    value: object,
) -> None:
    """Omit malformed envelopes and values that exceed the size limit.

    Result diagnostics remain safe when Taskiq returns unexpected data.
    """
    backend = _MemoryResultBackend()
    adapter = QueueTaskiqResultBackend(backend)
    await adapter.set_result(
        "untrusted-result",
        TaskiqResult[object](
            is_err=False,
            log=None,
            return_value=value,
            execution_time=0.0,
            labels={},
        ),
    )

    assert backend.results["untrusted-result"].return_value == {
        "has_value": False,
        "value": None,
    }


def _application() -> Application:
    """Create an application with the canonical Queue provider.

    Returns:
        An unstarted application with its application-owned manager.
    """
    return Application(service_providers=(QueueServiceProvider(),))


@pytest.mark.anyio
async def test_result_handle_validates_wait_options() -> None:
    """Reject invalid timing values before contacting a result backend.

    The handle still exposes its receipt identifier without backend access.
    """
    application = _application()
    receipt = DispatchReceipt(
        job_id="pending-result",
        connection="sync",
        queue="default",
        state="queued",
    )

    async with application:
        manager = application.container.make(QueueManager)
        handle = QueueResultHandle(manager, receipt)

        assert handle.job_id == receipt.job_id
        with pytest.raises(QueueResultError):
            await handle.wait_async(poll_interval=0)
        with pytest.raises(QueueResultError):
            await handle.wait_async(poll_interval=float("nan"))
        with pytest.raises(QueueResultError):
            await handle.wait_async(timeout=-1)
        with pytest.raises(QueueResultError):
            await handle.wait_async(timeout=float("inf"))


@pytest.mark.anyio
async def test_manager_sanitizes_result_readiness_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Map backend diagnostics to a safe native result error.

    The underlying exception text must not cross the Queue result boundary.
    """
    application = _application()
    receipt = DispatchReceipt(
        job_id="pending-result",
        connection="sync",
        queue="default",
        state="queued",
    )
    backend = _RawResultBackend(
        TaskiqResult[object](
            is_err=False,
            log=None,
            return_value=None,
            execution_time=0.0,
            labels={},
        ),
        fail_readiness=True,
    )

    async with application:
        manager = application.container.make(QueueManager)

        async def select_backend(
            selected: DispatchReceipt,
        ) -> QueueTaskiqResultBackend:
            """Return the test backend through the manager boundary.

            Args:
                selected: Receipt requested by the caller.

            Returns:
                A deliberately failing result backend.
            """
            _ = selected
            return cast("QueueTaskiqResultBackend", backend)

        monkeypatch.setattr(manager, "_result_backend_for", select_backend)

        with pytest.raises(QueueResultError) as captured:
            await manager.result_is_ready(receipt)

    assert "private backend detail" not in str(captured.value)


@pytest.mark.parametrize(
    "value",
    [object(), {"has_value": "true", "value": "invalid"}],
)
@pytest.mark.anyio
async def test_manager_rejects_malformed_result_envelopes(
    monkeypatch: pytest.MonkeyPatch,
    value: object,
) -> None:
    """Reject malformed values that cross the adapter contract boundary.

    This protects the manager if an adapter violates its safe payload policy.
    """
    application = _application()
    receipt = DispatchReceipt(
        job_id="malformed-result",
        connection="sync",
        queue="default",
        state="queued",
    )
    raw_backend = _RawResultBackend(
        TaskiqResult[object](
            is_err=False,
            log=None,
            return_value=value,
            execution_time=0.0,
            labels={},
        )
    )

    async with application:
        manager = application.container.make(QueueManager)

        async def select_backend(
            selected: DispatchReceipt,
        ) -> QueueTaskiqResultBackend:
            """Return malformed data through the adapter boundary.

            Args:
                selected: Receipt requested by the caller.

            Returns:
                A raw backend that violates the adapter guarantee.
            """
            _ = selected
            return cast("QueueTaskiqResultBackend", raw_backend)

        monkeypatch.setattr(manager, "_result_backend_for", select_backend)

        with pytest.raises(QueueResultError):
            await manager.read_result(receipt)
