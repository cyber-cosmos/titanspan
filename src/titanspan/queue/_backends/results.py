"""Adapt Taskiq results to Queue's bounded JSON policy.
"""  # fmt: skip

from __future__ import annotations

import json
from collections.abc import Mapping
from math import isfinite
from typing import cast

from pydantic import JsonValue, TypeAdapter, ValidationError
from taskiq.abc.result_backend import AsyncResultBackend
from taskiq.result import TaskiqResult

from titanspan.queue._serialization import validate_payload_depth

_RESULT_ERROR_MESSAGE = "The queued job failed."
_MAX_RESULT_BYTES = 1_000_000
_MAX_RESULT_DEPTH = 64
_RESULT_ADAPTER = TypeAdapter(JsonValue)
_EMPTY_RESULT: dict[str, object] = {
    "has_value": False,
    "value": None,
}


class QueueTaskiqResultBackend(AsyncResultBackend[object]):
    """Keep Taskiq result transport behind a safe native boundary.

    Queue drops worker logs, arbitrary labels, and exception messages before
    Taskiq persists a result. Only bounded JSON values cross this adapter.
    """

    def __init__(self, backend: AsyncResultBackend[object]) -> None:
        """Wrap one application-owned Taskiq result backend.

        Args:
            backend: Taskiq backend that owns result transport and expiry.
        """
        self._backend = backend

    async def startup(self) -> None:
        """Start the backend through its owning Taskiq broker.
        """  # fmt: skip
        await self._backend.startup()

    async def shutdown(self) -> None:
        """Close the backend through its owning Taskiq broker.
        """  # fmt: skip
        await self._backend.shutdown()

    async def set_result(
        self,
        task_id: str,
        result: TaskiqResult[object],
    ) -> None:
        """Persist a redacted, JSON-safe result record.

        Args:
            task_id: Taskiq identifier for the completed job.
            result: Worker result supplied by Taskiq.
        """
        await self._backend.set_result(task_id, _safe_taskiq_result(result))

    async def is_result_ready(self, task_id: str) -> bool:
        """Check result readiness through the selected backend.

        Args:
            task_id: Taskiq identifier for the result.

        Returns:
            Whether the backend retains a result for this identifier.
        """
        return await self._backend.is_result_ready(task_id)

    async def get_result(
        self,
        task_id: str,
        with_logs: bool = False,
    ) -> TaskiqResult[object]:
        """Return a sanitized result from the selected backend.

        Args:
            task_id: Taskiq identifier for the result.
            with_logs: Ignored because Queue does not retain worker logs.

        Returns:
            A sanitized Taskiq result record.
        """
        _ = with_logs
        result = await self._backend.get_result(task_id, with_logs=False)
        return _safe_taskiq_result(result)

    _backend: AsyncResultBackend[object]


def _safe_taskiq_result(
    result: TaskiqResult[object],
) -> TaskiqResult[object]:
    """Remove untrusted diagnostics and bound a stored result payload.

    Args:
        result: Taskiq result produced locally or loaded from the backend.

    Returns:
        A validated result containing no exception message or worker log.
    """
    error = RuntimeError(_RESULT_ERROR_MESSAGE) if result.is_err else None
    execution_time = result.execution_time
    if not isfinite(execution_time) or execution_time < 0:
        execution_time = 0.0
    return TaskiqResult[object](
        is_err=result.is_err,
        log=None,
        return_value=(
            dict(_EMPTY_RESULT)
            if result.is_err
            else _safe_result_payload(result.return_value)
        ),
        execution_time=execution_time,
        labels={},
        error=error,
    )


def _safe_result_payload(value: object) -> dict[str, object]:
    """Accept only the expected bounded Queue result envelope.

    Args:
        value: Result payload from a Queue worker or result backend.

    Returns:
        A safe payload, or a record that states the value was omitted.
    """
    if not isinstance(value, Mapping):
        return dict(_EMPTY_RESULT)
    values = cast("Mapping[object, object]", value)
    if set(values) != {"has_value", "value"}:
        return dict(_EMPTY_RESULT)
    has_value = values.get("has_value")
    if type(has_value) is not bool:
        return dict(_EMPTY_RESULT)
    if not has_value:
        return dict(_EMPTY_RESULT)
    try:
        json_value = _RESULT_ADAPTER.validate_python(
            values.get("value"),
            strict=True,
        )
        validate_payload_depth(json_value, _MAX_RESULT_DEPTH)
        encoded = json.dumps(
            json_value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError, ValidationError):
        return dict(_EMPTY_RESULT)
    if len(encoded) > _MAX_RESULT_BYTES:
        return dict(_EMPTY_RESULT)
    return {"has_value": True, "value": json_value}


__all__ = ["QueueTaskiqResultBackend"]
