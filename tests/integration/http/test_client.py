"""Exercise pooled HTTP clients against a loopback server.

These tests use real HTTPX2 transports and never contact public services.
"""

import asyncio
import json
from collections.abc import Iterator
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from titanspan.contracts.http import OutgoingRequest
from titanspan.http._backends.client import HttpxClientAdapter
from titanspan.http.client.pending_request import PendingRequest
from titanspan.http.configuration import ClientConfiguration
from titanspan.http.exceptions import HttpClientError, HttpStatusError

pytestmark = pytest.mark.integration

_SERVER_JOIN_TIMEOUT_SECONDS = 2


def _response_payload(path: str, url: str, cookie: str) -> bytes:
    """Build one bounded payload for the selected loopback endpoint.

    Args:
        path: Request path without its query.
        url: Complete request URL from the local server handler.
        cookie: Explicit incoming cookie header.

    Returns:
        Response bytes for the local HTTP integration.
    """
    if path == "/stream":
        return b"first\nsecond\n"
    if path == "/events":
        return b"event: update\nid: local-1\ndata: ready\n\n"
    if path == "/set-cookie":
        return b"{}"
    if path == "/query":
        query = parse_qs(urlsplit(url).query, keep_blank_values=True)
        return json.dumps(
            {**query, "cookie": cookie},
            separators=(",", ":"),
        ).encode("utf-8")
    if path.startswith("/status/"):
        return b'{"message":"failed"}'
    query = parse_qs(urlsplit(url).query)
    return ('{"page":' + query.get("page", ["null"])[0] + "}").encode("utf-8")


@pytest.mark.anyio
async def test_adapter_rejects_untrusted_outbound_url_schemes() -> None:
    """Reject unsupported direct contract URLs before opening a connection.

    The native client boundary also checks requests that bypass its builder.
    """
    adapter = HttpxClientAdapter(ClientConfiguration())
    try:
        with pytest.raises(HttpClientError, match="destinations"):
            await adapter.request_async(
                OutgoingRequest(
                    method="GET",
                    url="file:///etc/passwd",
                )
            )
    finally:
        await adapter.aclose()


@pytest.mark.anyio
async def test_configured_base_url_resolves_relative_requests(
    http_server: tuple[str, Queue[tuple[str, str | None]]],
) -> None:
    """Resolve request-relative paths through the configured HTTPX2 base.

    Args:
        http_server: Local URL and queue of observed request metadata.
    """
    base_url, received = http_server
    adapter = HttpxClientAdapter(
        ClientConfiguration(base_url=base_url),
    )
    try:
        response = await adapter.request_async(
            OutgoingRequest(method="GET", url="/query"),
        )
        assert response.json() == {"cookie": ""}
        await response.aclose()
        assert received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS) == (
            "GET",
            None,
        )
    finally:
        await adapter.aclose()


@pytest.fixture
def http_server() -> Iterator[tuple[str, Queue[tuple[str, str | None]]]]:
    """Start a loopback receiver that reports method and auth header.

    Yields:
        The local base URL and a queue of observed request metadata.
    """
    received: Queue[tuple[str, str | None]] = Queue()

    class Receiver(BaseHTTPRequestHandler):
        """Provide deterministic JSON and streaming endpoint responses.

        The integration uses real components and local test services.
        """

        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            """Return a response selected by the local test path.

            The integration uses real components and local test services.
            """
            self._respond()

        def do_POST(self) -> None:
            """Record a JSON request body before returning its echo.

            The integration uses real components and local test services.
            """
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            received.put((body, self.headers.get("Authorization")))
            content_type = self.headers.get("Content-Type", "")
            if content_type.startswith("application/x-www-form-urlencoded"):
                payload = json.dumps(
                    parse_qs(body, keep_blank_values=True),
                    separators=(",", ":"),
                ).encode("utf-8")
            else:
                payload = body.encode("utf-8")
            self.send_response(HTTPStatus.CREATED)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _respond(self) -> None:
            """Send a bounded response for status and streaming cases.

            The integration uses real components and local test services.
            """
            received.put((self.command, self.headers.get("Authorization")))
            path = urlsplit(self.path).path
            payload = _response_payload(
                path,
                self.path,
                self.headers.get("Cookie", ""),
            )
            status = (
                HTTPStatus.SERVICE_UNAVAILABLE
                if path == "/status/503"
                else HTTPStatus.OK
            )
            self.send_response(status)
            content_type = {
                "/events": "text/event-stream; charset=utf-8",
            }.get(path, "application/json")
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            if path == "/set-cookie":
                self.send_header("Set-Cookie", "session=upstream; Path=/")
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=_SERVER_JOIN_TIMEOUT_SECONDS)


def test_sync_client_uses_isolated_builder_options(
    http_server: tuple[str, Queue[tuple[str, str | None]]],
) -> None:
    """Send JSON through sync HTTP and keep auth scoped to its builder.

    Args:
        http_server: Local URL and queue of observed request metadata.
    """
    url, received = http_server
    client = HttpxClientAdapter(ClientConfiguration())
    try:
        authenticated = (
            PendingRequest(client).with_token("local-test").as_json()
        )
        created = authenticated.post(
            f"{url}/documents",
            {"title": "Guide"},
        )
        assert created.status_code == HTTPStatus.CREATED.value
        assert created.json() == {"title": "Guide"}
        created.close()

        anonymous = PendingRequest(client).get(
            f"{url}/documents",
            params={"page": 4},
        )
        assert anonymous.json() == {"page": 4}
        anonymous.close()

        assert received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS) == (
            '{"title":"Guide"}',
            "Bearer local-test",
        )
        assert received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS) == (
            "GET",
            None,
        )
    finally:
        asyncio.run(client.aclose())


def test_sync_client_does_not_reuse_response_cookies(
    http_server: tuple[str, Queue[tuple[str, str | None]]],
) -> None:
    """Keep upstream response cookies out of later application requests.

    Callers must opt into outgoing cookies on each request. The shared
    connection pool must not retain upstream session state.
    """
    url, received = http_server
    client = HttpxClientAdapter(ClientConfiguration())
    request = PendingRequest(client)
    try:
        first = request.get(f"{url}/set-cookie")
        first.close()
        second = request.get(f"{url}/query")

        body = second.json()
        assert isinstance(body, dict)
        assert body.get("cookie") == ""
        second.close()
        received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS)
        received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS)
    finally:
        asyncio.run(client.aclose())


@pytest.mark.anyio
async def test_async_client_does_not_reuse_response_cookies(
    http_server: tuple[str, Queue[tuple[str, str | None]]],
) -> None:
    """Keep async upstream response cookies out of later requests.

    Async pooling must preserve the same request-local cookie policy as the
    synchronous client.
    """
    url, received = http_server
    client = HttpxClientAdapter(ClientConfiguration())
    request = PendingRequest(client)
    try:
        first = await request.get_async(f"{url}/set-cookie")
        await first.aclose()
        second = await request.get_async(f"{url}/query")

        body = second.json()
        assert isinstance(body, dict)
        assert body.get("cookie") == ""
        await second.aclose()
        received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS)
        received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS)
    finally:
        await client.aclose()


def test_sync_client_streams_with_bounded_connection_ownership(
    http_server: tuple[str, Queue[tuple[str, str | None]]],
) -> None:
    """Stream through the synchronous pool until its context closes.

    Args:
        http_server: Local URL and queue of observed request metadata.
    """
    url, received = http_server
    client = HttpxClientAdapter(ClientConfiguration())
    try:
        with PendingRequest(client).stream("GET", f"{url}/stream") as result:
            chunks = list(result.iter_bytes())

        assert b"".join(chunks) == b"first\nsecond\n"
        assert received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS) == (
            "GET",
            None,
        )
    finally:
        asyncio.run(client.aclose())


@pytest.mark.anyio
async def test_async_client_streams_and_escalates_status_explicitly(
    http_server: tuple[str, Queue[tuple[str, str | None]]],
) -> None:
    """Stream bytes and preserve ordinary HTTP error responses as values.

    Args:
        http_server: Local URL and queue of observed request metadata.
    """
    url, received = http_server
    client = HttpxClientAdapter(ClientConfiguration())
    request = PendingRequest(client)
    try:
        async with request.stream_async("GET", f"{url}/stream") as result:
            chunks = [chunk async for chunk in result.iter_bytes_async()]
        assert b"".join(chunks) == b"first\nsecond\n"

        failure = await request.get_async(f"{url}/status/503")
        assert failure.server_error()
        with pytest.raises(HttpStatusError) as captured:
            failure.throw()
        assert captured.value.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        await failure.aclose()

        assert received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS) == (
            "GET",
            None,
        )
        assert received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS) == (
            "GET",
            None,
        )
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_async_client_consumes_sse_from_loopback_server(
    http_server: tuple[str, Queue[tuple[str, str | None]]],
) -> None:
    """Parse server-sent events over a real pooled HTTPX2 connection.

    Args:
        http_server: Local URL and queue of observed request metadata.
    """
    url, received = http_server
    client = HttpxClientAdapter(ClientConfiguration())
    try:
        async with PendingRequest(client).stream_async(
            "GET",
            f"{url}/events",
        ) as response:
            events = [event async for event in response.iter_sse_async()]

        assert len(events) == 1
        assert events[0].event == "update"
        assert events[0].identifier == "local-1"
        assert events[0].data == "ready"
        assert received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS) == (
            "GET",
            None,
        )
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_async_client_normalizes_forms_queries_and_response_metadata(
    http_server: tuple[str, Queue[tuple[str, str | None]]],
) -> None:
    """Send bounded wire values through real pooled HTTPX2 connections.

    Args:
        http_server: Local URL and queue of observed request metadata.
    """
    url, received = http_server
    client = HttpxClientAdapter(ClientConfiguration())
    request = PendingRequest(client)
    try:
        query = await (
            request.with_query_parameters(
                {"skip": None, "tag": ["one", "two"], "enabled": True}
            )
            .with_header("X-Client", "local")
            .with_cookies({"session": "test-cookie"})
            .timeout(2)
            .without_redirecting()
            .get_async(f"{url}/query")
        )
        assert query.json() == {
            "tag": ["one", "two"],
            "enabled": ["true"],
            "cookie": "session=test-cookie",
        }
        assert query.header("content-type") == "application/json"
        assert query.status_code == HTTPStatus.OK
        await query.aclose()

        cookie_response = await request.get_async(f"{url}/set-cookie")
        assert cookie_response.cookies == {"session": "upstream"}
        await cookie_response.aclose()

        with pytest.raises(ValueError, match="cookie names and values"):
            await request.with_cookies({"session;admin": "yes"}).get_async(
                f"{url}/query"
            )

        form = await request.as_form().post_async(
            f"{url}/documents",
            {
                "active": True,
                "empty": None,
                "label": ["a", 2],
            },
        )
        assert form.json() == {
            "active": ["true"],
            "empty": [""],
            "label": ["a", "2"],
        }
        await form.aclose()

        content = await request.post_async(
            f"{url}/documents",
            b"raw body",
        )
        assert content.body() == b"raw body"
        assert content.text() == "raw body"
        await content.aclose()

        assert received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS) == (
            "GET",
            None,
        )
        assert received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS) == (
            "GET",
            None,
        )
        assert received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS) == (
            "active=true&empty=&label=a&label=2",
            None,
        )
        assert received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS) == (
            "raw body",
            None,
        )
    finally:
        await client.aclose()


def test_sync_streaming_response_releases_pooled_connection(
    http_server: tuple[str, Queue[tuple[str, str | None]]],
) -> None:
    """Consume a real synchronous stream inside its connection context.

    Args:
        http_server: Local URL and queue of observed request metadata.
    """
    url, received = http_server
    client = HttpxClientAdapter(ClientConfiguration())
    request = PendingRequest(client)
    try:
        with request.stream("GET", f"{url}/stream") as response:
            assert list(response.iter_bytes()) == [b"first\nsecond\n"]
        assert received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS) == (
            "GET",
            None,
        )
    finally:
        asyncio.run(client.aclose())


def test_sync_client_sends_native_multipart_attachments(
    http_server: tuple[str, Queue[tuple[str, str | None]]],
) -> None:
    """Send multipart form fields and an attached byte payload.

    The loopback server verifies the actual HTTPX2 multipart wire body.
    """
    url, received = http_server
    client = HttpxClientAdapter(ClientConfiguration())
    request = PendingRequest(client).attach(
        "document",
        b"attachment-data",
        filename="note.txt",
        content_type="text/plain",
    )
    try:
        response = request.post(
            f"{url}/documents",
            {"title": "Review"},
        )
        assert response.status_code == HTTPStatus.CREATED
        response.close()

        wire_body, _ = received.get(timeout=_SERVER_JOIN_TIMEOUT_SECONDS)
        assert wire_body.startswith("--")
        assert 'name="title"' in wire_body
        assert 'name="document"; filename="note.txt"' in wire_body
        assert "attachment-data" in wire_body
    finally:
        asyncio.run(client.aclose())
