"""Verify fake response validation, matching, assertions, and restoration.

HTTPX2 transport behavior is exercised by separate local integrations.
"""

from typing import TYPE_CHECKING, cast

import pytest

from titanspan.http.exceptions import HttpFakeError
from titanspan.http.testing import (
    HttpFake,
    HttpFakeResponse,
    HttpRequestPattern,
    SentRequest,
    current_http_fake,
    require_http_fake,
)

pytestmark = pytest.mark.unit

if TYPE_CHECKING:
    from titanspan.contracts.http import JsonValue
    from titanspan.http.testing import HttpFakeResponses


def _request() -> SentRequest:
    """Create one immutable request for assertion behavior checks.

    The fixture has stable header and body values for pattern matching.
    """
    return SentRequest(
        method="POST",
        url="https://example.test/items/7",
        headers={"x-trace": "trace-7"},
        body=b"payload",
    )


def test_fake_response_validation_and_immutable_header_snapshots() -> None:
    """Validate fake status and JSON values before building transports.

    Header snapshots cannot be mutated through the caller's original mapping.
    """
    headers = {"X-Mode": "test"}
    response = HttpFakeResponse(headers=headers)
    headers["X-Mode"] = "changed"
    assert response.headers == {"X-Mode": "test"}

    with pytest.raises(ValueError, match="between 100 and 599"):
        HttpFakeResponse(status=99)
    with pytest.raises(TypeError, match="JSON value"):
        HttpFakeResponse(content=cast("JsonValue", object()))


def test_fake_assertions_match_urls_patterns_and_predicates() -> None:
    """Match captured requests and report failed sent-count assertions.

    Every matcher observes the same immutable request snapshot.
    """
    pattern = HttpRequestPattern(
        url="https://example.test/items/*",
        method="post",
        headers={"X-Trace": "trace-7"},
        body=b"payload",
    )
    fake = HttpFake({pattern: HttpFakeResponse({"ok": True})})
    request = _request()

    with fake:
        assert current_http_fake() is fake
        assert require_http_fake() is fake
        assert fake.response_for(request).content == {"ok": True}
        assert request.header("X-Trace") == "trace-7"
        fake.assert_sent()
        fake.assert_sent("https://example.test/*")
        fake.assert_sent(lambda sent: sent.method == "POST")
        fake.assert_not_sent("https://other.test/*")
        fake.assert_sent_count(1, pattern)

        with pytest.raises(AssertionError, match="was not sent"):
            fake.assert_sent("https://other.test/*")
        with pytest.raises(AssertionError, match="forbidden pattern"):
            fake.assert_not_sent(pattern)
        with pytest.raises(AssertionError, match="count did not match"):
            fake.assert_sent_count(2)
        with pytest.raises(ValueError, match="cannot be negative"):
            fake.assert_sent_count(-1)

    assert current_http_fake() is None
    with pytest.raises(HttpFakeError, match="active fake context"):
        require_http_fake()
    with pytest.raises(HttpFakeError, match="not active"):
        fake.__exit__(None, None, None)


def test_fake_rejects_reentry_and_invalid_response_definitions() -> None:
    """Reject ambiguous context reuse and malformed response sequences.

    Invalid response definitions fail during fake construction.
    """
    fake = HttpFake({"https://example.test/*": HttpFakeResponse()})
    with fake, pytest.raises(HttpFakeError, match="cannot be re-entered"):
        fake.__enter__()

    invalid = cast(
        "HttpFakeResponses",
        {"https://example.test/*": "invalid response"},
    )
    malformed_sequence = cast(
        "HttpFakeResponses",
        {"https://example.test/*": [HttpFakeResponse(), object()]},
    )
    empty_sequence = cast(
        "HttpFakeResponses",
        {"https://example.test/*": []},
    )
    with pytest.raises(TypeError, match="HttpFakeResponse"):
        HttpFake(invalid)
    with pytest.raises(TypeError, match="HttpFakeResponse"):
        HttpFake(malformed_sequence)
    with pytest.raises(ValueError, match="cannot be empty"):
        HttpFake(empty_sequence)


@pytest.mark.anyio
async def test_fake_context_supports_async_enter_and_exit() -> None:
    """Bind and restore the active fake from asynchronous context managers.

    Async code uses the same context-local session as synchronous code.
    """
    fake = HttpFake({"https://example.test/*": HttpFakeResponse()})
    async with fake:
        assert current_http_fake() is fake

    assert current_http_fake() is None
