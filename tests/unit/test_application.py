"""Tests for application settings, dependency injection, and lifecycle."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from dishka import Provider, Scope, provide
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pytest import MonkeyPatch

from titanspan import Application
from titanspan.config import Settings


@dataclass
class ManagedResource:
    """Resource whose cleanup is observable in the lifecycle test."""

    closed: bool = False


class ResourceProvider(Provider):
    """Provide an application-scoped resource with async cleanup."""

    def __init__(self, resources: list[ManagedResource]) -> None:
        """Store the resources created by this provider."""
        super().__init__()
        self.resources = resources

    @provide(scope=Scope.APP)
    async def resource(self) -> AsyncIterator[ManagedResource]:
        """Yield a resource and mark it closed during container shutdown."""
        resource = ManagedResource()
        self.resources.append(resource)
        try:
            yield resource
        finally:
            resource.closed = True


def test_settings_read_environment_values(monkeypatch: MonkeyPatch) -> None:
    """Read typed settings from the TITANSPAN environment prefix."""
    monkeypatch.setenv("TITANSPAN_DEBUG", "true")

    assert Settings().debug is True


def test_settings_reject_invalid_boolean_values(
    monkeypatch: MonkeyPatch,
) -> None:
    """Reject malformed typed values instead of silently coercing them."""
    monkeypatch.setenv("TITANSPAN_DEBUG", "sometimes")

    with pytest.raises(ValidationError):
        Settings()


def test_fastapi_dependency_resolution_and_resource_cleanup() -> None:
    """Resolve a provider dependency and close it after ASGI shutdown."""
    resources: list[ManagedResource] = []
    application = Application(providers=[ResourceProvider(resources)])
    router = APIRouter(route_class=DishkaRoute)

    @router.get("/resource")
    async def read_resource(
        resource: FromDishka[ManagedResource],
    ) -> dict[str, bool]:
        return {"closed": resource.closed}

    application.asgi.include_router(router)

    with TestClient(application.asgi) as client:
        response = client.get("/resource")

    assert response.status_code == 200
    assert response.json() == {"closed": False}
    assert resources == [ManagedResource(closed=True)]


def test_resource_cleanup_after_handler_failure() -> None:
    """Close app-scoped resources when a request handler raises."""
    resources: list[ManagedResource] = []
    application = Application(providers=[ResourceProvider(resources)])
    router = APIRouter(route_class=DishkaRoute)

    @router.get("/failure")
    async def fail(
        resource: FromDishka[ManagedResource],
    ) -> dict[str, bool]:
        del resource
        raise RuntimeError("handler failed")

    application.asgi.include_router(router)

    with TestClient(application.asgi, raise_server_exceptions=False) as client:
        response = client.get("/failure")

    assert response.status_code == 500
    assert resources == [ManagedResource(closed=True)]
