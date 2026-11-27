"""Adapt supported ASGI test clients to the native Testing lifecycle.

The adapter delegates protocol and client behavior to installed dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx2
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from fastapi import FastAPI

_ASYNC_BASE_URL = "http://testserver"

SyncTestClient = TestClient
AsyncTestClient = httpx2.AsyncClient


def create_sync_client(application: FastAPI) -> SyncTestClient:
    """Create the supported synchronous client for a native ASGI app.

    Args:
        application: Titanspan ASGI host composed by Foundation.

    Returns:
        Starlette's in-process client with lifespan management enabled.
    """
    return TestClient(application)


def create_async_client(application: FastAPI) -> AsyncTestClient:
    """Create the supported asynchronous client for a native ASGI app.

    Args:
        application: Titanspan ASGI host composed by Foundation.

    Returns:
        HTTPX2 client using its in-process ASGI transport.
    """
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=application),
        base_url=_ASYNC_BASE_URL,
    )


__all__ = [
    "AsyncTestClient",
    "SyncTestClient",
    "create_async_client",
    "create_sync_client",
]
