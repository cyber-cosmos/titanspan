"""Describe native synchronous and asynchronous outgoing HTTP clients.

The same application-owned client contract exposes explicit operations for
both execution modes and never returns conditional awaitable values.
"""

from collections.abc import (
    AsyncIterator,
    Iterator,
    Mapping,
)
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from dataclasses import dataclass, field
from typing import Protocol, Self, runtime_checkable

from titanspan.contracts.http.events import ServerSentEvent
from titanspan.contracts.http.types import (
    JsonValue,
    QueryParameters,
    RequestPayload,
)

_ASCII_CONTROL_MAX = 31
_DELETE_CODEPOINT = 127
_INVALID_MULTIPART_CONTENT = "Multipart file content must be bytes."
_INVALID_MULTIPART_FILENAME = "Multipart filenames must be printable."
_INVALID_MULTIPART_MEDIA_TYPE = "Multipart content types must be valid."


def _empty_string_mapping() -> Mapping[str, str]:
    """Return an independently allocated typed mapping default.

    Returns:
        An empty mapping with string keys and values.
    """
    return {}


@dataclass(frozen=True, slots=True)
class MultipartFile:
    """Describe a replayable multipart attachment using immutable bytes.

    Attributes:
        filename: Filename sent in the multipart content disposition.
        content: Complete attachment bytes owned by the caller.
        content_type: Media type sent for the attachment.
    """

    filename: str
    content: bytes
    content_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        """Reject multipart metadata that can inject header lines.

        Raises:
            ValueError: If a filename or content type is malformed.
            TypeError: If attachment content is not immutable bytes.
        """
        if not self.filename or any(
            ord(character) <= _ASCII_CONTROL_MAX
            or ord(character) == _DELETE_CODEPOINT
            for character in self.filename
        ):
            raise ValueError(_INVALID_MULTIPART_FILENAME)
        media_type = self.content_type.split(";", maxsplit=1)[0]
        if (
            "/" not in media_type
            or not media_type.strip()
            or "\r" in self.content_type
            or "\n" in self.content_type
        ):
            raise ValueError(_INVALID_MULTIPART_MEDIA_TYPE)
        if type(self.content) is not bytes:
            raise TypeError(_INVALID_MULTIPART_CONTENT)


@dataclass(frozen=True, slots=True)
class OutgoingRequest:
    """Describe one transport-neutral outgoing request.

    Options are copied by the request builder before construction so a
    submitted request cannot be changed by later builder operations.

    Attributes:
        method: HTTP method, normalized by the transport.
        url: Absolute destination or URL relative to the configured base.
        headers: Request-specific headers.
        params: Query parameters, including repeated scalar values.
        json_body: JSON-compatible body, including explicit JSON null.
        json_enabled: Whether ``json_body`` represents an intentional body.
        data: Form, text, or bytes body when JSON mode is disabled.
        files: Ordered, replayable multipart file fields.
        cookies: Request-specific cookies.
        timeout: Total request timeout override in seconds.
        follow_redirects: Redirect behavior override for this request.
    """

    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=_empty_string_mapping)
    params: QueryParameters | None = None
    json_body: JsonValue | None = None
    json_enabled: bool = False
    data: RequestPayload = None
    files: tuple[tuple[str, MultipartFile], ...] = ()
    cookies: Mapping[str, str] = field(default_factory=_empty_string_mapping)
    timeout: float | None = None
    follow_redirects: bool | None = None


@runtime_checkable
class HttpClientResponse(Protocol):
    """Expose response data without leaking the selected transport type.

    Callers rely on native contracts, not concrete backend types.
    """

    @property
    def status_code(self) -> int:
        """Return the HTTP response status code.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    @property
    def headers(self) -> Mapping[str, str]:
        """Return an immutable response-header snapshot.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    @property
    def cookies(self) -> Mapping[str, str]:
        """Return response cookies without retaining them in the client pool.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def body(self) -> bytes:
        """Return buffered response bytes.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def text(self) -> str:
        """Decode response bytes using the response encoding.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def json(self) -> JsonValue:
        """Parse and validate a JSON-compatible response value.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def successful(self) -> bool:
        """Return whether the status is within the successful range.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def failed(self) -> bool:
        """Return whether the response status is 4xx or 5xx.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def server_error(self) -> bool:
        """Return whether the response status is 5xx.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def throw(self) -> Self:
        """Raise a native status error when the response is unsuccessful.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def header(self, name: str, default: str | None = None) -> str | None:
        """Retrieve one response header case-insensitively.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def iter_bytes(self) -> Iterator[bytes]:
        """Return an iterator over streamed response bytes.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def iter_bytes_async(self) -> AsyncIterator[bytes]:
        """Return an async iterator over streamed response bytes.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def iter_sse(self) -> Iterator[ServerSentEvent]:
        """Parse a synchronous response stream as Server-Sent Events.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def iter_sse_async(self) -> AsyncIterator[ServerSentEvent]:
        """Parse an async response stream while preserving backpressure.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def close(self) -> None:
        """Close a synchronously opened response and release its connection.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def aclose(self) -> None:
        """Close any transport response resources still owned by this value.

        Callers rely on native contracts, not concrete backend types.
        """
        ...


@runtime_checkable
class HttpClient(Protocol):
    """Perform pooled HTTP requests through explicit sync and async methods.

    Callers rely on native contracts, not concrete backend types.
    """

    def request(
        self,
        request: OutgoingRequest,
    ) -> HttpClientResponse:
        """Perform a blocking request outside asynchronous event loops.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def request_async(
        self,
        request: OutgoingRequest,
    ) -> HttpClientResponse:
        """Perform a request using the active asynchronous runtime.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def stream(
        self,
        request: OutgoingRequest,
    ) -> AbstractContextManager[HttpClientResponse]:
        """Open a synchronous stream with explicit response ownership.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def stream_async(
        self,
        request: OutgoingRequest,
    ) -> AbstractAsyncContextManager[HttpClientResponse]:
        """Open an asynchronous stream closed when its context exits.

        Callers rely on native contracts, not concrete backend types.
        """
        ...


__all__ = ["HttpClient", "HttpClientResponse", "OutgoingRequest"]
