"""Verify response construction, encoding, and header safety.

Local fixtures keep these assertions deterministic.
"""

from collections.abc import AsyncGenerator, AsyncIterator
from http import HTTPStatus
from pathlib import Path
from typing import Self, cast

import pytest

from titanspan.contracts.http import JsonValue
from titanspan.contracts.http.events import ServerSentEvent
from titanspan.http.response import (
    CookieOptions,
    FileResponse,
    HtmlResponse,
    JsonResponse,
    RedirectResponse,
    Response,
    StreamResponse,
)
from titanspan.http.response_factory import NativeResponseFactory

pytestmark = pytest.mark.unit
_EXPECTED_RESPONSE_COOKIES = 2


def test_text_and_json_responses_keep_status_and_media_type() -> None:
    """Build plain and JSON responses with caller-selected status codes.

    The assertions verify the public result and its error paths.
    """
    plain = Response(
        "ready",
        status=HTTPStatus.ACCEPTED,
        content_type="text/plain",
    )
    structured = JsonResponse(
        {"ready": True},
        status=HTTPStatus.CREATED,
    )

    assert plain.status_code == HTTPStatus.ACCEPTED
    assert plain.body == b"ready"
    assert plain.headers["content-type"] == "text/plain; charset=utf-8"
    assert structured.status_code == HTTPStatus.CREATED
    assert structured.body == b'{"ready":true}'
    assert structured.headers["content-type"] == "application/json"
    assert structured.with_header("X-Request-ID", "request-1") is structured
    assert structured.headers["X-Request-ID"] == "request-1"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("Bad Header", "value"),
        ("X-Trace", "safe\r\nInjected: yes"),
    ],
)
def test_response_rejects_header_injection(
    name: str,
    value: str,
) -> None:
    """Reject malformed header tokens and response-splitting values.

    The assertions verify the public result and its error paths.
    """
    response = Response()

    with pytest.raises(
        ValueError,
        match=r"unsupported characters|line breaks",
    ):
        response.with_header(name, value)


def test_response_rejects_unsafe_headers_at_construction() -> None:
    """Validate constructor headers before the backend encodes them.

    The assertions verify the public result and its error paths.
    """
    with pytest.raises(ValueError, match="line breaks"):
        Response(headers={"X-Trace": "safe\nInjected: yes"})


def test_response_never_sends_content_for_bodyless_status() -> None:
    """Discard supplied bytes for status codes that cannot carry a body.

    The assertions verify the public result and its error paths.
    """
    response = Response("discarded", status=204)

    assert response.body == b""


def test_json_response_rejects_bodyless_status() -> None:
    """Require the dedicated empty response constructor for bodyless codes.

    The assertions verify the public result and its error paths.
    """
    with pytest.raises(ValueError, match="cannot carry a response body"):
        JsonResponse({"ready": True}, status=204)


def test_cookie_defaults_and_cache_policy_are_explicit() -> None:
    """Set secure cookie flags and a private no-store cache policy.

    The assertions verify the public result and its error paths.
    """
    response = Response().with_cookie("session", "opaque")
    response.cache_control(max_age=0, no_store=True)

    cookie = response.headers["set-cookie"]
    assert "secure" in cookie.lower()
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()
    assert response.headers["cache-control"] == ("private, no-store, max-age=0")
    assert response.cache_control() is response
    assert response.headers["cache-control"] == "private"


def test_response_variants_create_and_remove_cookies(
    tmp_path: Path,
) -> None:
    """Expose fluent cookie operations across native response types.

    Removal appends an expiry header with the configured cookie scope.
    """

    async def chunks() -> AsyncIterator[bytes]:
        """Yield one body chunk for the streaming response case.

        The generator backs the response cookie behavior test.
        """
        yield b"stream"

    path = tmp_path / "download.txt"
    path.write_text("download", encoding="utf-8")
    responses = (
        Response(),
        JsonResponse({"ok": True}),
        HtmlResponse("<p>ok</p>"),
        RedirectResponse("/next"),
        StreamResponse(chunks()),
        FileResponse(path),
    )

    for response in responses:
        assert response.with_cookie("session", "opaque") is response
        assert response.without_cookie("session") is response
        cookies = [
            value.decode("latin-1")
            for name, value in response.raw_headers
            if name.lower() == b"set-cookie"
        ]
        assert len(cookies) == _EXPECTED_RESPONSE_COOKIES
        assert "session=opaque" in cookies[0]
        assert 'session="";' in cookies[1]
        assert "max-age=0" in cookies[1].lower()


def test_cookie_and_cache_validation_rejects_unsafe_values() -> None:
    """Reject invalid cookie policies and negative cache lifetimes.

    The assertions verify the public result and its error paths.
    """
    invalid_options = CookieOptions()
    object.__setattr__(invalid_options, "same_site", "invalid")
    with pytest.raises(ValueError, match="same_site"):
        Response().with_cookie(
            "name",
            "value",
            options=invalid_options,
        )
    with pytest.raises(ValueError, match="line breaks"):
        Response().with_cookie("name", "bad\r\nvalue")
    with pytest.raises(ValueError, match="line breaks"):
        Response().with_cookie("bad name", "value")
    with pytest.raises(ValueError, match="non-negative"):
        Response().cache_control(max_age=-1)


def test_cookie_options_validate_attributes_and_allow_explicit_policy() -> None:
    """Serialize explicit cookie attributes and reject delimiter injection.

    The assertions verify the public result and its error paths.
    """
    response = Response().with_cookie(
        "session_id",
        "opaque-token",
        options=CookieOptions(
            max_age=60,
            path="/account",
            domain="example.test",
            secure=False,
            http_only=False,
            same_site="strict",
        ),
    )
    cookie = response.headers["set-cookie"].lower()
    assert "max-age=60" in cookie
    assert "path=/account" in cookie
    assert "domain=example.test" in cookie
    assert "samesite=strict" in cookie
    assert "secure" not in cookie
    assert "httponly" not in cookie
    assert response.cache_control(private=False, max_age=30) is response
    assert response.headers["cache-control"] == "public, max-age=30"

    invalid_options = (
        CookieOptions(path="/bad;path"),
        CookieOptions(path="/bad\x7fpath"),
        CookieOptions(domain="example.test; Secure"),
        CookieOptions(max_age=-1),
    )
    for options in invalid_options:
        with pytest.raises(ValueError, match="Cookie"):
            Response().with_cookie("session", "value", options=options)
    with pytest.raises(ValueError, match="domain"):
        Response().with_cookie(
            "session",
            "value",
            options=CookieOptions(domain="example.test\r"),
        )


@pytest.mark.parametrize(
    ("location", "allow_external"),
    [
        ("//attacker.example", False),
        ("https://attacker.example", False),
        ("javascript:alert(1)", True),
    ],
)
def test_redirect_rejects_protocol_relative_and_unapproved_urls(
    location: str,
    allow_external: bool,
) -> None:
    """Prevent protocol-relative and non-HTTP redirect destinations.

    The assertions verify the public result and its error paths.
    """
    with pytest.raises(
        ValueError,
        match=r"not permitted|explicit permission|Redirect",
    ):
        RedirectResponse(location, allow_external=allow_external)


def test_redirect_accepts_local_paths_and_explicit_http_destinations() -> None:
    """Permit local redirects by default and HTTP URLs by explicit choice.

    The assertions verify the public result and its error paths.
    """
    local = RedirectResponse("/documents", status=HTTPStatus.FOUND)
    external = RedirectResponse(
        "https://example.test/",
        allow_external=True,
    )

    assert local.status_code == HTTPStatus.FOUND
    assert local.headers["location"] == "/documents"
    assert external.headers["location"] == "https://example.test/"


def test_html_response_and_redirect_validation_cover_native_status_rules() -> (
    None
):
    """Validate HTML response headers and reject malformed redirects.

    The assertions verify the public result and its error paths.
    """
    html = HtmlResponse("<h1>Ready</h1>", status=HTTPStatus.ACCEPTED)
    assert html.body == b"<h1>Ready</h1>"
    assert html.headers["content-type"] == "text/html; charset=utf-8"
    assert html.with_header("X-Trace", "done") is html
    redirect = RedirectResponse("/local")
    assert redirect.with_header("X-Trace", "done") is redirect

    with pytest.raises(ValueError, match="301, 302"):
        RedirectResponse("/local", status=HTTPStatus.OK)
    with pytest.raises(ValueError, match="non-empty and printable"):
        RedirectResponse("")
    with pytest.raises(ValueError, match="non-empty and printable"):
        RedirectResponse("/safe\x00path")
    with pytest.raises(ValueError, match="explicit permission"):
        RedirectResponse("ftp://example.test/file", allow_external=True)


def test_response_factory_produces_empty_bodyless_responses() -> None:
    """Create an empty 204 response through the native response factory.

    The assertions verify the public result and its error paths.
    """
    response = NativeResponseFactory().no_content()

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.body == b""


def test_factory_builds_specialized_responses_and_validates_empty_status() -> (
    None
):
    """Exercise factory operations and preserve their specialized types.

    The assertions verify the public result and its error paths.
    """
    factory = NativeResponseFactory()
    bodyless = factory("discarded", status=HTTPStatus.NOT_MODIFIED)
    assert bodyless.body == b""

    json_response = factory.json({"ready": True})
    html_response = factory.html("<p>ready</p>")
    redirect_response = factory.redirect("/ready")
    assert json_response.headers["content-type"] == "application/json"
    assert html_response.headers["content-type"].startswith("text/html")
    assert redirect_response.headers["location"] == "/ready"

    with pytest.raises(ValueError, match="status 204 or 304"):
        factory.no_content(status=HTTPStatus.OK)

    file_response = factory.download(__file__, filename="report.py")
    assert file_response.headers["content-disposition"].endswith(
        'filename="report.py"'
    )


@pytest.mark.anyio
async def test_stream_response_encodes_chunks_and_closes_source() -> None:
    """Forward chunks incrementally and close an async generator source.

    The assertions verify the public result and its error paths.
    """
    finalized = False

    async def source() -> AsyncIterator[bytes | str]:
        """Yield mixed chunks and record finalization by the wrapper.

        Local fixtures keep these assertions deterministic.
        """
        nonlocal finalized
        try:
            yield "first"
            yield b"second"
        finally:
            finalized = True

    response = StreamResponse(source(), content_type="text/plain")
    iterator = response.body_iterator
    chunks = [chunk async for chunk in iterator]

    assert chunks == [b"first", b"second"]
    assert finalized
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.with_header("X-Stream", "yes") is response


@pytest.mark.anyio
async def test_event_stream_encodes_metadata_and_json_values() -> None:
    """Encode typed SSE data without collecting the event source.

    The assertions verify the public result and its error paths.
    """

    async def events() -> AsyncIterator[ServerSentEvent]:
        """Yield one event with every optional metadata field.

        Local fixtures keep these assertions deterministic.
        """
        yield ServerSentEvent(
            {"token": "ok"},
            event="delta",
            identifier="node-1",
            retry=500,
        )

    response = NativeResponseFactory().event_stream(events())
    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks == [
        b'event: delta\nid: node-1\nretry: 500\ndata: {"token":"ok"}\n\n'
    ]
    assert response.headers["content-type"].startswith("text/event-stream")


@pytest.mark.parametrize(
    ("event", "message"),
    [
        (ServerSentEvent("data", identifier="invalid\x00id"), "NUL"),
        (ServerSentEvent("data", retry=-1), "non-negative"),
        (ServerSentEvent("data", event="invalid\rfield"), "carriage"),
    ],
)
def test_server_sent_event_rejects_unsafe_metadata(
    event: ServerSentEvent,
    message: str,
) -> None:
    """Reject control characters and invalid retry values before encoding.

    SSE metadata is line-oriented and must not permit field injection.
    """
    with pytest.raises(ValueError, match=message):
        event.encode()


@pytest.mark.anyio
async def test_event_stream_encodes_json_values_and_closes_source() -> None:
    """Encode plain data and finalize an async source on early close.

    The assertions verify the public result and its error paths.
    """
    finalized = False

    async def events() -> AsyncIterator[JsonValue]:
        """Yield JSON-compatible data for automatic event wrapping.

        Local fixtures keep these assertions deterministic.
        """
        yield {"token": "one"}

    factory = NativeResponseFactory()
    event_response = factory.event_stream(events())
    assert [chunk async for chunk in event_response.body_iterator] == [
        b'data: {"token":"one"}\n\n'
    ]

    async def source() -> AsyncIterator[bytes | str]:
        """Yield chunks while allowing the wrapper to finalize the source.

        Local fixtures keep these assertions deterministic.
        """
        nonlocal finalized
        try:
            yield "first"
            yield "second"
        finally:
            finalized = True

    response = factory.stream(source())
    iterator = cast(
        "AsyncGenerator[bytes, None]",
        aiter(response.body_iterator),
    )
    assert await anext(iterator) == b"first"
    await iterator.aclose()
    assert finalized


@pytest.mark.anyio
async def test_stream_encoder_supports_custom_async_iterators() -> None:
    """Encode async iterators whose implementation is not a generator.

    The assertions verify the public result and its error paths.
    """

    class Chunks:
        """Yield one chunk without providing generator finalization.

        Local fixtures keep these assertions deterministic.
        """

        def __init__(self) -> None:
            """Start the iterator before its first chunk.

            Local fixtures keep these assertions deterministic.
            """
            self._started = False

        def __aiter__(self) -> Self:
            """Return the stateful iterator itself.

            Local fixtures keep these assertions deterministic.
            """
            return self

        async def __anext__(self) -> bytes:
            """Return a chunk once, then signal normal completion.

            Local fixtures keep these assertions deterministic.
            """
            if self._started:
                raise StopAsyncIteration
            self._started = True
            return b"chunk"

        _started: bool

    response = StreamResponse(Chunks())
    assert [chunk async for chunk in response.body_iterator] == [b"chunk"]


def test_file_download_uses_safe_basename(tmp_path: Path) -> None:
    """Strip client-like path components from the download disposition.

    The assertions verify the public result and its error paths.
    """
    file_path = tmp_path / "report.txt"
    file_path.write_text("report", encoding="utf-8")

    response = FileResponse(file_path, filename="../../private/report.txt")

    assert response.headers["content-disposition"].endswith(
        'filename="report.txt"'
    )


def test_file_response_rejects_unsafe_download_metadata(tmp_path: Path) -> None:
    """Reject bodyless status and unsafe filename or media type metadata.

    The assertions verify the public result and its error paths.
    """
    file_path = tmp_path / "report.txt"
    file_path.write_text("report", encoding="utf-8")

    with pytest.raises(ValueError, match="cannot carry a response body"):
        FileResponse(file_path, status=HTTPStatus.NO_CONTENT)
    with pytest.raises(ValueError, match="line breaks"):
        FileResponse(file_path, filename="report\r\n.txt")
    with pytest.raises(ValueError, match="line breaks"):
        FileResponse(file_path, content_type="text/plain\nX-Bad: yes")

    file_response = FileResponse(file_path)
    assert file_response.with_header("X-File", "ready") is file_response
