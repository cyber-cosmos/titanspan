"""Verify native request services remain scoped through ASGI delivery.

The tests exercise FastAPI's in-process ASGI client, Titanspan's native
container, and the complete response send lifecycle.
"""

from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Annotated

import anyio
import pytest
from fastapi import Depends
from fastapi import Request as FastAPIRequest
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect
from starlette.types import Message, Scope

from titanspan.contracts.http import (
    HttpRequest,
    HttpResponse,
    RequestHandler,
)
from titanspan.foundation import Application
from titanspan.http import Request
from titanspan.http.exceptions import HttpContextError
from titanspan.http.helpers import request as active_request
from titanspan.http.helpers import response

pytestmark = pytest.mark.integration
_CLIENT_DISCONNECTED_MESSAGE = "client disconnected"
_STREAM_GENERATION_FAILURE = "stream generation failed"


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


def test_request_exposes_route_metadata_from_native_dispatch() -> None:
    """Read the selected route and path values through Request properties.

    The HTTP component consumes metadata set by the Routing boundary.
    """
    application = Application(config={"app": {"name": "route metadata"}})

    async def endpoint(request: Request) -> dict[str, object]:
        """Return native route metadata for a selected path.

        The HTTP request wrapper does not import Routing implementation types.
        """
        return {
            "name": request.route_name,
            "parameters": dict(request.route_parameters),
        }

    application.router.get(
        "/documents/{document_id}",
        endpoint,
    ).name("documents.show")
    with TestClient(application.asgi) as client:
        result = client.get("/documents/42")

    assert result.status_code == HTTPStatus.OK
    assert result.json() == {
        "name": "documents.show",
        "parameters": {"document_id": "42"},
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


@pytest.mark.anyio
async def test_disconnect_finalizes_stream_before_request_scope_closes() -> (
    None
):
    """Finalize a disconnected stream while request context remains active.

    The ASGI send failure models a client disconnect after response headers.
    The stream finalizer must run before Foundation closes request services.
    """
    application = Application(config={"app": {"name": "disconnect test"}})
    observed: list[str] = []

    async def endpoint(request: Request) -> object:
        """Return a stream that reads request-local context during cleanup.

        Args:
            request: Request-scoped service supplied by the native Container.

        Returns:
            A streaming response that observes its lifecycle finalizer.
        """

        async def chunks() -> AsyncIterator[bytes]:
            """Yield one chunk and inspect context when transmission stops.

            The request context must remain active through source finalization.
            """
            try:
                yield b"first"
            finally:
                observed.append(
                    "active" if active_request() is request else "different"
                )

        return response().stream(chunks(), content_type="text/plain")

    application.router.get("/stream-disconnect", endpoint)
    await application.startup()
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/stream-disconnect",
        "raw_path": b"/stream-disconnect",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 45000),
        "extensions": {},
        "state": {},
    }
    first_request = True

    async def receive() -> Message:
        """Return the empty request body expected for this GET operation.

        A second receive reports disconnection after response transmission.
        """
        nonlocal first_request
        if first_request:
            first_request = False
            return {
                "type": "http.request",
                "body": b"",
                "more_body": False,
            }
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        """Fail response transmission after the first streamed body chunk.

        Args:
            message: ASGI message produced by the response implementation.

        Raises:
            OSError: To model a client that disconnected during transmission.
        """
        if message["type"] == "http.response.body":
            raise OSError(_CLIENT_DISCONNECTED_MESSAGE)

    try:
        with pytest.raises(ClientDisconnect):
            await application.asgi(scope, receive, send)
        with pytest.raises(HttpContextError):
            active_request()
    finally:
        await application.shutdown()

    assert observed == ["active"]


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_cancelled_stream_finalizes_before_request_scope_closes() -> None:
    """Finalize a cancelled stream before the request scope exits.

    Cancellation during ASGI transmission must not abandon response-owned
    generators or close request dependencies before their finalizers run.
    """
    application = Application(config={"app": {"name": "cancel test"}})
    observed: list[str] = []
    send_started = anyio.Event()

    async def endpoint(request: Request) -> object:
        """Return a stream whose finalizer reads request-local context.

        Args:
            request: Request-scoped service supplied by the native Container.

        Returns:
            A response that blocks while sending its first body chunk.
        """

        async def chunks() -> AsyncIterator[bytes]:
            """Yield a chunk and record active context during cancellation.

            The request context must remain active through source finalization.
            """
            try:
                yield b"first"
            finally:
                observed.append(
                    "active" if active_request() is request else "different"
                )

        return response().stream(chunks(), content_type="text/plain")

    application.router.get("/stream-cancel", endpoint)
    await application.startup()
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/stream-cancel",
        "raw_path": b"/stream-cancel",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 45000),
        "extensions": {},
        "state": {},
    }

    async def receive() -> Message:
        """Return the empty request body for this GET operation.

        The ASGI server reports no additional messages after request input.
        """
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        """Wait at the first body chunk until the test cancels transmission.

        Args:
            message: ASGI message produced by the response implementation.
        """
        if message["type"] == "http.response.body" and message.get("more_body"):
            send_started.set()
            await anyio.sleep_forever()

    try:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(application.asgi, scope, receive, send)
            await send_started.wait()
            task_group.cancel_scope.cancel()
        with pytest.raises(HttpContextError):
            active_request()
    finally:
        await application.shutdown()

    assert observed == ["active"]


@pytest.mark.anyio
async def test_stream_failure_after_headers_sends_no_second_response() -> None:
    """Propagate a stream error without rendering a second HTTP response.

    The request scope remains alive through generator finalization.
    """

    class PassThroughMiddleware:
        """Exercise stream errors while native global middleware is active.

        The response body remains owned by the downstream ASGI sender.
        """

        async def handle(
            self,
            request: HttpRequest,
            next_handler: RequestHandler,
        ) -> HttpResponse:
            """Forward the request without buffering the response stream.

            Args:
                request: Active request supplied by Foundation.
                next_handler: Remaining native middleware and route.

            Returns:
                The original downstream streaming response.
            """
            return await next_handler(request)

    application = Application(
        config={"app": {"name": "stream failure"}},
        http_middleware=(PassThroughMiddleware,),
    )
    observed: list[str] = []

    async def endpoint(request: Request) -> object:
        """Return a stream that fails after sending one body chunk.

        Args:
            request: Request-scoped service retained during stream cleanup.

        Returns:
            A streaming response whose body source raises after one chunk.
        """

        async def content() -> AsyncIterator[bytes]:
            """Yield one chunk, then raise a stable test error.

            Record that the request context remains active during finalization.
            """
            try:
                yield b"first"
                raise RuntimeError(_STREAM_GENERATION_FAILURE)
            finally:
                observed.append(
                    "active" if active_request() is request else "different"
                )

        return response().stream(content(), content_type="text/plain")

    application.router.get("/stream-failure", endpoint)
    await application.startup()
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/stream-failure",
        "raw_path": b"/stream-failure",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 45000),
        "extensions": {},
        "state": {},
    }
    messages: list[Message] = []

    async def receive() -> Message:
        """Return one empty request body for this GET operation.

        The request has no payload.
        """
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        """Record ASGI messages without a client abstraction.

        Args:
            message: Response message emitted by the application.
        """
        messages.append(message)

    try:
        with pytest.raises(RuntimeError, match=_STREAM_GENERATION_FAILURE):
            await application.asgi(scope, receive, send)
        with pytest.raises(HttpContextError):
            active_request()
    finally:
        await application.shutdown()

    starts = [
        message
        for message in messages
        if message["type"] == "http.response.start"
    ]
    bodies = [
        message
        for message in messages
        if message["type"] == "http.response.body"
    ]
    assert len(starts) == 1
    assert starts[0]["status"] == HTTPStatus.OK
    assert bodies[0]["body"] == b"first"
    assert b"".join(message["body"] for message in bodies) == b"first"
    assert bodies[-1]["more_body"] is False
    assert observed == ["active"]


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


def test_body_limit_covers_interoperability_routes_too() -> None:
    """Apply one configured body limit to every ASGI route.

    FastAPI interoperability routes must receive the same bounded ASGI
    receiver as native Titanspan request adapters.
    """
    application = Application(
        config={
            "app": {"name": "interop body limit"},
            "http": {"server": {"max_body_size": 4}},
        }
    )

    async def endpoint(request: FastAPIRequest) -> dict[str, int]:
        """Read the incoming body through the host interoperability API.

        Args:
            request: Backend request supplied by the ASGI host.

        Returns:
            The received byte count if the configured limit permits it.
        """
        return {"size": len(await request.body())}

    application.asgi.add_api_route(
        "/interop-bounded",
        endpoint,
        methods=["POST"],
    )

    with TestClient(application.asgi) as client:
        result = client.post("/interop-bounded", content=b"12345")

    assert result.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
