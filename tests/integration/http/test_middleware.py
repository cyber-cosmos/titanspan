"""Exercise native HTTP middleware through a real in-process ASGI server.

The integration uses real components and local test services.
"""

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.foundation import ServiceProvider
from titanspan.contracts.http import HttpRequest, HttpResponse, RequestHandler
from titanspan.foundation import Application
from titanspan.http import Response

pytestmark = pytest.mark.integration


class TraceRecorder:
    """Collect middleware order and request metadata for one test app.

    The integration uses real components and local test services.
    """

    def __init__(self) -> None:
        """Initialize an isolated ordered trace.

        The integration uses real components and local test services.
        """
        self.events: list[str] = []

    events: list[str]


class TraceProvider(ServiceProvider):
    """Register the test trace before the application composes its graph.

    The integration uses real components and local test services.
    """

    def __init__(self, trace: TraceRecorder) -> None:
        """Retain the isolated test trace for provider registration.

        The integration uses real components and local test services.
        """
        self._trace = trace

    def register(self, container: ServiceRegistry) -> None:
        """Bind the trace instance before graph composition begins.

        The integration uses real components and local test services.
        """
        container.instance(TraceRecorder, self._trace)

    _trace: TraceRecorder


class FirstMiddleware:
    """Record outer execution and add a header after downstream handling.

    The integration uses real components and local test services.
    """

    def __init__(self, trace: TraceRecorder) -> None:
        """Receive the application-owned trace service.

        The integration uses real components and local test services.
        """
        self._trace = trace

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Wrap the next response while observing the active request.

        The integration uses real components and local test services.
        """
        self._trace.events.append(f"first:{request.path}")
        response = await next_handler(request)
        response.with_header("X-First", "complete")
        return response

    _trace: TraceRecorder


class SecondMiddleware:
    """Record the inner middleware before and after route execution.

    The integration uses real components and local test services.
    """

    def __init__(self, trace: TraceRecorder) -> None:
        """Receive the same application-owned trace service.

        The integration uses real components and local test services.
        """
        self._trace = trace

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Record ordered execution around the downstream route.

        The integration uses real components and local test services.
        """
        self._trace.events.append("second:before")
        response = await next_handler(request)
        self._trace.events.append("second:after")
        return response

    _trace: TraceRecorder


def test_native_middleware_is_ordered_injected_and_can_transform_response() -> (
    None
):
    """Inject middleware from the native container around a real route.

    The integration uses real components and local test services.
    """
    trace = TraceRecorder()
    application = Application(
        config={"app": {"name": "middleware test"}},
        service_providers=(TraceProvider(trace),),
        http_middleware=(FirstMiddleware, SecondMiddleware),
    )

    async def endpoint() -> Response:
        """Return one native response through the ASGI test client.

        The integration uses real components and local test services.
        """
        return Response("ok")

    application.asgi.add_api_route("/middleware", endpoint)

    with TestClient(application.asgi) as client:
        result = client.get("/middleware")

    assert result.status_code == HTTPStatus.OK
    assert result.text == "ok"
    assert result.headers["x-first"] == "complete"
    assert trace.events == [
        "first:/middleware",
        "second:before",
        "second:after",
    ]
