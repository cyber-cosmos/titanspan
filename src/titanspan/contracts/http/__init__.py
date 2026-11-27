"""Expose shared HTTP service and value contracts.

Callers rely on native contracts, not concrete backend types.
"""

from titanspan.contracts.http.client import (
    HttpClient,
    HttpClientResponse,
    MultipartFile,
    OutgoingRequest,
)
from titanspan.contracts.http.cookies import (
    DEFAULT_COOKIE_OPTIONS,
    CookieOptions,
)
from titanspan.contracts.http.events import ServerSentEvent
from titanspan.contracts.http.middleware import (
    HttpMiddleware,
    RequestHandler,
)
from titanspan.contracts.http.request import HttpRequest
from titanspan.contracts.http.response import (
    HttpResponse,
    ResponseFactory,
)
from titanspan.contracts.http.types import (
    JsonValue,
    QueryParameters,
    QueryParameterValue,
    RequestPayload,
)
from titanspan.contracts.http.uploaded_file import HttpUploadedFile

__all__ = [
    "DEFAULT_COOKIE_OPTIONS",
    "CookieOptions",
    "HttpClient",
    "HttpClientResponse",
    "HttpMiddleware",
    "HttpRequest",
    "HttpResponse",
    "HttpUploadedFile",
    "JsonValue",
    "MultipartFile",
    "OutgoingRequest",
    "QueryParameterValue",
    "QueryParameters",
    "RequestHandler",
    "RequestPayload",
    "ResponseFactory",
    "ServerSentEvent",
]
