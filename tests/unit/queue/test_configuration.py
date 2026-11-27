"""Verify Queue configuration validation and safe diagnostics."""

import pytest

from titanspan.config import Repository
from titanspan.queue.configuration import QueueConfiguration
from titanspan.queue.exceptions import QueueConfigurationError

pytestmark = pytest.mark.unit
_PAYLOAD_DEPTH_LIMIT = 12


def test_repository_selects_explicit_namespace_and_default_connection() -> None:
    """Preserve an operator-selected namespace across worker processes.

    Applications with one name can use separate deployment namespaces.
    """
    repository = Repository(
        {
            "app": {"name": "document-service"},
            "queue": {
                "namespace": "document-staging",
                "connections": {"sync": {"driver": "sync"}},
            },
        }
    )

    configuration = QueueConfiguration.from_repository(repository)

    assert configuration.namespace == "document-staging"
    assert configuration.default_connection == "sync"


def test_repository_reads_payload_nesting_limit() -> None:
    """Load the configured bound before accepting Queue messages."""
    repository = Repository(
        {"queue": {"max_payload_depth": _PAYLOAD_DEPTH_LIMIT}}
    )

    configuration = QueueConfiguration.from_repository(repository)

    assert configuration.max_payload_depth == _PAYLOAD_DEPTH_LIMIT


def test_connection_configuration_redacts_secret_options() -> None:
    """Keep connection credentials out of representations and errors."""
    configuration = QueueConfiguration(
        connections={
            "redis": {
                "driver": "redis_stream",
                "options": {
                    "url": "redis://user:secret@localhost/0",
                },
            }
        },
        default_connection="redis",
    )

    assert "secret" not in repr(configuration.connection_configurations)
    assert "secret" not in repr(
        configuration.connection_configurations["redis"]
    )


@pytest.mark.parametrize(
    "value",
    ["", "bad:namespace", "../unsafe", "space value"],
)
def test_repository_rejects_unsafe_namespace(value: str) -> None:
    """Reject malformed namespaces before broker construction."""
    repository = Repository(
        {
            "app": {"name": "document-service"},
            "queue": {
                "namespace": value,
                "connections": {"sync": {"driver": "sync"}},
            },
        }
    )

    with pytest.raises(QueueConfigurationError):
        QueueConfiguration.from_repository(repository)


@pytest.mark.parametrize("value", [0, 257, True, "16"])
def test_configuration_rejects_invalid_payload_nesting_limit(
    value: object,
) -> None:
    """Reject invalid depth limits instead of silently coercing them."""
    repository = Repository({"queue": {"max_payload_depth": value}})

    with pytest.raises(QueueConfigurationError):
        QueueConfiguration.from_repository(repository)
