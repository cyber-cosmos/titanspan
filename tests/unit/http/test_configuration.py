"""Verify strict application-level HTTP configuration parsing.

Local fixtures keep these assertions deterministic.
"""

import pytest

from titanspan.config import Repository
from titanspan.http.configuration import (
    ClientConfiguration,
    HttpConfiguration,
    ServerConfiguration,
)
from titanspan.http.exceptions import HttpConfigurationError

pytestmark = pytest.mark.unit
_BODY_LIMIT = 2048
_TIMEOUT_SECONDS = 12.0
_CONNECTION_LIMIT = 8
_KEEPALIVE_LIMIT = 4


def test_configuration_uses_documented_defaults() -> None:
    """Provide secure bounded defaults when the namespace is absent.

    The assertions verify the public result and its error paths.
    """
    configuration = HttpConfiguration.from_repository(Repository())

    assert configuration.server == ServerConfiguration()
    assert configuration.client == ClientConfiguration()
    assert configuration.client.verify_tls
    assert not configuration.client.follow_redirects


def test_configuration_reads_values_from_canonical_repository() -> None:
    """Apply application settings without creating another settings store.

    The assertions verify the public result and its error paths.
    """
    repository = Repository(
        {
            "http": {
                "server": {"max_body_size": _BODY_LIMIT},
                "client": {
                    "timeout": _TIMEOUT_SECONDS,
                    "max_connections": _CONNECTION_LIMIT,
                    "max_keepalive_connections": _KEEPALIVE_LIMIT,
                    "follow_redirects": True,
                    "verify_tls": False,
                    "base_url": "https://service.test/api/",
                },
            }
        }
    )

    configuration = HttpConfiguration.from_repository(repository)

    assert configuration.server.max_body_size == _BODY_LIMIT
    assert configuration.client.timeout == _TIMEOUT_SECONDS
    assert configuration.client.max_connections == _CONNECTION_LIMIT
    assert configuration.client.max_keepalive_connections == _KEEPALIVE_LIMIT
    assert configuration.client.follow_redirects
    assert not configuration.client.verify_tls
    assert configuration.client.base_url.endswith("/")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("http.server.max_body_size", True),
        ("http.server.max_form_fields", 0),
        ("http.client.timeout", "secret-timeout"),
        ("http.client.verify_tls", 1),
        ("http.client.base_url", None),
    ],
)
def test_configuration_rejects_invalid_values_without_disclosing_them(
    path: str,
    value: object,
) -> None:
    """Reject invalid shapes and avoid embedding configured data in errors.

    The assertions verify the public result and its error paths.
    """
    repository = Repository()
    repository.set(path, value)

    with pytest.raises(HttpConfigurationError) as error:
        HttpConfiguration.from_repository(repository)

    assert path in str(error.value)
    assert "secret-timeout" not in str(error.value)


def test_keepalive_pool_cannot_exceed_total_connection_limit() -> None:
    """Reject inconsistent client pool bounds during startup validation.

    The assertions verify the public result and its error paths.
    """
    repository = Repository(
        {
            "http": {
                "client": {
                    "max_connections": 2,
                    "max_keepalive_connections": 3,
                }
            }
        }
    )

    with pytest.raises(HttpConfigurationError, match="cannot exceed"):
        HttpConfiguration.from_repository(repository)
