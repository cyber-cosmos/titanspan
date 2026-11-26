"""Build immutable outgoing HTTP requests and execute them explicitly.

Fluent updates isolate request options until execution.
"""

from __future__ import annotations

import base64
import math
import random
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import anyio
from pydantic import TypeAdapter, ValidationError

from titanspan.contracts.http import (
    HttpClient,
    HttpClientResponse,
    JsonValue,
    OutgoingRequest,
    QueryParameters,
    QueryParameterValue,
    RequestPayload,
)
from titanspan.http.exceptions import (
    HttpClientError,
    HttpTransportError,
)

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager, AbstractContextManager

_RETRYABLE_STATUSES = (408, 425, 429, 500, 502, 503, 504)
_IDEMPOTENT_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PUT"})
_JSON_ADAPTER = TypeAdapter(JsonValue)
_MAX_RETRY_DELAY = 30.0
_INVALID_JSON_BODY_ERROR = "JSON request bodies must contain JSON values only."
_INVALID_FORM_BODY_ERROR = "Form request bodies must be mappings or byte text."
_INVALID_BASE_URL_ERROR = "HTTP base_url must use an absolute HTTP(S) URL."
_INVALID_AUTH_HEADER_MESSAGE = (
    "Bearer tokens must be non-empty and single-line."
)
_INVALID_TIMEOUT_ERROR = "HTTP timeout must be a finite positive value."
_INVALID_RETRY_ATTEMPTS_ERROR = "Retry attempts must be at least one."
_INVALID_RETRY_BACKOFF_ERROR = "Retry backoff must be finite and non-negative."
_INVALID_RETRY_STATUS_ERROR = "Retry statuses must be valid HTTP status codes."
_UNREACHABLE_SEND_ERROR = "A configured request attempt must resolve."
_INVALID_HEADER_ERROR = (
    "HTTP headers must use valid names and single-line values."
)
_MAX_HTTP_STATUS = 599
_MIN_HTTP_STATUS = 100


@dataclass(frozen=True, slots=True)
class _RequestOptions:
    """Store isolated immutable builder options for one pending request.

    Fluent updates isolate request options until execution.
    """

    base_url: str | None = None
    headers: tuple[tuple[str, str], ...] = ()
    params: tuple[tuple[str, QueryParameterValue], ...] = ()
    cookies: tuple[tuple[str, str], ...] = ()
    timeout: float | None = None
    follow_redirects: bool | None = None
    body: RequestPayload | JsonValue = None
    body_is_set: bool = False
    json_mode: bool = False
    attempts: int = 1
    backoff: float = 0.1
    jitter: bool = True
    retry_statuses: tuple[int, ...] = _RETRYABLE_STATUSES


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
        if not value.startswith(("http://", "https://")):
            raise ValueError(_INVALID_BASE_URL_ERROR)
        return self._with_options(base_url=value.rstrip("/") + "/")

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
        if isinstance(body, Mapping):
            body = dict(body)
        return self._with_options(body=body, body_is_set=True)

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
        merged.update(params)
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
        """Send one sync request and apply the configured safe retry policy.

        Fluent updates isolate request options until execution.
        """
        payload = self._payload(data)
        headers = _headers_dict(self._options.headers)
        safe_to_retry = _is_retry_safe(method, headers)
        attempts = self._options.attempts if safe_to_retry else 1
        for attempt in range(attempts):
            try:
                response = self._client.request(
                    self._outgoing_request(
                        method,
                        url,
                        data=payload,
                        params=params,
                    ),
                )
            except HttpTransportError:
                if attempt + 1 >= attempts:
                    raise
                time.sleep(self._retry_delay(attempt, None))
                continue
            if (
                attempt + 1 < attempts
                and response.status_code in self._options.retry_statuses
            ):
                delay = self._retry_delay(attempt, response)
                response.close()
                time.sleep(delay)
                continue
            return response
        raise AssertionError(_UNREACHABLE_SEND_ERROR)

    async def _send_async(
        self,
        method: str,
        url: str,
        *,
        data: RequestPayload | JsonValue,
        params: QueryParameters | None,
    ) -> HttpClientResponse:
        """Send one async request and apply the configured safe retry policy.

        Fluent updates isolate request options until execution.
        """
        payload = self._payload(data)
        headers = _headers_dict(self._options.headers)
        safe_to_retry = _is_retry_safe(method, headers)
        attempts = self._options.attempts if safe_to_retry else 1
        for attempt in range(attempts):
            try:
                response = await self._client.request_async(
                    self._outgoing_request(
                        method,
                        url,
                        data=payload,
                        params=params,
                    ),
                )
            except HttpTransportError:
                if attempt + 1 >= attempts:
                    raise
                await anyio.sleep(self._retry_delay(attempt, None))
                continue
            if (
                attempt + 1 < attempts
                and response.status_code in self._options.retry_statuses
            ):
                delay = self._retry_delay(attempt, response)
                await response.aclose()
                await anyio.sleep(delay)
                continue
            return response
        raise AssertionError(_UNREACHABLE_SEND_ERROR)

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
            try:
                json_body = _JSON_ADAPTER.validate_python(data)
            except ValidationError as error:
                raise HttpClientError(_INVALID_JSON_BODY_ERROR) from error
        elif include_body and data is not None:
            if not isinstance(data, (Mapping, str, bytes)):
                raise TypeError(_INVALID_FORM_BODY_ERROR)
            request_data = data

        return OutgoingRequest(
            method=method.upper(),
            url=self._url(url),
            headers=_headers_dict(self._options.headers),
            params=_merge_params(self._options.params, params),
            json_body=json_body,
            json_enabled=json_enabled,
            data=request_data,
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
        if self._options.base_url is None:
            return url
        return urljoin(self._options.base_url, url)

    def _retry_delay(
        self,
        attempt: int,
        response: HttpClientResponse | None,
    ) -> float:
        """Compute capped exponential delay with optional jitter.

        Args:
            attempt: Zero-based failed attempt.
            response: Response that may contain Retry-After seconds.

        Returns:
            Delay seconds bounded to a finite 30 second maximum.
        """
        retry_after = (
            None if response is None else response.header("retry-after")
        )
        if retry_after is not None and retry_after.isdigit():
            return min(float(retry_after), _MAX_RETRY_DELAY)
        delay = min(
            self._options.backoff * (2**attempt),
            _MAX_RETRY_DELAY,
        )
        if self._options.jitter and delay:
            delay = random.SystemRandom().uniform(
                delay * 0.75,
                delay * 1.25,
            )
        return min(delay, _MAX_RETRY_DELAY)

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


def _merge_params(
    base: Sequence[tuple[str, QueryParameterValue]],
    override: QueryParameters | None,
) -> QueryParameters:
    """Merge builder and per-call query options deterministically.

    Fluent updates isolate request options until execution.
    """
    values: dict[str, QueryParameterValue] = dict(base)
    if override is not None:
        values.update(override)
    return values


def _is_retry_safe(method: str, headers: Mapping[str, str]) -> bool:
    """Check standard idempotent methods and explicit idempotency keys.

    Fluent updates isolate request options until execution.
    """
    return method.upper() in _IDEMPOTENT_METHODS or any(
        name.lower() == "idempotency-key" and bool(value)
        for name, value in headers.items()
    )


__all__ = ["PendingRequest"]
