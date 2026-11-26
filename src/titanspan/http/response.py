"""Provide native response objects accepted by the ASGI integration.

The operation follows native HTTP contracts and explicit ownership.
"""

from collections.abc import AsyncGenerator, AsyncIterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Self
from urllib.parse import urlsplit

from titanspan.contracts.http import JsonValue
from titanspan.contracts.http.events import ServerSentEvent
from titanspan.http._backends.asgi import (
    FileResponseBackend,
    HtmlResponseBackend,
    JsonResponseBackend,
    RedirectResponseBackend,
    ResponseBackend,
    StreamingResponseBackend,
)

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_INVALID_COOKIE_SAMESITE_ERROR = (
    "Cookie same_site must be lax, strict, or none."
)
_BODYLESS_STATUS_ERROR = "HTTP status cannot carry a response body."
_COOKIE_LINE_BREAK_ERROR = "Cookie values must not contain line breaks."
_COOKIE_DOMAIN_LINE_BREAK_ERROR = "Cookie domain must not contain line breaks."
_NEGATIVE_CACHE_AGE_ERROR = "Cache max_age must be non-negative."
_DOWNLOAD_NAME_LINE_BREAK_ERROR = (
    "Download filename must not contain line breaks."
)
_INVALID_HEADER_NAME_ERROR = "Header name contains unsupported characters."
_INVALID_HEADER_VALUE_ERROR = "Header values must not contain line breaks."
_INVALID_REDIRECT_STATUS_ERROR = (
    "Redirect status must be 301, 302, 303, 307, or 308."
)
_INVALID_REDIRECT_LOCATION_ERROR = (
    "Redirect locations must be non-empty and printable."
)
_PROTOCOL_RELATIVE_REDIRECT_ERROR = (
    "Protocol-relative redirects are not permitted."
)
_EXTERNAL_REDIRECT_ERROR = "External redirects require explicit permission."
_HEADER_NAME_CHARS = frozenset(
    "!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)
_COOKIE_VALUE_CHARS = frozenset(
    "!#$%&'()*+-./0123456789:<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[]^_`"
    "abcdefghijklmnopqrstuvwxyz{|}~"
)
_NEGATIVE_COOKIE_AGE_ERROR = "Cookie max_age must be non-negative."
_ASCII_CONTROL_MAX = 31
_ASCII_DELETE = 127


@dataclass(frozen=True, slots=True)
class CookieOptions:
    """Describe response-cookie attributes using secure defaults.

    Attributes:
        max_age: Optional lifetime in seconds.
        path: Cookie path scope.
        domain: Optional host scope.
        secure: Restrict transmission to HTTPS.
        http_only: Prevent ordinary browser script access.
        same_site: Cross-site request policy.
    """

    max_age: int | None = None
    path: str = "/"
    domain: str | None = None
    secure: bool = True
    http_only: bool = True
    same_site: Literal["lax", "strict", "none"] = "lax"


_DEFAULT_COOKIE_OPTIONS = CookieOptions()


class Response(ResponseBackend):
    """Represent a plain text or byte response with fluent header methods.

    Fluent methods mutate this response and return the same object. The
    underlying server adapter transmits it through the standard ASGI send
    interface.
    """

    def __init__(
        self,
        content: str | bytes | None = None,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
        content_type: str | None = None,
    ) -> None:
        """Create a response with explicit content, status, and headers.

        Args:
            content: Text or bytes sent as the response body.
            status: HTTP status code.
            headers: Additional response headers.
            content_type: Optional media type.
        """
        if content_type is not None:
            validate_header("Content-Type", content_type)
        super().__init__(
            content=None if status in {204, 304} else content,
            status_code=status,
            headers=_validated_headers(headers),
            media_type=content_type,
        )

    def with_header(self, name: str, value: str) -> Self:
        """Set one validated header and return this mutable response.

        Args:
            name: Header token name.
            value: Header value without carriage returns or line feeds.

        Returns:
            The same response instance for fluent configuration.

        Raises:
            ValueError: If the name or value could inject a header line.
        """
        validate_header(name, value)
        self.headers[name] = value
        return self

    def with_cookie(
        self,
        name: str,
        value: str,
        *,
        options: CookieOptions = _DEFAULT_COOKIE_OPTIONS,
    ) -> Self:
        """Append a cookie using secure defaults.

        Args:
            name: Cookie name.
            value: Cookie value.
            options: Cookie attributes. Defaults are secure and HttpOnly.

        Returns:
            The same response instance.

        Raises:
            ValueError: If the cookie name, value, or path is unsafe.
        """
        _validate_cookie(name, value, options)
        self.set_cookie(
            name,
            value,
            max_age=options.max_age,
            path=options.path,
            domain=options.domain,
            secure=options.secure,
            httponly=options.http_only,
            samesite=options.same_site,
        )
        return self

    def cache_control(
        self,
        *,
        max_age: int | None = None,
        private: bool = True,
        no_store: bool = False,
    ) -> Self:
        """Set a small explicit Cache-Control policy.

        Args:
            max_age: Optional non-negative freshness lifetime in seconds.
            private: Mark the response as private to one user by default.
            no_store: Prevent storage when the response is sensitive.

        Returns:
            The same response instance.

        Raises:
            ValueError: If ``max_age`` is negative.
        """
        if max_age is not None and max_age < 0:
            raise ValueError(_NEGATIVE_CACHE_AGE_ERROR)
        directives = ["private" if private else "public"]
        if no_store:
            directives.append("no-store")
        if max_age is not None:
            directives.append(f"max-age={max_age}")
        return self.with_header("Cache-Control", ", ".join(directives))


class JsonResponse(JsonResponseBackend):
    """Represent a JSON response from a JSON-compatible value.

    The operation follows native HTTP contracts and explicit ownership.
    """

    def __init__(
        self,
        content: JsonValue,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Create a JSON response without accepting arbitrary model objects.

        Args:
            content: JSON-compatible scalar, list, or string-keyed mapping.
            status: HTTP status code.
            headers: Additional response headers.
        """
        _require_body_status(status)
        super().__init__(
            content=content,
            status_code=status,
            headers=_validated_headers(headers),
        )

    def with_header(self, name: str, value: str) -> Self:
        """Set one validated header and return this response.

        Args:
            name: Header token name.
            value: Header value without line breaks.

        Returns:
            This response instance.
        """
        validate_header(name, value)
        self.headers[name] = value
        return self


class HtmlResponse(HtmlResponseBackend):
    """Represent an HTML response with an explicit status code.

    The operation follows native HTTP contracts and explicit ownership.
    """

    def __init__(
        self,
        content: str,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Create an HTML response.

        Args:
            content: Application-produced HTML document or fragment.
            status: HTTP status code.
            headers: Additional response headers.
        """
        super().__init__(
            content=content,
            status_code=status,
            headers=_validated_headers(headers),
        )

    def with_header(self, name: str, value: str) -> Self:
        """Set one validated response header and return this response.

        Args:
            name: Header token name.
            value: Header value without line breaks.

        Returns:
            The same response instance.
        """
        validate_header(name, value)
        self.headers[name] = value
        return self


class RedirectResponse(RedirectResponseBackend):
    """Represent a validated redirect response.

    The operation follows native HTTP contracts and explicit ownership.
    """

    def __init__(
        self,
        location: str,
        *,
        status: int = 303,
        allow_external: bool = False,
    ) -> None:
        """Create a redirect while rejecting unsafe default destinations.

        Args:
            location: Relative path, or external URL when explicitly allowed.
            status: One of the supported redirect status codes.
            allow_external: Permit an absolute HTTP or HTTPS destination.

        Raises:
            ValueError: If the status or destination is unsafe.
        """
        _validate_redirect(location, status, allow_external=allow_external)
        super().__init__(location, status_code=status)

    def with_header(self, name: str, value: str) -> Self:
        """Set one validated response header and return this response.

        Args:
            name: Header token name.
            value: Header value without line breaks.

        Returns:
            The same response instance.
        """
        validate_header(name, value)
        self.headers[name] = value
        return self


class StreamResponse(StreamingResponseBackend):
    """Stream an async byte or text iterator without collecting its output.

    The operation follows native HTTP contracts and explicit ownership.
    """

    def __init__(
        self,
        content: AsyncIterable[bytes | str],
        *,
        content_type: str = "application/octet-stream",
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Wrap an async source and preserve backpressure and cancellation.

        Args:
            content: Source that yields response chunks incrementally.
            content_type: Media type sent with the response.
            status: HTTP status code.
            headers: Additional response headers.
        """
        _require_body_status(status)
        validate_header("Content-Type", content_type)
        super().__init__(
            _encode_chunks(content),
            status_code=status,
            headers=_validated_headers(headers),
            media_type=content_type,
        )

    def with_header(self, name: str, value: str) -> Self:
        """Set one validated response header and return this response.

        Args:
            name: Header token name.
            value: Header value without line breaks.

        Returns:
            The same response instance.
        """
        validate_header(name, value)
        self.headers[name] = value
        return self


class FileResponse(FileResponseBackend):
    """Stream one application-selected file as a download response.

    The operation follows native HTTP contracts and explicit ownership.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        filename: str | None = None,
        status: int = 200,
        content_type: str | None = None,
    ) -> None:
        """Create a file response for a trusted application path.

        Args:
            path: Existing local file selected by trusted application code.
            filename: Optional download name reduced to a safe basename.
            status: HTTP status code.
            content_type: Optional explicit media type.

        Raises:
            ValueError: If the selected download name contains control bytes.
        """
        download_name = None
        _require_body_status(status)
        if content_type is not None:
            validate_header("Content-Type", content_type)
        if filename is not None:
            if "\r" in filename or "\n" in filename:
                raise ValueError(_DOWNLOAD_NAME_LINE_BREAK_ERROR)
            download_name = PurePosixPath(filename.replace("\\", "/")).name
        super().__init__(
            path,
            status_code=status,
            filename=download_name,
            media_type=content_type,
        )

    def with_header(self, name: str, value: str) -> Self:
        """Set one validated response header and return this response.

        Args:
            name: Header token name.
            value: Header value without line breaks.

        Returns:
            The same response instance.
        """
        validate_header(name, value)
        self.headers[name] = value
        return self


async def _encode_chunks(
    source: AsyncIterable[bytes | str],
) -> AsyncGenerator[bytes, None]:
    """Encode text chunks and finalize an async-generator source.

    Args:
        source: User-provided streaming source.

    Yields:
        Encoded bytes in the order supplied by the source.
    """
    iterator = source.__aiter__()
    try:
        async for chunk in iterator:
            yield chunk.encode("utf-8") if isinstance(chunk, str) else chunk
    finally:
        if isinstance(iterator, AsyncGenerator):
            await iterator.aclose()


def validate_header(name: str, value: str) -> None:
    """Reject header names and values that could inject new header lines.

    Args:
        name: Header field name.
        value: Header field value.

    Raises:
        ValueError: If either value is malformed or contains line controls.
    """
    if not name or any(char not in _HEADER_NAME_CHARS for char in name):
        raise ValueError(_INVALID_HEADER_NAME_ERROR)
    if "\r" in value or "\n" in value:
        raise ValueError(_INVALID_HEADER_VALUE_ERROR)


def _validate_cookie(
    name: str,
    value: str,
    options: CookieOptions,
) -> None:
    """Reject cookie syntax that can inject names or attributes.

    Args:
        name: Cookie token name.
        value: Cookie-octet value.
        options: Attributes serialized onto the Set-Cookie header.

    Raises:
        ValueError: If any supplied cookie field is malformed.
    """
    if options.same_site not in {"lax", "strict", "none"}:
        raise ValueError(_INVALID_COOKIE_SAMESITE_ERROR)
    if options.max_age is not None and options.max_age < 0:
        raise ValueError(_NEGATIVE_COOKIE_AGE_ERROR)
    if not name or not all(char in _HEADER_NAME_CHARS for char in name):
        raise ValueError(_COOKIE_LINE_BREAK_ERROR)
    if not all(char in _COOKIE_VALUE_CHARS for char in value):
        raise ValueError(_COOKIE_LINE_BREAK_ERROR)
    if ";" in options.path or any(
        ord(char) <= _ASCII_CONTROL_MAX or ord(char) == _ASCII_DELETE
        for char in options.path
    ):
        raise ValueError(_COOKIE_LINE_BREAK_ERROR)
    if options.domain is not None and any(
        char in options.domain for char in "\r\n;"
    ):
        raise ValueError(_COOKIE_DOMAIN_LINE_BREAK_ERROR)


def _validated_headers(
    headers: Mapping[str, str] | None,
) -> Mapping[str, str] | None:
    """Validate every caller-supplied header before backend construction.

    Args:
        headers: Optional response header mapping.

    Returns:
        An independent mapping suitable for the ASGI response backend.

    Raises:
        ValueError: If any header name or value is malformed.
    """
    if headers is None:
        return None
    validated = dict(headers)
    for name, value in validated.items():
        validate_header(name, value)
    return validated


def _require_body_status(status: int) -> None:
    """Reject response variants that cannot truthfully carry a body.

    Args:
        status: Proposed response status.

    Raises:
        ValueError: If the status forbids a representation body.
    """
    if status in {204, 304}:
        raise ValueError(_BODYLESS_STATUS_ERROR)


def _validate_redirect(
    location: str,
    status: int,
    *,
    allow_external: bool,
) -> None:
    """Validate the redirect status and avoid unsafe default open redirects.

    Args:
        location: Candidate redirect target.
        status: Redirect status.
        allow_external: Whether absolute HTTP(S) URLs are allowed.

    Raises:
        ValueError: If the location or status violates the safe policy.
    """
    if status not in _REDIRECT_STATUSES:
        raise ValueError(_INVALID_REDIRECT_STATUS_ERROR)
    if not location or any(char in location for char in "\r\n\x00"):
        raise ValueError(_INVALID_REDIRECT_LOCATION_ERROR)
    parsed = urlsplit(location)
    if location.startswith("//"):
        raise ValueError(_PROTOCOL_RELATIVE_REDIRECT_ERROR)
    if (parsed.scheme or parsed.netloc) and (
        not allow_external or parsed.scheme not in {"http", "https"}
    ):
        raise ValueError(_EXTERNAL_REDIRECT_ERROR)


__all__ = [
    "FileResponse",
    "HtmlResponse",
    "JsonResponse",
    "RedirectResponse",
    "Response",
    "ServerSentEvent",
    "StreamResponse",
]
