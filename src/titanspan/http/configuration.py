"""Validate HTTP service settings read from the canonical config repository.

Configuration is parsed once during application composition and shared by
the request boundary and pooled outgoing clients.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from titanspan.http.exceptions import HttpConfigurationError

if TYPE_CHECKING:
    from titanspan.contracts.config import ConfigReader

_DEFAULT_BODY_LIMIT = 10 * 1024 * 1024
_KEEPALIVE_EXCEEDS_CONNECTIONS_ERROR = (
    "[http.client.max_keepalive_connections] cannot exceed "
    "[http.client.max_connections]."
)


@dataclass(frozen=True, slots=True)
class ServerConfiguration:
    """Hold request size and multipart parser limits.

    Attributes:
        max_body_size: Maximum request bytes consumed by the HTTP adapter.
        max_form_files: Maximum uploaded files accepted in one form.
        max_form_fields: Maximum non-file form fields accepted.
        max_part_size: Maximum size of a non-file multipart part.
    """

    max_body_size: int = _DEFAULT_BODY_LIMIT
    max_form_files: int = 100
    max_form_fields: int = 1000
    max_part_size: int = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ClientConfiguration:
    """Hold connection-pool and transport defaults for one application.

    Attributes:
        timeout: Default total request timeout in seconds.
        connect_timeout: Default connection-establishment timeout.
        max_connections: Maximum active transport connections.
        max_keepalive_connections: Maximum idle pooled connections.
        keepalive_expiry: Idle connection lifetime in seconds.
        follow_redirects: Whether redirects are followed by default.
        verify_tls: Whether TLS certificates are validated.
        base_url: Optional prefix applied by pending requests.
        http2: Whether HTTP/2 negotiation is enabled.
    """

    timeout: float = 5.0
    connect_timeout: float = 5.0
    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: float = 5.0
    follow_redirects: bool = False
    verify_tls: bool = True
    base_url: str = ""
    http2: bool = False


@dataclass(frozen=True, slots=True)
class HttpConfiguration:
    """Group validated server and client defaults for one application.

    Settings are validated before creating application-owned clients.
    """

    server: ServerConfiguration
    client: ClientConfiguration

    @classmethod
    def from_repository(cls, repository: ConfigReader) -> HttpConfiguration:
        """Read and validate the canonical ``http`` configuration namespace.

        Args:
            repository: Read-only configuration capability owned by the app.

        Returns:
            Immutable defaults shared by incoming and outgoing HTTP services.

        Raises:
            HttpConfigurationError: If a configured value has the wrong type
                or violates a positive-value constraint.
        """
        server = ServerConfiguration(
            max_body_size=_positive_int(
                repository.get(
                    "http.server.max_body_size",
                    _DEFAULT_BODY_LIMIT,
                ),
                "http.server.max_body_size",
            ),
            max_form_files=_positive_int(
                repository.get("http.server.max_form_files", 100),
                "http.server.max_form_files",
            ),
            max_form_fields=_positive_int(
                repository.get("http.server.max_form_fields", 1000),
                "http.server.max_form_fields",
            ),
            max_part_size=_positive_int(
                repository.get("http.server.max_part_size", 1024 * 1024),
                "http.server.max_part_size",
            ),
        )
        client = ClientConfiguration(
            timeout=_positive_float(
                repository.get("http.client.timeout", 5.0),
                "http.client.timeout",
            ),
            connect_timeout=_positive_float(
                repository.get("http.client.connect_timeout", 5.0),
                "http.client.connect_timeout",
            ),
            max_connections=_positive_int(
                repository.get("http.client.max_connections", 100),
                "http.client.max_connections",
            ),
            max_keepalive_connections=_positive_int(
                repository.get(
                    "http.client.max_keepalive_connections",
                    20,
                ),
                "http.client.max_keepalive_connections",
            ),
            keepalive_expiry=_positive_float(
                repository.get("http.client.keepalive_expiry", 5.0),
                "http.client.keepalive_expiry",
            ),
            follow_redirects=_boolean(
                repository.get("http.client.follow_redirects", False),
                "http.client.follow_redirects",
            ),
            verify_tls=_boolean(
                repository.get("http.client.verify_tls", True),
                "http.client.verify_tls",
            ),
            base_url=_string(
                repository.get("http.client.base_url", ""),
                "http.client.base_url",
            ),
            http2=_boolean(
                repository.get("http.client.http2", False),
                "http.client.http2",
            ),
        )
        if client.max_keepalive_connections > client.max_connections:
            raise HttpConfigurationError(_KEEPALIVE_EXCEEDS_CONNECTIONS_ERROR)
        return cls(server=server, client=client)


def _positive_int(value: object, key: str) -> int:
    """Validate a positive integer without accepting boolean values.

    Args:
        value: Value read from configuration.
        key: Safe configuration path used in the error message.

    Returns:
        The validated positive integer.

    Raises:
        HttpConfigurationError: If the value is not a positive integer.
    """
    if type(value) is not int or value <= 0:
        message = f"[{key}] must be a positive integer."
        raise HttpConfigurationError(message)
    return value


def _positive_float(value: object, key: str) -> float:
    """Validate a positive numeric timeout without accepting booleans.

    Args:
        value: Value read from configuration.
        key: Safe configuration path used in the error message.

    Returns:
        The validated value represented as a float.

    Raises:
        HttpConfigurationError: If the value is not positive and numeric.
    """
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value <= 0
    ):
        message = f"[{key}] must be a positive number."
        raise HttpConfigurationError(message)
    return float(value)


def _boolean(value: object, key: str) -> bool:
    """Validate one boolean configuration value strictly.

    Args:
        value: Value read from configuration.
        key: Safe configuration path used in the error message.

    Returns:
        The validated boolean.

    Raises:
        HttpConfigurationError: If the value is not exactly a boolean.
    """
    if type(value) is not bool:
        message = f"[{key}] must be a boolean."
        raise HttpConfigurationError(message)
    return value


def _string(value: object, key: str) -> str:
    """Validate a string configuration value.

    Args:
        value: Value read from configuration.
        key: Safe configuration path used in the error message.

    Returns:
        The validated string.

    Raises:
        HttpConfigurationError: If the value is not a string.
    """
    if not isinstance(value, str):
        message = f"[{key}] must be a string."
        raise HttpConfigurationError(message)
    return value


__all__ = [
    "ClientConfiguration",
    "HttpConfiguration",
    "ServerConfiguration",
]
