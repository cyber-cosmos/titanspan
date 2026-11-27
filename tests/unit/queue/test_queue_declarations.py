"""Verify Queue configuration and job policy boundaries.

Public declarations reject invalid values before a broker or handler starts.
"""

from __future__ import annotations

from dataclasses import replace
from math import inf, nan
from typing import TYPE_CHECKING, cast

import pytest

from titanspan.config import Repository
from titanspan.queue.configuration import (
    QueueConfiguration,
    QueueConnectionConfiguration,
    is_valid_name,
)
from titanspan.queue.exceptions import QueueConfigurationError
from titanspan.queue.job import Job, validate_job_policy

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

pytestmark = pytest.mark.unit


class _ValidJob(Job):
    """Declare a valid job policy for validation cases.
    """  # fmt: skip

    def handle(self) -> None:
        """Provide a synchronous handler declaration.
        """  # fmt: skip


class _InvalidAttemptsJob(_ValidJob):
    """Declare a non-positive attempt count.
    """  # fmt: skip

    tries = 0


class _BooleanAttemptsJob(_ValidJob):
    """Reject bool where an integer retry count is required.
    """  # fmt: skip

    tries = True


class _InvalidVersionJob(_ValidJob):
    """Declare a non-positive payload version.
    """  # fmt: skip

    schema_version = 0


class _InvalidTimeoutJob(_ValidJob):
    """Declare a boolean timeout.
    """  # fmt: skip

    timeout = True


class _InvalidBackoffJob(_ValidJob):
    """Declare a negative delay in the retry sequence.
    """  # fmt: skip

    backoff = (0, -1)


def _job_variant(name: str, **attributes: object) -> type[Job]:
    """Create one runtime job subtype for invalid declaration tests.

    Args:
        name: Diagnostic class name for the generated test type.
        attributes: Runtime-only class values under test.

    Returns:
        A trusted Job subtype whose declaration is checked at runtime.
    """
    generated = type(name, (_ValidJob,), attributes)
    return cast("type[Job]", generated)


_INVALID_MIDDLEWARE_CONTAINER = _job_variant(
    "InvalidMiddlewareContainerJob",
    middleware=[],
)
_INVALID_MIDDLEWARE_ENTRY = _job_variant(
    "InvalidMiddlewareEntryJob",
    middleware=(object,),
)


def test_valid_job_policy_accepts_supported_defaults() -> None:
    """Accept the base job policy without optional retry settings.
    """  # fmt: skip
    validate_job_policy(_ValidJob)


@pytest.mark.parametrize(
    "job_type",
    [
        _InvalidAttemptsJob,
        _BooleanAttemptsJob,
        _InvalidVersionJob,
        _INVALID_MIDDLEWARE_CONTAINER,
        _INVALID_MIDDLEWARE_ENTRY,
        _InvalidTimeoutJob,
        _InvalidBackoffJob,
    ],
)
def test_job_policy_rejects_invalid_declarations(
    job_type: type[Job],
) -> None:
    """Reject invalid attempts, versions, middleware, timeouts, and delays.
    """  # fmt: skip
    with pytest.raises((TypeError, ValueError)):
        validate_job_policy(job_type)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(QueueConfiguration(), connections={}),
        lambda: replace(QueueConfiguration(), default_connection="missing"),
        lambda: replace(QueueConfiguration(), default_queue="bad/name"),
        lambda: replace(QueueConfiguration(), namespace="bad namespace"),
        lambda: replace(QueueConfiguration(), max_payload_bytes=0),
        lambda: replace(QueueConfiguration(), max_payload_depth=257),
        lambda: replace(QueueConfiguration(), batch_history_limit=0),
        lambda: replace(QueueConfiguration(), batch_history_limit=10_001),
        lambda: replace(QueueConfiguration(), worker_concurrency=0),
        lambda: replace(QueueConfiguration(), prefetch=-1),
        lambda: replace(QueueConfiguration(), default_tries=True),
        lambda: replace(QueueConfiguration(), schedule_poll_interval=nan),
        lambda: replace(QueueConfiguration(), schedule_loop_interval=inf),
    ],
)
def test_configuration_rejects_invalid_policy(
    factory: Callable[[], QueueConfiguration],
) -> None:
    """Validate every mandatory limit before constructing Queue services.
    """  # fmt: skip
    with pytest.raises(QueueConfigurationError):
        factory()


@pytest.mark.parametrize(
    "queue_value",
    [
        None,
        [],
        {"connections": []},
        {"default_connection": 4},
        {"max_payload_bytes": True},
        {"schedule_loop_interval": "fast"},
    ],
)
def test_repository_rejects_malformed_queue_settings(
    queue_value: object,
) -> None:
    """Reject malformed repository values instead of coercing them.
    """  # fmt: skip
    repository = Repository({"queue": queue_value})

    with pytest.raises(QueueConfigurationError):
        QueueConfiguration.from_repository(repository)


def test_repository_rejects_invalid_application_namespace_source() -> None:
    """Require a string application name when deriving a broker namespace.
    """  # fmt: skip
    repository = Repository({"app": {"name": 3}})

    with pytest.raises(QueueConfigurationError):
        QueueConfiguration.from_repository(repository)


@pytest.mark.parametrize(
    "connections",
    [
        {},
        {"bad/name": {"driver": "sync"}},
        {"redis": {}},
        {"redis": {"driver": "redis", "options": []}},
        {"redis": {"driver": "redis", "options": {1: "value"}}},
    ],
)
def test_connection_declarations_reject_invalid_shapes(
    connections: Mapping[str, object],
) -> None:
    """Reject malformed driver names, options, and connection maps.
    """  # fmt: skip
    raw_connections = cast(
        "Mapping[str, QueueConnectionConfiguration | Mapping[str, object]]",
        connections,
    )

    with pytest.raises(QueueConfigurationError):
        QueueConfiguration(connections=raw_connections)


def test_connection_configuration_rejects_non_mapping_options() -> None:
    """Require connection options to use a mapping value.
    """  # fmt: skip
    with pytest.raises(QueueConfigurationError):
        QueueConnectionConfiguration(
            "redis_stream",
            cast("Mapping[str, object]", []),
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("primary-1", True),
        ("_private", False),
        ("queue/name", False),
        ("with space", False),
        ("éclair", False),
        ("x" * 129, False),
    ],
)
def test_queue_names_use_bounded_portable_characters(
    value: str,
    expected: bool,
) -> None:
    """Allow portable names and reject paths, spaces, and Unicode input.
    """  # fmt: skip
    assert is_valid_name(value) is expected
