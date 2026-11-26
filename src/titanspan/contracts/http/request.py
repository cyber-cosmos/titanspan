"""Describe the native incoming HTTP request boundary.

The contract exposes request metadata synchronously and payload access
through explicit asynchronous operations.
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Protocol, runtime_checkable

from titanspan.contracts.http.types import JsonValue


@runtime_checkable
class HttpRequest(Protocol):
    """Expose validated metadata and explicitly consumed request content.

    Callers rely on native contracts, not concrete backend types.
    """

    @property
    def request_id(self) -> str:
        """Return the bounded identifier assigned to this ASGI request.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    @property
    def correlation_id(self) -> str:
        """Return a bounded correlation header or the request identifier.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    @property
    def method(self) -> str:
        """Return the uppercase HTTP method name.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    @property
    def url(self) -> str:
        """Return the complete request URL as text.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    @property
    def path(self) -> str:
        """Return the URL path without query parameters.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    @property
    def host(self) -> str:
        """Return the parsed request host.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    @property
    def scheme(self) -> str:
        """Return the request URL scheme.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    @property
    def headers(self) -> Mapping[str, str]:
        """Return an immutable snapshot of request headers.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def header(self, name: str, default: str | None = None) -> str | None:
        """Retrieve a header without case-sensitive name matching.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def query(self, key: str, default: object = None) -> object:
        """Read one query parameter without consuming the body.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def query_values(self, key: str) -> tuple[str, ...]:
        """Return all values for a repeated query parameter in order.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def cookie(self, key: str, default: str | None = None) -> str | None:
        """Read one cookie value without consuming the request body.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def is_method(self, method: str) -> bool:
        """Compare the request method without case-sensitive matching.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def is_secure(self) -> bool:
        """Report whether the request uses HTTPS.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def is_ajax(self) -> bool:
        """Report the conventional XMLHttpRequest marker.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def is_json(self) -> bool:
        """Report whether the request body declares a JSON media type.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    @property
    def route_name(self) -> str | None:
        """Return the matched native route name when one was assigned.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    @property
    def route_parameters(self) -> Mapping[str, object]:
        """Return the matched route values as an immutable snapshot.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def accepts(self, media_type: str) -> bool:
        """Check whether the Accept header allows a media type.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def expects_json(self) -> bool:
        """Report whether JSON is requested by the client.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def has(self, key: str) -> bool:
        """Check whether an input path exists, including explicit null.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def filled(self, key: str) -> bool:
        """Check whether a present input value is non-empty.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def input(
        self,
        key: str,
        default: object = None,
    ) -> object:
        """Read a body-over-query value, parsing the body when necessary.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def json(self) -> JsonValue:
        """Parse the request body as a JSON value.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def body(self) -> bytes:
        """Buffer the complete request body within configured limits.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def form(self) -> Mapping[str, object]:
        """Parse form input using the configured multipart limits.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def string(
        self,
        key: str,
        default: str | None = None,
    ) -> str | None:
        """Read a string input without coercing incompatible values.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def integer(
        self,
        key: str,
        default: int | None = None,
    ) -> int | None:
        """Read an integer input without accepting booleans.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def float(
        self,
        key: str,
        default: float | None = None,
    ) -> float | None:
        """Read a finite numeric input value.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def boolean(
        self,
        key: str,
        default: bool | None = None,
    ) -> bool | None:
        """Read a boolean input using documented textual values.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def array(
        self,
        key: str,
        default: Mapping[str, object] | list[object] | None = None,
    ) -> Mapping[str, object] | list[object] | None:
        """Read a mapping or list without coercing scalar values.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def all(self) -> Mapping[str, object]:
        """Return query and body values with body values taking precedence.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def only(self, keys: Sequence[str]) -> Mapping[str, object]:
        """Return only the selected request input paths.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def except_(self, keys: Sequence[str]) -> Mapping[str, object]:
        """Return merged input except the selected top-level keys.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    def stream(self) -> AsyncIterator[bytes]:
        """Yield body chunks once without buffering the complete body.

        Callers rely on native contracts, not concrete backend types.
        """
        ...

    async def aclose(self) -> None:
        """Close temporary upload resources owned by the request parser.

        Callers rely on native contracts, not concrete backend types.
        """
        ...


__all__ = ["HttpRequest"]
