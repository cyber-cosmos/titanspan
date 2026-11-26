"""Verify real HTTPX2 error translation through its supported transports.

The integration uses real components and local test services.
"""

import asyncio
from http.cookiejar import CookieJar
from typing import TypedDict, Unpack

import httpx2
import pytest

from titanspan.contracts.http import OutgoingRequest
from titanspan.http._backends import client as client_backend
from titanspan.http._backends.client import HttpxClientAdapter
from titanspan.http.configuration import ClientConfiguration
from titanspan.http.exceptions import (
    HttpTimeoutError,
    HttpTransportError,
    SynchronousHttpInAsyncContextError,
)

pytestmark = pytest.mark.integration
_PRIVATE_TIMEOUT_DETAIL = "private timeout detail"
_PRIVATE_TRANSPORT_DETAIL = "private transport detail"


class _ClientOptions(TypedDict):
    """Describe constructor options forwarded to the real HTTPX2 client.

    The fixture replaces only transport creation and preserves client options.
    """

    timeout: httpx2.Timeout
    limits: httpx2.Limits
    verify: bool
    follow_redirects: bool
    base_url: str
    http2: bool
    cookies: CookieJar


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the real HTTPX2 pool with an explicit deterministic transport.

    Args:
        monkeypatch: Isolated replacement scope for client constructors.
    """
    original_sync = httpx2.Client
    original_async = httpx2.AsyncClient

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Raise selected backend errors without contacting a network.

        Args:
            request: Request constructed by the actual HTTPX2 client.

        Returns:
            A real HTTPX2 response for non-error paths.
        """
        if request.url.path == "/timeout":
            raise httpx2.ReadTimeout(_PRIVATE_TIMEOUT_DETAIL)
        if request.url.path == "/transport":
            raise httpx2.ConnectError(_PRIVATE_TRANSPORT_DETAIL)
        return httpx2.Response(200, request=request)

    def sync_client(**options: Unpack[_ClientOptions]) -> httpx2.Client:
        """Create the normal sync client with a controlled transport.

        The integration uses real components and local test services.
        """
        return original_sync(
            **options,
            transport=httpx2.MockTransport(handler),
        )

    def async_client(**options: Unpack[_ClientOptions]) -> httpx2.AsyncClient:
        """Create the normal async client with a controlled transport.

        The integration uses real components and local test services.
        """
        return original_async(
            **options,
            transport=httpx2.MockTransport(handler),
        )

    monkeypatch.setattr(client_backend.httpx2, "Client", sync_client)
    monkeypatch.setattr(
        client_backend.httpx2,
        "AsyncClient",
        async_client,
    )


def test_sync_transport_failures_use_sanitized_native_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translate backend timeout and connection exceptions at the boundary.

    The integration uses real components and local test services.
    """
    _install_transport(monkeypatch)
    client = HttpxClientAdapter(ClientConfiguration())
    try:
        with pytest.raises(HttpTimeoutError) as timeout:
            client.request(
                OutgoingRequest(
                    method="GET",
                    url="https://http.test/timeout",
                )
            )
        assert isinstance(timeout.value.__cause__, httpx2.ReadTimeout)
        assert "private timeout detail" not in str(timeout.value)

        with pytest.raises(HttpTransportError) as transport:
            client.request(
                OutgoingRequest(
                    method="GET",
                    url="https://http.test/transport",
                )
            )
        assert isinstance(transport.value.__cause__, httpx2.ConnectError)
        assert "private transport detail" not in str(transport.value)
    finally:
        asyncio.run(client.aclose())


@pytest.mark.anyio
async def test_async_transport_failures_and_client_lifecycle_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translate async failures and reject sync use inside an async task.

    The integration uses real components and local test services.
    """
    _install_transport(monkeypatch)
    client = HttpxClientAdapter(ClientConfiguration())
    try:
        with pytest.raises(SynchronousHttpInAsyncContextError):
            client.request(
                OutgoingRequest(
                    method="GET",
                    url="https://http.test/ok",
                )
            )

        with pytest.raises(HttpTimeoutError) as timeout:
            await client.request_async(
                OutgoingRequest(
                    method="GET",
                    url="https://http.test/timeout",
                )
            )
        assert isinstance(timeout.value.__cause__, httpx2.ReadTimeout)

        with pytest.raises(HttpTransportError) as transport:
            await client.request_async(
                OutgoingRequest(
                    method="GET",
                    url="https://http.test/transport",
                )
            )
        assert isinstance(transport.value.__cause__, httpx2.ConnectError)
    finally:
        await client.aclose()

    await client.aclose()
    with pytest.raises(RuntimeError, match="client is closed"):
        await client.request_async(
            OutgoingRequest(
                method="GET",
                url="https://http.test/closed",
            )
        )
