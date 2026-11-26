"""Exercise the private ASGI request adapter with real Starlette parsing.

The integration uses real components and local test services.
"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, cast

import anyio
import pytest
from starlette.types import Message, Scope

from titanspan.http._backends.asgi import create_request
from titanspan.http.configuration import ServerConfiguration
from titanspan.http.exceptions import RequestBodyTooLargeError
from titanspan.http.request import Request
from titanspan.http.response import (
    FileResponse,
    HtmlResponse,
    JsonResponse,
    RedirectResponse,
    Response,
    StreamResponse,
)
from titanspan.http.uploaded_file import UploadedFile

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration
_BODY_LIMIT = 3
_EXPECTED_UPLOAD_COUNT = 2
_FIRST_UPLOAD_SIZE = 5
_MULTIPART_BOUNDARY = "titanspan-test-boundary"


def _scope(
    *,
    headers: tuple[tuple[bytes, bytes], ...],
    query: bytes = b"tag=first&tag=second",
    client: tuple[str, int] | None = ("127.0.0.1", 44000),
    server: tuple[str, int] | None = ("example.test", 443),
) -> Scope:
    """Create a minimum HTTP ASGI scope for the Starlette adapter.

    Args:
        headers: Raw byte headers received from the ASGI server.
        query: Raw query bytes, including repeated values when needed.
        client: Server-observed peer or ``None`` for local connections.
        server: Server host and port exposed to the URL adapter.

    Returns:
        A typed HTTP scope accepted by the native request adapter.
    """
    return cast(
        "Scope",
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/upload",
            "raw_path": b"/upload",
            "query_string": query,
            "root_path": "",
            "headers": headers,
            "server": server,
            "client": client,
            "extensions": {},
        },
    )


def _request(
    body: bytes,
    *,
    headers: tuple[tuple[bytes, bytes], ...] = ((b"host", b"example.test"),),
    chunks: tuple[bytes, ...] | None = None,
    max_body_size: int = 1024,
    client: tuple[str, int] | None = ("127.0.0.1", 44000),
    server: tuple[str, int] | None = ("example.test", 443),
) -> Request:
    """Create a native request backed by a deterministic ASGI receiver.

    Args:
        body: Complete request body delivered in one or more chunks.
        headers: Raw request headers supplied to Starlette.
        chunks: Optional explicit body chunks for streaming assertions.
        max_body_size: Total accepted body limit.
        client: Peer address visible through ASGI metadata.
        server: Server host visible through ASGI URL construction.

    Returns:
        A request with real Starlette URL, form, and upload parsing.
    """
    pending = list(chunks or (body,))
    messages: Iterator[Message] = iter(
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(pending) - 1,
        }
        for index, chunk in enumerate(pending)
    )

    async def receive() -> Message:
        """Return the next chunk requested by Starlette.

        The integration uses real components and local test services.
        """
        return next(messages)

    configuration = ServerConfiguration(max_body_size=max_body_size)
    return create_request(
        _scope(headers=headers, client=client, server=server),
        receive,
        request_id="req-asgi-test",
        configuration=configuration,
    )


@pytest.mark.anyio
async def test_asgi_metadata_body_stream_and_missing_client() -> None:
    """Expose Starlette metadata and bounded bodies through native methods.

    The integration uses real components and local test services.
    """
    request = _request(
        b"payload",
        headers=(
            (b"host", b"example.test"),
            (b"cookie", b"session=opaque"),
            (b"content-type", b"application/octet-stream"),
        ),
    )

    assert request.method == "POST"
    assert request.url == "https://example.test/upload?tag=first&tag=second"
    assert request.path == "/upload"
    assert request.host == "example.test"
    assert request.scheme == "https"
    assert request.client == ("127.0.0.1", 44000)
    assert request.query_values("tag") == ("first", "second")
    assert request.cookies == {"session": "opaque"}
    assert request.header("CONTENT-TYPE") == "application/octet-stream"
    assert await request.body() == b"payload"
    assert [chunk async for chunk in request.stream()] == [b"payload"]
    await request.aclose()

    local = _request(b"", headers=(), client=None, server=None)
    assert local.host == ""
    assert local.client is None
    assert local.scheme == ""
    await local.aclose()

    streamed = _request(
        b"",
        chunks=(b"part-one", b"part-two"),
    )
    assert [chunk async for chunk in streamed.stream()] == [
        b"part-one",
        b"part-two",
    ]
    await streamed.aclose()


@pytest.mark.anyio
async def test_asgi_urlencoded_forms_preserve_repeated_values() -> None:
    """Parse standard form input and return repeated values in order.

    The integration uses real components and local test services.
    """
    request = _request(
        b"tag=one&tag=two&active=true",
        headers=(
            (b"host", b"example.test"),
            (b"content-type", b"application/x-www-form-urlencoded"),
        ),
    )

    assert await request.form() == {"tag": "two", "active": "true"}
    assert await request.input("active") == "true"
    assert await request.files("tag") == ()
    await request.aclose()


@pytest.mark.anyio
async def test_asgi_multipart_uploads_are_wrapped_and_finalized() -> None:
    """Parse real multipart uploads, bound files, and close parser resources.

    The integration uses real components and local test services.
    """
    content_type = (
        "multipart/form-data; boundary=" + _MULTIPART_BOUNDARY
    ).encode()
    body = (
        f"--{_MULTIPART_BOUNDARY}\r\n"
        'Content-Disposition: form-data; name="title"\r\n\r\n'
        "Report\r\n"
        f"--{_MULTIPART_BOUNDARY}\r\n"
        'Content-Disposition: form-data; name="files"; '
        'filename="../first.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "first\r\n"
        f"--{_MULTIPART_BOUNDARY}\r\n"
        'Content-Disposition: form-data; name="files"; '
        'filename="second.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "second\r\n"
        f"--{_MULTIPART_BOUNDARY}--\r\n"
    ).encode()
    request = _request(
        body,
        headers=(
            (b"host", b"example.test"),
            (b"content-type", content_type),
        ),
    )

    parsed = await request.form()
    selected = await request.file("files")
    uploads = await request.files("files")
    assert parsed["title"] == "Report"
    assert isinstance(selected, UploadedFile)
    assert selected.filename == "second.txt"
    assert len(uploads) == _EXPECTED_UPLOAD_COUNT
    assert selected is uploads[1]
    assert uploads[0].filename == "../first.txt"
    assert uploads[0].safe_filename == "first.txt"
    assert uploads[0].content_type == "text/plain"
    assert uploads[0].size == _FIRST_UPLOAD_SIZE
    assert await uploads[0].read() == b"first"
    assert await uploads[1].read() == b"second"

    await request.aclose()
    with pytest.raises(RuntimeError, match="upload is closed"):
        await uploads[0].read()


@pytest.mark.anyio
async def test_asgi_receive_wrapper_rejects_oversized_multichunk_bodies() -> (
    None
):
    """Count request bytes across chunks and retain native size errors.

    The integration uses real components and local test services.
    """
    request = _request(
        b"",
        chunks=(b"ab", b"cd"),
        max_body_size=_BODY_LIMIT,
    )

    with pytest.raises(RequestBodyTooLargeError):
        await request.body()
    await request.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "status"),
    [("HEAD", 200), ("GET", 205)],
)
async def test_asgi_responses_suppress_body_for_head_and_reset_content(
    method: str,
    status: int,
) -> None:
    """Transmit no response body for HEAD and 205 responses.

    The captured ASGI messages verify the response at the server boundary.
    """
    response = Response("discarded", status=status)
    scope = _scope(headers=())
    scope["method"] = method
    messages: list[Message] = []

    async def receive() -> Message:
        """Return one completed empty request body.

        The response under test does not need request input.
        """
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        """Capture each real response ASGI message for inspection.

        The test checks the body emitted by the native response object.
        """
        messages.append(message)

    await response(scope, receive, send)

    body_messages = [
        message
        for message in messages
        if message["type"] == "http.response.body"
    ]
    assert len(body_messages) == 1
    assert body_messages[0]["body"] == b""


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response_kind",
    ["plain", "json", "html", "redirect", "stream", "file"],
)
async def test_asgi_head_suppresses_all_native_response_bodies(
    response_kind: str,
    tmp_path: Path,
) -> None:
    """Suppress body bytes for each native response type on HEAD requests.

    The captured ASGI messages verify the server-facing response behavior.
    """
    file_path = tmp_path / "report.txt"
    file_path.write_text("file body", encoding="utf-8")

    async def chunks() -> AsyncIterator[bytes]:
        """Yield one body chunk for the native stream response.

        The HEAD adapter must suppress it at the ASGI boundary.
        """
        yield b"stream body"

    responses = {
        "plain": Response("plain body"),
        "json": JsonResponse({"ready": True}),
        "html": HtmlResponse("<p>ready</p>"),
        "redirect": RedirectResponse("/ready"),
        "stream": StreamResponse(chunks()),
        "file": FileResponse(file_path),
    }
    response = responses[response_kind]
    scope = _scope(headers=())
    scope["method"] = "HEAD"
    messages: list[Message] = []
    disconnect = anyio.Event()

    async def receive() -> Message:
        """Wait until the response completes or cancels its listener.

        StreamingResponse uses this receiver only for disconnect detection.
        """
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        """Capture each real response ASGI message for inspection.

        The assertion examines only the representation body messages.
        """
        messages.append(message)

    await response(scope, receive, send)

    body_messages = [
        message
        for message in messages
        if message["type"] == "http.response.body"
    ]
    assert body_messages
    assert all(message["body"] == b"" for message in body_messages)
