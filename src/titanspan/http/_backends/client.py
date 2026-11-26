"""Adapt the locked HTTPX2 clients behind native HTTP contracts.

HTTPX2 owns pools, TLS, connection acquisition, streaming and protocol
handling. This adapter translates its response and failure types at the
private boundary.
"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from dataclasses import replace
from http.cookiejar import Cookie, CookieJar
from typing import TYPE_CHECKING, TypedDict, cast

import anyio
import httpx2

from titanspan.contracts.http import (
    HttpClient,
    HttpClientResponse,
    JsonValue,
    MultipartFile,
    OutgoingRequest,
    QueryParameters,
)
from titanspan.http._backends.fake import (
    async_fake_transport,
    sync_fake_transport,
)
from titanspan.http._urls import (
    validate_base_url,
    validate_outbound_url,
)
from titanspan.http.client.response import ClientResponse
from titanspan.http.exceptions import (
    HttpTimeoutError,
    HttpTransportError,
    SynchronousHttpInAsyncContextError,
)
from titanspan.http.testing import HttpFake, current_http_fake

if TYPE_CHECKING:
    from collections.abc import (
        AsyncGenerator,
        AsyncIterator,
        Generator,
        Iterator,
        Mapping,
        Sequence,
    )

    from titanspan.http.configuration import ClientConfiguration

_OUTGOING_TIMEOUT_MESSAGE = "The outgoing HTTP request timed out."
_OUTGOING_TRANSPORT_MESSAGE = (
    "The outgoing HTTP request failed in the transport."
)
_CLIENT_CLOSED_MESSAGE = "The application HTTP client is closed."
_SCALAR_VALUES_MESSAGE = (
    "HTTP query and form values must be scalar or scalar lists."
)
_SYNC_ASYNC_CONTEXT_MESSAGE = (
    "Use the explicit async HTTP method inside an asynchronous task."
)

_INVALID_FORM_SEQUENCE_ERROR = (
    "HTTP form values must contain only scalar values."
)
_INVALID_COOKIE_ERROR = "HTTP cookie names and values must be safe tokens."
_COOKIE_NAME_CHARS = frozenset(
    "!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)
_COOKIE_VALUE_CHARS = frozenset(
    "!#$%&'()*+-./:<=>?@[]^_`{|}~0123456789abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


class _RequestOptions(TypedDict, total=False):
    """Type the public client keyword arguments assembled by the adapter.

    Optional fields let each request omit backend defaults instead of
    accidentally disabling them with an explicit ``None`` value.
    """

    headers: Mapping[str, str]
    params: dict[str, str | Sequence[str]]
    json: JsonValue | None
    content: str | bytes
    data: dict[str, str | Sequence[str]]
    files: Sequence[tuple[str, tuple[str, bytes, str]]]
    timeout: float
    follow_redirects: bool


class _ClientOptions(TypedDict):
    """Type values shared by the sync and async pooled clients.

    Transport details stay behind this private adapter.
    """

    timeout: httpx2.Timeout
    limits: httpx2.Limits
    verify: bool
    follow_redirects: bool
    base_url: str
    http2: bool


class _RequestIsolatedCookieJar(CookieJar):
    """Prevent the pooled client from retaining response cookies.

    Applications pass cookies explicitly on each request. This keeps the
    shared connection pool from carrying upstream session state between
    independent calls.
    """

    def set_cookie(self, cookie: Cookie) -> None:
        """Discard one cookie extracted from an upstream response.

        Args:
            cookie: Cookie offered by the HTTP transport.

        Side Effects:
            Leaves this jar empty so later requests cannot inherit state.
        """
        _ = cookie


class HttpxClientAdapter(HttpClient):
    """Own one sync and one async pooled transport client per application.

    Transport details stay behind this private adapter.
    """

    def __init__(self, configuration: ClientConfiguration) -> None:
        """Construct distinct sync and async pools from validated settings.

        Args:
            configuration: Application-level connection and timeout policy.

        Notes:
            Sync and async client resources are distinct. They share defaults,
            but their pools are never used across execution modes.
        """
        limits = httpx2.Limits(
            max_connections=configuration.max_connections,
            max_keepalive_connections=(configuration.max_keepalive_connections),
            keepalive_expiry=configuration.keepalive_expiry,
        )
        timeout = httpx2.Timeout(
            configuration.timeout,
            connect=configuration.connect_timeout,
        )
        base_url = (
            validate_base_url(configuration.base_url)
            if configuration.base_url
            else ""
        )
        common: _ClientOptions = {
            "timeout": timeout,
            "limits": limits,
            "verify": configuration.verify_tls,
            "follow_redirects": configuration.follow_redirects,
            "base_url": base_url,
            "http2": configuration.http2,
        }
        self._client_options = common
        self._sync_client = httpx2.Client(
            **common,
            cookies=_RequestIsolatedCookieJar(),
        )
        try:
            self._async_client = httpx2.AsyncClient(
                **common,
                cookies=_RequestIsolatedCookieJar(),
            )
        except BaseException:
            self._sync_client.close()
            raise
        self._closed = False

    def request(
        self,
        request: OutgoingRequest,
    ) -> HttpClientResponse:
        """Perform one blocking request outside any async runtime.

        Args:
            request: Immutable request data prepared by the native builder.

        Returns:
            A native response wrapper owning the transport response.

        Raises:
            SynchronousHttpInAsyncContextError: If called from an async task.
            HttpTimeoutError: If transport timed out.
            HttpTransportError: If a transport or protocol error occurred.
        """
        _require_sync_context()
        self._ensure_open()
        request = _validate_request_destination(
            request,
            self._client_options["base_url"],
        )
        try:
            fake = current_http_fake()
            if fake is None:
                response = self._sync_client.request(
                    request.method,
                    request.url,
                    **_request_options(request),
                )
            else:
                with self._sync_fake_client(fake) as client:
                    response = client.request(
                        request.method,
                        request.url,
                        **_request_options(request),
                    )
        except httpx2.TimeoutException as error:
            raise HttpTimeoutError(_OUTGOING_TIMEOUT_MESSAGE) from error
        except httpx2.HTTPError as error:
            raise HttpTransportError(_OUTGOING_TRANSPORT_MESSAGE) from error

        return ClientResponse(
            _HttpxResponseAccess(response),
            asynchronous=False,
        )

    async def request_async(
        self,
        request: OutgoingRequest,
    ) -> HttpClientResponse:
        """Perform one request using the active async runtime.

        Args:
            request: Immutable request data prepared by the native builder.

        Returns:
            A native response wrapper owning the transport response.

        Raises:
            HttpTimeoutError: If transport timed out.
            HttpTransportError: If a transport or protocol error occurred.
        """
        self._ensure_open()
        request = _validate_request_destination(
            request,
            self._client_options["base_url"],
        )
        try:
            fake = current_http_fake()
            if fake is None:
                response = await self._async_client.request(
                    request.method,
                    request.url,
                    **_request_options(request),
                )
            else:
                async with self._async_fake_client(fake) as client:
                    response = await client.request(
                        request.method,
                        request.url,
                        **_request_options(request),
                    )
        except httpx2.TimeoutException as error:
            raise HttpTimeoutError(_OUTGOING_TIMEOUT_MESSAGE) from error
        except httpx2.HTTPError as error:
            raise HttpTransportError(_OUTGOING_TRANSPORT_MESSAGE) from error

        return ClientResponse(
            _HttpxResponseAccess(response),
            asynchronous=True,
        )

    @contextmanager
    def stream(
        self,
        request: OutgoingRequest,
    ) -> Generator[HttpClientResponse, None, None]:
        """Stream a blocking response while owning its connection lifetime.

        Args:
            request: Immutable request data prepared by the native builder.

        Yields:
            A response whose byte iterator is consumed within this context.
        """
        _require_sync_context()
        self._ensure_open()
        request = _validate_request_destination(
            request,
            self._client_options["base_url"],
        )
        try:
            fake = current_http_fake()
            if fake is None:
                with self._sync_client.stream(
                    request.method,
                    request.url,
                    **_request_options(request),
                ) as response:
                    yield ClientResponse(
                        _HttpxResponseAccess(response),
                        asynchronous=False,
                    )
            else:
                with (
                    self._sync_fake_client(fake) as client,
                    client.stream(
                        request.method,
                        request.url,
                        **_request_options(request),
                    ) as response,
                ):
                    yield ClientResponse(
                        _HttpxResponseAccess(response),
                        asynchronous=False,
                    )
        except httpx2.TimeoutException as error:
            raise HttpTimeoutError(_OUTGOING_TIMEOUT_MESSAGE) from error
        except httpx2.HTTPError as error:
            raise HttpTransportError(_OUTGOING_TRANSPORT_MESSAGE) from error

    @asynccontextmanager
    async def stream_async(
        self,
        request: OutgoingRequest,
    ) -> AsyncGenerator[HttpClientResponse, None]:
        """Stream an async response with deterministic connection release.

        Args:
            request: Immutable request data prepared by the native builder.

        Yields:
            A response whose async byte iterator is bounded by backpressure.
        """
        self._ensure_open()
        request = _validate_request_destination(
            request,
            self._client_options["base_url"],
        )
        try:
            fake = current_http_fake()
            if fake is None:
                async with self._async_client.stream(
                    request.method,
                    request.url,
                    **_request_options(request),
                ) as response:
                    yield ClientResponse(
                        _HttpxResponseAccess(response),
                        asynchronous=True,
                    )
            else:
                async with (
                    self._async_fake_client(fake) as client,
                    client.stream(
                        request.method,
                        request.url,
                        **_request_options(request),
                    ) as response,
                ):
                    yield ClientResponse(
                        _HttpxResponseAccess(response),
                        asynchronous=True,
                    )
        except httpx2.TimeoutException as error:
            raise HttpTimeoutError(_OUTGOING_TIMEOUT_MESSAGE) from error
        except httpx2.HTTPError as error:
            raise HttpTransportError(_OUTGOING_TRANSPORT_MESSAGE) from error

    async def aclose(self) -> None:
        """Close both distinct transport pools exactly once.

        AnyIO's cancellation shield ensures the async connection pool is
        finalized before application shutdown propagates cancellation.
        """
        if self._closed:
            return
        self._closed = True
        try:
            with anyio.CancelScope(shield=True):
                await self._async_client.aclose()
        finally:
            self._sync_client.close()

    def _ensure_open(self) -> None:
        """Reject new operations after application shutdown begins.

        Raises:
            RuntimeError: If the owning application already closed this pool.
        """
        if self._closed:
            raise RuntimeError(_CLIENT_CLOSED_MESSAGE)

    def _sync_fake_client(self, fake: HttpFake) -> httpx2.Client:
        """Create a short-lived HTTPX2 client over the active fake transport.

        Args:
            fake: Context-local fake session selected for this request.

        Returns:
            A client that cannot reach the real network.
        """
        return httpx2.Client(
            **self._client_options,
            cookies=_RequestIsolatedCookieJar(),
            transport=sync_fake_transport(fake),
        )

    def _async_fake_client(self, fake: HttpFake) -> httpx2.AsyncClient:
        """Create a short-lived async client over the fake transport.

        Args:
            fake: Context-local fake session selected for this request.

        Returns:
            An async client that cannot reach the real network.
        """
        return httpx2.AsyncClient(
            **self._client_options,
            cookies=_RequestIsolatedCookieJar(),
            transport=async_fake_transport(fake),
        )

    _sync_client: httpx2.Client
    _async_client: httpx2.AsyncClient
    _client_options: _ClientOptions
    _closed: bool


def _validate_request_destination(
    request: OutgoingRequest,
    base_url: str,
) -> OutgoingRequest:
    """Check one outbound URL before transport request resolution.

    Args:
        request: Transport-neutral request data.
        base_url: Optional validated HTTPX2 base URL.

    Returns:
        A copy with its absolute or base-resolvable URL checked.
    """
    return replace(
        request,
        url=validate_outbound_url(request.url, base_url=base_url),
    )


def _request_options(
    request: OutgoingRequest,
) -> _RequestOptions:
    """Translate native request options to the backend's public call kwargs.

    Args:
        request: Immutable native request value.

    Returns:
        Only supported public keyword arguments for the backend request API.
    """
    options: _RequestOptions = {}
    headers = _request_headers(request)
    if headers:
        options["headers"] = headers
    if request.params is not None:
        options["params"] = _query_values(request.params)
    options.update(_request_body_options(request))
    if request.timeout is not None:
        options["timeout"] = request.timeout
    if request.follow_redirects is not None:
        options["follow_redirects"] = request.follow_redirects
    return options


def _request_headers(request: OutgoingRequest) -> dict[str, str]:
    """Merge explicit request cookies into an isolated header snapshot.

    Args:
        request: Native request value containing headers and cookies.

    Returns:
        Fresh request header mapping.
    """
    headers = dict(request.headers)
    if request.cookies:
        cookie = _cookie_header(request.cookies)
        existing = next(
            (name for name in headers if name.lower() == "cookie"), None
        )
        if existing is None:
            headers["Cookie"] = cookie
        else:
            headers[existing] = f"{headers[existing]}; {cookie}"
    return headers


def _request_body_options(request: OutgoingRequest) -> _RequestOptions:
    """Translate the selected body and multipart values for HTTPX2.

    Args:
        request: Native request value containing one configured body.

    Returns:
        Supported public HTTPX2 body keyword arguments.
    """
    options: _RequestOptions = {}
    if request.json_enabled:
        options["json"] = request.json_body
    if request.data is not None:
        if isinstance(request.data, (str, bytes)):
            options["content"] = request.data
        else:
            options["data"] = _form_values(request.data)
    if request.files:
        options["files"] = _multipart_files(request.files)
    return options


def _cookie_header(cookies: Mapping[str, str]) -> str:
    """Encode request-local cookies without mutating the pooled client.

    Args:
        cookies: Cookie name and value pairs from one immutable request.

    Returns:
        One RFC-compatible Cookie header value.

    Raises:
        ValueError: If a cookie name or value contains unsafe characters.
    """
    pairs: list[str] = []
    for name, value in cookies.items():
        if not name or any(char not in _COOKIE_NAME_CHARS for char in name):
            raise ValueError(_INVALID_COOKIE_ERROR)
        if any(char not in _COOKIE_VALUE_CHARS for char in value):
            raise ValueError(_INVALID_COOKIE_ERROR)
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def _query_values(
    params: QueryParameters,
) -> dict[str, str | Sequence[str]]:
    """Normalize query values to scalar strings accepted by the transport.

    Args:
        params: Native query mapping.

    Returns:
        String query values preserving supported repeated values.
    """
    converted: dict[str, str | Sequence[str]] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            converted[key] = tuple(
                _scalar_text(item) for item in cast("Sequence[object]", value)
            )
        else:
            converted[key] = _scalar_text(value)
    return converted


def _form_values(data: Mapping[str, object]) -> dict[str, str | Sequence[str]]:
    """Normalize form fields without serializing arbitrary application objects.

    Args:
        data: Form field mapping supplied by application code.

    Returns:
        Text values suitable for standard URL-encoded form transmission.

    Raises:
        TypeError: If any field is not a supported scalar or sequence.
    """
    converted: dict[str, str | Sequence[str]] = {}
    for key, value in data.items():
        if value is None:
            converted[key] = ""
        elif isinstance(value, (list, tuple)):
            converted[key] = _form_sequence(cast("Sequence[object]", value))
        else:
            converted[key] = _scalar_text(value)
    return converted


def _scalar_text(value: object) -> str:
    """Convert one supported scalar to its documented wire representation.

    Args:
        value: String, number, or boolean query/form value.

    Returns:
        Lower-case boolean text or the ordinary string representation.
    """
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) in {str, int, float}:
        return str(value)
    raise TypeError(_SCALAR_VALUES_MESSAGE)


def _form_sequence(value: Sequence[object]) -> tuple[str, ...]:
    """Validate and normalize one list or tuple of form scalar values.

    Args:
        value: Candidate form field collection.

    Returns:
        Normalized values preserving their input order.

    Raises:
        TypeError: If any item is not a string, number, or boolean.
    """
    normalized: list[str] = []
    for item in value:
        if type(item) not in {str, int, float, bool}:
            raise TypeError(_INVALID_FORM_SEQUENCE_ERROR)
        normalized.append(_scalar_text(item))
    return tuple(normalized)


def _multipart_files(
    values: Sequence[tuple[str, MultipartFile]],
) -> list[tuple[str, tuple[str, bytes, str]]]:
    """Translate replayable native attachments to HTTPX2 multipart values.

    Args:
        values: Ordered field names and immutable byte attachments.

    Returns:
        HTTPX2's supported ordered file tuple representation.
    """
    return [
        (name, (file.filename, file.content, file.content_type))
        for name, file in values
    ]


def _require_sync_context() -> None:
    """Reject blocking client calls from an active AnyIO runtime.

    Raises:
        SynchronousHttpInAsyncContextError: If an async task is active.
    """
    try:
        anyio.get_current_task()
    except anyio.NoEventLoopError:
        return
    raise SynchronousHttpInAsyncContextError(_SYNC_ASYNC_CONTEXT_MESSAGE)


class _HttpxResponseAccess:
    """Implement native response operations over one HTTPX2 response.

    Transport details stay behind this private adapter.
    """

    def __init__(self, response: httpx2.Response) -> None:
        """Retain the transport response behind the private adapter.

        Args:
            response: HTTPX2 response whose body or stream is caller-owned.
        """
        self._response = response

    @property
    def status_code(self) -> int:
        """Return the backend status value.

        Transport details stay behind this private adapter.
        """
        return self._response.status_code

    @property
    def headers(self) -> Mapping[str, str]:
        """Return response headers copied into ordinary string values.

        Transport details stay behind this private adapter.
        """
        return dict(self._response.headers.items())

    @property
    def cookies(self) -> Mapping[str, str]:
        """Return cookies set by this response without sharing a jar.

        Transport details stay behind this private adapter.
        """
        return dict(self._response.cookies.items())

    def body(self) -> bytes:
        """Return content already buffered by HTTPX2.

        Transport details stay behind this private adapter.
        """
        return self._response.content

    def text(self) -> str:
        """Decode buffered content using the backend's charset handling.

        Transport details stay behind this private adapter.
        """
        return self._response.text

    def json(self) -> object:
        """Decode buffered JSON through the backend's supported decoder.

        Transport details stay behind this private adapter.
        """
        return self._response.json()

    def iter_bytes(self) -> Iterator[bytes]:
        """Return a synchronous byte iterator from the backend response.

        Transport details stay behind this private adapter.
        """
        return self._response.iter_bytes()

    def iter_bytes_async(self) -> AsyncIterator[bytes]:
        """Return an async byte iterator from the backend response.

        Transport details stay behind this private adapter.
        """
        return self._response.aiter_bytes()

    def close(self) -> None:
        """Release a response opened through the synchronous pool.

        Transport details stay behind this private adapter.
        """
        self._response.close()

    async def aclose(self) -> None:
        """Release a response through the selected transport mode.

        Transport details stay behind this private adapter.
        """
        await self._response.aclose()

    _response: httpx2.Response


__all__ = [
    "HttpxClientAdapter",
]
