"""Verify Pipeline stages resolve from the canonical application graph.

The application-owned configuration repository is a real stage dependency.
"""

import pytest

from titanspan.contracts.config import ConfigRepository
from titanspan.foundation import Application
from titanspan.pipeline import Pipeline

pytestmark = pytest.mark.integration


class AddApplicationName:
    """Transform text using the app-owned configuration repository.

    Container construction supplies the active repository instance.
    """

    def __init__(self, repository: ConfigRepository) -> None:
        """Retain the dependency injected from the native Container.

        Args:
            repository: Configuration repository owned by the application.
        """
        self._repository = repository

    def handle(self, value: str) -> str:
        """Prefix one value with the configured application name.

        Args:
            value: Input text received from the previous stage.

        Returns:
            Text prefixed with the active application's name.
        """
        name = self._repository.get("app.name", "Application")
        return f"{name}:{value}"

    _repository: ConfigRepository


@pytest.mark.anyio
async def test_pipeline_uses_active_application_container_services() -> None:
    """Resolve stage dependencies through the app-owned Container.

    The explicit async path works with services composed by Foundation.
    """
    application = Application(config={"app": {"name": "Reports"}})

    async with application:
        sync_result = (
            Pipeline[str, str](container=application.container)
            .send("sync")
            .through([AddApplicationName])
            .then_return()
        )
        result = await (
            Pipeline[str, str](container=application.container)
            .send("ready")
            .through([AddApplicationName])
            .then_return_async()
        )

    assert sync_result == "Reports:sync"
    assert result == "Reports:ready"
