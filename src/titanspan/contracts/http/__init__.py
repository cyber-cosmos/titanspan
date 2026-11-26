"""Expose shared HTTP service and value contracts.

Callers rely on native contracts, not concrete backend types.
"""

from titanspan.contracts.http.client import (
    HttpClient,
    HttpClientResponse,
    OutgoingRequest,
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

__all__ = [
    "HttpClient",
    "HttpClientResponse",
    "HttpMiddleware",
    "HttpRequest",
    "HttpResponse",
    "JsonValue",
    "OutgoingRequest",
    "QueryParameterValue",
    "QueryParameters",
    "RequestHandler",
    "RequestPayload",
    "ResponseFactory",
    "ServerSentEvent",
]
