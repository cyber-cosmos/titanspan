"""Construct supported Taskiq brokers through public integration APIs.

Optional transport imports occur only when an application selects that
backend. Every broker uses Taskiq's JSON serializer.
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, cast

from taskiq.serializers.json_serializer import JSONSerializer

from titanspan.queue.exceptions import (
    QueueCapabilityError,
    QueueConfigurationError,
)

if TYPE_CHECKING:
    from taskiq.abc.broker import AsyncBroker
    from taskiq.abc.schedule_source import ScheduleSource

    from titanspan.queue.configuration import QueueConnectionConfiguration


class _TransportFactory(Protocol):
    """Describe an optional transport constructor at its adapter boundary.

    Some environments do not install optional broker packages. Keep their
    imports dynamic and type only the small interface Queue requires.
    """

    def __call__(self, **kwargs: object) -> AsyncBroker:
        """Create one Taskiq broker from validated settings."""
        ...


class _ScheduleSourceFactory(Protocol):
    """Describe the Redis schedule-source constructor."""

    def __call__(self, **kwargs: object) -> ScheduleSource:
        """Create one Taskiq schedule source."""
        ...


class _RabbitQueueFactory(Protocol):
    """Describe the RabbitMQ queue declaration constructor."""

    def __call__(self, **kwargs: object) -> object:
        """Create one durable Taskiq queue declaration."""
        ...


_OPTIONAL_DEPENDENCY_ERROR = (
    "Install the optional Queue backend extra selected by this connection."
)


def create_taskiq_transport(
    configuration: QueueConnectionConfiguration,
    *,
    namespace: str,
    connection_name: str,
    queue: str,
) -> tuple[AsyncBroker, ScheduleSource | None]:
    """Build one lazily owned broker and optional durable schedule source.

    Args:
        configuration: Validated connection configuration.
        namespace: Application-owned transport namespace.
        connection_name: Selected configured connection.
        queue: Logical Queue name selected for this worker.

    Returns:
        A Taskiq broker configured with JSON transport serialization and an
        optional backend-owned scheduling source.

    Raises:
        QueueCapabilityError: If the optional transport package is missing.
        QueueConfigurationError: If required backend options are invalid.
    """
    physical_queue = f"{namespace}:{connection_name}:{queue}"
    if configuration.driver == "redis_stream":
        broker, source = _create_redis_transport(
            configuration,
            namespace=namespace,
            connection_name=connection_name,
            queue=queue,
            physical_queue=physical_queue,
        )
    elif configuration.driver == "rabbitmq":
        broker = _create_rabbitmq_transport(
            configuration,
            physical_queue=physical_queue,
        )
        source = None
    else:
        msg = "The selected connection does not use a Taskiq transport."
        raise QueueConfigurationError(msg)
    broker.with_serializer(JSONSerializer(ensure_ascii=False))
    return broker, source


def _create_redis_transport(
    configuration: QueueConnectionConfiguration,
    *,
    namespace: str,
    connection_name: str,
    queue: str,
    physical_queue: str,
) -> tuple[AsyncBroker, ScheduleSource]:
    """Build acknowledged Redis Streams and JSON-backed delayed schedules.

    Args:
        configuration: Validated Redis settings.
        namespace: Application namespace used in coordination keys.
        connection_name: Selected connection identifier.
        queue: Logical queue name used in the schedule prefix.
        physical_queue: Namespaced Redis stream key.

    Returns:
        Stream broker and schedule source configured for JSON only.

    Raises:
        QueueCapabilityError: If the Redis integration extra is unavailable.
        QueueConfigurationError: If a Redis URL or option is invalid.
    """
    try:
        # Keep Redis optional until this configured backend is selected.
        module = import_module("taskiq_redis")
    except ImportError as error:
        raise QueueCapabilityError(_OPTIONAL_DEPENDENCY_ERROR) from error

    broker_factory = cast(
        "_TransportFactory",
        module.__dict__["RedisStreamBroker"],
    )
    source_factory = cast(
        "_ScheduleSourceFactory",
        module.__dict__["ListRedisScheduleSource"],
    )

    url = _required_text(configuration.options, "url")
    consumer_group = _optional_text(
        configuration.options,
        "consumer_group",
        f"{namespace}-{connection_name}-{queue}",
    )
    broker = broker_factory(
        url=url,
        queue_name=physical_queue,
        consumer_group_name=consumer_group,
        max_connection_pool_size=_optional_int(
            configuration.options,
            "max_connection_pool_size",
            20,
        ),
        idle_timeout=_optional_int(
            configuration.options,
            "idle_timeout_ms",
            600_000,
        ),
        unacknowledged_lock_timeout=_optional_float(
            configuration.options,
            "unacknowledged_lock_timeout_seconds",
            900.0,
        ),
        xread_count=_optional_int(configuration.options, "read_count", 100),
    )
    source = source_factory(
        url=url,
        prefix=f"{namespace}:{connection_name}:{queue}:schedule",
        max_connection_pool_size=_optional_int(
            configuration.options,
            "schedule_pool_size",
            4,
        ),
        serializer=JSONSerializer(ensure_ascii=False),
    )
    return broker, source


def _create_rabbitmq_transport(
    configuration: QueueConnectionConfiguration,
    *,
    physical_queue: str,
) -> AsyncBroker:
    """Build a durable RabbitMQ queue through the official Taskiq adapter.

    Args:
        configuration: Validated RabbitMQ settings.
        physical_queue: Namespaced task queue declared by the broker.

    Returns:
        A Taskiq broker with bounded prefetch and one durable queue.

    Raises:
        QueueCapabilityError: If the optional RabbitMQ extra is unavailable.
        QueueConfigurationError: If the connection URL is invalid.
    """
    try:
        # Keep RabbitMQ optional until this configured backend is selected.
        module = import_module("taskiq_aio_pika")
    except ImportError as error:
        raise QueueCapabilityError(_OPTIONAL_DEPENDENCY_ERROR) from error

    broker_factory = cast(
        "_TransportFactory",
        module.__dict__["AioPikaBroker"],
    )
    queue_factory = cast(
        "_RabbitQueueFactory",
        module.__dict__["Queue"],
    )

    url = _required_text(configuration.options, "url")
    return broker_factory(
        url=url,
        qos=_optional_int(configuration.options, "prefetch", 16),
        task_queues=[queue_factory(name=physical_queue, durable=True)],
    )


def _required_text(options: object, key: str) -> str:
    """Read one non-empty text value from trusted backend options.

    Args:
        options: Validated but backend-specific settings.
        key: Required option key.

    Returns:
        The selected text value.

    Raises:
        QueueConfigurationError: If the option is absent or invalid.
    """
    if not isinstance(options, Mapping):
        msg = "Queue backend options must be a mapping."
        raise QueueConfigurationError(msg)
    settings = cast("Mapping[str, object]", options)
    value = settings.get(key)
    if not isinstance(value, str) or not value:
        msg = f"Queue backend option [{key}] must be non-empty text."
        raise QueueConfigurationError(msg)
    return value


def _optional_text(options: object, key: str, default: str) -> str:
    """Read one optional text setting without exposing its value.

    Args:
        options: Backend settings mapping.
        key: Optional option key.
        default: Value used when the option is absent.

    Returns:
        The selected text value.
    """
    if not isinstance(options, Mapping):
        msg = "Queue backend options must be a mapping."
        raise QueueConfigurationError(msg)
    settings = cast("Mapping[str, object]", options)
    value = settings.get(key, default)
    if not isinstance(value, str) or not value:
        msg = f"Queue backend option [{key}] must be text."
        raise QueueConfigurationError(msg)
    return value


def _optional_int(options: object, key: str, default: int) -> int:
    """Read one positive integer backend setting.

    Args:
        options: Backend settings mapping.
        key: Optional option key.
        default: Value used when the option is absent.

    Returns:
        The selected positive integer.

    Raises:
        QueueConfigurationError: If the option is not a positive integer.
    """
    if not isinstance(options, Mapping):
        msg = "Queue backend options must be a mapping."
        raise QueueConfigurationError(msg)
    settings = cast("Mapping[str, object]", options)
    value = settings.get(key, default)
    if type(value) is not int or value < 1:
        msg = f"Queue backend option [{key}] must be a positive integer."
        raise QueueConfigurationError(msg)
    return value


def _optional_float(options: object, key: str, default: float) -> float:
    """Read one positive floating-point backend setting.

    Args:
        options: Backend settings mapping.
        key: Optional option key.
        default: Value used when the option is absent.

    Returns:
        The selected positive timeout.

    Raises:
        QueueConfigurationError: If the option is not a positive number.
    """
    if not isinstance(options, Mapping):
        msg = "Queue backend options must be a mapping."
        raise QueueConfigurationError(msg)
    settings = cast("Mapping[str, object]", options)
    value = settings.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        msg = f"Queue backend option [{key}] must be positive."
        raise QueueConfigurationError(msg)
    if value <= 0:
        msg = f"Queue backend option [{key}] must be positive."
        raise QueueConfigurationError(msg)
    return float(value)


__all__ = ["create_taskiq_transport"]
