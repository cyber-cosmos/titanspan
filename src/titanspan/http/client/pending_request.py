"""Build immutable outgoing HTTP requests and execute them explicitly.

Fluent updates isolate request options until execution.
"""

from __future__ import annotations

import base64
import math
import random
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from pydantic import TypeAdapter, ValidationError

from titanspan.contracts.http import (
    HttpClient,
    HttpClientResponse,
    JsonValue,
    MultipartFile,
    OutgoingRequest,
    QueryParameters,
    QueryParameterValue,
    RequestPayload,
)
from titanspan.http._urls import (
    validate_base_url,
    validate_outbound_url,
)
from titanspan.http.exceptions import (
    HttpClientError,
    HttpTransportError,
)
from titanspan.support import retry as retry_sync
from titanspan.support import retry_async

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager, AbstractContextManager

_RETRYABLE_STATUSES = (408, 425, 429, 500, 502, 503, 504)
_IDEMPOTENT_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PUT"})
_JSON_ADAPTER = TypeAdapter(JsonValue)
_MULTIPART_SEQUENCE_ADAPTER = TypeAdapter(tuple[object, ...])
_MAX_RETRY_DELAY = 30.0
_INVALID_JSON_BODY_ERROR = "JSON request bodies must contain JSON values only."
_INVALID_FORM_BODY_ERROR = "Form request bodies must be mappings or byte text."
_BODY_SNAPSHOT_ERROR = "HTTP request data could not be safely snapshotted."
_INVALID_AUTH_HEADER_MESSAGE = (
    "Bearer tokens must be non-empty and single-line."
)
_INVALID_TIMEOUT_ERROR = "HTTP timeout must be a finite positive value."
_INVALID_RETRY_ATTEMPTS_ERROR = "Retry attempts must be at least one."
_INVALID_RETRY_BACKOFF_ERROR = "Retry backoff must be finite and non-negative."
_INVALID_RETRY_STATUS_ERROR = "Retry statuses must be valid HTTP status codes."
_INVALID_HEADER_ERROR = (
    "HTTP headers must use valid names and single-line values."
)
_INVALID_MULTIPART_FIELD_ERROR = (
    "Multipart field names must be non-empty and single-line."
)
_MULTIPART_JSON_ERROR = "Multipart attachments cannot use JSON encoding."
_MAX_HTTP_STATUS = 599
_MIN_HTTP_STATUS = 100
_ASCII_CONTROL_MAX = 31
_DELETE_CODEPOINT = 127


@dataclass(frozen=True, slots=True)
class _RequestOptions:
    """Store isolated immutable builder options for one pending request.

    Fluent updates isolate request options until execution.
    """

    base_url: str | None = None
    headers: tuple[tuple[str, str], ...] = ()
    params: tuple[tuple[str, QueryParameterValue], ...] = ()
    cookies: tuple[tuple[str, str], ...] = ()
    files: tuple[tuple[str, MultipartFile], ...] = ()
    timeout: float | None = None
    follow_redirects: bool | None = None
    body: RequestPayload | JsonValue = None
    body_is_set: bool = False
    json_mode: bool = False
    attempts: int = 1
    backoff: float = 0.1
    jitter: bool = True
    retry_statuses: tuple[int, ...] = _RETRYABLE_STATUSES


class _RetryableResponseError(Exception):
    """Carry retry metadata from an HTTP response into Tenacity policy.

    The response is closed before this signal crosses the shared retry helper.
    """

    def __init__(self, retry_after: str | None) -> None:
        """Retain the optional server-provided delay for one retry.

        Args:
            retry_after: Numeric ``Retry-After`` value, if supplied.
        """
        super().__init__("The HTTP response status is configured for retry.")
        self.retry_after = retry_after

    retry_after: str | None


@dataclass(frozen=True, slots=True)
class PendingRequest:
    """Represent an immutable request configuration over a pooled client.

    Configuration methods return new builders. A builder can be reused
    concurrently because every operation receives fresh option mappings.
    Network operations use an explicit synchronous or asynchronous method.
    """

    _client: HttpClient
    _options: _RequestOptions = field(default_factory=_RequestOptions)

    def base_url(self, value: str) -> PendingRequest:
        """Set a base URL used to resolve relative request paths.

        Args:
            value: Absolute HTTP or HTTPS base URL.

        Returns:
            A new request builder.

        Raises:
            ValueError: If the URL is not an absolute HTTP(S) base.
        """
        return self._with_options(base_url=validate_base_url(value))

    def with_headers(self, values: Mapping[str, str]) -> PendingRequest:
        """Merge headers into this request builder without changing its parent.

        Args:
            values: Header names and values to add or replace.

        Returns:
            A new builder with an independent header snapshot.

        Raises:
            ValueError: If a name or value contains invalid line controls.
        """
        headers = _headers_dict(self._options.headers)
        for name, value in values.items():
            _validate_header(name, value)
            _replace_header(headers, name, value)
        return self._with_options(headers=tuple(headers.items()))

    def with_header(self, name: str, value: str) -> PendingRequest:
        """Set one request header immutably.

        Args:
            name: Header name.
            value: Header value.

        Returns:
            A new request builder.

        Raises:
            ValueError: If the header contains invalid line controls.
        """
        return self.with_headers({name: value})

    def with_token(self, token: str) -> PendingRequest:
        """Set bearer-token authentication for this request only.

        Args:
            token: Secret token without a scheme prefix.

        Returns:
            A new builder with an Authorization header.

        Raises:
            ValueError: If the token is empty or contains line breaks.
        """
        if not token or "\r" in token or "\n" in token:
            raise ValueError(_INVALID_AUTH_HEADER_MESSAGE)
        return self.with_header("Authorization", f"Bearer {token}")

    def with_basic_auth(self, username: str, password: str) -> PendingRequest:
        """Set HTTP Basic authentication without mutating other builders.

        Args:
            username: Account name.
            password: Account password.

        Returns:
            A new builder with a generated Basic Authorization header.
        """
        credentials = f"{username}:{password}".encode()
        token = base64.b64encode(credentials).decode("ascii")
        return self.with_header("Authorization", f"Basic {token}")

    def accept(self, media_type: str) -> PendingRequest:
        """Set the desired response media type.

        Args:
            media_type: Valid response media type string.

        Returns:
            A new request builder.
        """
        return self.with_header("Accept", media_type)

    def accept_json(self) -> PendingRequest:
        """Request an application/json response.

        Fluent updates isolate request options until execution.
        """
        return self.accept("application/json")

    def as_json(self) -> PendingRequest:
        """Encode mapping and scalar bodies as JSON for subsequent requests.

        Returns:
            A new builder that uses the JSON request-body mode.
        """
        return self._with_options(json_mode=True)

    def as_form(self) -> PendingRequest:
        """Encode mapping bodies as URL-encoded form fields.

        Returns:
            A new builder using the native scalar form encoder.
        """
        return self._with_options(json_mode=False)

    def with_body(self, body: RequestPayload | JsonValue) -> PendingRequest:
        """Set a reusable body value for subsequent request methods.

        Args:
            body: JSON-compatible or supported form/text/byte content.

        Returns:
            A new builder retaining a shallow copy of mapping bodies.
        """
        return self._with_options(
            body=_snapshot_value(body),
            body_is_set=True,
        )

    def with_query_parameters(
        self,
        params: QueryParameters,
    ) -> PendingRequest:
        """Merge query parameters into subsequent requests.

        Args:
            params: Scalar values or scalar sequences.

        Returns:
            A new builder with copied query values.
        """
        merged: dict[str, QueryParameterValue] = dict(self._options.params)
        merged.update(_snapshot_query_parameters(params))
        return self._with_options(params=tuple(merged.items()))

    def with_cookies(self, cookies: Mapping[str, str]) -> PendingRequest:
        """Merge cookie values into subsequent requests.

        Args:
            cookies: Cookie names and values for this builder.

        Returns:
            A new builder with a copied cookie mapping.
        """
        merged = dict(self._options.cookies)
        merged.update(cookies)
        return self._with_options(cookies=tuple(merged.items()))

    def with_files(
        self,
        values: Mapping[str, MultipartFile | Sequence[MultipartFile]],
    ) -> PendingRequest:
        """Append replayable multipart attachments to this builder.

        Args:
            values: Form field names mapped to one or more byte attachments.

        Returns:
            A new builder that sends multipart form data.

        Raises:
            TypeError: If a field does not contain ``MultipartFile`` values.
            ValueError: If a field name is empty or contains line breaks.
        """
        files = list(self._options.files)
        for name, value in values.items():
            _validate_multipart_field(name)
            files.extend(
                (name, attachment)
                for attachment in _multipart_attachments(value)
            )
        return self._with_options(
            files=tuple(files),
            json_mode=False,
        )

    def attach(
        self,
        name: str,
        content: bytes,
        *,
        filename: str,
        content_type: str = "application/octet-stream",
    ) -> PendingRequest:
        """Append one replayable attachment to multipart form data.

        Args:
            name: Multipart form field name.
            content: Immutable attachment bytes.
            filename: Filename sent in the multipart content disposition.
            content_type: Attachment media type.

        Returns:
            A new builder with the attachment appended.
        """
        return self.with_files(
            {
                name: MultipartFile(
                    filename=filename,
                    content=content,
                    content_type=content_type,
                ),
            }
        )

    def timeout(self, seconds: float) -> PendingRequest:
        """Set a finite positive request timeout.

        Args:
            seconds: Total request timeout in seconds.

        Returns:
            A new request builder.

        Raises:
            ValueError: If the timeout is not positive and finite.
        """
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError(_INVALID_TIMEOUT_ERROR)
        return self._with_options(timeout=seconds)

    def retry(
        self,
        attempts: int,
        *,
        backoff: float = 0.1,
        jitter: bool = True,
        statuses: Sequence[int] = _RETRYABLE_STATUSES,
    ) -> PendingRequest:
        """Set a bounded retry policy for idempotent or keyed requests.

        Unsafe methods are sent once unless an Idempotency-Key header is set.
        Transport failures and selected response statuses use exponential
        backoff with optional jitter. Cancellation is never intercepted.

        Args:
            attempts: Maximum total attempts, including the initial request.
            backoff: Base delay in seconds before the first retry.
            jitter: Add bounded random jitter to delay intervals.
            statuses: HTTP statuses that may be retried.

        Returns:
            A new request builder.

        Raises:
            ValueError: If the attempts or delay are invalid.
        """
        if attempts < 1:
            raise ValueError(_INVALID_RETRY_ATTEMPTS_ERROR)
        if not math.isfinite(backoff) or backoff < 0:
            raise ValueError(_INVALID_RETRY_BACKOFF_ERROR)
        if any(
            status < _MIN_HTTP_STATUS or status > _MAX_HTTP_STATUS
            for status in statuses
        ):
            raise ValueError(_INVALID_RETRY_STATUS_ERROR)
        return self._with_options(
            attempts=attempts,
            backoff=backoff,
            jitter=jitter,
            retry_statuses=tuple(dict.fromkeys(statuses)),
        )

    def without_redirecting(self) -> PendingRequest:
        """Disable redirects for subsequent requests on this builder.

        Fluent updates isolate request options until execution.
        """
        return self._with_options(follow_redirects=False)

    def request(
        self,
        method: str,
        url: str,
        *,
        data: RequestPayload | JsonValue = None,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Execute one request synchronously outside an async runtime.

        Args:
            method: HTTP method.
            url: Absolute URL or configured base-relative path.
            data: Optional body overriding a configured body.
            params: Query values overriding builder values by key.

        Returns:
            Native response wrapper.

        Raises:
            HttpTransportError: If a transport failure occurs after retries.
        """
        return self._send_sync(method, url, data=data, params=params)

    async def request_async(
        self,
        method: str,
        url: str,
        *,
        data: RequestPayload | JsonValue = None,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Execute one request in the active asynchronous runtime.

        Args:
            method: HTTP method.
            url: Absolute URL or configured base-relative path.
            data: Optional body overriding a configured body.
            params: Query values overriding builder values by key.

        Returns:
            Native response wrapper.
        """
        return await self._send_async(method, url, data=data, params=params)

    def get(
        self,
        url: str,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a GET request synchronously.

        Fluent updates isolate request options until execution.
        """
        return self._send_sync("GET", url, data=None, params=params)

    async def get_async(
        self,
        url: str,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a GET request asynchronously.

        Fluent updates isolate request options until execution.
        """
        return await self._send_async("GET", url, data=None, params=params)

    def post(
        self,
        url: str,
        data: RequestPayload | JsonValue = None,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a POST request synchronously.

        Fluent updates isolate request options until execution.
        """
        return self._send_sync("POST", url, data=data, params=params)

    async def post_async(
        self,
        url: str,
        data: RequestPayload | JsonValue = None,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a POST request asynchronously.

        Fluent updates isolate request options until execution.
        """
        return await self._send_async("POST", url, data=data, params=params)

    def put(
        self,
        url: str,
        data: RequestPayload | JsonValue = None,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a PUT request synchronously.

        Fluent updates isolate request options until execution.
        """
        return self._send_sync("PUT", url, data=data, params=params)

    async def put_async(
        self,
        url: str,
        data: RequestPayload | JsonValue = None,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a PUT request asynchronously.

        Fluent updates isolate request options until execution.
        """
        return await self._send_async("PUT", url, data=data, params=params)

    def patch(
        self,
        url: str,
        data: RequestPayload | JsonValue = None,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a PATCH request synchronously.

        Fluent updates isolate request options until execution.
        """
        return self._send_sync("PATCH", url, data=data, params=params)

    async def patch_async(
        self,
        url: str,
        data: RequestPayload | JsonValue = None,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a PATCH request asynchronously.

        Fluent updates isolate request options until execution.
        """
        return await self._send_async("PATCH", url, data=data, params=params)

    def delete(
        self,
        url: str,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a DELETE request synchronously.

        Fluent updates isolate request options until execution.
        """
        return self._send_sync("DELETE", url, data=None, params=params)

    async def delete_async(
        self,
        url: str,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a DELETE request asynchronously.

        Fluent updates isolate request options until execution.
        """
        return await self._send_async("DELETE", url, data=None, params=params)

    def head(self, url: str) -> HttpClientResponse:
        """Perform a HEAD request synchronously.

        Fluent updates isolate request options until execution.
        """
        return self._send_sync("HEAD", url, data=None, params=None)

    async def head_async(self, url: str) -> HttpClientResponse:
        """Perform a HEAD request asynchronously.

        Fluent updates isolate request options until execution.
        """
        return await self._send_async("HEAD", url, data=None, params=None)

    def options(self, url: str) -> HttpClientResponse:
        """Perform an OPTIONS request synchronously.

        Fluent updates isolate request options until execution.
        """
        return self._send_sync("OPTIONS", url, data=None, params=None)

    async def options_async(self, url: str) -> HttpClientResponse:
        """Perform an OPTIONS request asynchronously.

        Fluent updates isolate request options until execution.
        """
        return await self._send_async("OPTIONS", url, data=None, params=None)

    def stream(
        self,
        method: str,
        url: str,
        *,
        params: QueryParameters | None = None,
    ) -> AbstractContextManager[HttpClientResponse]:
        """Open a synchronous streaming response context.

        Args:
            method: HTTP method.
            url: Request URL.
            params: Additional query values.

        Returns:
            A context manager that releases the pooled connection on exit.
        """
        return self._client.stream(
            self._outgoing_request(
                method,
                url,
                data=None,
                params=params,
                include_body=False,
            ),
        )

    def stream_async(
        self,
        method: str,
        url: str,
        *,
        params: QueryParameters | None = None,
    ) -> AbstractAsyncContextManager[HttpClientResponse]:
        """Open an async streaming response context.

        Args:
            method: HTTP method.
            url: Request URL.
            params: Additional query values.

        Returns:
            An async context manager that closes the response on exit.
        """
        return self._client.stream_async(
            self._outgoing_request(
                method,
                url,
                data=None,
                params=params,
                include_body=False,
            ),
        )

    def _send_sync(
        self,
        method: str,
        url: str,
        *,
        data: RequestPayload | JsonValue,
        params: QueryParameters | None,
    ) -> HttpClientResponse:
        """Send one sync request through the shared retry controller.

        Fluent updates isolate request options until execution.
        """
        payload = self._payload(data)
        headers = _headers_dict(self._options.headers)
        safe_to_retry = _is_retry_safe(method, headers)
        attempts = self._options.attempts if safe_to_retry else 1

        def send(attempt: int) -> HttpClientResponse:
            """Perform one request and signal retryable statuses safely.

            Args:
                attempt: One-based attempt number from the retry controller.

            Returns:
                The response when it should be returned to the caller.

            Raises:
                HttpTransportError: When the transport request fails.
                _RetryableResponseError: When another attempt is permitted.
            """
            response = self._client.request(
                self._outgoing_request(
                    method,
                    url,
                    data=payload,
                    params=params,
                ),
            )
            if (
                attempt < attempts
                and response.status_code in self._options.retry_statuses
            ):
                retry_after = response.header("retry-after")
                response.close()
                raise _RetryableResponseError(retry_after)
            return response

        return retry_sync(
            attempts,
            send,
            sleep_milliseconds=self._retry_wait,
            when=_is_retryable_failure,
        )

    async def _send_async(
        self,
        method: str,
        url: str,
        *,
        data: RequestPayload | JsonValue,
        params: QueryParameters | None,
    ) -> HttpClientResponse:
        """Send one async request through the shared retry controller.

        Fluent updates isolate request options until execution.
        """
        payload = self._payload(data)
        headers = _headers_dict(self._options.headers)
        safe_to_retry = _is_retry_safe(method, headers)
        attempts = self._options.attempts if safe_to_retry else 1

        async def send(attempt: int) -> HttpClientResponse:
            """Perform one async request and close discarded responses.

            Args:
                attempt: One-based attempt number from the retry controller.

            Returns:
                The response when it should be returned to the caller.

            Raises:
                HttpTransportError: When the transport request fails.
                _RetryableResponseError: When another attempt is permitted.
            """
            response = await self._client.request_async(
                self._outgoing_request(
                    method,
                    url,
                    data=payload,
                    params=params,
                ),
            )
            if (
                attempt < attempts
                and response.status_code in self._options.retry_statuses
            ):
                retry_after = response.header("retry-after")
                await response.aclose()
                raise _RetryableResponseError(retry_after)
            return response

        return await retry_async(
            attempts,
            send,
            sleep_milliseconds=self._retry_wait,
            when=_is_retryable_failure,
        )

    def _outgoing_request(
        self,
        method: str,
        url: str,
        *,
        data: RequestPayload | JsonValue,
        params: QueryParameters | None,
        include_body: bool = True,
    ) -> OutgoingRequest:
        """Build an isolated transport-neutral request snapshot.

        Args:
            method: HTTP method selected by the public operation.
            url: Absolute or builder-relative request location.
            data: Selected request body.
            params: Per-operation query overrides.
            include_body: Whether the request should include its configured
                body. Streaming GETs pass ``False``.

        Returns:
            A value that remains unchanged when this builder is reused.
        """
        json_body: JsonValue | None = None
        request_data: RequestPayload = None
        json_enabled = include_body and self._options.json_mode
        if include_body and self._options.json_mode:
            if self._options.files:
                raise HttpClientError(_MULTIPART_JSON_ERROR)
            try:
                json_body = _JSON_ADAPTER.validate_python(_snapshot_value(data))
            except ValidationError as error:
                raise HttpClientError(_INVALID_JSON_BODY_ERROR) from error
        elif include_body and data is not None:
            if not isinstance(data, (Mapping, str, bytes)):
                raise TypeError(_INVALID_FORM_BODY_ERROR)
            request_data = (
                _snapshot_value(data) if isinstance(data, Mapping) else data
            )

        return OutgoingRequest(
            method=method.upper(),
            url=self._url(url),
            headers=_headers_dict(self._options.headers),
            params=_merge_params(self._options.params, params),
            json_body=json_body,
            json_enabled=json_enabled,
            data=request_data,
            files=self._options.files if include_body else (),
            cookies=dict(self._options.cookies),
            timeout=self._options.timeout,
            follow_redirects=self._options.follow_redirects,
        )

    def _payload(
        self,
        data: RequestPayload | JsonValue,
    ) -> RequestPayload | JsonValue:
        """Select operation body or the builder's reusable body.

        Args:
            data: Per-operation body value.

        Returns:
            The explicit operation value or configured builder value.
        """
        if data is not None:
            return data
        return self._options.body if self._options.body_is_set else None

    def _url(self, url: str) -> str:
        """Resolve a relative path against the optional request base URL.

        Fluent updates isolate request options until execution.
        """
        base_url = self._options.base_url
        candidate = validate_outbound_url(url, allow_relative=True)
        resolved = urljoin(base_url, candidate) if base_url else candidate
        return validate_outbound_url(
            resolved,
            allow_relative=base_url is None,
        )

    def _retry_wait(
        self,
        attempt: int,
        error: Exception,
    ) -> timedelta:
        """Compute an HTTP retry delay for the shared retry controller.

        Args:
            attempt: One-based failed attempt number.
            error: Retryable transport or response failure.

        Returns:
            A non-negative delay capped at 30 seconds.
        """
        retry_after = (
            error.retry_after
            if isinstance(error, _RetryableResponseError)
            else None
        )
        if retry_after is not None and retry_after.isdigit():
            seconds = min(float(retry_after), _MAX_RETRY_DELAY)
            return timedelta(seconds=seconds)
        delay = min(
            self._options.backoff * (2 ** (attempt - 1)),
            _MAX_RETRY_DELAY,
        )
        if self._options.jitter and delay:
            delay = random.SystemRandom().uniform(
                delay * 0.75,
                delay * 1.25,
            )
        return timedelta(seconds=min(delay, _MAX_RETRY_DELAY))

    def _with_options(self, **changes: object) -> PendingRequest:
        """Return a builder with a replaced immutable option object.

        Fluent updates isolate request options until execution.
        """
        return replace(self, _options=replace(self._options, **changes))


def _headers_dict(values: Sequence[tuple[str, str]]) -> dict[str, str]:
    """Return a fresh case-insensitive header merge target.

    Fluent updates isolate request options until execution.
    """
    return dict(values)


def _replace_header(headers: dict[str, str], name: str, value: str) -> None:
    """Replace a header while preserving the caller's latest spelling.

    Fluent updates isolate request options until execution.
    """
    existing = next(
        (key for key in headers if key.lower() == name.lower()), None
    )
    if existing is not None:
        del headers[existing]
    headers[name] = value


def _validate_header(name: str, value: str) -> None:
    """Reject malformed header names and response-splitting values.

    Fluent updates isolate request options until execution.
    """
    valid_name = bool(name) and all(
        char.isalnum() or char in "!#$%&'*+-.^_`|~" for char in name
    )
    if not valid_name or "\r" in value or "\n" in value:
        raise ValueError(_INVALID_HEADER_ERROR)


def _validate_multipart_field(name: str) -> None:
    """Reject multipart names that can alter the generated part header.

    Args:
        name: Untrusted form field name supplied by application code.

    Raises:
        ValueError: If the field name is empty or contains controls.
    """
    if not name or any(
        ord(character) <= _ASCII_CONTROL_MAX
        or ord(character) == _DELETE_CODEPOINT
        for character in name
    ):
        raise ValueError(_INVALID_MULTIPART_FIELD_ERROR)


def _multipart_attachments(value: object) -> tuple[MultipartFile, ...]:
    """Validate and snapshot one multipart field's attachment values.

    Args:
        value: One file or a sequence of files supplied by the caller.

    Returns:
        Immutable attachments in field order.

    Raises:
        TypeError: If the value contains non-file objects.
    """
    if isinstance(value, MultipartFile):
        return (value,)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(_INVALID_MULTIPART_FIELD_ERROR)
    attachments: list[MultipartFile] = []
    values = _MULTIPART_SEQUENCE_ADAPTER.validate_python(value)
    for attachment in values:
        if not isinstance(attachment, MultipartFile):
            raise TypeError(_INVALID_MULTIPART_FIELD_ERROR)
        attachments.append(attachment)
    return tuple(attachments)


def _merge_params(
    base: Sequence[tuple[str, QueryParameterValue]],
    override: QueryParameters | None,
) -> QueryParameters:
    """Merge builder and per-call query options deterministically.

    Fluent updates isolate request options until execution.
    """
    values: dict[str, QueryParameterValue] = {
        key: _snapshot_query_value(value) for key, value in base
    }
    if override is not None:
        values.update(_snapshot_query_parameters(override))
    return values


def _snapshot_value[ValueT](value: ValueT) -> ValueT:
    """Deep-copy request data before it enters reusable builder state.

    Args:
        value: Mapping or JSON-compatible value supplied by application code.

    Returns:
        A copy independent of mutable objects owned by the caller.

    Raises:
        HttpClientError: If the supplied value cannot be copied safely.
    """
    try:
        return deepcopy(value)
    except Exception as error:
        raise HttpClientError(_BODY_SNAPSHOT_ERROR) from error


def _snapshot_query_parameters(
    values: QueryParameters,
) -> dict[str, QueryParameterValue]:
    """Copy mutable query sequences into immutable tuples.

    Args:
        values: Query mapping supplied by application code.

    Returns:
        An independently owned query mapping.
    """
    return {key: _snapshot_query_value(value) for key, value in values.items()}


def _snapshot_query_value(
    value: QueryParameterValue,
) -> QueryParameterValue:
    """Copy repeated query values while preserving scalar values.

    Args:
        value: Scalar query value or a sequence of scalar values.

    Returns:
        The scalar or a tuple independent of the source sequence.
    """
    if isinstance(value, Sequence) and not isinstance(value, str):
        return tuple(value)
    return value


def _is_retry_safe(method: str, headers: Mapping[str, str]) -> bool:
    """Check standard idempotent methods and explicit idempotency keys.

    Fluent updates isolate request options until execution.
    """
    return method.upper() in _IDEMPOTENT_METHODS or any(
        name.lower() == "idempotency-key" and bool(value)
        for name, value in headers.items()
    )


def _is_retryable_failure(error: Exception) -> bool:
    """Select transport failures and configured HTTP status signals.

    Args:
        error: Exception raised by one request attempt.

    Returns:
        Whether the shared retry controller may schedule another attempt.
    """
    return isinstance(
        error,
        (HttpTransportError, _RetryableResponseError),
    )


__all__ = ["PendingRequest"]
