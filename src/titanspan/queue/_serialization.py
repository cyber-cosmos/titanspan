"""Encode trusted job declarations as bounded, versioned JSON messages.

The message type selects only a class registered by application code. Broker
contents never trigger imports or executable deserialization.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4, uuid5

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
)

from titanspan.queue.exceptions import (
    QueueSerializationError,
    UnknownJobError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from titanspan.queue.job import Job

_JOB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_INVALID_JOB_ERROR = "Queue jobs must be registered serializable Job classes."
_INVALID_MESSAGE_ERROR = "The queue message is malformed or unsupported."
_MESSAGE_VERSION = 1
_MAX_CHAIN_JOBS = 256
_SAFE_QUEUE_LABEL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"
_JSON_VALUE_ADAPTER = TypeAdapter(JsonValue)


class ChainedJobPayload(BaseModel):
    """Store one trusted continuation as validated JSON job data."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    job_id: UUID
    job_type: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )
    payload_version: int = Field(ge=1)
    payload: JsonValue


class JobEnvelope(BaseModel):
    """Describe one safe job message independently of its transport.

    The application validates every field before resolving the registered
    job class or calling its handler.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    version: Literal[1] = _MESSAGE_VERSION
    job_id: UUID
    job_type: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )
    payload_version: int
    connection: str = Field(
        min_length=1,
        max_length=128,
        pattern=_SAFE_QUEUE_LABEL_PATTERN,
    )
    queue: str = Field(
        min_length=1,
        max_length=128,
        pattern=_SAFE_QUEUE_LABEL_PATTERN,
    )
    dispatched_at: datetime
    correlation_id: str | None = Field(default=None, max_length=128)
    chain_id: str | None = Field(default=None, max_length=128)
    batch_id: str | None = Field(default=None, max_length=128)
    payload: JsonValue
    continuation: tuple[ChainedJobPayload, ...] = Field(
        default_factory=tuple,
        max_length=_MAX_CHAIN_JOBS,
    )


@dataclass(frozen=True, slots=True)
class DecodedJob:
    """Pair a validated transport message with its trusted job instance.

    Attributes:
        envelope: Validated identifiers and execution metadata.
        job: Instance constructed by the registered Pydantic adapter.
    """

    envelope: JobEnvelope
    job: Job
    continuation: tuple[DecodedChainedJob, ...] = ()


@dataclass(frozen=True, slots=True)
class DecodedChainedJob:
    """Pair trusted continuation metadata with its typed job instance."""

    payload: ChainedJobPayload
    job: Job


@dataclass(frozen=True, slots=True)
class JobMessageMetadata:
    """Hold transport metadata used to encode one job envelope.

    Attributes:
        connection: Selected application connection.
        queue: Selected logical queue.
        job_id: Optional caller-supplied identifier.
        correlation_id: Optional non-secret correlation value.
        chain_id: Optional chain membership identifier.
        batch_id: Optional batch membership identifier.
        delay_at: Optional absolute delivery time.
        continuation: Bounded job payloads that follow this job.
    """

    connection: str
    queue: str
    job_id: str | None = None
    correlation_id: str | None = None
    chain_id: str | None = None
    batch_id: str | None = None
    delay_at: datetime | None = None
    continuation: tuple[ChainedJobPayload, ...] = ()


class JobCodec:
    """Own one application's trusted job type and message mappings.

    The codec keeps type adapters only for classes explicitly registered by
    trusted application code.
    """

    def __init__(
        self,
        *,
        max_payload_bytes: int,
        max_payload_depth: int = 64,
    ) -> None:
        """Create a registry with bounded wire size and JSON nesting.

        Args:
            max_payload_bytes: Maximum encoded envelope size.
            max_payload_depth: Maximum nested containers in one job payload.
        """
        self._max_payload_bytes = max_payload_bytes
        self._max_payload_depth = max_payload_depth
        self._jobs_by_name: dict[str, type[Job]] = {}
        self._names_by_type: dict[type[Job], str] = {}
        self._adapters: dict[type[Job], TypeAdapter[object]] = {}

    @property
    def job_names(self) -> tuple[str, ...]:
        """Return trusted job names in registration order.
        """  # fmt: skip
        return tuple(self._jobs_by_name)

    def is_registered(self, job_type: type[Job]) -> bool:
        """Check whether the exact class has a trusted registration.

        Args:
            job_type: Candidate job class.

        Returns:
            Whether the exact class is registered.
        """
        return job_type in self._names_by_type

    def register(self, job_type: type[Job], name: str | None = None) -> str:
        """Register one serializable job class under a trusted identifier.

        Args:
            job_type: Dataclass or Pydantic job class.
            name: Optional stable application-owned job name.

        Returns:
            The trusted identifier used in job envelopes.

        Raises:
            QueueSerializationError: If the class or name is invalid.
        """
        selected_name = name or job_type.job_name or _qualified_name(job_type)
        if not _JOB_NAME_PATTERN.fullmatch(selected_name):
            raise QueueSerializationError(_INVALID_JOB_ERROR)
        if not callable(getattr(job_type, "handle", None)):
            raise QueueSerializationError(_INVALID_JOB_ERROR)
        if not (
            hasattr(job_type, "__dataclass_fields__") or _is_model(job_type)
        ):
            raise QueueSerializationError(_INVALID_JOB_ERROR)
        existing_type = self._jobs_by_name.get(selected_name)
        existing_name = self._names_by_type.get(job_type)
        if existing_type is not None or existing_name is not None:
            if existing_type is job_type and existing_name == selected_name:
                return selected_name
            msg = "A queue job name or class is already registered."
            raise QueueSerializationError(msg)
        try:
            adapter: TypeAdapter[object] = TypeAdapter(job_type)
        except (TypeError, ValueError) as error:
            raise QueueSerializationError(_INVALID_JOB_ERROR) from error
        self._jobs_by_name[selected_name] = job_type
        self._names_by_type[job_type] = selected_name
        self._adapters[job_type] = adapter
        return selected_name

    def encode(
        self,
        job: Job,
        metadata: JobMessageMetadata,
    ) -> bytes:
        """Serialize one registered job without including injected services.

        Args:
            job: Registered job data instance.
            metadata: Selected transport and correlation metadata.

        Returns:
            UTF-8 JSON bytes suitable for the Taskiq JSON serializer.

        Raises:
            QueueSerializationError: If data cannot be encoded or exceeds
                the configured message bound.
        """
        job_type = type(job)
        name = self._names_by_type.get(job_type)
        adapter = self._adapters.get(job_type)
        if name is None or adapter is None:
            msg = "The job class is not registered."
            raise UnknownJobError(msg)
        try:
            payload = _JSON_VALUE_ADAPTER.validate_python(
                adapter.dump_python(job, mode="json", by_alias=True),
                strict=True,
            )
            _validate_payload_depth(payload, self._max_payload_depth)
            envelope = JobEnvelope(
                job_id=(
                    UUID(metadata.job_id)
                    if metadata.job_id is not None
                    else uuid4()
                ),
                job_type=name,
                payload_version=job_type.schema_version,
                connection=metadata.connection,
                queue=metadata.queue,
                dispatched_at=datetime.now(UTC),
                correlation_id=metadata.correlation_id,
                chain_id=metadata.chain_id,
                batch_id=metadata.batch_id,
                payload=payload,
                continuation=metadata.continuation,
            )
            encoded = envelope.model_dump_json(
                by_alias=True,
                exclude_none=True,
            ).encode("utf-8")
        except QueueSerializationError:
            raise
        except (
            RecursionError,
            TypeError,
            ValueError,
            ValidationError,
        ) as error:
            msg = "The job payload is not supported by the configured schema."
            raise QueueSerializationError(msg) from error
        if len(encoded) > self._max_payload_bytes:
            msg = "The encoded job message exceeds the configured size limit."
            raise QueueSerializationError(msg)
        return encoded

    def encode_chain(
        self,
        jobs: Sequence[Job],
        *,
        chain_id: str,
        first_index: int = 1,
    ) -> tuple[ChainedJobPayload, ...]:
        """Encode trusted continuation jobs without executable objects.

        Args:
            jobs: Remaining registered jobs in execution order.
            chain_id: UUID assigned to the containing chain.
            first_index: Zero-based index of the first supplied job.

        Returns:
            Bounded immutable job payloads for the message envelope.

        Raises:
            QueueSerializationError: If a job or chain limit is invalid.
        """
        if len(jobs) > _MAX_CHAIN_JOBS:
            msg = "The chain exceeds the configured job limit."
            raise QueueSerializationError(msg)
        try:
            chain_uuid = UUID(chain_id)
        except ValueError as error:
            raise QueueSerializationError(_INVALID_MESSAGE_ERROR) from error
        entries: list[ChainedJobPayload] = []
        for offset, job in enumerate(jobs):
            job_type = type(job)
            name = self._names_by_type.get(job_type)
            adapter = self._adapters.get(job_type)
            if name is None or adapter is None:
                msg = "Every chained job must be explicitly registered."
                raise UnknownJobError(msg)
            try:
                payload = _JSON_VALUE_ADAPTER.validate_python(
                    adapter.dump_python(job, mode="json", by_alias=True),
                    strict=True,
                )
                _validate_payload_depth(payload, self._max_payload_depth)
                entries.append(
                    ChainedJobPayload(
                        job_id=uuid5(chain_uuid, str(first_index + offset)),
                        job_type=name,
                        payload_version=job_type.schema_version,
                        payload=payload,
                    )
                )
            except QueueSerializationError:
                raise
            except (
                RecursionError,
                TypeError,
                ValueError,
                ValidationError,
            ) as error:
                msg = "A chained job payload does not match its schema."
                raise QueueSerializationError(msg) from error
        return tuple(entries)

    def decode(self, encoded: bytes | str) -> DecodedJob:
        """Validate an untrusted JSON message against registered job schemas.

        Args:
            encoded: UTF-8 bytes or text received from the selected broker.

        Returns:
            Validated metadata and a registered job instance.

        Raises:
            QueueSerializationError: If the envelope or payload is invalid.
            UnknownJobError: If the message names an unregistered job type.
        """
        raw = encoded.encode("utf-8") if isinstance(encoded, str) else encoded
        if len(raw) > self._max_payload_bytes:
            msg = "The queue message exceeds the configured size limit."
            raise QueueSerializationError(msg)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise QueueSerializationError(_INVALID_MESSAGE_ERROR) from error
        if _has_excessive_nesting(
            text,
            self._max_payload_depth + 3,
        ):
            msg = "The queue message exceeds the configured nesting limit."
            raise QueueSerializationError(msg)
        try:
            envelope = JobEnvelope.model_validate_json(raw, strict=True)
        except ValidationError as error:
            raise QueueSerializationError(_INVALID_MESSAGE_ERROR) from error
        job_type = self._jobs_by_name.get(envelope.job_type)
        if job_type is None:
            msg = "The queue message names an unknown job."
            raise UnknownJobError(msg)
        if envelope.payload_version != job_type.schema_version:
            msg = "The job payload schema version is unsupported."
            raise QueueSerializationError(msg)
        _validate_payload_depth(envelope.payload, self._max_payload_depth)
        for item in envelope.continuation:
            _validate_payload_depth(item.payload, self._max_payload_depth)
        job = self._decode_registered_job(
            envelope.job_type,
            envelope.payload_version,
            envelope.payload,
        )
        continuation = tuple(
            DecodedChainedJob(
                payload=item,
                job=self._decode_registered_job(
                    item.job_type,
                    item.payload_version,
                    item.payload,
                ),
            )
            for item in envelope.continuation
        )
        return DecodedJob(
            envelope=envelope,
            job=job,
            continuation=continuation,
        )

    def _decode_registered_job(
        self,
        name: str,
        version: int,
        value: JsonValue,
    ) -> Job:
        """Validate one payload against an exact trusted registration.

        Args:
            name: Trusted catalog key from the message.
            version: Declared schema version.
            value: JSON value supplied by the broker.

        Returns:
            A typed job constructed by its registered adapter.

        Raises:
            QueueSerializationError: If its version or schema is invalid.
            UnknownJobError: If the job is not in the trusted catalog.
        """
        job_type = self._jobs_by_name.get(name)
        if job_type is None:
            msg = "The queue message names an unknown job."
            raise UnknownJobError(msg)
        if version != job_type.schema_version:
            msg = "The job payload schema version is unsupported."
            raise QueueSerializationError(msg)
        adapter = self._adapters[job_type]
        try:
            payload = json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            job = adapter.validate_json(payload, strict=True)
        except (
            RecursionError,
            TypeError,
            ValueError,
            ValidationError,
        ) as error:
            msg = "The job payload does not match its registered schema."
            raise QueueSerializationError(msg) from error
        if not isinstance(job, job_type):
            raise QueueSerializationError(_INVALID_MESSAGE_ERROR)
        return job


def _qualified_name(job_type: type[Job]) -> str:
    """Return a deterministic registration name without importing messages.

    Args:
        job_type: Trusted class declared by the application.

    Returns:
        Module and qualified class name.
    """
    return f"{job_type.__module__}:{job_type.__qualname__}"


def _validate_payload_depth(value: JsonValue, maximum: int) -> None:
    """Reject JSON payloads with too many nested array or object values.

    Args:
        value: JSON-compatible job payload.
        maximum: Maximum container depth, counting the payload root.

    Raises:
        QueueSerializationError: If the payload exceeds the configured bound.
    """
    pending: list[tuple[JsonValue, int]] = [(value, 0)]
    while pending:
        item, parent_depth = pending.pop()
        if isinstance(item, dict):
            item_depth = parent_depth + 1
            if item_depth > maximum:
                msg = "The job payload exceeds the configured nesting limit."
                raise QueueSerializationError(msg)
            pending.extend((child, item_depth) for child in item.values())
        elif isinstance(item, list):
            item_depth = parent_depth + 1
            if item_depth > maximum:
                msg = "The job payload exceeds the configured nesting limit."
                raise QueueSerializationError(msg)
            pending.extend((child, item_depth) for child in item)


def _has_excessive_nesting(value: str, maximum: int) -> bool:
    """Check JSON container depth without parsing untrusted nested values.

    Args:
        value: UTF-8 JSON text bounded by the message-size limit.
        maximum: Maximum structural depth for the complete envelope.

    Returns:
        Whether the text opens too many object or array containers.
    """
    depth = 0
    in_string = False
    escaped = False
    for character in value:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > maximum:
                return True
        elif character in "]}":
            depth = max(0, depth - 1)
    return False


def _is_model(job_type: type[Job]) -> bool:
    """Check whether a declared job also uses Pydantic's model base.

    Args:
        job_type: Candidate trusted job class.

    Returns:
        Whether the class derives from Pydantic ``BaseModel``.
    """
    return issubclass(job_type, BaseModel)


__all__ = [
    "ChainedJobPayload",
    "DecodedChainedJob",
    "DecodedJob",
    "JobCodec",
    "JobEnvelope",
    "JobMessageMetadata",
]
