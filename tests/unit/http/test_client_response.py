"""Verify native outgoing response behavior without a network transport.

Local fixtures keep these assertions deterministic.
"""

from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

from titanspan.contracts.http.events import ServerSentEvent
from titanspan.http.client.response import ClientResponse
from titanspan.http.exceptions import HttpClientError, HttpStatusError

if TYPE_CHECKING:
    from titanspan.http.client.response import ResponseAccess

pytestmark = pytest.mark.unit
_DOCUMENT_ID = 7


class ResponseAccessFake:
    """Provide deterministic response data and resource counters.

    Local fixtures keep these assertions deterministic.
    """

    def __init__(
        self,
        *,
        status_code: int = HTTPStatus.OK,
        json_value: object = None,
        body_error: Exception | None = None,
        chunks: tuple[bytes, ...] = (b"first", b"second"),
    ) -> None:
        """Create a transport response with optional malformed access.

        Args:
            status_code: Status observed by response helper methods.
            json_value: Object returned by the transport JSON decoder.
            body_error: Optional exception raised by buffered body methods.
            chunks: Byte chunks exposed by the transport iterators.
        """
        self.status_code = status_code
        self.headers = {"Content-Type": "application/json"}
        self.cookies = {"session": "response-cookie"}
        self.json_value = json_value
        self.body_error = body_error
        self.chunks = chunks
        self.closed = 0
        self.async_closed = 0

    def body(self) -> bytes:
        """Return buffered bytes or simulate an unavailable stream body.

        Local fixtures keep these assertions deterministic.
        """
        self._raise_body_error()
        return b'{"data":{"id":7}}'

    def text(self) -> str:
        """Decode the deterministic body used by text assertions.

        Local fixtures keep these assertions deterministic.
        """
        self._raise_body_error()
        return '{"data":{"id":7}}'

    def json(self) -> object:
        """Return the selected decoded JSON value.

        Local fixtures keep these assertions deterministic.
        """
        self._raise_body_error()
        return self.json_value

    def iter_bytes(self) -> Iterator[bytes]:
        """Yield two chunks to verify direct synchronous forwarding.

        Local fixtures keep these assertions deterministic.
        """
        yield from self.chunks

    async def iter_bytes_async(self) -> AsyncIterator[bytes]:
        """Yield response chunks through an asynchronous iterator.

        Local fixtures keep these assertions deterministic.
        """
        for chunk in self.chunks:
            yield chunk

    def close(self) -> None:
        """Count synchronous resource finalization calls.

        Local fixtures keep these assertions deterministic.
        """
        self.closed += 1

    async def aclose(self) -> None:
        """Count asynchronous resource finalization calls.

        Local fixtures keep these assertions deterministic.
        """
        self.async_closed += 1

    def _raise_body_error(self) -> None:
        """Raise the configured body error when exercising error paths.

        Local fixtures keep these assertions deterministic.
        """
        if self.body_error is not None:
            raise self.body_error

    status_code: int
    headers: Mapping[str, str]
    cookies: Mapping[str, str]
    json_value: object
    body_error: Exception | None
    chunks: tuple[bytes, ...]
    closed: int
    async_closed: int


def _response(
    access: ResponseAccessFake,
    *,
    asynchronous: bool = False,
) -> ClientResponse:
    """Bind the fake adapter to a native response wrapper.

    Local fixtures keep these assertions deterministic.
    """
    typed_access: ResponseAccess = access
    return ClientResponse(typed_access, asynchronous=asynchronous)


@pytest.mark.parametrize(
    ("status", "check"),
    [
        (HTTPStatus.OK, ClientResponse.ok),
        (HTTPStatus.CREATED, ClientResponse.created),
        (HTTPStatus.ACCEPTED, ClientResponse.accepted),
        (HTTPStatus.NO_CONTENT, ClientResponse.no_content),
        (HTTPStatus.NOT_FOUND, ClientResponse.not_found),
        (HTTPStatus.UNAUTHORIZED, ClientResponse.unauthorized),
        (HTTPStatus.FORBIDDEN, ClientResponse.forbidden),
        (HTTPStatus.TOO_MANY_REQUESTS, ClientResponse.too_many_requests),
    ],
)
def test_named_status_checks_match_exact_statuses(
    status: HTTPStatus,
    check: Callable[[ClientResponse], bool],
) -> None:
    """Expose native convenience checks for common response statuses.

    The assertions verify the public result and its error paths.
    """
    response = _response(ResponseAccessFake(status_code=status))

    assert check(response)


def test_status_groups_classify_success_client_and_server_errors() -> None:
    """Classify status families without automatically raising HTTP errors.

    The assertions verify the public result and its error paths.
    """
    success = _response(ResponseAccessFake(status_code=HTTPStatus.CREATED))
    client_error = _response(
        ResponseAccessFake(status_code=HTTPStatus.NOT_FOUND)
    )
    server_error = _response(
        ResponseAccessFake(status_code=HTTPStatus.BAD_GATEWAY)
    )

    assert success.successful()
    assert not success.failed()
    assert client_error.client_error()
    assert client_error.failed()
    assert server_error.server_error()
    assert server_error.failed()


def test_response_exposes_immutable_headers_and_typed_json_values() -> None:
    """Normalize header lookup and validate nested JSON data.

    The assertions verify the public result and its error paths.
    """
    response = _response(ResponseAccessFake(json_value={"data": {"id": 7}}))

    assert response.header("content-TYPE") == "application/json"
    assert response.cookies == {"session": "response-cookie"}
    assert response.json_path("data.id") == _DOCUMENT_ID
    assert response.body() == b'{"data":{"id":7}}'
    assert response.text() == '{"data":{"id":7}}'


def test_invalid_json_and_unbuffered_body_errors_are_native() -> None:
    """Translate decoder and stream-access failures without payload leaks.

    The assertions verify the public result and its error paths.
    """
    invalid = _response(
        ResponseAccessFake(json_value=object(), body_error=ValueError("secret"))
    )
    with pytest.raises(HttpClientError, match="not valid JSON") as captured:
        invalid.json()
    assert "secret" not in str(captured.value)

    unbuffered = _response(
        ResponseAccessFake(body_error=RuntimeError("body not loaded"))
    )
    with pytest.raises(HttpClientError, match="not buffered"):
        unbuffered.body()
    with pytest.raises(HttpClientError, match="not buffered"):
        unbuffered.text()


def test_status_escalation_is_explicit_and_safe() -> None:
    """Keep successful responses as values and sanitize error messages.

    The assertions verify the public result and its error paths.
    """
    successful = _response(ResponseAccessFake())
    assert successful.throw() is successful
    assert successful.throw_if(False) is successful
    assert successful.throw_if(lambda result: result.failed()) is successful

    rejected = _response(
        ResponseAccessFake(status_code=HTTPStatus.SERVICE_UNAVAILABLE)
    )
    with pytest.raises(HttpStatusError, match="status 503") as captured:
        rejected.throw_if(lambda result: result.server_error())
    assert "response payload" not in str(captured.value)


def test_sync_sse_parser_handles_multibyte_and_split_crlf_chunks() -> None:
    """Decode event fields across chunk and UTF-8 character boundaries.

    The transport may split both code points and CRLF line endings.
    """
    access = ResponseAccessFake(
        chunks=(
            b"\xef\xbb\xbfdata: snowman \xe2",
            b"\x98\x83\r",
            b"\nevent: update\nid: event-7\nretry: 250\n\n",
        )
    )
    response = _response(access)

    assert list(response.iter_sse()) == [
        ServerSentEvent(
            "snowman \u2603",
            event="update",
            identifier="event-7",
            retry=250,
        )
    ]


def test_sse_parser_resets_empty_event_type_and_bounds_event_size() -> None:
    """Apply SSE field reset semantics and stop oversized events.

    An empty event type resets to the default message type.
    """
    reset = _response(
        ResponseAccessFake(chunks=(b"event: update\nevent:\ndata: ready\n\n",))
    )
    assert list(reset.iter_sse()) == [ServerSentEvent("ready")]

    oversized = _response(
        ResponseAccessFake(chunks=(b"data: " + b"x" * 1_048_576 + b"\n\n",))
    )
    with pytest.raises(HttpClientError, match="event exceeds"):
        list(oversized.iter_sse())


@pytest.mark.anyio
async def test_stream_iteration_and_matching_cleanup_are_explicit() -> None:
    """Forward sync and async chunks and close each response only once.

    The assertions verify the public result and its error paths.
    """
    sync_access = ResponseAccessFake()
    sync_response = _response(sync_access)
    assert list(sync_response.iter_bytes()) == [b"first", b"second"]
    sync_response.close()
    sync_response.close()
    assert sync_access.closed == 1

    async_access = ResponseAccessFake()
    async_response = _response(async_access, asynchronous=True)
    chunks = [chunk async for chunk in async_response.iter_bytes_async()]
    assert chunks == [b"first", b"second"]
    with pytest.raises(HttpClientError, match="Use aclose"):
        async_response.close()
    await async_response.aclose()
    await async_response.aclose()
    assert async_access.async_closed == 1

    sync_access = ResponseAccessFake()
    sync_response = _response(sync_access)
    await sync_response.aclose()
    assert sync_access.closed == 1


@pytest.mark.anyio
async def test_async_sse_flushes_final_cr_and_bounds_partial_lines() -> None:
    """Flush a final CR delimiter and reject an oversized partial line.

    Async parsing retains backpressure while enforcing the event-size bound.
    """
    final_line = _response(
        ResponseAccessFake(chunks=(b"data: final\n\r",)),
        asynchronous=True,
    )
    events = [event async for event in final_line.iter_sse_async()]
    assert events == [ServerSentEvent("final")]

    oversized = _response(
        ResponseAccessFake(chunks=(b"x" * 1_048_577,)),
        asynchronous=True,
    )
    with pytest.raises(HttpClientError, match="event exceeds"):
        _ = [event async for event in oversized.iter_sse_async()]
