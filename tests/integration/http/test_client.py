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

from titanspan.http._backends.client import HttpxClientAdapter
from titanspan.http.client.pending_request import PendingRequest
from titanspan.http.configuration import ClientConfiguration
from titanspan.http.exceptions import HttpStatusError

_SERVER_JOIN_TIMEOUT_SECONDS = 2


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
            if path == "/stream":
                payload = b"first\nsecond\n"
            elif path == "/query":
                query = parse_qs(
                    urlsplit(self.path).query,
                    keep_blank_values=True,
                )
                payload = json.dumps(
                    {
                        **query,
                        "cookie": self.headers.get("Cookie", ""),
                    },
                    separators=(",", ":"),
                ).encode("utf-8")
            elif path.startswith("/status/"):
                payload = b'{"message":"failed"}'
            else:
                query = parse_qs(urlsplit(self.path).query)
                payload = (
                    '{"page":' + query.get("page", ["null"])[0] + "}"
                ).encode("utf-8")
            status = (
                HTTPStatus.SERVICE_UNAVAILABLE
                if path == "/status/503"
                else HTTPStatus.OK
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
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
