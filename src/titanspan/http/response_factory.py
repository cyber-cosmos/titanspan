"""Construct native plain, JSON, file, and streaming responses.

The operation follows native HTTP contracts and explicit ownership.
"""

from collections.abc import AsyncIterable, AsyncIterator, Mapping
from pathlib import Path

from titanspan.contracts.http import JsonValue, ResponseFactory
from titanspan.http.response import (
    FileResponse,
    HtmlResponse,
    JsonResponse,
    RedirectResponse,
    Response,
    ServerSentEvent,
    StreamResponse,
)

_INVALID_NO_CONTENT_STATUS_ERROR = (
    "No-content responses require status 204, 205, or 304."
)


class NativeResponseFactory(ResponseFactory):
    """Create Titanspan response objects for incoming ASGI handlers.

    The operation follows native HTTP contracts and explicit ownership.
    """

    def __call__(
        self,
        content: str | bytes | None = None,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        """Construct a text or byte response.

        Args:
            content: Body sent to the client.
            status: HTTP response status.
            headers: Additional response headers.

        Returns:
            A native response accepted by FastAPI and Starlette.
        """
        if status in {204, 304}:
            content = None
        return Response(content, status=status, headers=headers)

    def json(
        self,
        content: JsonValue,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> JsonResponse:
        """Construct a JSON response from a JSON-compatible value.

        Args:
            content: JSON scalar, list, or mapping.
            status: HTTP response status.
            headers: Additional response headers.

        Returns:
            A native JSON response with application/json media type.
        """
        return JsonResponse(content, status=status, headers=headers)

    def html(
        self,
        content: str,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> HtmlResponse:
        """Construct an HTML response.

        Args:
            content: Application-generated HTML content.
            status: HTTP response status.
            headers: Additional response headers.

        Returns:
            A native response with text/html media type.
        """
        return HtmlResponse(content, status=status, headers=headers)

    def redirect(
        self,
        location: str,
        *,
        status: int = 303,
        allow_external: bool = False,
    ) -> RedirectResponse:
        """Construct a relative redirect by default.

        Args:
            location: Relative path or explicitly permitted absolute URL.
            status: Redirect status code.
            allow_external: Permit an absolute HTTP or HTTPS target.

        Returns:
            A native redirect response.
        """
        return RedirectResponse(
            location,
            status=status,
            allow_external=allow_external,
        )

    def no_content(self, *, status: int = 204) -> Response:
        """Construct an empty response with a bodyless status.

        Args:
            status: Bodyless HTTP response code.

        Returns:
            An empty response.

        Raises:
            ValueError: If a status other than 204, 205, or 304 is selected.
        """
        if status not in {204, 205, 304}:
            raise ValueError(_INVALID_NO_CONTENT_STATUS_ERROR)
        return Response(status=status)

    def stream(
        self,
        content: AsyncIterable[bytes | str],
        *,
        content_type: str = "application/octet-stream",
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> StreamResponse:
        """Construct a response that forwards each chunk incrementally.

        Args:
            content: Async source of bytes or text chunks.
            content_type: Response media type.
            status: HTTP response status.
            headers: Additional response headers.

        Returns:
            A streaming response that does not buffer the complete source.
        """
        return StreamResponse(
            content,
            content_type=content_type,
            status=status,
            headers=headers,
        )

    def event_stream(
        self,
        events: AsyncIterable[ServerSentEvent | JsonValue],
        *,
        status: int = 200,
    ) -> StreamResponse:
        """Construct a Server-Sent Event response.

        Args:
            events: Incremental SSE values or plain JSON-compatible data.
            status: HTTP response status.

        Returns:
            A no-buffering ``text/event-stream`` response.
        """
        return StreamResponse(
            _encode_events(events),
            content_type="text/event-stream; charset=utf-8",
            status=status,
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def download(
        self,
        path: str | Path,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> FileResponse:
        """Stream a trusted application-selected file to the client.

        Args:
            path: Local path selected by application code.
            filename: Optional download basename.
            content_type: Optional explicit media type.

        Returns:
            A response that streams the file without loading it in memory.
        """
        return FileResponse(
            path,
            filename=filename,
            content_type=content_type,
        )


async def _encode_events(
    events: AsyncIterable[ServerSentEvent | JsonValue],
) -> AsyncIterator[bytes]:
    """Encode each event immediately before it reaches the server.

    Args:
        events: User-provided async event source.

    Yields:
        One complete encoded event at a time.
    """
    async for event in events:
        value = (
            event
            if isinstance(event, ServerSentEvent)
            else ServerSentEvent(event)
        )
        yield value.encode()


__all__ = ["NativeResponseFactory"]
