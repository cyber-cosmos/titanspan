"""Verify real FastAPI and Dishka application and request scopes.

The tests cross the ASGI integration boundary and observe resource ownership
without mocking dependency resolution.
"""

from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from http import HTTPStatus
from threading import Lock

import pytest

# The current Dishka overload exposes Any to strict static analysis.
from dishka import (
    Provider,
    Scope,
    provide,  # pyright: ignore[reportUnknownVariableType]
)
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from fastapi.testclient import TestClient

from titanspan import Application

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

    def __init__(self, resources: list[ManagedResource]) -> None:
        """Retain the test-owned resource observation list.

        Args:
            resources: List populated when the provider first resolves.
        """
        super().__init__()
        self.resources = resources

    @provide(scope=Scope.APP)
    async def resource(self) -> AsyncIterator[ManagedResource]:
        """Yield one app instance and mark it finalized at shutdown.

        Yields:
            The shared resource resolved by application requests.
        """
        resource = ManagedResource()
        self.resources.append(resource)
        try:
            yield resource
        finally:
            # The generator's finally block exposes Dishka's close behavior.
            resource.closed = True


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
