"""Verify route modules register through application startup.

The production service provider and ASGI adapter load the discovered routes.
"""

import sys
from http import HTTPStatus
from pathlib import Path
from types import ModuleType

import anyio
import pytest
from fastapi.testclient import TestClient

from titanspan.foundation import Application
from titanspan.routing import (
    DuplicateRouteError,
    RouteCache,
    RouteDiscoveryError,
    Router,
)

pytestmark = pytest.mark.integration


def configured_endpoint() -> dict[str, str]:
    """Return the response body used by an explicit route module.

    Returns:
        A stable mapping for the ASGI response assertion.
    """
    return {"source": "configured"}


def register_configured_routes(router: Router) -> None:
    """Register a route through one explicitly configured module hook.

    Args:
        router: Application router supplied during provider startup.
    """
    router.get("/configured", configured_endpoint).name("configured.index")


def test_conventional_route_files_register_web_then_api(
    tmp_path: Path,
) -> None:
    """Load only the conventional files inside the configured route root.

    The web module registers before the API module during application startup.
    """
    route_directory = tmp_path / "routes"
    route_directory.mkdir()
    (route_directory / "web.py").write_text(
        "def web_endpoint():\n"
        "    return {'source': 'web'}\n\n"
        "def register_routes(router):\n"
        "    router.get('/web', web_endpoint).name('web.index')\n",
        encoding="utf-8",
    )
    (route_directory / "api.py").write_text(
        "def api_endpoint():\n"
        "    return {'source': 'api'}\n\n"
        "def register_routes(router):\n"
        "    router.get('/api', api_endpoint).name('api.index')\n",
        encoding="utf-8",
    )
    application = Application(config={"routing": {"path": str(tmp_path)}})

    with TestClient(application.asgi) as client:
        web_response = client.get("/web")
        api_response = client.get("/api")

    assert web_response.status_code == HTTPStatus.OK
    assert web_response.json() == {"source": "web"}
    assert api_response.status_code == HTTPStatus.OK
    assert api_response.json() == {"source": "api"}
    assert [route.route_name for route in application.router.routes.all()] == [
        "web.index",
        "api.index",
    ]


def test_configured_route_import_errors_are_actionable() -> None:
    """Report invalid configured modules as a startup discovery failure.

    Foundation preserves the original import exception as the cause.
    """
    application = Application(
        config={
            "routing": {
                "discover": False,
                "modules": ("missing_application.routes",),
            },
        },
    )

    with (
        pytest.raises(RouteDiscoveryError, match="configured route module"),
        TestClient(application.asgi),
    ):
        pass


def test_explicit_modules_register_in_configured_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load trusted module names without scanning unrelated import paths.

    Module hooks register against the application Router only at startup.
    """
    module_name = "titanspan_test_configured_route_module"
    module = ModuleType(module_name)
    module.__dict__["register_routes"] = register_configured_routes
    monkeypatch.setitem(sys.modules, module_name, module)
    application = Application(
        config={
            "routing": {
                "discover": False,
                "modules": (module_name,),
            },
        },
    )

    with TestClient(application.asgi) as client:
        response = client.get("/configured")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"source": "configured"}
    assert application.router.routes.named("configured.index").path == (
        "/configured"
    )


def test_conventional_route_conflicts_preserve_duplicate_detection(
    tmp_path: Path,
) -> None:
    """Reject method and path duplicates across conventional route files.

    Route discovery preserves the canonical collection's conflict error.
    """
    route_directory = tmp_path / "routes"
    route_directory.mkdir()
    for filename, route_name in (
        ("web.py", "web.duplicate"),
        ("api.py", "api.duplicate"),
    ):
        (route_directory / filename).write_text(
            "def endpoint():\n"
            "    return {'source': 'duplicate'}\n\n"
            "def register_routes(router):\n"
            f"    router.get('/duplicate', endpoint).name('{route_name}')\n",
            encoding="utf-8",
        )
    application = Application(config={"routing": {"path": str(tmp_path)}})

    with (
        pytest.raises(DuplicateRouteError, match="methods and paths"),
        TestClient(application.asgi),
    ):
        pass


@pytest.mark.anyio
async def test_route_discovery_isolated_for_concurrent_applications(
    tmp_path: Path,
) -> None:
    """Load one trusted route tree into separate concurrent app catalogs.

    Temporary route module state is scoped to each application Router.
    """
    route_directory = tmp_path / "routes"
    route_directory.mkdir()
    (route_directory / "web.py").write_text(
        "def endpoint():\n"
        "    return {'source': 'isolated'}\n\n"
        "def register_routes(router):\n"
        "    router.get('/isolated', endpoint).name('isolated.index')\n",
        encoding="utf-8",
    )
    first = Application(config={"routing": {"path": str(tmp_path)}})
    second = Application(config={"routing": {"path": str(tmp_path)}})

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(first.startup)
        tasks.start_soon(second.startup)

    first_action = first.router.routes.named("isolated.index").action
    second_action = second.router.routes.named("isolated.index").action
    cache = RouteCache(tmp_path / "routes.json")
    cache.write(first.router)
    cached_second = cache.read(second.router)
    assert first.router is not second.router
    assert first_action is not second_action
    assert cached_second[0].action.startswith("callable-file:")
    await first.shutdown()
    await second.shutdown()
