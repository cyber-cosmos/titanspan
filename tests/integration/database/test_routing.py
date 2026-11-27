"""Verify route model binding uses the active Database service.

The tests exercise the native Routing binder against real SQLite records.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import DatabaseServiceProvider, Model, bind_model
from titanspan.facades.database import DB
from titanspan.foundation import Application
from titanspan.routing import Router

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
_CREATED_SLUG = "ada-lovelace"
_CREATED_USER = "Ada Lovelace"


class RouteUser(Model):
    """Represent a user addressed by a non-primary route key.

    The mapped slug verifies the model's explicit route-key convention.
    """

    table = "route_users"
    route_key_name = "slug"
    fillable = ("slug", "name")

    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))


def test_model_binding_resolves_by_route_key_and_returns_not_found(
    tmp_path: Path,
) -> None:
    """Resolve a typed model and render a missing row as HTTP 404.

    Args:
        tmp_path: Isolated Application root for the SQLite database.
    """

    async def create_schema() -> None:
        """Create the real table used by model binding.

        The startup callback runs under the Application's active context.
        """
        await DB.statement_async(
            "CREATE TABLE route_users ("
            "id INTEGER PRIMARY KEY, "
            "slug VARCHAR(80) NOT NULL UNIQUE, "
            "name VARCHAR(120) NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )

    application = (
        Application.builder()
        .with_base_path(tmp_path)
        .with_config(
            {
                "database": {
                    "default": "sqlite",
                    "connections": {
                        "sqlite": {
                            "driver": "sqlite",
                            "database": "database/route-binding.sqlite",
                        },
                    },
                },
            },
        )
        .with_service_provider(DatabaseServiceProvider())
        .on_startup(create_schema)
        .build()
    )

    async def create_user() -> dict[str, object]:
        """Create one record before the binding request.

        Returns:
            The generated identity and stable route key.
        """
        user = await RouteUser.create_async(
            {"slug": _CREATED_SLUG, "name": _CREATED_USER},
        )
        return {"id": user.id, "slug": user.slug}

    async def show_user(user: RouteUser) -> dict[str, object]:
        """Expose only values from the model resolved by the binder.

        Args:
            user: Model loaded through the registered route callback.

        Returns:
            Safe values used to verify model identity and route selection.
        """
        return {"id": user.id, "name": user.name}

    application.router.post("/users", create_user)
    application.router.get("/users/{user}", show_user)
    bind_model(application.router, RouteUser, parameter="user")

    with TestClient(application.asgi) as client:
        created = client.post("/users")
        found = client.get(f"/users/{_CREATED_SLUG}")
        missing = client.get("/users/not-present")

    assert created.status_code == HTTPStatus.OK
    assert created.json() == {"id": 1, "slug": _CREATED_SLUG}
    assert found.status_code == HTTPStatus.OK
    assert found.json() == {"id": 1, "name": _CREATED_USER}
    assert missing.status_code == HTTPStatus.NOT_FOUND


def test_model_binding_validates_route_keys() -> None:
    """Accept mapped overrides and reject unsafe or missing columns.

    Route keys select mapped columns and never become raw SQL fragments.
    """
    router = Router()
    bind_model(
        router,
        RouteUser,
        parameter="user",
        route_key="id",
    )

    assert router.binding_for("user") is not None

    for route_key in ("missing", "id; DROP TABLE route_users"):
        with pytest.raises(ValueError, match="mapped model column"):
            bind_model(
                Router(),
                RouteUser,
                parameter="user",
                route_key=route_key,
            )
