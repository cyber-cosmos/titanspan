"""Deliver native records to explicitly configured HTTP endpoints.

The adapter uses only the standard library, does not install a process-wide
HTTP opener, and rejects redirects to keep destination selection explicit.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from threading import Lock
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    model_validator,
)

from titanspan.logging.exceptions import (
    LogBackendError,
    LogConfigurationError,
    LogLifecycleError,
)
from titanspan.logging.formatters import TextLogFormatter

if TYPE_CHECKING:
    from collections.abc import Mapping

    from titanspan.logging.record import LogRecord

WebhookStyle = Literal["json", "slack"]
_MAX_URL_LENGTH = 2_048
_MAX_HEADER_COUNT = 32
_MAX_HEADER_LENGTH = 8_192
_HTTP_SUCCESS_MINIMUM = 200
_HTTP_SUCCESS_EXCLUSIVE_MAXIMUM = 300


class WebhookOptions(BaseModel):
    """Validate an explicitly configured JSON webhook destination.

    Attributes:
        url: HTTP or HTTPS endpoint supplied by trusted application config.
        timeout: Maximum request time in seconds, capped to bound shutdown.
        allow_http: Whether non-encrypted HTTP is allowed for local testing.
        headers: Additional request headers, including optional credentials.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: SecretStr = Field(min_length=1, max_length=_MAX_URL_LENGTH)
    timeout: float = Field(default=5.0, gt=0, le=60)
    allow_http: bool = False
    headers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_destination(self) -> WebhookOptions:
        """Reject unsafe URL components and malformed HTTP headers.

        Returns:
            This validated options object.

        Raises:
            ValueError: If the URL or header collection is invalid.
        """
        parsed = urlsplit(self.url.get_secret_value())
        allowed_schemes = {"https"}
        if self.allow_http:
            allowed_schemes.add("http")
        if (
            parsed.scheme not in allowed_schemes
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            message = "Webhook URL must be an allowed HTTP(S) destination"
            raise ValueError(message)
        if len(self.headers) > _MAX_HEADER_COUNT:
            message = "Webhook header count exceeds its configured bound"
            raise ValueError(message)
        for name, value in self.headers.items():
            if (
                not name
                or any(character in name for character in "\r\n:")
                or any(character in value for character in "\r\n")
                or len(name) + len(value) > _MAX_HEADER_LENGTH
            ):
                message = "Webhook header contains invalid or oversized data"
                raise ValueError(message)
            if name.casefold() in {"host", "content-length"}:
                message = "Webhook headers cannot override transport framing"
                raise ValueError(message)
        if not math.isfinite(self.timeout):
            message = "Webhook timeout must be a finite number"
            raise ValueError(message)
        return self


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Prevent endpoint responses from changing the configured destination.

    Log payloads remain pinned to the destination selected by application
    configuration rather than following server-controlled redirects.
    """

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        """Reject every redirect rather than forwarding log payloads.

        Args:
            req: The original request.
            fp: The response object returned by urllib.
            code: The redirect status.
            msg: The server reason phrase.
            headers: Response headers.
            newurl: The redirect target, which is never followed.

        Returns:
            ``None`` so urllib reports the redirect as an HTTP error.
        """
        del req, fp, code, msg, headers, newurl


class WebhookLogDriver:
    """POST bounded native log payloads to a trusted webhook destination.

    Network I/O is synchronous by design. Call ``Logger.log_async`` when
    emitting from an async task so the request runs in AnyIO's worker pool.
    URLs are trusted deployment configuration; this driver is not an SSRF
    defense for URLs controlled by untrusted users.
    """

    def __init__(
        self,
        options: WebhookOptions,
        *,
        style: WebhookStyle = "json",
    ) -> None:
        """Create a driver without opening a network connection.

        Args:
            options: Validated native endpoint settings.
            style: JSON record or Slack-compatible text payload.
        """
        self._options = options
        self._style = style
        self._formatter = TextLogFormatter()
        self._opener = urllib.request.build_opener(_RejectRedirects())
        self._closed = False
        self._lock = Lock()

    def write(self, record: LogRecord) -> None:
        """Send one sanitized record and require a successful response.

        Args:
            record: The normalized and redacted application record.

        Raises:
            LogBackendError: If the remote endpoint rejects the request.
            LogLifecycleError: If this driver has been closed.
            URLError: If the endpoint cannot be reached before timeout.
        """
        with self._lock:
            if self._closed:
                message = "The webhook log driver is closed"
                raise LogLifecycleError(message)
        body = self._payload(record)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Titanspan/0.1",
            **self._options.headers,
        }
        request = urllib.request.Request(  # noqa: S310
            self._options.url.get_secret_value(),
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            # URL validation allows HTTP(S) only, and this opener rejects
            # redirects so records cannot be forwarded to a new destination.
            with self._opener.open(
                request,
                timeout=self._options.timeout,
            ) as response:
                if (
                    response.status < _HTTP_SUCCESS_MINIMUM
                    or response.status >= _HTTP_SUCCESS_EXCLUSIVE_MAXIMUM
                ):
                    message = "Webhook endpoint returned a non-success status"
                    raise LogBackendError(message)
        except urllib.error.HTTPError as error:
            message = f"Webhook endpoint returned HTTP {error.code}"
            raise LogBackendError(message) from error

    def flush(self) -> None:
        """Complete immediately because each request is delivered inline.

        The webhook driver has no buffered transport state to drain.
        """

    def close(self) -> None:
        """Prevent future requests without changing process-wide networking.

        Only the opener owned by this driver becomes unavailable.
        """
        with self._lock:
            self._closed = True

    def _payload(self, record: LogRecord) -> bytes:
        """Encode one sanitized record using the selected payload contract.

        Args:
            record: The native record already processed by the channel.

        Returns:
            UTF-8 JSON bytes for the configured webhook style.
        """
        if self._style == "slack":
            payload: dict[str, object] = {
                "text": self._formatter.format(record),
            }
        else:
            payload = record.to_dict()
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")


def webhook_options(options: Mapping[str, object]) -> WebhookOptions:
    """Validate mapping configuration without exposing input values in errors.

    Args:
        options: Native endpoint settings from a channel configuration.

    Returns:
        Validated settings ready for driver construction.

    Raises:
        LogConfigurationError: If any endpoint option is invalid.
    """
    try:
        return WebhookOptions.model_validate(options)
    except ValidationError as error:
        locations = ", ".join(
            ".".join(str(part) for part in issue["loc"])
            for issue in error.errors()
        )
        message = f"Invalid webhook channel options: {locations}"
        raise LogConfigurationError(message) from error
