"""Validate Queue settings from the canonical application configuration.

Connection options remain private to backend construction and are never
rendered in ordinary configuration diagnostics.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from math import isfinite
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from titanspan.queue.exceptions import QueueConfigurationError

if TYPE_CHECKING:
    from titanspan.contracts.config import ConfigRepository

_DEFAULT_CONNECTION = "sync"
_DEFAULT_QUEUE = "default"
_DEFAULT_NAMESPACE = "titanspan"
_DEFAULT_MAX_PAYLOAD_BYTES = 1_000_000
_DEFAULT_MAX_PAYLOAD_DEPTH = 64
_MAX_PAYLOAD_DEPTH = 256
_DEFAULT_WORKER_CONCURRENCY = 16
_DEFAULT_PREFETCH = 0
_DEFAULT_TRIES = 1
_DEFAULT_SCHEDULE_POLL_INTERVAL = 1.0
_DEFAULT_SCHEDULE_LOOP_INTERVAL = 1.0
_MINIMUM_NAME_LENGTH = 1
_MAXIMUM_NAME_LENGTH = 128
_BUILTIN_DRIVERS = frozenset({"sync", "null", "redis_stream", "rabbitmq"})


def _validate_payload_limits(max_bytes: int, max_depth: int) -> None:
    """Reject invalid message size and JSON nesting limits.

    Args:
        max_bytes: Maximum encoded message size.
        max_depth: Maximum JSON container depth per job payload.

    Raises:
        QueueConfigurationError: If either limit falls outside its policy.
    """
    if type(max_bytes) is not int or max_bytes < 1:
        msg = "The maximum Queue payload size must be positive."
        raise QueueConfigurationError(msg)
    if type(max_depth) is not int or not 1 <= max_depth <= _MAX_PAYLOAD_DEPTH:
        msg = "Queue payload depth must be between 1 and 256."
        raise QueueConfigurationError(msg)


def _empty_options() -> Mapping[str, object]:
    """Create a correctly typed empty backend option mapping.
    """  # fmt: skip
    return {}


@dataclass(frozen=True, slots=True)
class QueueConnectionConfiguration:
    """Describe one named backend connection.

    Attributes:
        driver: Built-in or trusted custom backend name.
        options: Backend-specific application settings.
    """

    driver: str
    options: Mapping[str, object] = field(default_factory=_empty_options)

    def __post_init__(self) -> None:
        """Validate driver settings and snapshot the options mapping.

        Raises:
            QueueConfigurationError: If a driver or option key is invalid.
        """
        if not is_valid_name(self.driver):
            msg = "Queue driver name is invalid."
            raise QueueConfigurationError(msg)
        object.__setattr__(
            self,
            "options",
            _snapshot_options(self.options),
        )

    def __repr__(self) -> str:
        """Render backend configuration without exposing secret options.
        """  # fmt: skip
        return (
            f"QueueConnectionConfiguration(driver={self.driver!r}, "
            "options=<redacted>)"
        )


@dataclass(frozen=True, slots=True)
class QueueConfiguration:
    """Hold validated connection names, limits, and application namespace.

    Attributes:
        default_connection: Connection selected when a job has no override.
        default_queue: Queue selected when a job has no override.
        namespace: Stable application prefix for broker queue names.
        connections: Immutable configured connection declarations.
        max_payload_bytes: Maximum encoded job envelope size.
        max_payload_depth: Maximum nested JSON containers per job payload.
        worker_concurrency: Maximum asynchronous jobs handled by a worker.
        prefetch: Additional backend messages allowed beyond active capacity.
        default_tries: Total attempts for jobs without an override.
        schedule_poll_interval: Seconds between schedule source refreshes.
        schedule_loop_interval: Seconds between due-time checks.
    """

    default_connection: str = _DEFAULT_CONNECTION
    default_queue: str = _DEFAULT_QUEUE
    namespace: str = _DEFAULT_NAMESPACE
    connections: Mapping[
        str, QueueConnectionConfiguration | Mapping[str, object]
    ] = field(
        default_factory=lambda: {
            _DEFAULT_CONNECTION: QueueConnectionConfiguration("sync"),
        }
    )
    max_payload_bytes: int = _DEFAULT_MAX_PAYLOAD_BYTES
    max_payload_depth: int = _DEFAULT_MAX_PAYLOAD_DEPTH
    worker_concurrency: int = _DEFAULT_WORKER_CONCURRENCY
    prefetch: int = _DEFAULT_PREFETCH
    default_tries: int = _DEFAULT_TRIES
    schedule_poll_interval: float = _DEFAULT_SCHEDULE_POLL_INTERVAL
    schedule_loop_interval: float = _DEFAULT_SCHEDULE_LOOP_INTERVAL

    def __post_init__(self) -> None:
        """Validate selected connections and positive operation limits.

        Raises:
            QueueConfigurationError: If the configuration is inconsistent.
        """
        normalized = _normalize_connections(self.connections)
        if self.default_connection not in normalized:
            msg = "The default Queue connection is not configured."
            raise QueueConfigurationError(msg)
        if not is_valid_name(self.default_queue):
            msg = "The default queue name is invalid."
            raise QueueConfigurationError(msg)
        if not is_valid_name(self.namespace):
            msg = "The application queue namespace is invalid."
            raise QueueConfigurationError(msg)
        _validate_payload_limits(
            self.max_payload_bytes,
            self.max_payload_depth,
        )
        if (
            type(self.worker_concurrency) is not int
            or self.worker_concurrency < 1
        ):
            msg = "Queue worker concurrency must be positive."
            raise QueueConfigurationError(msg)
        if type(self.prefetch) is not int or self.prefetch < 0:
            msg = "Queue worker prefetch must not be negative."
            raise QueueConfigurationError(msg)
        if type(self.default_tries) is not int or self.default_tries < 1:
            msg = "The default Queue attempt count must be positive."
            raise QueueConfigurationError(msg)
        if not _positive_finite(self.schedule_poll_interval):
            msg = "The schedule poll interval must be positive and finite."
            raise QueueConfigurationError(msg)
        if not _positive_finite(self.schedule_loop_interval):
            msg = "The schedule loop interval must be positive and finite."
            raise QueueConfigurationError(msg)
        object.__setattr__(self, "connections", MappingProxyType(normalized))

    @property
    def connection_configurations(
        self,
    ) -> Mapping[str, QueueConnectionConfiguration]:
        """Return immutable normalized connection declarations.
        """  # fmt: skip
        return cast(
            "Mapping[str, QueueConnectionConfiguration]",
            self.connections,
        )

    @classmethod
    def from_repository(
        cls,
        repository: ConfigRepository,
    ) -> QueueConfiguration:
        """Read and validate the application's ``queue`` configuration.

        Args:
            repository: Canonical application configuration service.

        Returns:
            An immutable Queue configuration snapshot.

        Raises:
            QueueConfigurationError: If loaded values are malformed.
        """
        raw = repository.get("queue", {})
        if not isinstance(raw, Mapping):
            msg = "The queue configuration value must be a mapping."
            raise QueueConfigurationError(msg)
        values = cast("Mapping[str, object]", raw)
        app_name = repository.get("app.name", _DEFAULT_NAMESPACE)
        if not isinstance(app_name, str):
            msg = "The application name used by Queue must be a string."
            raise QueueConfigurationError(msg)
        connections = values.get(
            "connections",
            {_DEFAULT_CONNECTION: {"driver": "sync"}},
        )
        if not isinstance(connections, Mapping):
            msg = "Queue connections must be a mapping."
            raise QueueConfigurationError(msg)
        connection_values = cast(
            "Mapping[str, QueueConnectionConfiguration | Mapping[str, object]]",
            connections,
        )
        return cls(
            default_connection=_string_value(
                values,
                "default_connection",
                _DEFAULT_CONNECTION,
            ),
            default_queue=_string_value(
                values,
                "default_queue",
                _DEFAULT_QUEUE,
            ),
            namespace=_string_value(
                values,
                "namespace",
                _namespace(app_name),
            ),
            connections=connection_values,
            max_payload_bytes=_int_value(
                values,
                "max_payload_bytes",
                _DEFAULT_MAX_PAYLOAD_BYTES,
            ),
            max_payload_depth=_int_value(
                values,
                "max_payload_depth",
                _DEFAULT_MAX_PAYLOAD_DEPTH,
            ),
            worker_concurrency=_int_value(
                values,
                "worker_concurrency",
                _DEFAULT_WORKER_CONCURRENCY,
            ),
            prefetch=_int_value(values, "prefetch", _DEFAULT_PREFETCH),
            default_tries=_int_value(
                values,
                "default_tries",
                _DEFAULT_TRIES,
            ),
            schedule_poll_interval=_float_value(
                values,
                "schedule_poll_interval",
                _DEFAULT_SCHEDULE_POLL_INTERVAL,
            ),
            schedule_loop_interval=_float_value(
                values,
                "schedule_loop_interval",
                _DEFAULT_SCHEDULE_LOOP_INTERVAL,
            ),
        )


def _normalize_connections(
    values: Mapping[str, QueueConnectionConfiguration | Mapping[str, object]],
) -> dict[str, QueueConnectionConfiguration]:
    """Convert raw connection maps into validated immutable values.

    Args:
        values: Connection names mapped to typed settings or plain mappings.

    Returns:
        Validated configurations in declaration order.

    Raises:
        QueueConfigurationError: If connection names or settings are invalid.
    """
    if not values:
        msg = "At least one Queue connection must be configured."
        raise QueueConfigurationError(msg)
    normalized: dict[str, QueueConnectionConfiguration] = {}
    for name, value in values.items():
        if not is_valid_name(name):
            msg = "A Queue connection name is invalid."
            raise QueueConfigurationError(msg)
        if isinstance(value, QueueConnectionConfiguration):
            normalized[name] = value
            continue
        driver = value.get("driver")
        if not isinstance(driver, str):
            msg = "Each Queue connection requires a driver name."
            raise QueueConfigurationError(msg)
        options = value.get("options", {})
        if not isinstance(options, Mapping):
            msg = "Queue connection options must be a mapping."
            raise QueueConfigurationError(msg)
        normalized[name] = QueueConnectionConfiguration(
            driver,
            cast("Mapping[str, object]", options),
        )
    return normalized


def _snapshot_options(options: object) -> Mapping[str, object]:
    """Validate and freeze one connection option mapping.

    Args:
        options: Caller-supplied backend settings.

    Returns:
        An immutable copy with string keys.

    Raises:
        QueueConfigurationError: If the value or its keys are invalid.
    """
    if not isinstance(options, Mapping):
        msg = "Queue connection options must be a mapping."
        raise QueueConfigurationError(msg)
    raw_keys = cast("Mapping[object, object]", options)
    if not all(isinstance(key, str) for key in raw_keys):
        msg = "Queue option names must be strings."
        raise QueueConfigurationError(msg)
    normalized = cast("Mapping[str, object]", options)
    return MappingProxyType(dict(normalized))


def _namespace(value: str) -> str:
    """Create a bounded namespace that separates applications safely.

    Args:
        value: Configured application name.

    Returns:
        A stable identifier containing a readable prefix and digest.
    """
    stem = "".join(
        character if character.isascii() and character.isalnum() else "-"
        for character in value
    ).strip("-")
    digest = sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{stem[:48] or 'application'}-{digest}"


def _string_value(
    values: Mapping[str, object],
    key: str,
    default: str,
) -> str:
    """Read one required string from a validated top-level map.

    Args:
        values: Source configuration values.
        key: Selected setting name.
        default: Fallback when the setting is absent.

    Returns:
        The string setting.
    """
    value = values.get(key, default)
    if not isinstance(value, str):
        msg = f"Queue setting [{key}] must be text."
        raise QueueConfigurationError(msg)
    return value


def _int_value(
    values: Mapping[str, object],
    key: str,
    default: int,
) -> int:
    """Read one integer setting without accepting booleans.

    Args:
        values: Source configuration values.
        key: Selected setting name.
        default: Fallback when the setting is absent.

    Returns:
        The validated integer setting.
    """
    value = values.get(key, default)
    if type(value) is not int:
        msg = f"Queue setting [{key}] must be an integer."
        raise QueueConfigurationError(msg)
    return value


def _float_value(
    values: Mapping[str, object],
    key: str,
    default: float,
) -> float:
    """Read one finite number from application configuration.

    Args:
        values: Source configuration values.
        key: Selected setting name.
        default: Fallback when the setting is absent.

    Returns:
        The validated number as a float.
    """
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        msg = f"Queue setting [{key}] must be a finite number."
        raise QueueConfigurationError(msg)
    result = float(value)
    if not isfinite(result):
        msg = f"Queue setting [{key}] must be a finite number."
        raise QueueConfigurationError(msg)
    return result


def _positive_finite(value: object) -> bool:
    """Check a number used to poll delayed work.

    Args:
        value: Candidate interval in seconds.

    Returns:
        Whether the value is a finite positive integer or float.
    """
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and isfinite(value)
        and value > 0
    )


def is_valid_name(value: str) -> bool:
    """Check an application-controlled identifier without accepting paths.

    Args:
        value: Connection, queue, driver, or namespace identifier.

    Returns:
        Whether the value uses bounded portable characters.
    """
    return (
        _MINIMUM_NAME_LENGTH <= len(value) <= _MAXIMUM_NAME_LENGTH
        and value[0].isalnum()
        and all(
            character.isascii() and (character.isalnum() or character in "_.-")
            for character in value
        )
    )


__all__ = [
    "QueueConfiguration",
    "QueueConnectionConfiguration",
    "is_valid_name",
]
