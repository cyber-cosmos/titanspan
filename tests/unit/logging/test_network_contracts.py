"""Verify safe configuration boundaries for network logging drivers.

Tests use synthetic configuration only and never contact a network service.
"""

import pytest

from titanspan.logging.drivers.network import webhook_options
from titanspan.logging.exceptions import LogConfigurationError

pytestmark = pytest.mark.unit
PRIVATE_MARKER = "credential-must-not-appear"


@pytest.mark.parametrize(
    "options",
    [
        {"url": "http://logs.example.test"},
        {"url": f"https://user:{PRIVATE_MARKER}@logs.example.test"},
        {"url": "https://logs.example.test/path#fragment"},
        {
            "url": "https://logs.example.test",
            "headers": {"X-Log": "value\r\ninjected: true"},
        },
        {
            "url": "https://logs.example.test",
            "headers": {"Host": "attacker.example.test"},
        },
        {"url": "https://logs.example.test", "unknown": "value"},
    ],
)
def test_webhook_configuration_rejects_unsafe_destinations(
    options: dict[str, object],
) -> None:
    """Reject insecure URLs and malformed transport configuration.

    The validator reports field locations without copying configured values.

    Args:
        options: A malformed destination that must fail closed.
    """
    with pytest.raises(LogConfigurationError) as error:
        webhook_options(options)

    assert PRIVATE_MARKER not in str(error.value)


def test_webhook_configuration_allows_explicit_local_http() -> None:
    """Allow plain HTTP only after an explicit configuration opt-in.

    This supports loopback integration tests without changing network policy.
    """
    result = webhook_options(
        {
            "url": "http://127.0.0.1:9000/logs",
            "allow_http": True,
        },
    )

    assert result.url.get_secret_value() == "http://127.0.0.1:9000/logs"


def test_webhook_configuration_rejects_transport_override_headers() -> None:
    """Prevent callers from replacing HTTP framing headers.

    The request library remains responsible for host and body length fields.
    """
    with pytest.raises(LogConfigurationError):
        webhook_options(
            {
                "url": "https://logs.example.test",
                "headers": {"Content-Length": "0"},
            },
        )


def test_webhook_configuration_rejects_oversized_header_sets() -> None:
    """Bound custom headers before a channel can send a log record.

    Invalid configuration is rejected before any network resource is opened.
    """
    headers = {f"X-Header-{index}": "value" for index in range(33)}

    with pytest.raises(LogConfigurationError):
        webhook_options(
            {
                "url": "https://logs.example.test",
                "headers": headers,
            },
        )
