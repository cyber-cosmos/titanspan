"""Provide context-local outgoing HTTP fakes and request assertions.

HTTPX2 mock transports adapt these native records at the private backend edge.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from threading import Lock
from types import MappingProxyType
from typing import TYPE_CHECKING

from pydantic import TypeAdapter, ValidationError

from titanspan.contracts.http import JsonValue
from titanspan.http.exceptions import (
    HttpFakeError,
    UnexpectedHttpRequestError,
)

if TYPE_CHECKING:
    from types import TracebackType
    from typing import Self

_NO_FAKE_ERROR = "HTTP fake operations require an active fake context."
_INVALID_FAKE_STATUS_ERROR = "Fake HTTP statuses must be between 100 and 599."
_EMPTY_FAKE_SEQUENCE_ERROR = "Fake response sequences cannot be empty."
_NO_MATCHING_FAKE_ERROR = "No fake response matched the outgoing request."
_EXHAUSTED_FAKE_ERROR = "The matched fake response sequence is exhausted."
_ASSERTION_SENT_ERROR = "The expected HTTP request was not sent."
_ASSERTION_NOT_SENT_ERROR = "An HTTP request matched the forbidden pattern."
_ASSERTION_COUNT_ERROR = "The HTTP request count did not match."
_INVALID_FAKE_RESPONSE_TYPE_ERROR = (
    "Fake values must be HttpFakeResponse objects."
)
_INVALID_FAKE_CONTENT_ERROR = "Fake JSON content must be a JSON value."
_NEGATIVE_REQUEST_COUNT_ERROR = "HTTP request counts cannot be negative."
_FAKE_REENTRY_ERROR = "An HTTP fake context cannot be re-entered."
_FAKE_NOT_ACTIVE_ERROR = "The HTTP fake context is not active."
_MIN_HTTP_STATUS = 100
_MAX_HTTP_STATUS = 599
_JSON_ADAPTER = TypeAdapter(JsonValue)
_FAKE_SEQUENCE_ADAPTER = TypeAdapter(tuple[object, ...])


def _empty_headers() -> Mapping[str, str]:
    """Return a fresh typed header mapping for fake response defaults.

    Each fake snapshots the caller's header values during construction.
    """
    return {}


@dataclass(frozen=True, slots=True)
class HttpFakeResponse:
    """Describe a deterministic outgoing HTTP response.

    A mapping, list, scalar, or string content value is JSON encoded only when
    it is not a string. Bytes remain unchanged, and ``None`` means no body.

    Attributes:
        content: JSON value, text, bytes, or no response body.
        status: HTTP status code returned to the client.
        headers: Optional response headers, including explicit cookies.
    """

    content: JsonValue | bytes | None = None
    status: int = 200
    headers: Mapping[str, str] = field(default_factory=_empty_headers)

    def __post_init__(self) -> None:
        """Snapshot headers and validate status before transport creation.

        Raises:
            ValueError: If the status is outside the HTTP response range.
        """
        if (
            type(self.status) is not int
            or not _MIN_HTTP_STATUS <= self.status <= _MAX_HTTP_STATUS
        ):
            raise ValueError(_INVALID_FAKE_STATUS_ERROR)
        if not isinstance(self.content, (bytes, str, type(None))):
            try:
                _JSON_ADAPTER.validate_python(self.content)
            except ValidationError as error:
                raise TypeError(_INVALID_FAKE_CONTENT_ERROR) from error
        headers: dict[str, str] = dict(self.headers)
        object.__setattr__(self, "headers", MappingProxyType(headers))


@dataclass(frozen=True, slots=True)
class SentRequest:
    """Expose one recorded request without leaking HTTPX2 objects.

    Attributes:
        method: Uppercase request method.
        url: Fully composed request URL.
        headers: Lower-case request headers.
        body: Complete request body captured by the fake transport.
    """

    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes

    def header(self, name: str, default: str | None = None) -> str | None:
        """Return one recorded header using case-insensitive lookup.

        Args:
            name: Header name to retrieve.
            default: Value returned when the name is absent.

        Returns:
            The matching header value or the supplied default.
        """
        return self.headers.get(name.lower(), default)


@dataclass(frozen=True, slots=True)
class HttpRequestPattern:
    """Match recorded requests by URL, method, headers, and optional body.

    Attributes:
        url: Case-sensitive glob matched against the complete URL.
        method: Optional method matched without case sensitivity.
        headers: Header values that must match exactly.
        body: Optional complete body value that must match exactly.
    """

    url: str = "*"
    method: str | None = None
    headers: Mapping[str, str] = field(default_factory=_empty_headers)
    body: bytes | None = None

    def __post_init__(self) -> None:
        """Snapshot header predicates for stable matching.

        Matching remains independent of later caller mapping changes.
        """
        headers: dict[str, str] = {
            name.lower(): value for name, value in self.headers.items()
        }
        object.__setattr__(self, "headers", MappingProxyType(headers))

    def matches(self, request: SentRequest) -> bool:
        """Check whether one recorded request satisfies this pattern.

        Args:
            request: Captured request from an active fake context.

        Returns:
            Whether every configured request predicate matches.
        """
        return (
            fnmatchcase(request.url, self.url)
            and (self.method is None or request.method == self.method.upper())
            and all(
                request.header(name) == value
                for name, value in self.headers.items()
            )
            and (self.body is None or request.body == self.body)
        )

    def __hash__(self) -> int:
        """Hash normalized immutable predicates for use as fake map keys.

        Header order does not change the equality or hash of a pattern.
        """
        return hash(
            (
                self.url,
                self.method,
                tuple(sorted(self.headers.items())),
                self.body,
            )
        )


type HttpRequestMatcher = (
    str | HttpRequestPattern | Callable[[SentRequest], bool]
)
type HttpFakeValue = HttpFakeResponse | Sequence[HttpFakeResponse]
type HttpFakeResponses = Mapping[
    str | HttpRequestPattern,
    HttpFakeValue,
]
type _ResponseSequence = tuple[HttpFakeResponse, ...]
type _ConfiguredFake = tuple[
    str | HttpRequestPattern,
    _ResponseSequence,
    bool,
]

_ACTIVE_FAKE: ContextVar[HttpFake | None] = ContextVar(
    "titanspan_http_fake",
    default=None,
)


class HttpFake:
    """Intercept requests in one sync or async execution context.

    An unmatched request raises instead of reaching the network. Nested fake
    contexts restore the outer context when they exit.
    """

    def __init__(self, responses: HttpFakeResponses) -> None:
        """Create a fake session and snapshot its response definitions.

        Args:
            responses: URL globs or request patterns mapped to responses.

        Raises:
            ValueError: If a response sequence is empty.
            TypeError: If a response definition is malformed.
        """
        patterns: list[_ConfiguredFake] = []
        for pattern, value in responses.items():
            sequence, repeated = _normalize_response_definition(value)
            patterns.append((pattern, sequence, repeated))
        self._patterns = tuple(patterns)
        self._uses = [0 for _ in patterns]
        self._requests: list[SentRequest] = []
        self._lock = Lock()
        self._token: Token[HttpFake | None] | None = None

    def __enter__(self) -> Self:
        """Bind this fake to the synchronous execution context.

        The context token records the fake that must be restored on exit.
        """
        self._bind()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Restore the previous fake even when the block raises.

        Exception details pass through the context manager unchanged.
        """
        _ = exc_type, exc, traceback
        self._restore()

    async def __aenter__(self) -> Self:
        """Bind this fake to the asynchronous execution context.

        Child operations inherit the selected context-local fake.
        """
        self._bind()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Restore the previous fake after asynchronous work completes.

        Cancellation and exceptions still restore the context token.
        """
        _ = exc_type, exc, traceback
        self._restore()

    @property
    def requests(self) -> tuple[SentRequest, ...]:
        """Return an immutable snapshot of matched and unmatched calls.

        The returned values do not expose HTTPX2 request objects.
        """
        with self._lock:
            return tuple(self._requests)

    def assert_sent(self, matcher: HttpRequestMatcher | None = None) -> None:
        """Assert that at least one recorded request matches a predicate.

        Args:
            matcher: URL glob, request pattern, or request predicate.

        Raises:
            AssertionError: If no request matches the selected predicate.
        """
        if not any(_matches(request, matcher) for request in self.requests):
            raise AssertionError(_ASSERTION_SENT_ERROR)

    def assert_not_sent(
        self,
        matcher: HttpRequestMatcher | None = None,
    ) -> None:
        """Assert that no recorded request matches a predicate.

        Args:
            matcher: URL glob, request pattern, or request predicate.

        Raises:
            AssertionError: If a request matches the selected predicate.
        """
        if any(_matches(request, matcher) for request in self.requests):
            raise AssertionError(_ASSERTION_NOT_SENT_ERROR)

    def assert_sent_count(
        self,
        count: int,
        matcher: HttpRequestMatcher | None = None,
    ) -> None:
        """Assert the exact number of calls that match a predicate.

        Args:
            count: Expected request count.
            matcher: Optional URL glob, request pattern, or predicate.

        Raises:
            AssertionError: If the matching count differs from ``count``.
            ValueError: If ``count`` is negative.
        """
        if count < 0:
            raise ValueError(_NEGATIVE_REQUEST_COUNT_ERROR)
        actual = sum(_matches(request, matcher) for request in self.requests)
        if actual != count:
            raise AssertionError(_ASSERTION_COUNT_ERROR)

    def _bind(self) -> None:
        """Set the active fake and retain its context-local reset token.

        Re-entering the same fake instance would make restoration ambiguous.
        """
        if self._token is not None:
            raise HttpFakeError(_FAKE_REENTRY_ERROR)
        self._token = _ACTIVE_FAKE.set(self)

    def _restore(self) -> None:
        """Restore the fake value that preceded this context.

        ContextVar tokens restore nested scopes in last-in-first-out order.
        """
        if self._token is None:
            raise HttpFakeError(_FAKE_NOT_ACTIVE_ERROR)
        _ACTIVE_FAKE.reset(self._token)
        self._token = None

    def response_for(self, request: SentRequest) -> HttpFakeResponse:
        """Record and resolve one transport request without exposing URLs.

        Args:
            request: Request captured by the HTTPX2 mock transport.

        Returns:
            The next response assigned to the first matching pattern.

        Raises:
            UnexpectedHttpRequestError: If no response pattern matches or its
                configured sequence has been exhausted.
        """
        with self._lock:
            self._requests.append(request)
            for index, (pattern, responses, repeat) in enumerate(
                self._patterns
            ):
                if not _matches(request, pattern):
                    continue
                response_index = self._uses[index]
                if response_index >= len(responses) and not repeat:
                    raise UnexpectedHttpRequestError(_EXHAUSTED_FAKE_ERROR)
                self._uses[index] += 1
                return responses[min(response_index, len(responses) - 1)]
        raise UnexpectedHttpRequestError(_NO_MATCHING_FAKE_ERROR)

    _patterns: tuple[_ConfiguredFake, ...]
    _uses: list[int]
    _requests: list[SentRequest]
    _lock: Lock
    _token: Token[HttpFake | None] | None


def current_http_fake() -> HttpFake | None:
    """Return the fake bound to this execution context, if any.

    The selected value does not cross unrelated context boundaries.
    """
    return _ACTIVE_FAKE.get()


def _normalize_response_definition(
    value: object,
) -> tuple[_ResponseSequence, bool]:
    """Validate one scalar or ordered fake response definition.

    Args:
        value: One response object or a sequence supplied by the caller.

    Returns:
        An immutable response sequence and whether a scalar repeats.

    Raises:
        TypeError: If the value is not a response or response sequence.
        ValueError: If the sequence is empty.
    """
    if isinstance(value, HttpFakeResponse):
        return (value,), True
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        raise TypeError(_INVALID_FAKE_RESPONSE_TYPE_ERROR)
    responses: list[HttpFakeResponse] = []
    values = _FAKE_SEQUENCE_ADAPTER.validate_python(value)
    for response in values:
        if not isinstance(response, HttpFakeResponse):
            raise TypeError(_INVALID_FAKE_RESPONSE_TYPE_ERROR)
        responses.append(response)
    if not responses:
        raise ValueError(_EMPTY_FAKE_SEQUENCE_ERROR)
    return tuple(responses), False


def require_http_fake() -> HttpFake:
    """Return the active fake or raise a safe testing-context error.

    Raises:
        HttpFakeError: If no fake context is active.
    """
    fake = current_http_fake()
    if fake is None:
        raise HttpFakeError(_NO_FAKE_ERROR)
    return fake


def _matches(
    request: SentRequest,
    matcher: HttpRequestMatcher | str | HttpRequestPattern | None,
) -> bool:
    """Match one request against a URL, structured pattern, or callback.

    Args:
        request: Recorded outgoing request.
        matcher: Predicate to evaluate, or ``None`` for any request.

    Returns:
        Whether the selected matcher accepts the request.
    """
    if matcher is None:
        return True
    if isinstance(matcher, str):
        return fnmatchcase(request.url, matcher)
    if isinstance(matcher, HttpRequestPattern):
        return matcher.matches(request)
    return matcher(request)


__all__ = [
    "HttpFake",
    "HttpFakeResponse",
    "HttpRequestMatcher",
    "HttpRequestPattern",
    "SentRequest",
    "current_http_fake",
    "require_http_fake",
]
