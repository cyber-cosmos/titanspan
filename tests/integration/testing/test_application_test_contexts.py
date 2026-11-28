"""Verify native test contexts use real application services and ASGI paths.

The helpers wrap production Foundation and Container lifecycles.
"""

from importlib.metadata import EntryPoint, EntryPoints
from pathlib import Path
from typing import Protocol

import anyio
import pytest

import titanspan.foundation.builder as builder_module
from titanspan.config import Settings
from titanspan.container import ContainerClosedError
from titanspan.contracts.config import ConfigRepository
from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.foundation import ApplicationPaths, ServiceProvider
from titanspan.contracts.http import HttpRequest, HttpResponse, RequestHandler
from titanspan.testing import ApplicationTest, AsyncApplicationTest

pytestmark = pytest.mark.integration
_HTTP_OK = 200
_TEST_FAILURE = "test failure"
_CONFIG_TYPE_ERROR = "The configured application name must be a string."


class _Label(Protocol):
    """Describe a service injected into the test application route.

    The provider and replacement both satisfy this structural contract.
    """

    def value(self) -> str:
        """Return one application label.

        Returns:
            The label selected by the active service graph.
        """
        ...


class _ProductionLabel:
    """Represent the service registered by the real provider.

    The integration test replaces this value through the application graph.
    """

    def value(self) -> str:
        """Return the production service label.

        Returns:
            The stable value owned by the production provider.
        """
        return "production"


class _ReplacementLabel:
    """Represent a test-local replacement selected through Container.

    The application test helper registers this value under the same contract.
    """

    def value(self) -> str:
        """Return the replacement service label.

        Returns:
            The stable value selected by the test application.
        """
        return "replacement"


class _LabelProvider(ServiceProvider):
    """Register the production label under its shared contract.

    Application testing retains this provider in the real lifecycle.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Bind the label using the application's canonical service registry.

        Args:
            container: Native service registry composed by Foundation.
        """
        container.singleton(_Label, _ProductionLabel)


def _label_route(label: _Label) -> dict[str, str]:
    """Return the value injected through the production request path.

    Args:
        label: Application service resolved by the active Container.

    Returns:
        One JSON-safe service label.
    """
    return {"value": label.value()}


class _ResponseHeaderMiddleware:
    """Add a marker header through the native middleware contract.

    ApplicationTest must compose this class through Foundation's builder.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Delegate the request and mark the returned response.

        Args:
            request: Current request passed through the production router.
            next_handler: Downstream handler in the native middleware chain.

        Returns:
            The downstream response with the test marker header.
        """
        response = await next_handler(request)
        response.with_header("X-Test-Application", "configured")
        return response


def _ready_route() -> dict[str, bool]:
    """Return one payload for settings and middleware integration checks.

    Returns:
        A JSON-safe readiness marker.
    """
    return {"ready": True}


def _application_identity(
    label: _Label,
    config: ConfigRepository,
    paths: ApplicationPaths,
) -> dict[str, str]:
    """Return values from the active test application's service graph.

    Args:
        label: Service instance registered for the selected application.
        config: Application-owned configuration repository.
        paths: Application-owned root path contract.

    Returns:
        Values that demonstrate isolation between application instances.
    """
    application_name = config.get("app.name", "")
    if not isinstance(application_name, str):
        raise TypeError(_CONFIG_TYPE_ERROR)
    return {
        "label": label.value(),
        "name": application_name,
        "root": paths.base_path.name,
    }


def test_application_test_uses_container_replacement_and_temporary_root() -> (
    None
):
    """Run a real sync ASGI request with a temporary service substitution.

    The helper owns the temporary path and closes the application afterwards.
    """
    test_app = ApplicationTest(
        config={"app": {"name": "Test application"}},
        service_providers=(_LabelProvider(),),
        replacements={_Label: _ReplacementLabel()},
    )
    root = test_app.base_path
    test_app.application.router.get("/label", _label_route)

    with test_app:
        response = test_app.client.get("/label")
        assert response.status_code == _HTTP_OK
        assert response.json() == {"value": "replacement"}

    with pytest.raises(ContainerClosedError):
        test_app.application.container.make(_Label)
    assert not root.exists()


def test_application_test_passes_settings_and_middleware_to_builder() -> None:
    """Use typed settings and native middleware in the test application.

    The route crosses the production middleware and ASGI boundaries.
    """
    settings = Settings(app_name="Test builder")
    test_app = ApplicationTest(
        settings=settings,
        http_middleware=(_ResponseHeaderMiddleware,),
    )
    test_app.application.router.get("/ready", _ready_route)

    with test_app:
        response = test_app.client.get("/ready")

    assert test_app.application.settings is settings
    assert response.status_code == _HTTP_OK
    assert response.json() == {"ready": True}
    assert response.headers["x-test-application"] == "configured"


def test_application_test_discovers_trusted_provider_entry_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve discovered providers through a real synchronous ASGI request.

    ApplicationTest must use Foundation's canonical provider-aware builder.
    """
    entry_point = EntryPoint(
        name="label-provider",
        value=f"{__name__}:_LabelProvider",
        group="titanspan.providers",
    )

    def fake_entry_points(*, group: str | None = None) -> EntryPoints:
        """Return the trusted provider selected by the application builder.

        Args:
            group: Entry-point group requested during application creation.

        Returns:
            The test provider for the framework's trusted group.
        """
        assert group == "titanspan.providers"
        return EntryPoints([entry_point])

    monkeypatch.setattr(builder_module, "entry_points", fake_entry_points)
    test_app = ApplicationTest()
    test_app.application.router.get("/label", _label_route)

    with test_app:
        response = test_app.client.get("/label")

    assert response.status_code == _HTTP_OK
    assert response.json() == {"value": "production"}


@pytest.mark.anyio
async def test_async_application_test_starts_and_closes_real_asgi_app() -> None:
    """Run an async route through HTTPX2 ASGI transport and clean up.

    Foundation startup and shutdown remain the production lifecycle boundary.
    """
    test_app = AsyncApplicationTest(
        service_providers=(_LabelProvider(),),
        replacements={_Label: _ReplacementLabel()},
    )
    root = test_app.base_path

    async def label_route(label: _Label) -> dict[str, str]:
        """Return the injected label from an async endpoint.

        Args:
            label: Application service resolved by the request Container.

        Returns:
            One JSON-safe service label.
        """
        return {"value": label.value()}

    test_app.application.router.get("/label", label_route)
    async with test_app:
        response = await test_app.client.get("/label")
        assert response.status_code == _HTTP_OK
        assert response.json() == {"value": "replacement"}

    with pytest.raises(ContainerClosedError):
        test_app.application.container.make(_Label)
    assert not root.exists()


@pytest.mark.anyio
async def test_async_application_test_discovers_trusted_provider_entry_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve discovered providers through an asynchronous ASGI request.

    AsyncApplicationTest shares Foundation's canonical provider-aware builder.
    """
    entry_point = EntryPoint(
        name="label-provider",
        value=f"{__name__}:_LabelProvider",
        group="titanspan.providers",
    )

    def fake_entry_points(*, group: str | None = None) -> EntryPoints:
        """Return the trusted provider selected by the application builder.

        Args:
            group: Entry-point group requested during application creation.

        Returns:
            The test provider for the framework's trusted group.
        """
        assert group == "titanspan.providers"
        return EntryPoints([entry_point])

    monkeypatch.setattr(builder_module, "entry_points", fake_entry_points)
    test_app = AsyncApplicationTest()
    test_app.application.router.get("/label", _label_route)

    async with test_app:
        response = await test_app.client.get("/label")

    assert response.status_code == _HTTP_OK
    assert response.json() == {"value": "production"}


def test_sync_test_context_cleans_up_after_test_failure() -> None:
    """Finalize the application and temporary root when assertions fail.

    The context preserves the original test exception after cleanup.
    """
    test_app = ApplicationTest()
    root = test_app.base_path

    with test_app, pytest.raises(RuntimeError, match=_TEST_FAILURE):
        raise RuntimeError(_TEST_FAILURE)

    with pytest.raises(ContainerClosedError):
        test_app.application.container.make(_Label)
    assert not root.exists()


@pytest.mark.anyio
async def test_async_test_context_shields_cleanup_during_cancellation() -> None:
    """Run shutdown hooks after cancellation exits the test context.

    The owned temporary root is removed after async cleanup completes.
    """
    test_app = AsyncApplicationTest()
    root = test_app.base_path

    with anyio.CancelScope() as scope:
        async with test_app:
            scope.cancel()

    with pytest.raises(ContainerClosedError):
        test_app.application.container.make(_Label)
    assert not root.exists()


def test_test_client_is_unavailable_outside_its_context() -> None:
    """Require explicit client lifecycle ownership for sync tests.

    Client access fails before entry and after the context has closed.
    """
    test_app = ApplicationTest()

    with pytest.raises(RuntimeError, match="Enter the application test"):
        _ = test_app.client


def test_test_application_preserves_composition_owned_services() -> None:
    """Keep configuration, path, and Container identity with Foundation.

    Tests replace application services through providers instead.
    """
    with pytest.raises(
        ValueError, match="Replace configuration through config"
    ):
        ApplicationTest(replacements={ConfigRepository: object()})


def test_test_applications_keep_roots_config_and_replacements_independent(
    tmp_path: Path,
) -> None:
    """Keep two application roots, settings, and replacements independent.

    Args:
        tmp_path: Parent directory supplied by pytest for both roots.
    """
    first = ApplicationTest(
        base_path=tmp_path / "first",
        config={"app": {"name": "First application"}},
        service_providers=(_LabelProvider(),),
        replacements={_Label: _ReplacementLabel()},
    )
    second = ApplicationTest(
        base_path=tmp_path / "second",
        config={"app": {"name": "Second application"}},
        service_providers=(_LabelProvider(),),
        replacements={_Label: _ProductionLabel()},
    )
    first.application.router.get("/identity", _application_identity)
    second.application.router.get("/identity", _application_identity)

    with first:
        first_response = first.client.get("/identity")
    with second:
        second_response = second.client.get("/identity")

    assert first_response.json() == {
        "label": "replacement",
        "name": "First application",
        "root": "first",
    }
    assert second_response.json() == {
        "label": "production",
        "name": "Second application",
        "root": "second",
    }
