"""Adapt Starlette's ASGI request and response primitives privately.

Only this module imports incoming request implementation types. Public HTTP
objects retain native Titanspan signatures and lifecycle semantics.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, NamedTuple, cast

from anyio import CancelScope
from starlette.datastructures import FormData
from starlette.datastructures import UploadFile as StarletteUpload
from starlette.requests import Request as StarletteRequest
from starlette.responses import (
    FileResponse as StarletteFileResponse,
)
from starlette.responses import (
    HTMLResponse as StarletteHTMLResponse,
)
from starlette.responses import (
    JSONResponse as StarletteJSONResponse,
)
from starlette.responses import (
    RedirectResponse as StarletteRedirectResponse,
)
from starlette.responses import (
    Response as StarletteResponse,
)
from starlette.responses import (
    StreamingResponse as StarletteStreamingResponse,
)

from titanspan.http.exceptions import RequestBodyTooLargeError
from titanspan.http.request import Request
from titanspan.http.uploaded_file import UploadedFile

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping, Sequence

    from starlette.types import Message, Receive, Scope, Send

    from titanspan.http.configuration import ServerConfiguration
    from titanspan.http.request import RequestBackend

_BODY_LIMIT_MESSAGE = "The request body exceeds the configured size limit."


class RequestBoundary(NamedTuple):
    """Pair one native request with its authoritative ASGI receiver.

    Foundation passes the same bounded receiver to the downstream ASGI host.
    This prevents interoperability routes from bypassing the request limit.
    """

    request: Request
    receive: Receive


class ResponseBackend(StarletteResponse):
    """Provide a native subclass accepted by ASGI response integrations.

    Transport details stay behind this private adapter.
    """


class JsonResponseBackend(StarletteJSONResponse):
    """Provide a JSON response implementation for native wrappers.

    Transport details stay behind this private adapter.
    """


class HtmlResponseBackend(StarletteHTMLResponse):
    """Provide an HTML response implementation for native wrappers.

    Transport details stay behind this private adapter.
    """


class RedirectResponseBackend(StarletteRedirectResponse):
    """Provide a redirect response implementation for native wrappers.

    Transport details stay behind this private adapter.
    """


class StreamingResponseBackend(StarletteStreamingResponse):
    """Stream async chunks through the server's ASGI send channel.

    Close the iterator before the owning ASGI request scope exits.
    """

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Transmit the stream and finalize its iterator on every exit.

        Args:
            scope: ASGI connection scope supplied by the server.
            receive: ASGI receiver used for disconnect detection.
            send: ASGI sender used to transmit response messages.

        Cancellation is shielded only while the response-owned generator
        runs its finalizer. This completes cleanup before the request scope.
        """
        try:
            await super().__call__(scope, receive, send)
        finally:
            iterator = self.body_iterator
            if isinstance(iterator, AsyncGenerator):
                with CancelScope(shield=True):
                    await iterator.aclose()


class FileResponseBackend(StarletteFileResponse):
    """Stream a trusted application file through the ASGI response path.

    Transport details stay behind this private adapter.
    """


class _StarletteRequestBackend:
    """Provide normalized metadata and parsing for one ASGI request.

    Transport details stay behind this private adapter.
    """

    def __init__(self, request: StarletteRequest) -> None:
        """Retain the request object created by the ASGI server boundary.

        Args:
            request: Backend request whose receive callable has a size limit.
        """
        self._request = request
        self._form_data: FormData | None = None
        self._uploads: list[UploadedFile] = []
        self._uploads_by_identity: dict[int, UploadedFile] = {}

    @property
    def method(self) -> str:
        """Return the method from the ASGI scope.

        Transport details stay behind this private adapter.
        """
        return self._request.method

    @property
    def url(self) -> str:
        """Return the fully rendered request URL.

        Transport details stay behind this private adapter.
        """
        return str(self._request.url)

    @property
    def path(self) -> str:
        """Return the URL path from the ASGI request.

        Transport details stay behind this private adapter.
        """
        return self._request.url.path

    @property
    def host(self) -> str:
        """Return the URL host without a port.

        Transport details stay behind this private adapter.
        """
        return self._request.url.hostname or ""

    @property
    def scheme(self) -> str:
        """Return the URL scheme supplied by the server or proxy adapter.

        Transport details stay behind this private adapter.
        """
        return self._request.url.scheme

    @property
    def headers(self) -> tuple[tuple[str, str], ...]:
        """Return header pairs for immutable native snapshots.

        Transport details stay behind this private adapter.
        """
        return tuple(self._request.headers.items())

    @property
    def query_items(self) -> tuple[tuple[str, str], ...]:
        """Return all query pairs without collapsing repeated parameters.

        Transport details stay behind this private adapter.
        """
        return tuple(self._request.query_params.multi_items())

    @property
    def cookies(self) -> Mapping[str, str]:
        """Return parsed request cookies as a new mapping.

        Transport details stay behind this private adapter.
        """
        return dict(self._request.cookies)

    @property
    def client(self) -> tuple[str, int] | None:
        """Return the server-observed client host and port when available.

        Transport details stay behind this private adapter.
        """
        address = self._request.client
        if address is None:
            return None
        return address.host, address.port

    def header(self, name: str, default: str | None = None) -> str | None:
        """Retrieve one case-insensitive header through the backend mapping.

        Transport details stay behind this private adapter.
        """
        return self._request.headers.get(name, default)

    async def body(self) -> bytes:
        """Read the body through Starlette's bounded receive wrapper.

        Transport details stay behind this private adapter.
        """
        return await self._request.body()

    async def stream(self) -> AsyncIterator[bytes]:
        """Forward backend chunks without collecting the request body.

        Transport details stay behind this private adapter.
        """
        async for chunk in self._request.stream():
            if chunk:
                yield chunk

    async def form(
        self,
        *,
        max_files: int,
        max_fields: int,
        max_part_size: int,
    ) -> Mapping[str, object]:
        """Parse form values and wrap uploaded files in native objects.

        Transport details stay behind this private adapter.
        """
        form_data = await self._parsed_form(
            max_files=max_files,
            max_fields=max_fields,
            max_part_size=max_part_size,
        )
        return {
            key: self._native_value(value)
            for key, value in form_data.multi_items()
        }

    async def form_values(
        self,
        key: str,
        *,
        max_files: int,
        max_fields: int,
        max_part_size: int,
    ) -> Sequence[object]:
        """Return all repeated form values for one field.

        Transport details stay behind this private adapter.
        """
        form_data = await self._parsed_form(
            max_files=max_files,
            max_fields=max_fields,
            max_part_size=max_part_size,
        )
        return tuple(
            self._native_value(value) for value in form_data.getlist(key)
        )

    async def aclose(self) -> None:
        """Finalize all parser-owned temporary upload files.

        Transport details stay behind this private adapter.
        """
        try:
            for upload in self._uploads:
                await upload.aclose()
        finally:
            if self._form_data is not None:
                await self._form_data.close()

    async def _parsed_form(
        self,
        *,
        max_files: int,
        max_fields: int,
        max_part_size: int,
    ) -> FormData:
        """Parse a form once and retain it for repeated input access.

        Args:
            max_files: Maximum multipart upload count.
            max_fields: Maximum non-file form field count.
            max_part_size: Maximum non-file multipart part size.

        Returns:
            The cached or newly parsed backend form data.
        """
        if self._form_data is None:
            self._form_data = await self._request.form(
                max_files=max_files,
                max_fields=max_fields,
                max_part_size=max_part_size,
            )
        return self._form_data

    def _native_value(self, value: object) -> object:
        """Replace backend upload objects with Titanspan upload wrappers.

        Transport details stay behind this private adapter.
        """
        if not isinstance(value, StarletteUpload):
            return value

        existing = self._uploads_by_identity.get(id(value))
        if existing is not None:
            return existing

        upload = UploadedFile(
            filename=value.filename or "",
            content_type=value.content_type,
            size=value.size,
            read_bytes=value.read,
            close_file=value.close,
        )
        self._uploads.append(upload)
        self._uploads_by_identity[id(value)] = upload
        return upload

    _request: StarletteRequest
    _form_data: FormData | None
    _uploads: list[UploadedFile]
    _uploads_by_identity: dict[int, UploadedFile]


def create_request(
    scope: Scope,
    receive: Receive,
    *,
    request_id: str,
    configuration: ServerConfiguration,
) -> Request:
    """Create a native request and cap bytes accepted from ASGI receive.

    Args:
        scope: ASGI request scope owned by the server.
        receive: ASGI receive callback supplied to the application.
        request_id: Correlation identifier assigned by outer middleware.
        configuration: Validated request and multipart size limits.

    Returns:
        A Titanspan request adapter bound to the supplied ASGI connection.
    """
    bounded_receive = _limit_receive(receive, configuration)
    return _request_from_bounded_receive(
        scope,
        bounded_receive,
        request_id=request_id,
        configuration=configuration,
    )


def create_request_boundary(
    scope: Scope,
    receive: Receive,
    *,
    request_id: str,
    configuration: ServerConfiguration,
) -> RequestBoundary:
    """Create the request and receiver shared by the complete ASGI stack.

    Args:
        scope: HTTP ASGI scope owned by the server.
        receive: Original receiver supplied by the ASGI server.
        request_id: Correlation identifier for this request.
        configuration: Validated request and multipart limits.

    Returns:
        Native request and the same size-limited receiver for downstream use.
    """
    bounded_receive = _limit_receive(receive, configuration)
    request = _request_from_bounded_receive(
        scope,
        bounded_receive,
        request_id=request_id,
        configuration=configuration,
    )
    return RequestBoundary(request, bounded_receive)


def _limit_receive(
    receive: Receive,
    configuration: ServerConfiguration,
) -> Receive:
    """Wrap one ASGI receiver with a cumulative request-body limit.

    Args:
        receive: Original ASGI message receiver.
        configuration: Validated maximum body size.

    Returns:
        A receiver that rejects the first chunk beyond the configured limit.
    """
    consumed = 0

    async def limited_receive() -> Message:
        """Reject a body chunk that would exceed the configured size limit.

        The wrapper is shared by the request adapter and downstream ASGI app.
        """
        nonlocal consumed
        message: Message = await receive()
        if message.get("type") == "http.request":
            body = cast("bytes", message.get("body", b""))
            consumed += len(body)
            if consumed > configuration.max_body_size:
                raise RequestBodyTooLargeError(_BODY_LIMIT_MESSAGE)
        return message

    return limited_receive


def _request_from_bounded_receive(
    scope: Scope,
    receive: Receive,
    *,
    request_id: str,
    configuration: ServerConfiguration,
) -> Request:
    """Build the native adapter from the receiver owned by one boundary.

    Args:
        scope: HTTP ASGI request scope.
        receive: Already bounded receiver shared with downstream dispatch.
        request_id: Correlation identifier for this request.
        configuration: Validated multipart limits.

    Returns:
        A native request bound to the supplied receiver.
    """
    backend = _StarletteRequestBackend(StarletteRequest(scope, receive=receive))
    return Request(
        cast("RequestBackend", backend),
        request_id=request_id,
        max_form_files=configuration.max_form_files,
        max_form_fields=configuration.max_form_fields,
        max_part_size=configuration.max_part_size,
    )


__all__ = [
    "FileResponseBackend",
    "HtmlResponseBackend",
    "JsonResponseBackend",
    "RedirectResponseBackend",
    "RequestBoundary",
    "ResponseBackend",
    "StreamingResponseBackend",
    "create_request",
    "create_request_boundary",
]
