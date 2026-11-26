"""Verify real FastAPI and Dishka application and request scopes.

The tests cross the ASGI integration boundary and observe resource ownership
without mocking dependency resolution.
"""

from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from http import HTTPStatus
from threading import Lock
from typing import Annotated

import pytest

# The current Dishka overload exposes Any to strict static analysis.
from dishka import (
    Provider,
    Scope,
    provide,  # pyright: ignore[reportUnknownVariableType]
)
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from titanspan import Application
from titanspan._application_context import active_application_context
from titanspan.container import ContainerScope
from titanspan.container import Scope as NativeScope
from titanspan.contracts.container import ServiceRegistry

HANDLER_FAILURE_MESSAGE = "handler failed"
EXPECTED_REQUEST_COUNT = 2

pytestmark = pytest.mark.integration


@dataclass
class ManagedResource:
    """Track whether Dishka finalized an application-scoped resource.

    Attributes:
        closed: Whether the resource generator completed during shutdown.
    """

    closed: bool = False


class ResourceProvider(Provider):
    """Provide one app-scoped resource with observable cleanup.

    Attributes:
        resources: Instances created by the asynchronous provider.
    """

    def __init__(
        self,
        resources: list[ManagedResource],
        events: list[str] | None = None,
    ) -> None:
        """Retain the test-owned resource observation list.

        Args:
            resources: List populated when the provider first resolves.
            events: Optional ordered cleanup observations.
        """
        super().__init__()
        self.resources = resources
        self.events = events

    @provide(scope=Scope.APP)
    async def resource(self) -> AsyncIterator[ManagedResource]:
        """Yield one app instance and mark it finalized at shutdown.

        Yields:
            The shared resource resolved by application requests.
        """
        resource = ManagedResource()
        self.resources.append(resource)
        if self.events is not None:
            self.events.append("route-created")
        try:
            yield resource
        finally:
            # The generator's finally block exposes Dishka's close behavior.
            resource.closed = True
            if self.events is not None:
                self.events.append("route-closed")


@dataclass(frozen=True)
class RequestScopedResource:
    """Identify a single instance created within one HTTP request.

    Attributes:
        identifier: Monotonic provider-local creation number.
    """

    identifier: int


class RequestScopedProvider(Provider):
    """Create an independent value for each Dishka request scope.

    Attributes:
        created: Number of request-scoped values produced by the provider.
        creation_lock: Protects the observable counter during concurrent use.
    """

    def __init__(self) -> None:
        """Initialize the deterministic request creation counter.

        The counter lets the integration test observe scope isolation without
        introducing timing assumptions or external state.
        """
        super().__init__()
        self.created: int = 0
        self.creation_lock = Lock()

    @provide(scope=Scope.REQUEST)
    def request_resource(self) -> RequestScopedResource:
        """Create a new immutable resource for the active request.

        Returns:
            A request-local value with a unique test identifier.
        """
        # Keep the test observation race-free as requests execute concurrently.
        with self.creation_lock:
            self.created += 1
            identifier = self.created
        return RequestScopedResource(identifier=identifier)


@dataclass
class NativeStreamingResource:
    """Track a native request resource while an ASGI body is streamed.

    Attributes:
        closed: Whether the active request scope finalized this resource.
    """

    closed: bool = False


class NativeStreamingProvider:
    """Register a request resource through the Titanspan container.

    Attributes:
        resources: Resources created and finalized by native request scopes.
    """

    def __init__(self, resources: list[NativeStreamingResource]) -> None:
        """Retain resources for lifecycle assertions after HTTP completion.

        Args:
            resources: Test-owned list populated by the resource factory.
        """
        self.resources = resources

    def register(self, container: ServiceRegistry) -> None:
        """Register the resource with the canonical request lifecycle.

        Args:
            container: Native application service registry.
        """
        container.scoped(
            NativeStreamingResource,
            self._request_resource,
            scope=NativeScope.REQUEST,
        )

    async def _request_resource(
        self,
    ) -> AsyncIterator[NativeStreamingResource]:
        """Yield a request value until its scope has fully exited.

        Yields:
            A resource whose finalization is observable by the test.
        """
        resource = NativeStreamingResource()
        self.resources.append(resource)
        try:
            yield resource
        finally:
            resource.closed = True

    resources: list[NativeStreamingResource]


@dataclass
class NativeApplicationResource:
    """Track an application-owned resource used to verify close ordering.

    Attributes:
        closed: Whether the native application container finalized it.
    """

    closed: bool = False


class NativeApplicationProvider:
    """Own an app-scoped generator resource through the native container.

    Attributes:
        events: Ordered resource lifecycle observations.
    """

    def __init__(self, events: list[str]) -> None:
        """Retain events shared with the optional route graph fixture.

        Args:
            events: Ordered lifecycle observations populated by both graphs.
        """
        self.events = events

    def register(self, container: ServiceRegistry) -> None:
        """Register the native resource and prepare it during application boot.

        Args:
            container: Canonical Titanspan application registry.
        """
        container.singleton(
            NativeApplicationResource,
            self._application_resource,
        )

    async def _application_resource(
        self,
    ) -> AsyncIterator[NativeApplicationResource]:
        """Yield a resource whose cleanup ordering is observable.

        Yields:
            An application-scoped resource owned by the native container.
        """
        resource = NativeApplicationResource()
        self.events.append("native-created")
        try:
            yield resource
        finally:
            resource.closed = True
            self.events.append("native-closed")

    async def boot(self, resource: NativeApplicationResource) -> None:
        """Resolve the resource before the host begins serving requests.

        Args:
            resource: App-scoped value whose finalizer belongs to the app.
        """
        assert not resource.closed

    events: list[str]


def test_app_scope_resource_is_shared_and_closed_at_shutdown() -> None:
    """Reuse app scope across requests and finalize it on lifespan exit.

    The real FastAPI client starts the application lifespan and Dishka
    resolves the provider through its FastAPI integration.
    """
    resources: list[ManagedResource] = []
    application = Application(providers=[ResourceProvider(resources)])
    router = APIRouter(route_class=DishkaRoute)

    @router.get("/resource")
    async def read_resource(
        resource: FromDishka[ManagedResource],
    ) -> dict[str, bool]:
        """Report resource state while the app scope remains active.

        Args:
            resource: App-scoped resource resolved by Dishka.

        Returns:
            Current resource finalization state.
        """
        return {"closed": resource.closed}

    application.asgi.include_router(router)

    with TestClient(application.asgi) as client:
        first = client.get("/resource")
        second = client.get("/resource")

    assert first.status_code == HTTPStatus.OK
    assert second.status_code == HTTPStatus.OK
    assert first.json() == {"closed": False}
    assert second.json() == {"closed": False}
    assert resources == [ManagedResource(closed=True)]


@pytest.mark.concurrency
def test_request_scope_isolated_between_concurrent_http_requests() -> None:
    """Create a distinct dependency instance for each concurrent request.

    The provider count verifies the actual Dishka request scope rather than
    relying on a mocked resolver or timing-based assertion. A thread pool
    submits both requests together through the real ASGI test client.
    """
    provider = RequestScopedProvider()
    application = Application(providers=[provider])
    router = APIRouter(route_class=DishkaRoute)

    @router.get("/request-resource")
    async def read_request_resource(
        resource: FromDishka[RequestScopedResource],
    ) -> dict[str, int]:
        """Return the identifier assigned in the active request scope.

        Args:
            resource: Request-scoped resource resolved by Dishka.

        Returns:
            The request-local provider creation number.
        """
        return {"identifier": resource.identifier}

    application.asgi.include_router(router)

    # Submit requests together to exercise actual independent ASGI scopes.
    with (
        TestClient(application.asgi) as client,
        ThreadPoolExecutor(
            max_workers=EXPECTED_REQUEST_COUNT,
        ) as executor,
    ):
        responses = list(
            executor.map(
                client.get,
                ["/request-resource"] * EXPECTED_REQUEST_COUNT,
            )
        )

    assert all(response.status_code == HTTPStatus.OK for response in responses)
    assert {response.json()["identifier"] for response in responses} == {
        1,
        2,
    }
    assert provider.created == EXPECTED_REQUEST_COUNT


def test_resource_is_closed_when_request_handler_fails() -> None:
    """Finalize app scope even when a handler raises during a request.

    The test server converts the unhandled handler failure to HTTP 500 while
    the application shutdown path remains responsible for resource cleanup.
    """
    resources: list[ManagedResource] = []
    application = Application(providers=[ResourceProvider(resources)])
    router = APIRouter(route_class=DishkaRoute)

    @router.get("/failure")
    async def fail_request(
        resource: FromDishka[ManagedResource],
    ) -> dict[str, bool]:
        """Raise an expected handler error after resolving the resource.

        Args:
            resource: Resolved dependency that keeps the app provider active.

        Returns:
            This function never returns a response.
        """
        del resource
        raise RuntimeError(HANDLER_FAILURE_MESSAGE)

    application.asgi.include_router(router)

    with TestClient(
        application.asgi,
        raise_server_exceptions=False,
    ) as client:
        response = client.get("/failure")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert resources == [ManagedResource(closed=True)]


def test_route_resources_close_before_native_application_resources() -> None:
    """Finalize the optional route graph before native application services.

    Real generator resources in both graphs record their cleanup sequence
    while the ASGI host owns application startup and shutdown.
    """
    events: list[str] = []
    route_resources: list[ManagedResource] = []
    application = Application(
        providers=[ResourceProvider(route_resources, events)],
        service_providers=[NativeApplicationProvider(events)],
    )
    router = APIRouter(route_class=DishkaRoute)

    @router.get("/resource-order")
    async def read_route_resource(
        resource: FromDishka[ManagedResource],
    ) -> dict[str, bool]:
        """Read the external graph resource while both graphs remain open.

        Args:
            resource: Route-scoped value owned by the optional route graph.

        Returns:
            Whether the route resource is still open during request handling.
        """
        return {"closed": resource.closed}

    application.asgi.include_router(router)

    with TestClient(application.asgi) as client:
        response = client.get("/resource-order")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"closed": False}
    assert events == [
        "native-created",
        "route-created",
        "route-closed",
        "native-closed",
    ]


def test_native_request_context_and_scope_cover_streaming_response() -> None:
    """Keep app context and request resources alive through final body send.

    The route uses a native dependency bridge and the actual ASGI test client;
    each body iteration observes the active request scope before cleanup.
    """
    resources: list[NativeStreamingResource] = []
    provider = NativeStreamingProvider(resources)
    application = Application(service_providers=[provider])
    router = APIRouter()
    observations: list[tuple[bool, bool, bool]] = []

    @router.get("/native-stream")
    async def stream_resource(
        resource: Annotated[
            NativeStreamingResource,
            Depends(application.dependency(NativeStreamingResource)),
        ],
    ) -> StreamingResponse:
        """Stream observations of request-owned native application state.

        Args:
            resource: Request-scoped resource injected through Titanspan.

        Returns:
            A streaming response whose producer runs after response headers.
        """

        async def body() -> AsyncIterator[bytes]:
            """Record context state at each streaming boundary.

            Yields:
                Two body segments while the request lifecycle remains active.
            """
            for segment in (b"first", b"second"):
                active = active_application_context()
                scope_active = (
                    active is not None
                    and isinstance(active.scope, ContainerScope)
                    and active.scope.is_active
                )
                observations.append(
                    (
                        not resource.closed,
                        active is not None
                        and active.application is application,
                        scope_active,
                    )
                )
                yield segment

        return StreamingResponse(body(), media_type="text/plain")

    application.asgi.include_router(router)

    with TestClient(application.asgi) as client:
        response = client.get("/native-stream")

    assert response.status_code == HTTPStatus.OK
    assert response.content == b"firstsecond"
    assert observations == [(True, True, True), (True, True, True)]
    assert resources == [NativeStreamingResource(closed=True)]
