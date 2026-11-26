"""Verify immutable HTTP request building and bounded retry decisions.

Local fixtures keep these assertions deterministic.
"""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager, contextmanager
from http import HTTPStatus
from typing import TYPE_CHECKING, Self, cast

import pytest

from titanspan.contracts.http import MultipartFile
from titanspan.http.client.pending_request import PendingRequest
from titanspan.http.exceptions import HttpClientError, HttpTransportError
from titanspan.support import helpers as support_helpers

if TYPE_CHECKING:
    from collections.abc import (
        AsyncGenerator,
        AsyncIterator,
        Generator,
        Iterator,
        Mapping,
        Sequence,
    )

    from titanspan.contracts.http import (
        HttpClientResponse,
        JsonValue,
        OutgoingRequest,
        RequestPayload,
        ServerSentEvent,
    )

pytestmark = pytest.mark.unit
_SUCCESS_LOWER = HTTPStatus.OK
_SUCCESS_UPPER = HTTPStatus.MULTIPLE_CHOICES
_CLIENT_ERROR_LOWER = HTTPStatus.BAD_REQUEST
_SERVER_ERROR_LOWER = HTTPStatus.INTERNAL_SERVER_ERROR
_SERVER_ERROR_UPPER = HTTPStatus.NETWORK_AUTHENTICATION_REQUIRED
_REQUEST_TIMEOUT_SECONDS = 4
_TWO_ATTEMPTS = 2
_THREE_SECONDS = 3
_MAX_RETRY_AFTER = 30
_MIN_JITTER_DELAY = 3
_MAX_JITTER_DELAY = 5
_LOCAL_TRANSPORT_ERROR = "local failure"


class ResponseFake:
    """Represent a transport result while recording explicit cleanup.

    Local fixtures keep these assertions deterministic.
    """

    def __init__(self, status_code: int) -> None:
        """Create a response with one chosen status code.

        Local fixtures keep these assertions deterministic.
        """
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}
        self.closed = False

    def body(self) -> bytes:
        """Return a deterministic buffered representation.

        Local fixtures keep these assertions deterministic.
        """
        return b'{"ok":true}'

    @property
    def cookies(self) -> Mapping[str, str]:
        """Return no cookies for deterministic builder responses.

        The fake response does not model upstream cookie state.
        """
        return {}

    def text(self) -> str:
        """Return the decoded buffered representation.

        Local fixtures keep these assertions deterministic.
        """
        return self.body().decode()

    def json(self) -> JsonValue:
        """Return a JSON-compatible response value.

        Local fixtures keep these assertions deterministic.
        """
        return {"ok": True}

    def successful(self) -> bool:
        """Report whether this response is successful.

        Local fixtures keep these assertions deterministic.
        """
        return _SUCCESS_LOWER <= self.status_code < _SUCCESS_UPPER

    def failed(self) -> bool:
        """Report whether this response is an HTTP error.

        Local fixtures keep these assertions deterministic.
        """
        return self.status_code >= _CLIENT_ERROR_LOWER

    def server_error(self) -> bool:
        """Report whether the response is a server error.

        Local fixtures keep these assertions deterministic.
        """
        return _SERVER_ERROR_LOWER <= self.status_code < _SERVER_ERROR_UPPER

    def throw(self) -> Self:
        """Return the response for builder lifecycle tests.

        Local fixtures keep these assertions deterministic.
        """
        return self

    def header(self, name: str, default: str | None = None) -> str | None:
        """Return one header or its fallback value.

        Local fixtures keep these assertions deterministic.
        """
        return self.headers.get(name.lower(), default)

    def iter_bytes(self) -> Iterator[bytes]:
        """Yield one deterministic response chunk.

        Local fixtures keep these assertions deterministic.
        """
        yield self.body()

    async def iter_bytes_async(self) -> AsyncIterator[bytes]:
        """Yield one deterministic asynchronous response chunk.

        Local fixtures keep these assertions deterministic.
        """
        yield self.body()

    def iter_sse(self) -> Iterator[ServerSentEvent]:
        """Return no events for deterministic JSON responses.

        SSE parsing is covered by the native response tests.
        """
        return iter(())

    def iter_sse_async(self) -> AsyncIterator[ServerSentEvent]:
        """Return an empty asynchronous iterator for fake responses.

        SSE parsing is covered by the native response tests.
        """

        async def empty() -> AsyncIterator[ServerSentEvent]:
            """Yield events through the asynchronous response interface.

            This fixture contains no events.
            """
            for event in self.iter_sse():
                yield event

        return empty()

    def close(self) -> None:
        """Record synchronous response cleanup.

        Local fixtures keep these assertions deterministic.
        """
        self.closed = True

    async def aclose(self) -> None:
        """Record asynchronous response cleanup.

        Local fixtures keep these assertions deterministic.
        """
        self.closed = True

    status_code: int
    headers: Mapping[str, str]
    closed: bool


class ClientFake:
    """Record outgoing transport requests and return selected statuses.

    Local fixtures keep these assertions deterministic.
    """

    def __init__(
        self,
        statuses: tuple[int, ...] = (HTTPStatus.OK,),
    ) -> None:
        """Create a fake with ordered response statuses.

        Local fixtures keep these assertions deterministic.
        """
        self.statuses = statuses
        self.requests: list[OutgoingRequest] = []
        self.responses: list[ResponseFake] = []

    def request(self, request: OutgoingRequest) -> HttpClientResponse:
        """Record one blocking request and create its configured response.

        Local fixtures keep these assertions deterministic.
        """
        self.requests.append(request)
        response = self._next_response()
        self.responses.append(response)
        return response

    async def request_async(
        self,
        request: OutgoingRequest,
    ) -> HttpClientResponse:
        """Record one asynchronous request and create its response.

        Local fixtures keep these assertions deterministic.
        """
        self.requests.append(request)
        response = self._next_response()
        self.responses.append(response)
        return response

    @contextmanager
    def stream(
        self,
        request: OutgoingRequest,
    ) -> Generator[HttpClientResponse, None, None]:
        """Expose a response in a synchronous stream context.

        Local fixtures keep these assertions deterministic.
        """
        yield self.request(request)

    @asynccontextmanager
    async def stream_async(
        self,
        request: OutgoingRequest,
    ) -> AsyncGenerator[HttpClientResponse, None]:
        """Expose a response in an asynchronous stream context.

        Local fixtures keep these assertions deterministic.
        """
        yield await self.request_async(request)

    def _next_response(self) -> ResponseFake:
        """Select a response status, repeating the final configured status.

        Local fixtures keep these assertions deterministic.
        """
        index = len(self.requests) - 1
        status = self.statuses[min(index, len(self.statuses) - 1)]
        return ResponseFake(status)

    statuses: tuple[int, ...]
    requests: list[OutgoingRequest]
    responses: list[ResponseFake]


class FailingClientFake(ClientFake):
    """Fail a chosen number of requests before returning real response fakes.

    Local fixtures keep these assertions deterministic.
    """

    def __init__(self, failures: int) -> None:
        """Create a fake that raises a native transport error first.

        Local fixtures keep these assertions deterministic.
        """
        super().__init__()
        self.failures = failures

    def request(self, request: OutgoingRequest) -> HttpClientResponse:
        """Raise a transport failure or delegate to the response fake.

        Local fixtures keep these assertions deterministic.
        """
        if self.failures:
            self.failures -= 1
            raise HttpTransportError(_LOCAL_TRANSPORT_ERROR)
        return super().request(request)

    async def request_async(
        self,
        request: OutgoingRequest,
    ) -> HttpClientResponse:
        """Raise an async transport failure or delegate to the fake.

        Local fixtures keep these assertions deterministic.
        """
        if self.failures:
            self.failures -= 1
            raise HttpTransportError(_LOCAL_TRANSPORT_ERROR)
        return await super().request_async(request)

    failures: int


class RetryAfterClientFake(ClientFake):
    """Return Retry-After metadata with the first retryable response.

    Local fixtures keep these assertions deterministic.
    """

    def request(self, request: OutgoingRequest) -> HttpClientResponse:
        """Attach a server-selected delay before retry evaluation.

        Local fixtures keep these assertions deterministic.
        """
        response = super().request(request)
        if len(self.requests) == 1:
            self.responses[-1].headers = {
                "retry-after": self.retry_after,
            }
        return response

    retry_after: str = "35"


@pytest.mark.anyio
async def test_builder_options_are_isolated_and_snapshotted_per_request() -> (
    None
):
    """Keep auth, query values, cookies, and JSON mode builder-local.

    The assertions verify the public result and its error paths.
    """
    client = ClientFake()
    root = PendingRequest(client)
    authorized = (
        root.base_url("https://api.example.test/v1")
        .with_token("secret-token")
        .with_query_parameters({"page": 1})
        .with_cookies({"session": "cookie"})
        .timeout(_REQUEST_TIMEOUT_SECONDS)
        .as_json()
    )

    await authorized.post_async("documents", {"name": "report"})
    await root.get_async("https://other.example.test/")

    first, second = client.requests
    assert first.method == "POST"
    assert first.url == "https://api.example.test/v1/documents"
    assert first.headers["Authorization"] == "Bearer secret-token"
    assert first.params == {"page": 1}
    assert first.cookies == {"session": "cookie"}
    assert first.json_enabled
    assert first.json_body == {"name": "report"}
    assert first.timeout == _REQUEST_TIMEOUT_SECONDS
    assert not second.headers
    assert second.cookies == {}
    assert second.params == {}
    assert not second.json_enabled


@pytest.mark.anyio
async def test_builder_snapshots_nested_payload_and_query_values() -> None:
    """Isolate builder state from later caller mutations.

    Nested JSON mappings and repeated query values must not remain aliased to
    mutable objects supplied during builder configuration.
    """
    client = ClientFake()
    tags = ["original"]
    labels = ["original"]
    body = {"nested": {"labels": labels}}
    request = (
        PendingRequest(client)
        .as_json()
        .with_body(body)
        .with_query_parameters({"tag": tags})
    )

    labels.append("changed")
    tags.append("changed")

    await request.post_async("https://api.example.test/items")

    sent = client.requests[0]
    assert sent.json_body == {"nested": {"labels": ["original"]}}
    assert sent.params == {"tag": ("original",)}


@pytest.mark.anyio
async def test_retry_closes_retryable_response_and_preserves_safe_status() -> (
    None
):
    """Retry an idempotent request and close each discarded response.

    The assertions verify the public result and its error paths.
    """
    client = ClientFake((HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.OK))
    request = PendingRequest(client).retry(
        _TWO_ATTEMPTS,
        backoff=0,
        jitter=False,
    )

    response = await request.get_async("https://api.example.test/")

    assert response.status_code == _SUCCESS_LOWER
    assert len(client.requests) == _TWO_ATTEMPTS
    assert client.responses[0].closed
    assert not client.responses[1].closed


@pytest.mark.anyio
async def test_retry_does_not_repeat_unsafe_post_without_idempotency_key() -> (
    None
):
    """Send a failed non-idempotent request only once by default.

    The assertions verify the public result and its error paths.
    """
    client = ClientFake((HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.OK))
    request = PendingRequest(client).retry(
        3,
        backoff=0,
        jitter=False,
    )

    response = await request.post_async(
        "https://api.example.test/payments",
        {"amount": 20},
    )

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert len(client.requests) == 1


@pytest.mark.anyio
async def test_idempotency_key_allows_explicit_post_retry() -> None:
    """Permit retry for an unsafe method when the caller supplies a key.

    The assertions verify the public result and its error paths.
    """
    client = ClientFake((HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.OK))
    request = (
        PendingRequest(client)
        .with_header("Idempotency-Key", "payment-1")
        .retry(2, backoff=0, jitter=False)
    )

    response = await request.post_async(
        "https://api.example.test/payments",
        {"amount": 20},
    )

    assert response.status_code == HTTPStatus.OK
    assert len(client.requests) == _TWO_ATTEMPTS


@pytest.mark.anyio
async def test_builder_rejects_invalid_options_and_arbitrary_json_objects() -> (
    None
):
    """Validate request options and reject unsupported serialization values.

    The assertions verify the public result and its error paths.
    """
    request = PendingRequest(ClientFake())

    with pytest.raises(ValueError, match="absolute HTTP"):
        request.base_url("/relative")
    for url in (
        "file:///etc/passwd",
        "https://{}:{}@example.test/data".format("user", "secret"),
        "//example.test/data",
    ):
        with pytest.raises(HttpClientError, match="destinations"):
            await request.get_async(url)
    for base_url in (
        "file:///etc/passwd",
        "https://{}:{}@example.test/api".format("user", "secret"),
        "https://example.test/api?token=secret",
    ):
        with pytest.raises(ValueError, match="base_url"):
            request.base_url(base_url)
    with pytest.raises(ValueError, match="positive"):
        request.timeout(0)
    with pytest.raises(ValueError, match="at least one"):
        request.retry(0)
    with pytest.raises(ValueError, match="valid HTTP status"):
        request.retry(2, statuses=(700,))
    with pytest.raises(HttpClientError, match="JSON request bodies"):
        await request.as_json().post_async(
            "https://api.example.test/",
            {"unsafe": object()},
        )


@pytest.mark.anyio
async def test_builder_rejects_multipart_json_and_invalid_fields() -> None:
    """Reject mixed JSON uploads and malformed multipart fields.

    Attachment metadata is validated before the transport receives a request.
    """
    request = PendingRequest(ClientFake())
    attachment = MultipartFile("report.txt", b"content", "text/plain")

    with pytest.raises(HttpClientError, match="cannot use JSON encoding"):
        await (
            request.with_files({"document": attachment})
            .as_json()
            .post_async(
                "https://api.example.test/upload",
                {"ok": True},
            )
        )

    with pytest.raises(ValueError, match="Multipart field"):
        request.with_files({"bad\nfield": attachment})

    with pytest.raises(TypeError, match="Multipart field"):
        request.with_files(
            cast(
                "Mapping[str, MultipartFile | Sequence[MultipartFile]]",
                {"document": "not an attachment"},
            )
        )

    with pytest.raises(TypeError, match="Multipart field"):
        request.with_files(
            cast(
                "Mapping[str, MultipartFile | Sequence[MultipartFile]]",
                {"document": (attachment, "not an attachment")},
            )
        )


def test_builder_options_merge_and_execute_a_form_request() -> None:
    """Build independent options with deterministic overrides and encoding.

    The assertions verify the public result and its error paths.
    """
    client = ClientFake()
    root = PendingRequest(client)
    request = (
        root.base_url("https://api.example.test/v1")
        .with_headers({"X-Mode": "initial", "X-Trace": "one"})
        .with_header("x-mode", "final")
        .with_basic_auth("user", "pass")
        .accept_json()
        .as_form()
        .with_body({"ignored": "reusable"})
        .with_query_parameters({"page": 1, "tag": ["a", "b"]})
        .with_cookies({"session": "local"})
        .timeout(3)
        .without_redirecting()
    )

    result = request.request(
        "post",
        "documents",
        data={"active": True, "empty": None, "labels": ["a", 2]},
        params={"page": 2},
    )
    sent = client.requests[0]

    assert result.status_code == HTTPStatus.OK
    assert sent.method == "POST"
    assert sent.url == "https://api.example.test/v1/documents"
    assert sent.headers["x-mode"] == "final"
    assert sent.headers["Authorization"] == (
        "Basic " + base64.b64encode(b"user:pass").decode("ascii")
    )
    assert sent.headers["Accept"] == "application/json"
    assert sent.params == {"page": 2, "tag": ("a", "b")}
    assert sent.data == {"active": True, "empty": None, "labels": ["a", 2]}
    assert sent.cookies == {"session": "local"}
    assert sent.timeout == _THREE_SECONDS
    assert sent.follow_redirects is False
    result.close()

    bearer = root.with_token("token").get("https://api.example.test")
    assert client.requests[1].headers["Authorization"] == "Bearer token"
    bearer.close()

    with pytest.raises(ValueError, match="non-empty"):
        root.with_token("")
    with pytest.raises(ValueError, match="single-line"):
        root.with_token("bad\ntoken")
    with pytest.raises(ValueError, match="valid names"):
        root.with_header("Bad Header", "value")
    with pytest.raises(ValueError, match="single-line"):
        root.with_header("X-Trace", "bad\rvalue")
    with pytest.raises(ValueError, match="finite and non-negative"):
        root.retry(2, backoff=float("inf"))
    with pytest.raises(ValueError, match="valid HTTP status"):
        root.retry(2, statuses=(99,))


@pytest.mark.anyio
async def test_all_request_methods_and_stream_contexts_are_available() -> None:
    """Exercise explicit sync and async verbs with stream context ownership.

    The assertions verify the public result and its error paths.
    """
    client = ClientFake()
    request = PendingRequest(client)
    sync_results = [
        request.get("https://api.example.test"),
        request.post("https://api.example.test", {"a": 1}),
        request.put("https://api.example.test", b"body"),
        request.patch("https://api.example.test", "body"),
        request.delete("https://api.example.test"),
        request.head("https://api.example.test"),
        request.options("https://api.example.test"),
    ]
    with request.stream("GET", "https://api.example.test") as response:
        assert list(response.iter_bytes()) == [b'{"ok":true}']
    assert [item.method for item in client.requests[:8]] == [
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
        "GET",
    ]

    async_results = [
        await request.request_async("GET", "https://api.example.test"),
        await request.get_async("https://api.example.test"),
        await request.post_async("https://api.example.test", {"a": 1}),
        await request.put_async("https://api.example.test", {"a": 1}),
        await request.patch_async("https://api.example.test", {"a": 1}),
        await request.delete_async("https://api.example.test"),
        await request.head_async("https://api.example.test"),
        await request.options_async("https://api.example.test"),
    ]
    async with request.stream_async(
        "GET",
        "https://api.example.test",
    ) as response:
        assert [chunk async for chunk in response.iter_bytes_async()] == [
            b'{"ok":true}'
        ]

    assert [item.method for item in client.requests[8:]] == [
        "GET",
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
        "GET",
    ]
    for result in (*sync_results, *async_results):
        await result.aclose()


def test_sync_retry_handles_transport_errors_retry_after_and_payload_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry safe failures, cap Retry-After, and reject unsafe form objects.

    The assertions verify the public result and its error paths.
    """
    sleeps: list[float] = []
    monkeypatch.setattr(support_helpers, "_retry_sleep", sleeps.append)
    client = FailingClientFake(failures=1)
    response = (
        PendingRequest(client)
        .retry(
            2,
            backoff=0,
            jitter=False,
        )
        .get("https://api.example.test")
    )
    assert len(client.requests) == 1
    assert sleeps == [0]
    response.close()
    body_client = ClientFake()
    body_response = (
        PendingRequest(body_client)
        .with_body("body text")
        .as_form()
        .post("https://api.example.test")
    )
    assert body_client.requests[0].data == "body text"
    body_response.close()

    retry_after_client = RetryAfterClientFake(
        (HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.OK)
    )
    statuses_response = PendingRequest(retry_after_client).retry(
        2,
        backoff=0,
        jitter=False,
    )
    statuses_response.get("https://api.example.test").close()
    assert sleeps[-1] == _MAX_RETRY_AFTER

    invalid_payload = cast(
        "RequestPayload",
        ["not", "a", "mapping"],
    )
    with pytest.raises(TypeError, match="Form request bodies"):
        PendingRequest(ClientFake()).post(
            "https://api.example.test",
            invalid_payload,
        )

    exhausted = PendingRequest(FailingClientFake(failures=2)).retry(
        2,
        backoff=0,
        jitter=False,
    )
    with pytest.raises(HttpTransportError, match="local failure"):
        exhausted.get("https://api.example.test")

    invalid_retry_client = RetryAfterClientFake(
        (HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.OK)
    )
    invalid_retry_client.retry_after = "not-a-number"
    invalid_retry = PendingRequest(invalid_retry_client).retry(
        _TWO_ATTEMPTS,
        backoff=0,
        jitter=False,
    )
    previous_sleep_count = len(sleeps)
    invalid_retry.get("https://api.example.test").close()
    assert len(sleeps) == previous_sleep_count + 1
    assert sleeps[-1] == 0


@pytest.mark.anyio
async def test_async_retry_handles_transport_errors_and_jitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry async transport failures without swallowing cancellation paths.

    The assertions verify the public result and its error paths.
    """
    delays: list[float] = []

    def record_sleep(seconds: float) -> None:
        """Record retry delays without waiting during deterministic tests.

        Local fixtures keep these assertions deterministic.
        """
        delays.append(seconds)

    async def record_sleep_async(seconds: float) -> None:
        """Record asynchronous retry waits without delaying the test.

        Local fixtures keep these assertions deterministic.
        """
        record_sleep(seconds)

    monkeypatch.setattr(
        support_helpers,
        "_retry_sleep_async",
        record_sleep_async,
    )
    client = FailingClientFake(failures=1)
    response = (
        await PendingRequest(client)
        .retry(
            2,
            backoff=0,
            jitter=False,
        )
        .get_async("https://api.example.test")
    )
    assert len(client.requests) == 1
    assert delays == [0]
    await response.aclose()

    jitter_client = ClientFake((HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.OK))
    request = PendingRequest(jitter_client).retry(
        _TWO_ATTEMPTS,
        backoff=4,
        jitter=True,
    )
    jitter_response = await request.get_async("https://api.example.test")
    await jitter_response.aclose()
    assert _MIN_JITTER_DELAY <= delays[-1] <= _MAX_JITTER_DELAY

    exhausted = PendingRequest(FailingClientFake(failures=2)).retry(
        _TWO_ATTEMPTS,
        backoff=0,
        jitter=False,
    )
    with pytest.raises(HttpTransportError, match=_LOCAL_TRANSPORT_ERROR):
        await exhausted.get_async("https://api.example.test")
