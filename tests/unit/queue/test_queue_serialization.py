"""Verify bounded JSON envelopes and trusted job resolution.

The tests never execute or import a job named by an untrusted payload.
"""

import json
from dataclasses import dataclass

import pytest

from titanspan.queue import Job
from titanspan.queue._serialization import JobCodec, JobMessageMetadata
from titanspan.queue.exceptions import (
    QueueSerializationError,
    UnknownJobError,
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.security,
    pytest.mark.regression,
]


@dataclass
class _NumberJob(Job):
    """Carry one integer through the JSON envelope.

    The class remains trusted only after explicit codec registration.
    """

    value: int

    def handle(self) -> None:
        """Satisfy the public job convention without side effects.

        The codec tests do not execute the handler.
        """


@dataclass
class _NestedJob(Job):
    """Carry JSON data for nesting-boundary tests.
    """  # fmt: skip

    value: dict[str, object]

    def handle(self) -> None:
        """Satisfy the job convention without executing side effects.
        """  # fmt: skip


def test_registered_job_round_trip_preserves_typed_payload() -> None:
    """Serialize only registered job data and reconstruct its class.

    The wire envelope carries a stable registered name and schema version.
    """
    codec = JobCodec(max_payload_bytes=1024)
    codec.register(_NumberJob, "numbers.increment")

    encoded = codec.encode(
        _NumberJob(42),
        JobMessageMetadata(connection="sync", queue="default"),
    )
    decoded = codec.decode(encoded)

    assert decoded.job == _NumberJob(42)
    assert decoded.envelope.job_type == "numbers.increment"
    assert decoded.envelope.payload_version == 1
    assert decoded.envelope.version == 1


def test_codec_rejects_unregistered_types_and_untrusted_names() -> None:
    """Reject unregistered classes without importing message-controlled code.

    The codec resolves names only through its application-owned registry.
    """
    codec = JobCodec(max_payload_bytes=1024)

    with pytest.raises(UnknownJobError):
        codec.encode(
            _NumberJob(1),
            JobMessageMetadata(connection="sync", queue="default"),
        )

    codec.register(_NumberJob, "numbers.increment")
    payload = {
        "version": 1,
        "job_id": "123e4567-e89b-12d3-a456-426614174000",
        "job_type": "builtins:eval",
        "payload_version": 1,
        "connection": "sync",
        "queue": "default",
        "dispatched_at": "2026-11-27T00:00:00Z",
        "payload": {"value": 1},
    }

    with pytest.raises(UnknownJobError):
        codec.decode(json.dumps(payload))


def test_codec_rejects_coercion_and_oversized_messages() -> None:
    """Reject schema coercion and enforce the bound before parsing.

    Invalid job data never reaches a registered handler.
    """
    codec = JobCodec(max_payload_bytes=512)
    codec.register(_NumberJob, "numbers.increment")
    encoded = codec.encode(
        _NumberJob(1),
        JobMessageMetadata(connection="sync", queue="default"),
    )
    payload = json.loads(encoded)
    payload["payload"]["value"] = "1"

    with pytest.raises(QueueSerializationError):
        codec.decode(json.dumps(payload))

    with pytest.raises(QueueSerializationError):
        codec.decode(" " * 513)


def test_codec_rejects_payloads_that_exceed_the_configured_limit() -> None:
    """Apply the encoded-size limit before a broker can publish the job.

    A caller cannot increase the configured transport message bound.
    """
    codec = JobCodec(max_payload_bytes=128)
    codec.register(_NumberJob, "numbers.increment")

    with pytest.raises(QueueSerializationError):
        codec.encode(
            _NumberJob(1),
            JobMessageMetadata(connection="sync", queue="default"),
        )


def test_codec_rejects_nested_payload_before_publication() -> None:
    """Reject trusted job data beyond the configured nesting bound.
    """  # fmt: skip
    codec = JobCodec(max_payload_bytes=1024, max_payload_depth=2)
    codec.register(_NestedJob, "nested")

    with pytest.raises(QueueSerializationError):
        codec.encode(
            _NestedJob({"level": {"level": {"value": 1}}}),
            JobMessageMetadata(connection="sync", queue="default"),
        )


def test_codec_rejects_untrusted_nested_payload_before_validation() -> None:
    """Reject excessive broker JSON nesting before model construction.
    """  # fmt: skip
    writer = JobCodec(max_payload_bytes=1024, max_payload_depth=8)
    writer.register(_NestedJob, "nested")
    encoded = writer.encode(
        _NestedJob({"level": {"level": {"value": 1}}}),
        JobMessageMetadata(connection="sync", queue="default"),
    )
    reader = JobCodec(max_payload_bytes=1024, max_payload_depth=2)
    reader.register(_NestedJob, "nested")

    with pytest.raises(QueueSerializationError):
        reader.decode(encoded)


def test_codec_ignores_delimiters_inside_json_strings() -> None:
    """Count JSON containers without treating string content as syntax.
    """  # fmt: skip
    codec = JobCodec(max_payload_bytes=1024, max_payload_depth=2)
    codec.register(_NestedJob, "nested")
    encoded = codec.encode(
        _NestedJob({"value": "[[[[{{{{"}),
        JobMessageMetadata(connection="sync", queue="default"),
    )

    assert codec.decode(encoded).job == _NestedJob({"value": "[[[[{{{{"})


def test_codec_rejects_deep_untrusted_json_before_backend_validation() -> None:
    """Reject extreme nesting before invoking recursive schema parsing.
    """  # fmt: skip
    codec = JobCodec(max_payload_bytes=10_000, max_payload_depth=2)
    codec.register(_NestedJob, "nested")
    encoded = '{"payload":' + "[" * 1000 + "0" + "]" * 1000 + "}"

    with pytest.raises(QueueSerializationError, match="nesting limit"):
        codec.decode(encoded)
