"""Expose outgoing HTTP responses through a native transport-neutral API.

Response content and cleanup remain explicit.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, Self

from pydantic import TypeAdapter, ValidationError

from titanspan.contracts.http import HttpClientResponse, JsonValue
from titanspan.http.exceptions import (
    HttpClientError,
    HttpStatusError,
)
from titanspan.support import Arr

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator, Mapping

_JSON_ADAPTER = TypeAdapter(JsonValue)
_BODY_NOT_BUFFERED_ERROR = (
    "The response body is not buffered; consume its stream."
)
_INVALID_JSON_RESPONSE_ERROR = "The response body is not valid JSON."
_ASYNC_RESPONSE_CLOSE_ERROR = "Use aclose for an asynchronous response."
_STATUS_SUCCESS_LOWER = 200
_STATUS_SUCCESS_UPPER = 300
_STATUS_CLIENT_ERROR_LOWER = 400
_STATUS_SERVER_ERROR_UPPER = 600
_STATUS_CREATED = 201
_STATUS_ACCEPTED = 202
_STATUS_NO_CONTENT = 204
_STATUS_UNAUTHORIZED = 401
_STATUS_FORBIDDEN = 403
_STATUS_NOT_FOUND = 404
_STATUS_TOO_MANY_REQUESTS = 429


class ResponseAccess(Protocol):
    """Describe response operations supplied by a private transport adapter.

    Response content and cleanup remain explicit.
    """

    @property
    def status_code(self) -> int:
        """Return the transport response status.

        Response content and cleanup remain explicit.
        """
        ...

    @property
    def headers(self) -> Mapping[str, str]:
        """Return transport headers without copying response content.

        Response content and cleanup remain explicit.
        """
        ...

    def body(self) -> bytes:
        """Return a fully buffered response body.

        Response content and cleanup remain explicit.
        """
        ...

    def text(self) -> str:
        """Decode buffered content using transport-selected encoding.

        Response content and cleanup remain explicit.
        """
        ...

    def json(self) -> object:
        """Decode JSON without applying Titanspan value validation.

        Response content and cleanup remain explicit.
        """
        ...

    def iter_bytes(self) -> Iterator[bytes]:
        """Iterate response bytes synchronously.

        Response content and cleanup remain explicit.
        """
        ...

    def iter_bytes_async(self) -> AsyncIterator[bytes]:
        """Iterate response bytes asynchronously.

        Response content and cleanup remain explicit.
        """
        ...

    def close(self) -> None:
        """Release a synchronously opened response.

        Response content and cleanup remain explicit.
        """
        ...

    async def aclose(self) -> None:
        """Release a response through its owning async client.

        Response content and cleanup remain explicit.
        """
        ...


class ClientResponse(HttpClientResponse):
    """Expose status, headers, body helpers, and explicit cleanup methods.

    Buffered response operations are synchronous because response data is
    already available. Streaming methods preserve transport backpressure.
    """

    def __init__(
        self,
        access: ResponseAccess,
        *,
        asynchronous: bool,
    ) -> None:
        """Bind transport-neutral access operations to one response.

        Args:
            access: Adapter implementing the native response access contract.
            asynchronous: Whether asynchronous cleanup owns this response.
        """
        self._access = access
        self._asynchronous = asynchronous
        self._closed = False

    @property
    def status_code(self) -> int:
        """Return the numeric response status.

        Response content and cleanup remain explicit.
        """
        return self._access.status_code

    @property
    def status(self) -> int:
        """Return the numeric response status using the concise spelling.

        Response content and cleanup remain explicit.
        """
        return self.status_code

    @property
    def headers(self) -> Mapping[str, str]:
        """Return an immutable, lower-case response-header snapshot.

        Response content and cleanup remain explicit.
        """
        values = {
            name.lower(): value for name, value in self._access.headers.items()
        }
        return MappingProxyType(values)

    def header(self, name: str, default: str | None = None) -> str | None:
        """Retrieve a response header without case-sensitive lookup.

        Args:
            name: Header name.
            default: Value returned when absent.

        Returns:
            Header value or the supplied default.
        """
        return self.headers.get(name.lower(), default)

    def body(self) -> bytes:
        """Return buffered response bytes.

        Returns:
            Complete response body bytes.

        Raises:
            HttpClientError: If the response is not buffered.
        """
        try:
            return self._access.body()
        except Exception as error:
            raise HttpClientError(_BODY_NOT_BUFFERED_ERROR) from error

    def text(self) -> str:
        """Decode buffered response bytes using transport encoding.

        Returns:
            Decoded response text.

        Raises:
            HttpClientError: If the response is not buffered.
        """
        try:
            return self._access.text()
        except Exception as error:
            raise HttpClientError(_BODY_NOT_BUFFERED_ERROR) from error

    def json(self) -> JsonValue:
        """Parse and validate a buffered JSON response.

        Returns:
            A JSON-compatible scalar, sequence, or mapping.

        Raises:
            HttpClientError: If the content is unbuffered, invalid JSON, or
                contains values outside the supported JSON data model.
        """
        try:
            return _JSON_ADAPTER.validate_python(self._access.json())
        except (ValidationError, ValueError) as error:
            raise HttpClientError(_INVALID_JSON_RESPONSE_ERROR) from error

    def json_path(
        self,
        key: str,
        default: object = None,
    ) -> object:
        """Retrieve a nested JSON value using a dotted path.

        Args:
            key: Direct key or nested dot path.
            default: Value returned for a missing path.

        Returns:
            The matching JSON value or the supplied default.
        """
        return Arr.get(self.json(), key, default)

    def successful(self) -> bool:
        """Return whether the response status is in the 2xx range.

        Response content and cleanup remain explicit.
        """
        return _STATUS_SUCCESS_LOWER <= self.status_code < _STATUS_SUCCESS_UPPER

    def failed(self) -> bool:
        """Return whether the response status is at least 400.

        Response content and cleanup remain explicit.
        """
        return self.status_code >= _STATUS_CLIENT_ERROR_LOWER

    def client_error(self) -> bool:
        """Return whether the status is in the 4xx range.

        Response content and cleanup remain explicit.
        """
        return (
            _STATUS_CLIENT_ERROR_LOWER
            <= self.status_code
            < _STATUS_SERVER_ERROR_UPPER - 100
        )

    def server_error(self) -> bool:
        """Return whether the status is in the 5xx range.

        Response content and cleanup remain explicit.
        """
        return (
            _STATUS_SERVER_ERROR_UPPER - 100
            <= self.status_code
            < _STATUS_SERVER_ERROR_UPPER
        )

    def ok(self) -> bool:
        """Return whether the status is exactly 200.

        Response content and cleanup remain explicit.
        """
        return self.status_code == _STATUS_SUCCESS_LOWER

    def created(self) -> bool:
        """Return whether the status is exactly 201.

        Response content and cleanup remain explicit.
        """
        return self.status_code == _STATUS_CREATED

    def accepted(self) -> bool:
        """Return whether the status is exactly 202.

        Response content and cleanup remain explicit.
        """
        return self.status_code == _STATUS_ACCEPTED

    def no_content(self) -> bool:
        """Return whether the status is exactly 204.

        Response content and cleanup remain explicit.
        """
        return self.status_code == _STATUS_NO_CONTENT

    def not_found(self) -> bool:
        """Return whether the status is exactly 404.

        Response content and cleanup remain explicit.
        """
        return self.status_code == _STATUS_NOT_FOUND

    def unauthorized(self) -> bool:
        """Return whether the status is exactly 401.

        Response content and cleanup remain explicit.
        """
        return self.status_code == _STATUS_UNAUTHORIZED

    def forbidden(self) -> bool:
        """Return whether the status is exactly 403.

        Response content and cleanup remain explicit.
        """
        return self.status_code == _STATUS_FORBIDDEN

    def too_many_requests(self) -> bool:
        """Return whether the status is exactly 429.

        Response content and cleanup remain explicit.
        """
        return self.status_code == _STATUS_TOO_MANY_REQUESTS

    def throw(self) -> Self:
        """Raise a sanitized native error for 4xx or 5xx responses.

        Returns:
            This response when its status is not an error.

        Raises:
            HttpStatusError: If the response status is at least 400.
        """
        if self.failed():
            raise HttpStatusError(
                self.status_code,
                f"The HTTP server returned status {self.status_code}.",
            )
        return self

    def throw_if(self, condition: bool | Callable[[Self], bool]) -> Self:
        """Conditionally escalate an unsuccessful HTTP status.

        Args:
            condition: Boolean or predicate evaluated against this response.

        Returns:
            This response when the condition is false.

        Raises:
            HttpStatusError: If the condition is true and status is 4xx/5xx.
        """
        should_throw = condition(self) if callable(condition) else condition
        return self.throw() if should_throw else self

    def iter_bytes(self) -> Iterator[bytes]:
        """Iterate streamed response chunks synchronously.

        Yields:
            Response chunks in transport order.
        """
        return self._access.iter_bytes()

    def iter_bytes_async(self) -> AsyncIterator[bytes]:
        """Return an async iterator preserving transport backpressure.

        Returns:
            Async response chunks.
        """
        return self._access.iter_bytes_async()

    def close(self) -> None:
        """Close a sync response and release its connection.

        Raises:
            RuntimeError: If the response belongs to an async client.
        """
        if self._asynchronous:
            raise HttpClientError(_ASYNC_RESPONSE_CLOSE_ERROR)
        if not self._closed:
            self._access.close()
            self._closed = True

    async def aclose(self) -> None:
        """Close a response once through its matching transport lifecycle.

        Response content and cleanup remain explicit.
        """
        if self._closed:
            return
        if self._asynchronous:
            await self._access.aclose()
        else:
            self._access.close()
        self._closed = True

    _access: ResponseAccess
    _asynchronous: bool
    _closed: bool


__all__ = ["ClientResponse"]
