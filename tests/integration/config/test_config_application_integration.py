"""Verify configuration is shared across application boundaries.

The tests use real FastAPI routing and Dishka resolution rather than mocks.
"""

from http import HTTPStatus
from pathlib import Path

import pytest
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from fastapi.testclient import TestClient

from titanspan.config import ConfigManager, Repository
from titanspan.contracts import ConfigRepository
from titanspan.facades import Config
from titanspan.foundation import Application

pytestmark = [pytest.mark.integration, pytest.mark.feature]
_BOOTSTRAP_WORKER_COUNT = 5


def test_application_loads_config_and_shares_it_with_facade_and_container(
    tmp_path: Path,
) -> None:
    """Expose one repository through HTTP facade and dependency injection.

    Args:
        tmp_path: Isolated application root for trusted local config files.
    """
    config_path = tmp_path / "config"
    config_path.mkdir()
    (tmp_path / ".env").write_text("APP_NAME=From dotenv\n", encoding="utf-8")
    (config_path / "app.py").write_text(
        "from titanspan.support import env\n"
        "config = {'name': env('APP_NAME', 'Default'), 'debug': True}\n",
        encoding="utf-8",
    )

    application = Application(base_path=tmp_path)
    router = APIRouter(route_class=DishkaRoute)

    @router.get("/config")
    def read_config(
        repository: FromDishka[ConfigRepository],
    ) -> dict[str, object]:
        """Return the shared repository values from both public access paths.

        Args:
            repository: Native contract resolved by the active Dishka scope.

        Returns:
            Configuration values observed by the facade and injected service.
        """
        return {
            "facade_name": Config.get("app.name"),
            "repository_name": repository.get("app.name"),
            "debug": Config.boolean("app.debug"),
        }

    application.asgi.include_router(router)

    assert application.config is not None
    assert isinstance(application.config, Repository)
    assert application.asgi.title == "From dotenv"
    assert application.asgi.debug is True

    with TestClient(application.asgi) as client:
        response = client.get("/config")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "facade_name": "From dotenv",
        "repository_name": "From dotenv",
        "debug": True,
    }


def test_config_manager_accepts_explicit_environment_file_and_package_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Select dotenv input and retain package defaults under app values.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Environment fixture that removes external overrides.
    """
    monkeypatch.delenv("APP_NAME", raising=False)
    config_path = tmp_path / "config"
    config_path.mkdir()
    (tmp_path / ".env").write_text("APP_NAME=Root\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text(
        "APP_NAME=Local\n",
        encoding="utf-8",
    )
    (config_path / "app.py").write_text(
        "from titanspan.support import env\n"
        "config = {'name': env('APP_NAME', 'Default')}\n",
        encoding="utf-8",
    )

    manager = ConfigManager(
        base_path=tmp_path,
        environment_file=".env.local",
        package_defaults={"queue": {"workers": 3}},
    )
    repository = manager.load(
        overrides={"queue.workers": _BOOTSTRAP_WORKER_COUNT}
    )

    assert repository.string("app.name") == "Local"
    assert repository.integer("queue.workers") == _BOOTSTRAP_WORKER_COUNT
