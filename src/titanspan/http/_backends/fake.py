"""Adapt native fake sessions to supported HTTPX2 mock transports.

The fake session owns matching and records; HTTPX2 owns request preparation.
"""

from __future__ import annotations

import json
from types import MappingProxyType

import httpx2

from titanspan.http.testing import HttpFake, HttpFakeResponse, SentRequest


def sync_fake_transport(fake: HttpFake) -> httpx2.MockTransport:
    """Create an HTTPX2 transport for one synchronous fake request.

    Args:
        fake: Context-local session that records and resolves the call.

    Returns:
        A fresh HTTPX2 mock transport with no network fallback.
    """

    def handle(request: httpx2.Request) -> httpx2.Response:
        """Capture a fully encoded request and return its fake response.

        HTTPX2 owns request preparation before it calls this handler.
        """
        sent = SentRequest(
            method=request.method,
            url=str(request.url),
            headers=MappingProxyType(
                {name.lower(): value for name, value in request.headers.items()}
            ),
            body=request.read(),
        )
        return _response(request, fake.response_for(sent))

    return httpx2.MockTransport(handle)


def async_fake_transport(fake: HttpFake) -> httpx2.MockTransport:
    """Create an HTTPX2 transport for one asynchronous fake request.

    Args:
        fake: Context-local session that records and resolves the call.

    Returns:
        A fresh HTTPX2 mock transport with no network fallback.
    """

    async def handle(request: httpx2.Request) -> httpx2.Response:
        """Capture an async request body before resolving its response.

        HTTPX2 owns request preparation before it calls this handler.
        """
        sent = SentRequest(
            method=request.method,
            url=str(request.url),
            headers=MappingProxyType(
                {name.lower(): value for name, value in request.headers.items()}
            ),
            body=await request.aread(),
        )
        return _response(request, fake.response_for(sent))

    return httpx2.MockTransport(handle)


def _response(
    request: httpx2.Request,
    fake: HttpFakeResponse,
) -> httpx2.Response:
    """Build one real HTTPX2 response from native fake data.

    Args:
        request: Prepared request supplied by the HTTPX2 transport.
        fake: Native response selected by the active fake context.

    Returns:
        A buffered response that follows ordinary HTTPX2 decoding behavior.
    """
    headers = dict(fake.headers)
    content = fake.content
    if isinstance(content, bytes):
        body = content
    elif isinstance(content, str):
        body = content.encode("utf-8")
        headers.setdefault("Content-Type", "text/plain; charset=utf-8")
    elif content is None:
        body = b""
    else:
        body = json.dumps(
            content,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    return httpx2.Response(
        fake.status,
        headers=headers,
        content=body,
        request=request,
    )


__all__ = ["async_fake_transport", "sync_fake_transport"]
