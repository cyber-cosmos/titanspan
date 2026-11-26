"""Expose Titanspan's public outgoing client types.

The operation follows native HTTP contracts and explicit ownership.
"""

from titanspan.http.client.pending_request import PendingRequest
from titanspan.http.client.pool import (
    HttpPoolInput,
    HttpPoolOutput,
    HttpPoolRequest,
    HttpPoolValue,
    HttpRequestKey,
    HttpRequestPool,
)
from titanspan.http.client.response import ClientResponse

__all__ = [
    "ClientResponse",
    "HttpPoolInput",
    "HttpPoolOutput",
    "HttpPoolRequest",
    "HttpPoolValue",
    "HttpRequestKey",
    "HttpRequestPool",
    "PendingRequest",
]
