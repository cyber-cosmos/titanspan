"""Expose pooled outgoing HTTP through the shared application facade base.

Resolution follows the active application's container.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.contracts.http import (
    HttpClient,
    HttpClientResponse,
    JsonValue,
    MultipartFile,
    QueryParameters,
    RequestPayload,
)
from titanspan.facades.base import Facade
from titanspan.http.client.pending_request import PendingRequest
from titanspan.http.client.pool import HttpRequestPool
from titanspan.http.testing import (
    HttpFake,
    HttpFakeResponse,
    HttpFakeResponses,
    HttpRequestMatcher,
    HttpRequestPattern,
    SentRequest,
    require_http_fake,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from contextlib import AbstractAsyncContextManager, AbstractContextManager


class Http(Facade[HttpClient]):
    """Resolve the application HTTP client and immutable request builders.

    Resolution follows the active application's container.
    """

    service_contract = HttpClient

    @classmethod
    def fake(cls, responses: HttpFakeResponses) -> HttpFake:
        """Create a context-local fake transport for outgoing requests.

        The active application client remains registered and owned by its
        container; the fake only intercepts calls in the current context.
        """
        _ = cls
        return HttpFake(responses)

    @classmethod
    def fake_response(
        cls,
        content: JsonValue | bytes | None = None,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> HttpFakeResponse:
        """Create one buffered response value for an HTTP fake.

        Args:
            content: JSON value, text, bytes, or no response body.
            status: HTTP status returned by the fake transport.
            headers: Optional response headers.

        Returns:
            A transport-neutral fake response.
        """
        _ = cls
        return HttpFakeResponse(
            content=content,
            status=status,
            headers={} if headers is None else headers,
        )

    @classmethod
    def request_pattern(
        cls,
        *,
        url: str = "*",
        method: str | None = None,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ) -> HttpRequestPattern:
        """Create a structured matcher for fake responses and assertions.

        Args:
            url: Case-sensitive glob matched against the complete URL.
            method: Optional HTTP method filter.
            headers: Header values that must match exactly.
            body: Optional complete request body that must match exactly.

        Returns:
            A request pattern using immutable header snapshots.
        """
        _ = cls
        return HttpRequestPattern(
            url=url,
            method=method,
            headers={} if headers is None else headers,
            body=body,
        )

    @classmethod
    def sent_requests(cls) -> tuple[SentRequest, ...]:
        """Return the immutable requests recorded by the active fake.

        The current execution context selects the active fake session.
        """
        _ = cls
        return require_http_fake().requests

    @classmethod
    def assert_sent(
        cls,
        matcher: HttpRequestMatcher | None = None,
    ) -> None:
        """Assert that a request matching the optional pattern was sent.

        An omitted pattern matches any recorded outgoing request.
        """
        _ = cls
        require_http_fake().assert_sent(matcher)

    @classmethod
    def assert_not_sent(
        cls,
        matcher: HttpRequestMatcher | None = None,
    ) -> None:
        """Assert that no request matching the optional pattern was sent.

        An omitted pattern checks that the fake recorded no request.
        """
        _ = cls
        require_http_fake().assert_not_sent(matcher)

    @classmethod
    def assert_sent_count(
        cls,
        count: int,
        matcher: HttpRequestMatcher | None = None,
    ) -> None:
        """Assert an exact matching request count in the active fake.

        An omitted pattern counts every request recorded in this context.
        """
        _ = cls
        require_http_fake().assert_sent_count(count, matcher)

    @classmethod
    def client(cls) -> HttpClient:
        """Return the client service after application startup.

        Returns:
            Shared HTTP service with explicit sync and async operations.
        """
        return cls.resolve_service()

    @classmethod
    def pending_request(cls) -> PendingRequest:
        """Create an isolated request builder over the active client.

        Resolution follows the active application's container.
        """
        return PendingRequest(cls.client())

    @classmethod
    def pool(cls, *, max_concurrency: int) -> HttpRequestPool:
        """Create a bounded pool for explicitly asynchronous HTTP requests.

        Args:
            max_concurrency: Maximum simultaneous request callbacks.

        Returns:
            A pool whose requests resolve through the active HTTP client.
        """
        _ = cls
        return HttpRequestPool(max_concurrency)

    @classmethod
    def base_url(cls, value: str) -> PendingRequest:
        """Create a builder with a request-local base URL.

        Resolution follows the active application's container.
        """
        return cls.pending_request().base_url(value)

    @classmethod
    def with_headers(cls, values: Mapping[str, str]) -> PendingRequest:
        """Create a builder with request-local headers.

        Resolution follows the active application's container.
        """
        return cls.pending_request().with_headers(values)

    @classmethod
    def with_header(cls, name: str, value: str) -> PendingRequest:
        """Create a builder with one request-local header.

        Resolution follows the active application's container.
        """
        return cls.pending_request().with_header(name, value)

    @classmethod
    def with_token(cls, token: str) -> PendingRequest:
        """Create a builder with bearer-token authentication.

        Resolution follows the active application's container.
        """
        return cls.pending_request().with_token(token)

    @classmethod
    def with_basic_auth(
        cls,
        username: str,
        password: str,
    ) -> PendingRequest:
        """Create a builder with HTTP Basic authentication.

        Resolution follows the active application's container.
        """
        return cls.pending_request().with_basic_auth(username, password)

    @classmethod
    def accept(cls, media_type: str) -> PendingRequest:
        """Create a builder requesting the selected response media type.

        Resolution follows the active application's container.
        """
        return cls.pending_request().accept(media_type)

    @classmethod
    def accept_json(cls) -> PendingRequest:
        """Create a builder requesting JSON responses.

        Resolution follows the active application's container.
        """
        return cls.pending_request().accept_json()

    @classmethod
    def as_json(cls) -> PendingRequest:
        """Create a builder that encodes request bodies as JSON.

        Resolution follows the active application's container.
        """
        return cls.pending_request().as_json()

    @classmethod
    def as_form(cls) -> PendingRequest:
        """Create a builder that encodes mappings as form values.

        Resolution follows the active application's container.
        """
        return cls.pending_request().as_form()

    @classmethod
    def with_query_parameters(
        cls,
        values: QueryParameters,
    ) -> PendingRequest:
        """Create a builder with request-local query parameters.

        Resolution follows the active application's container.
        """
        return cls.pending_request().with_query_parameters(values)

    @classmethod
    def with_cookies(cls, values: Mapping[str, str]) -> PendingRequest:
        """Create a builder with request-local cookies.

        Resolution follows the active application's container.
        """
        return cls.pending_request().with_cookies(values)

    @classmethod
    def with_files(
        cls,
        values: Mapping[str, MultipartFile | Sequence[MultipartFile]],
    ) -> PendingRequest:
        """Create a builder with request-local multipart attachments.

        Resolution follows the active application's container.
        """
        return cls.pending_request().with_files(values)

    @classmethod
    def attach(
        cls,
        name: str,
        content: bytes,
        *,
        filename: str,
        content_type: str = "application/octet-stream",
    ) -> PendingRequest:
        """Create a builder with one replayable multipart attachment.

        Resolution follows the active application's container.
        """
        return cls.pending_request().attach(
            name,
            content,
            filename=filename,
            content_type=content_type,
        )

    @classmethod
    def timeout(cls, seconds: float) -> PendingRequest:
        """Create a builder with an explicit finite request timeout.

        Resolution follows the active application's container.
        """
        return cls.pending_request().timeout(seconds)

    @classmethod
    def retry(
        cls,
        attempts: int,
        *,
        backoff: float = 0.1,
        jitter: bool = True,
        statuses: Sequence[int] = (408, 425, 429, 500, 502, 503, 504),
    ) -> PendingRequest:
        """Create a builder with bounded retry rules.

        Args:
            attempts: Maximum total attempts, including the first request.
            backoff: Base delay before retrying in seconds.
            jitter: Add bounded randomness to retry delays.
            statuses: Retryable HTTP status codes.

        Returns:
            A native request builder with an isolated retry policy.
        """
        return cls.pending_request().retry(
            attempts,
            backoff=backoff,
            jitter=jitter,
            statuses=statuses,
        )

    @classmethod
    def without_redirecting(cls) -> PendingRequest:
        """Create a builder that does not follow redirects.

        Resolution follows the active application's container.
        """
        return cls.pending_request().without_redirecting()

    @classmethod
    def get(
        cls,
        url: str,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a blocking GET outside async application tasks.

        Resolution follows the active application's container.
        """
        return cls.pending_request().get(url, params=params)

    @classmethod
    async def get_async(
        cls,
        url: str,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a GET through the active asynchronous runtime.

        Resolution follows the active application's container.
        """
        return await cls.pending_request().get_async(url, params=params)

    @classmethod
    def post(
        cls,
        url: str,
        data: RequestPayload = None,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a blocking POST outside async application tasks.

        Resolution follows the active application's container.
        """
        return cls.pending_request().post(url, data, params=params)

    @classmethod
    async def post_async(
        cls,
        url: str,
        data: RequestPayload = None,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a POST through the active asynchronous runtime.

        Resolution follows the active application's container.
        """
        return await cls.pending_request().post_async(url, data, params=params)

    @classmethod
    def put(
        cls,
        url: str,
        data: RequestPayload = None,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a blocking PUT outside async application tasks.

        Resolution follows the active application's container.
        """
        return cls.pending_request().put(url, data, params=params)

    @classmethod
    async def put_async(
        cls,
        url: str,
        data: RequestPayload = None,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a PUT through the active asynchronous runtime.

        Resolution follows the active application's container.
        """
        return await cls.pending_request().put_async(url, data, params=params)

    @classmethod
    def patch(
        cls,
        url: str,
        data: RequestPayload = None,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a blocking PATCH outside async application tasks.

        Resolution follows the active application's container.
        """
        return cls.pending_request().patch(url, data, params=params)

    @classmethod
    async def patch_async(
        cls,
        url: str,
        data: RequestPayload = None,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a PATCH through the active asynchronous runtime.

        Resolution follows the active application's container.
        """
        return await cls.pending_request().patch_async(
            url,
            data,
            params=params,
        )

    @classmethod
    def delete(
        cls,
        url: str,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a blocking DELETE outside async application tasks.

        Resolution follows the active application's container.
        """
        return cls.pending_request().delete(url, params=params)

    @classmethod
    async def delete_async(
        cls,
        url: str,
        *,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a DELETE through the active asynchronous runtime.

        Resolution follows the active application's container.
        """
        return await cls.pending_request().delete_async(url, params=params)

    @classmethod
    def head(cls, url: str) -> HttpClientResponse:
        """Perform a blocking HEAD outside async application tasks.

        Resolution follows the active application's container.
        """
        return cls.pending_request().head(url)

    @classmethod
    async def head_async(cls, url: str) -> HttpClientResponse:
        """Perform a HEAD through the active asynchronous runtime.

        Resolution follows the active application's container.
        """
        return await cls.pending_request().head_async(url)

    @classmethod
    def options(cls, url: str) -> HttpClientResponse:
        """Perform a blocking OPTIONS outside async application tasks.

        Resolution follows the active application's container.
        """
        return cls.pending_request().options(url)

    @classmethod
    async def options_async(cls, url: str) -> HttpClientResponse:
        """Perform OPTIONS through the active asynchronous runtime.

        Resolution follows the active application's container.
        """
        return await cls.pending_request().options_async(url)

    @classmethod
    def stream(
        cls,
        method: str,
        url: str,
        *,
        params: QueryParameters | None = None,
    ) -> AbstractContextManager[HttpClientResponse]:
        """Open a synchronous response stream with explicit cleanup.

        Resolution follows the active application's container.
        """
        return cls.pending_request().stream(method, url, params=params)

    @classmethod
    def stream_async(
        cls,
        method: str,
        url: str,
        *,
        params: QueryParameters | None = None,
    ) -> AbstractAsyncContextManager[HttpClientResponse]:
        """Open an asynchronous response stream with explicit cleanup.

        Resolution follows the active application's container.
        """
        return cls.pending_request().stream_async(method, url, params=params)

    @classmethod
    def request(
        cls,
        method: str,
        url: str,
        *,
        data: RequestPayload = None,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a generic blocking HTTP request.

        Resolution follows the active application's container.
        """
        return cls.pending_request().request(
            method,
            url,
            data=data,
            params=params,
        )

    @classmethod
    async def request_async(
        cls,
        method: str,
        url: str,
        *,
        data: RequestPayload = None,
        params: QueryParameters | None = None,
    ) -> HttpClientResponse:
        """Perform a generic asynchronous HTTP request.

        Resolution follows the active application's container.
        """
        return await cls.pending_request().request_async(
            method,
            url,
            data=data,
            params=params,
        )


__all__ = ["Http"]
