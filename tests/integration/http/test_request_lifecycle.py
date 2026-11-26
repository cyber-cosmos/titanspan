"""Verify native request services remain scoped through ASGI delivery.

The tests exercise FastAPI's in-process ASGI client, Titanspan's native
container, and the complete response send lifecycle.
"""

from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from titanspan.contracts.http import HttpRequest
from titanspan.foundation import Application
from titanspan.http import Request
from titanspan.http.helpers import request as active_request
from titanspan.http.helpers import response

pytestmark = pytest.mark.integration


def test_native_request_is_injected_and_resolved_from_one_scope() -> None:
    """Expose one request identity through DI and the native helper.

    Request instances must not become application singletons, and both
    access paths must see the same object for the active ASGI call.
    """
    application = Application(config={"app": {"name": "HTTP test"}})
    resolve_request = application.dependency(HttpRequest)

    async def endpoint(
        value: Annotated[HttpRequest, Depends(resolve_request)],
    ) -> dict[str, object]:
        """Return request identity and parsed query metadata.

        The integration uses real components and local test services.
        """
        native = active_request()
        return {
            "same": value is native,
            "concrete": application.make(Request) is native,
            "method": value.method,
            "query": value.query("page"),
        }

    application.asgi.add_api_route(
        "/items",
        endpoint,
        methods=["GET"],
    )

    with TestClient(application.asgi) as client:
        result = client.get("/items?page=3")

    assert result.status_code == HTTPStatus.OK
    assert result.json() == {
        "same": True,
        "concrete": True,
        "method": "GET",
        "query": "3",
    }


def test_request_scope_remains_active_until_stream_finishes() -> None:
    """Keep request context available after the endpoint returned.

    A streaming source runs during ASGI response transmission. Its request
    helper must still resolve the same request that the route received.
    """
    application = Application(config={"app": {"name": "HTTP stream"}})
    observed: list[str] = []
    resolve_request = application.dependency(HttpRequest)

    async def endpoint(
        value: Annotated[HttpRequest, Depends(resolve_request)],
    ) -> object:
        """Return a stream that reads request state after route execution.

        The integration uses real components and local test services.
        """
        request_id = value.headers.get("x-request-id", "missing")

        async def content() -> AsyncIterator[bytes]:
            """Read scoped state when Starlette sends the response body.

            The integration uses real components and local test services.
            """
            current = active_request()
            observed.append("same" if current is value else "different")
            observed.append(current.request_id)
            yield request_id.encode("utf-8")

        return response().stream(content(), content_type="text/plain")

    application.asgi.add_api_route(
        "/stream",
        endpoint,
        methods=["GET"],
    )

    with TestClient(application.asgi) as client:
        result = client.get(
            "/stream",
            headers={"x-request-id": "stream-123"},
        )

    assert result.status_code == HTTPStatus.OK
    assert result.text == "stream-123"
    assert observed == ["same", "stream-123"]


def test_oversized_request_body_returns_a_native_413_response() -> None:
    """Enforce configured body limits through the real ASGI middleware.

    The integration uses real components and local test services.
    """
    application = Application(
        config={
            "app": {"name": "body limit test"},
            "http": {"server": {"max_body_size": 4}},
        }
    )
    resolve_request = application.dependency(HttpRequest)

    async def endpoint(
        value: Annotated[HttpRequest, Depends(resolve_request)],
    ) -> dict[str, int]:
        """Consume request body under the application size policy.

        The integration uses real components and local test services.
        """
        return {"size": len(await value.body())}

    application.asgi.add_api_route(
        "/bounded",
        endpoint,
        methods=["POST"],
    )

    with TestClient(application.asgi) as client:
        result = client.post("/bounded", content=b"12345")

    assert result.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
