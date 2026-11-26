"""Verify Foundation supplies its effective root to route discovery.

The test uses the real provider lifecycle and ASGI application.
"""

from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from titanspan.foundation import Application

pytestmark = [pytest.mark.architecture, pytest.mark.integration]


def test_application_base_path_owns_conventional_route_discovery(
    tmp_path: Path,
) -> None:
    """Load conventional routes from the configured application root.

    A caller should not also need to set ``routing.path`` for the default
    application route files to follow ``Application.base_path``.
    """
    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "web.py").write_text(
        "def index():\n"
        "    return {'root': 'application'}\n\n"
        "def register_routes(router):\n"
        "    router.get('/rooted', index).name('rooted.index')\n",
        encoding="utf-8",
    )
    application = Application(base_path=tmp_path)

    with TestClient(application.asgi) as client:
        response = client.get("/rooted")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"root": "application"}
    assert application.router.has("rooted.index")


def test_relative_routing_path_resolves_under_application_root(
    tmp_path: Path,
) -> None:
    """Resolve a relative route override from the effective app root.

    Absolute ``routing.path`` values remain explicit filesystem locations.
    """
    route_root = tmp_path / "source"
    routes = route_root / "routes"
    routes.mkdir(parents=True)
    (routes / "web.py").write_text(
        "def index():\n"
        "    return {'root': 'override'}\n\n"
        "def register_routes(router):\n"
        "    router.get('/relative', index).name('relative.index')\n",
        encoding="utf-8",
    )
    application = Application(
        base_path=tmp_path,
        config={"routing": {"path": "source"}},
    )

    with TestClient(application.asgi) as client:
        response = client.get("/relative")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"root": "override"}
