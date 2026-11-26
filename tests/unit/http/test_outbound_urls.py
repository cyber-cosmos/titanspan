"""Verify HTTP URL policy rejects unsafe and malformed destinations.

The checks do not claim comprehensive SSRF protection.
"""

import pytest

from titanspan.http._urls import validate_base_url, validate_outbound_url
from titanspan.http.exceptions import HttpClientError

pytestmark = pytest.mark.unit


def test_url_policy_accepts_http_destinations_and_relative_paths() -> None:
    """Accept HTTP(S) destinations and paths resolved by a base URL.

    Relative paths remain unchanged for resolution by HTTPX2.
    """
    assert validate_base_url("https://api.example.test/v1") == (
        "https://api.example.test/v1/"
    )
    assert validate_outbound_url("/users", base_url="https://api.test/v1/") == (
        "/users"
    )
    assert (
        validate_outbound_url(
            "https://api.example.test/users",
        )
        == "https://api.example.test/users"
    )


def test_url_policy_rejects_malformed_and_credentialed_destinations() -> None:
    """Reject malformed authorities, unsafe schemes, and relative escapes.

    Every outbound destination must have a supported HTTP boundary.
    """
    for value in (
        "",
        "file:///etc/passwd",
        "https://{}:{}@example.test/".format("user", "secret"),
        "//example.test/path",
        "https://[",
        "https://example.test:invalid/",
        "http://example.test\\@evil.test/",
    ):
        with pytest.raises(HttpClientError, match=r"HTTP\(S\) URLs"):
            validate_outbound_url(value)

    with pytest.raises(HttpClientError, match=r"HTTP\(S\) URLs"):
        validate_outbound_url("relative/path")
    with pytest.raises(HttpClientError, match=r"HTTP\(S\) URLs"):
        validate_outbound_url("relative/path", base_url="file:///unsafe/")


def test_base_url_rejects_invalid_authority_and_query_components() -> None:
    """Reject unsupported base URLs before they reach a client pool.

    Query strings and fragments must remain request-local values.
    """
    for value in (
        "http://example.test:bad-port/",
        "https://example.test/v1?token=secret",
        "https://example.test/v1#fragment",
        "https://name@example.test/",
    ):
        with pytest.raises(ValueError, match="base_url"):
            validate_base_url(value)
