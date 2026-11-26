"""Verify HTTP facade delegation through the active application container.

Local transport fixtures verify facade calls without public network access.
"""

from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Generator,
    Iterator,
    Mapping,
)
from contextlib import asynccontextmanager, contextmanager
from http import HTTPStatus

import pytest

from titanspan.contracts.http import (
    HttpClient,
    HttpClientResponse,
    JsonValue,
    MultipartFile,
    OutgoingRequest,
    ServerSentEvent,
)
from titanspan.facades import Http
from titanspan.foundation import Application
from titanspan.http.client.pending_request import PendingRequest
from titanspan.http.client.response import ClientResponse

pytestmark = pytest.mark.unit


class ResponseAccessFake:
    """Provide one native response without external transport resources.

    The facade test only needs stable response metadata and cleanup signals.
    """

    @property
    def status_code(self) -> int:
        """Return the deterministic successful status.

        This value lets the facade test verify native response access.
        """
        return HTTPStatus.OK

    @property
    def headers(self) -> Mapping[str, str]:
        """Return immutable-looking headers for the wrapped response.

        No mutable client defaults are shared with individual requests.
        """
        return {"content-type": "application/json"}

    @property
    def cookies(self) -> Mapping[str, str]:
        """Return an empty response-cookie snapshot.

        The fixture never receives Set-Cookie headers.
        """
        return {}

    def body(self) -> bytes:
        """Return the small body used by response facade assertions.

        The body remains stable across requests.
        """
        return b"{}"

    def text(self) -> str:
        """Decode the deterministic response body as text.

        The text matches the encoded JSON response.
        """
        return "{}"

    def json(self) -> JsonValue:
        """Return a JSON object for typed response parsing.

        The returned mapping contains no shared mutable state.
        """
        return {}

    def iter_bytes(self) -> Iterator[bytes]:
        """Yield one synchronous response chunk.

        This exercises facade streaming without a transport.
        """
        yield b"{}"

    async def iter_bytes_async(self) -> AsyncIterator[bytes]:
        """Yield one asynchronous response chunk.

        The iterator keeps the async facade path deterministic.
        """
        yield b"{}"

    def iter_sse(self) -> Iterator[ServerSentEvent]:
        """Return no events for the buffered JSON fixture response.

        Streaming event behavior is exercised in response integration tests.
        """
        return iter(())

    def iter_sse_async(self) -> AsyncIterator[ServerSentEvent]:
        """Return an empty asynchronous event iterator.

        The facade unit fixture contains no event-stream content.
        """

        async def empty() -> AsyncIterator[ServerSentEvent]:
            """Yield events through the asynchronous response interface.

            This fixture contains no events.
            """
            for event in self.iter_sse():
                yield event

        return empty()

    def close(self) -> None:
        """Complete synchronous response cleanup without side effects.

        The fixture has no underlying network resource to release.
        """

    async def aclose(self) -> None:
        """Complete asynchronous response cleanup without side effects.

        The fixture has no underlying network resource to release.
        """


class RecordingHttpClient:
    """Capture native requests while returning transport-neutral responses.

    The test client is application-local and never opens a network socket.
    """

    def __init__(self) -> None:
        """Start an empty request log for one application instance.

        The log is not shared with other test applications.
        """
        self.requests: list[OutgoingRequest] = []

    def request(self, request: OutgoingRequest) -> HttpClientResponse:
        """Record a sync call and return its response wrapper.

        Args:
            request: Transport-neutral request created by the facade.

        Returns:
            A native response that owns no external resource.
        """
        self.requests.append(request)
        return ClientResponse(ResponseAccessFake(), asynchronous=False)

    async def request_async(
        self,
        request: OutgoingRequest,
    ) -> HttpClientResponse:
        """Record an async call and return its response wrapper.

        Args:
            request: Transport-neutral request created by the facade.

        Returns:
            A native response with asynchronous cleanup semantics.
        """
        self.requests.append(request)
        return ClientResponse(ResponseAccessFake(), asynchronous=True)

    @contextmanager
    def stream(
        self,
        request: OutgoingRequest,
    ) -> Generator[HttpClientResponse, None, None]:
        """Record and yield a sync response for its context lifetime.

        Args:
            request: Streaming request assembled by the facade.

        Yields:
            The response while the caller owns its stream context.
        """
        response = self.request(request)
        try:
            yield response
        finally:
            response.close()

    @asynccontextmanager
    async def stream_async(
        self,
        request: OutgoingRequest,
    ) -> AsyncGenerator[HttpClientResponse, None]:
        """Record and yield an async response for its context lifetime.

        Args:
            request: Streaming request assembled by the facade.

        Yields:
            The response while the caller owns its async stream context.
        """
        response = await self.request_async(request)
        try:
            yield response
        finally:
            await response.aclose()

    requests: list[OutgoingRequest]


def _application() -> Application:
    """Create an application for task-local facade override tests.

    Returns:
        An application with its production HTTP provider registered.
    """
    return Application()


def test_http_facade_requires_an_active_application() -> None:
    """Reject service resolution when no application context is active.

    The shared facade base owns context lookup for every component.
    """
    with pytest.raises(RuntimeError, match="Bind an application context"):
        Http.client()


def test_http_facade_builders_and_sync_requests_share_client() -> None:
    """Exercise every synchronous convenience method through one client.

    Builder calls remain local and each network-shaped operation records one
    immutable request through the application-registered HTTP contract.
    """
    client = RecordingHttpClient()
    application = _application()

    with (
        application.context(),
        application.container.override({HttpClient: client}),
    ):
        assert Http.client() is client
        builders = (
            Http.pending_request(),
            Http.base_url("https://api.example.test/v1"),
            Http.with_headers({"X-Mode": "test"}),
            Http.with_header("X-Trace", "one"),
            Http.with_token("token"),
            Http.with_basic_auth("user", "password"),
            Http.accept("application/problem+json"),
            Http.accept_json(),
            Http.as_json(),
            Http.as_form(),
            Http.with_query_parameters({"page": 1}),
            Http.with_cookies({"session": "local"}),
            Http.timeout(2),
            Http.retry(2, backoff=0, jitter=False),
            Http.without_redirecting(),
            Http.with_files(
                {"report": MultipartFile("report.txt", b"content")}
            ),
            Http.attach(
                "document",
                b"content",
                filename="report.txt",
            ),
        )
        assert all(isinstance(builder, PendingRequest) for builder in builders)

        responses = [
            Http.get("https://api.example.test/get", params={"page": 1}),
            Http.post("https://api.example.test/post", {"name": "report"}),
            Http.put("https://api.example.test/put", {"name": "report"}),
            Http.patch(
                "https://api.example.test/patch",
                {"name": "report"},
            ),
            Http.delete("https://api.example.test/delete"),
            Http.head("https://api.example.test/head"),
            Http.options("https://api.example.test/options"),
            Http.request(
                "POST",
                "https://api.example.test/request",
                data={"name": "report"},
            ),
        ]
        with Http.stream("GET", "https://api.example.test/stream") as result:
            assert result.status_code == HTTPStatus.OK

        for result in responses:
            assert result.status_code == HTTPStatus.OK
            result.close()

    assert [request.method for request in client.requests] == [
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
        "POST",
        "GET",
    ]


@pytest.mark.anyio
async def test_http_facade_async_requests_and_streams_share_client() -> None:
    """Exercise every asynchronous HTTP method with application context.

    The local contract implementation verifies the facade preserves explicit
    async operations and stream response ownership without network access.
    """
    client = RecordingHttpClient()
    application = _application()

    with (
        application.context(),
        application.container.override({HttpClient: client}),
    ):
        responses = [
            await Http.get_async("https://api.example.test/get"),
            await Http.post_async(
                "https://api.example.test/post",
                {"name": "report"},
            ),
            await Http.put_async(
                "https://api.example.test/put",
                {"name": "report"},
            ),
            await Http.patch_async(
                "https://api.example.test/patch",
                {"name": "report"},
            ),
            await Http.delete_async("https://api.example.test/delete"),
            await Http.head_async("https://api.example.test/head"),
            await Http.options_async("https://api.example.test/options"),
            await Http.request_async(
                "POST",
                "https://api.example.test/request",
                data={"name": "report"},
            ),
        ]
        async with Http.stream_async(
            "GET",
            "https://api.example.test/stream",
        ) as result:
            assert result.status_code == HTTPStatus.OK

        for result in responses:
            assert result.status_code == HTTPStatus.OK
            await result.aclose()

    assert [request.method for request in client.requests] == [
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
        "POST",
        "GET",
    ]
