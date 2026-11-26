"""Describe native HTTP response construction and observation.

Response types avoid exposing the ASGI implementation used by the server
adapter.
"""

from collections.abc import AsyncIterable, Mapping
from typing import Protocol, Self, runtime_checkable

from titanspan.contracts.http.events import ServerSentEvent
from titanspan.contracts.http.types import JsonValue


@runtime_checkable
class HttpResponse(Protocol):
    """Represent a response that can be returned from an ASGI endpoint.

    Callers rely on native contracts, not concrete backend types.
    """

    @property
    def status_code(self) -> int:
        """Return the numeric HTTP status code.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    @property
    def headers(self) -> Mapping[str, str]:
        """Return the response headers.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def with_header(self, name: str, value: str) -> Self:
        """Set a response header and return this response.

        Callers rely on native contracts, not concrete backend types.
        """
        ...


@runtime_checkable
class ResponseFactory(Protocol):
    """Construct server responses through native typed operations.

    Callers rely on native contracts, not concrete backend types.
    """

    def __call__(
        self,
        content: str | bytes | None = None,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        """Construct a plain text or byte response.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def json(
        self,
        content: JsonValue,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        """Construct a JSON response from a JSON-compatible value.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def redirect(
        self,
        location: str,
        *,
        status: int = 303,
    ) -> HttpResponse:
        """Construct a redirect after validating the location header.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def html(
        self,
        content: str,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        """Construct an HTML response.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def no_content(self, *, status: int = 204) -> HttpResponse:
        """Construct an empty response for a bodyless status.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def stream(
        self,
        content: AsyncIterable[bytes | str],
        *,
        content_type: str = "application/octet-stream",
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        """Construct a response that forwards an async iterator directly.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def event_stream(
        self,
        events: AsyncIterable[ServerSentEvent | JsonValue],
        *,
        status: int = 200,
    ) -> HttpResponse:
        """Construct an incrementally encoded Server-Sent Event response.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def download(
        self,
        path: str,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> HttpResponse:
        """Construct a file response for a trusted application path.

        Callers rely on native contracts, not concrete backend types.
        """
        ...


__all__ = ["HttpResponse", "ResponseFactory"]
