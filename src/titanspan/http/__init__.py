"""Expose Titanspan's native incoming and outgoing HTTP capabilities.

The operation follows native HTTP contracts and explicit ownership.
"""

from titanspan.contracts.http import (
    HttpClient,
    HttpClientResponse,
    HttpMiddleware,
    HttpRequest,
    HttpResponse,
    JsonValue,
    MultipartFile,
    QueryParameters,
    RequestPayload,
    ResponseFactory,
    ServerSentEvent,
)
from titanspan.http.client import (
    ClientResponse,
    HttpPoolInput,
    HttpPoolOutput,
    HttpPoolRequest,
    HttpPoolValue,
    HttpRequestKey,
    HttpRequestPool,
    PendingRequest,
)
from titanspan.http.configuration import (
    ClientConfiguration,
    HttpConfiguration,
    ServerConfiguration,
)
from titanspan.http.exceptions import (
    HttpClientError,
    HttpConfigurationError,
    HttpContextError,
    HttpError,
    HttpFakeError,
    HttpStatusError,
    HttpTimeoutError,
    HttpTransportError,
    RequestBodyConsumedError,
    RequestBodyTooLargeError,
    RequestError,
    RequestInputError,
    SynchronousHttpInAsyncContextError,
    UnexpectedHttpRequestError,
)
from titanspan.http.helpers import request, response
from titanspan.http.middleware import (
    CorsMiddleware,
    HttpsRedirectMiddleware,
    TrustedHostMiddleware,
)
from titanspan.http.request import Request
from titanspan.http.response import (
    CookieOptions,
    FileResponse,
    HtmlResponse,
    JsonResponse,
    RedirectResponse,
    Response,
    StreamResponse,
    validate_header,
)
from titanspan.http.response_factory import NativeResponseFactory
from titanspan.http.service_provider import HttpServiceProvider
from titanspan.http.testing import (
    HttpFake,
    HttpFakeResponse,
    HttpFakeResponses,
    HttpRequestMatcher,
    HttpRequestPattern,
    SentRequest,
)
from titanspan.http.uploaded_file import UploadedFile

__all__ = [
    "ClientConfiguration",
    "ClientResponse",
    "CookieOptions",
    "CorsMiddleware",
    "FileResponse",
    "HtmlResponse",
    "HttpClient",
    "HttpClientError",
    "HttpClientResponse",
    "HttpConfiguration",
    "HttpConfigurationError",
    "HttpContextError",
    "HttpError",
    "HttpFake",
    "HttpFakeError",
    "HttpFakeResponse",
    "HttpFakeResponses",
    "HttpMiddleware",
    "HttpPoolInput",
    "HttpPoolOutput",
    "HttpPoolRequest",
    "HttpPoolValue",
    "HttpRequest",
    "HttpRequestKey",
    "HttpRequestMatcher",
    "HttpRequestPattern",
    "HttpRequestPool",
    "HttpResponse",
    "HttpServiceProvider",
    "HttpStatusError",
    "HttpTimeoutError",
    "HttpTransportError",
    "HttpsRedirectMiddleware",
    "JsonResponse",
    "JsonValue",
    "MultipartFile",
    "NativeResponseFactory",
    "PendingRequest",
    "QueryParameters",
    "RedirectResponse",
    "Request",
    "RequestBodyConsumedError",
    "RequestBodyTooLargeError",
    "RequestError",
    "RequestInputError",
    "RequestPayload",
    "Response",
    "ResponseFactory",
    "SentRequest",
    "ServerConfiguration",
    "ServerSentEvent",
    "StreamResponse",
    "SynchronousHttpInAsyncContextError",
    "TrustedHostMiddleware",
    "UnexpectedHttpRequestError",
    "UploadedFile",
    "request",
    "response",
    "validate_header",
]
