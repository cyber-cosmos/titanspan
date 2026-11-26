"""Validate outbound HTTP URL schemes and credential exposure.

URL checks reject unsupported schemes and embedded credentials. They do not
resolve DNS or claim comprehensive server-side request forgery protection.
"""

from urllib.parse import urljoin, urlsplit

from titanspan.http.exceptions import HttpClientError

_INVALID_OUTBOUND_URL_ERROR = (
    "Outgoing HTTP destinations must be valid HTTP(S) URLs without credentials."
)
_INVALID_BASE_URL_ERROR = "HTTP base_url must use an absolute HTTP(S) URL."
_ASCII_CONTROL_MAX = 31
_DELETE_CODEPOINT = 127


def validate_base_url(value: str) -> str:
    """Validate and normalize one configured absolute base URL.

    Args:
        value: Application or request-local HTTP base URL.

    Returns:
        The URL with one trailing slash for relative resolution.

    Raises:
        ValueError: If the value contains an unsupported destination.
    """
    if not _valid_absolute_http_url(value):
        raise ValueError(_INVALID_BASE_URL_ERROR)
    parsed = urlsplit(value)
    if parsed.query or parsed.fragment:
        raise ValueError(_INVALID_BASE_URL_ERROR)
    return value.rstrip("/") + "/"


def validate_outbound_url(
    value: str,
    *,
    base_url: str = "",
    allow_relative: bool = False,
) -> str:
    """Reject unsupported outbound schemes and embedded credentials.

    Args:
        value: Absolute URL or relative path supplied by application code.
        base_url: Optional HTTP(S) base URL used by the pooled client.
        allow_relative: Keep a relative path for resolution by a configured
            HTTP client when the base URL is not available at this boundary.

    Returns:
        The original value when it satisfies the destination policy.

    Raises:
        HttpClientError: If an explicit destination is unsafe or malformed.
    """
    if (
        not value
        or "\\" in value
        or any(
            ord(character) <= _ASCII_CONTROL_MAX
            or ord(character) == _DELETE_CODEPOINT
            for character in value
        )
    ):
        raise HttpClientError(_INVALID_OUTBOUND_URL_ERROR)
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise HttpClientError(_INVALID_OUTBOUND_URL_ERROR) from error
    if parsed.scheme:
        if not _valid_absolute_http_url(value):
            raise HttpClientError(_INVALID_OUTBOUND_URL_ERROR)
        return value
    if parsed.netloc or value.startswith("//"):
        raise HttpClientError(_INVALID_OUTBOUND_URL_ERROR)
    if base_url:
        resolved = urljoin(base_url, value)
        if not _valid_absolute_http_url(resolved):
            raise HttpClientError(_INVALID_OUTBOUND_URL_ERROR)
    elif not allow_relative:
        raise HttpClientError(_INVALID_OUTBOUND_URL_ERROR)
    return value


def _valid_absolute_http_url(value: str) -> bool:
    """Check one absolute URL without accepting userinfo or odd schemes.

    Args:
        value: Candidate absolute URL.

    Returns:
        Whether the URL has an HTTP(S) scheme and a valid hostname.
    """
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.lower() in {"http", "https"}
        and bool(parsed.netloc)
        and hostname is not None
        and parsed.username is None
        and parsed.password is None
    )


__all__ = ["validate_base_url", "validate_outbound_url"]
