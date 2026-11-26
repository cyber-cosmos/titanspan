"""Test typed settings behavior used during application construction.

Environment parsing is isolated here; ASGI and dependency lifecycle behavior
is covered by the integration suite.
"""

from importlib.metadata import EntryPoint, EntryPoints
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from dishka import Provider

import titanspan.foundation.builder as builder_module
from titanspan.config import (
    ConfigValueError,
    Settings,
    SettingsValidationError,
)
from titanspan.contracts.container import ServiceRegistry
from titanspan.foundation import Application
from titanspan.foundation.exceptions import ProviderDiscoveryError

if TYPE_CHECKING:
    from titanspan.foundation.builder import ApplicationBuilder


class _DiscoveredService:
    """Identify one service contributed by a discovered provider.

    The value lets the test assert that entry-point discovery reaches the
    canonical application container.
    """

    def __init__(self, value: str) -> None:
        """Retain the provider marker used by the registration assertion.

        Args:
            value: Marker configured by the discovered provider.
        """
        self.value = value

    value: str


class _DiscoveredProvider:
    """Register one service through the native provider contract.

    The class is loaded through a synthetic Python entry point in tests.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Contribute a service instance to application composition.

        Args:
            container: Canonical application registry.
        """
        container.instance(_DiscoveredService, _DiscoveredService("plugin"))


_DISCOVERED_PROVIDER_INSTANCE = _DiscoveredProvider()


class _CountingCustomizer:
    """Count calls made by the logging channel customization boundary.

    This fixture verifies that builder hooks reach the configured manager.
    """

    def __init__(self) -> None:
        """Start with no customized channels.

        The count increments when a native channel is first initialized.
        """
        self.calls = 0

    def customize(self, logger: object) -> None:
        """Count one logger setup without depending on backend types.

        Args:
            logger: Native logger supplied by the framework.
        """
        _ = logger
        self.calls += 1

    calls: int


pytestmark = pytest.mark.unit


def test_settings_read_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read typed values from the configured environment variable prefix.

    Args:
        monkeypatch: Pytest fixture that restores process environment changes.
    """
    monkeypatch.setenv("TITANSPAN_DEBUG", "true")

    assert Settings().debug is True


def test_settings_reject_invalid_boolean_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject malformed booleans rather than silently accepting them.

    Args:
        monkeypatch: Pytest fixture that restores process environment changes.
    """
    monkeypatch.setenv("TITANSPAN_DEBUG", "sometimes")

    with pytest.raises(SettingsValidationError):
        Settings()


def test_application_exposes_its_typed_settings_lazily(
    tmp_path: Path,
) -> None:
    """Expose the exact Settings instance used during bootstrap.

    Args:
        tmp_path: Isolated temporary directory for application sources.
    """
    settings = Settings(app_name="Configured")
    application = Application(base_path=tmp_path, settings=settings)

    assert application.settings is settings


@pytest.mark.anyio
async def test_application_builder_sets_paths_environment_and_provider(
    tmp_path: Path,
) -> None:
    """Build an application with explicit bootstrap inputs.

    The builder uses the same Application composition root and exposes its
    configured environment and conventional paths.
    """
    application = (
        Application.builder()
        .with_base_path(tmp_path)
        .with_config({"app": {"name": "Builder", "env": "testing"}})
        .build()
    )

    assert application.base_path == tmp_path.resolve()
    assert application.path("routes", "web.py") == (
        tmp_path / "routes" / "web.py"
    )
    assert application.config_path == tmp_path / "config"
    assert application.storage_path == tmp_path / "storage"
    assert application.bootstrap_path == tmp_path / "bootstrap"
    assert application.environment == "testing"
    assert application.is_environment("development", "TESTING")
    assert not application.is_environment()
    assert application.debug is False

    await application.shutdown()


@pytest.mark.anyio
async def test_application_builder_discovers_configured_provider_entry_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load only providers from the explicitly selected entry-point group.

    The provider contributes its instance through the application's native
    ServiceRegistry.
    """
    entry_point = EntryPoint(
        name="sample",
        value=f"{__name__}:{_DiscoveredProvider.__name__}",
        group="example.titanspan.providers",
    )

    def fake_entry_points(*, group: str | None = None) -> EntryPoints:
        """Return one deterministic provider entry point.

        Args:
            group: Entry-point group requested by the builder.

        Returns:
            The provider entry point when its group matches.
        """
        assert group == "example.titanspan.providers"
        return EntryPoints([entry_point])

    monkeypatch.setattr(builder_module, "entry_points", fake_entry_points)
    builder: ApplicationBuilder = Application.builder().discover_providers(
        group="example.titanspan.providers"
    )
    builder.discover_providers(group="example.titanspan.providers")
    application = builder.build()

    assert application.make(_DiscoveredService).value == "plugin"

    await application.shutdown()


@pytest.mark.anyio
async def test_application_builder_loads_provider_instances_and_backend_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load an installed provider instance through its trusted entry point.

    The explicit backend adapter remains optional and is passed to the
    existing application integration boundary.
    """
    entry_point = EntryPoint(
        name="instance",
        value=f"{__name__}:_DISCOVERED_PROVIDER_INSTANCE",
        group="example.instance.providers",
    )

    def fake_entry_points(*, group: str | None = None) -> EntryPoints:
        """Return the selected provider instance entry point.

        Args:
            group: Entry-point group requested by the builder.

        Returns:
            The provider instance entry point when its group matches.
        """
        assert group == "example.instance.providers"
        return EntryPoints([entry_point])

    monkeypatch.setattr(builder_module, "entry_points", fake_entry_points)
    application = (
        Application.builder()
        .discover_providers(group="example.instance.providers")
        .with_fastapi_provider(Provider())
        .build()
    )

    assert application.make(_DiscoveredService).value == "plugin"
    await application.shutdown()


@pytest.mark.anyio
async def test_builder_uses_native_provider_and_hooks() -> None:
    """Compose settings, providers, logging, and callbacks on one app.

    The builder passes every option through the canonical Application
    composition root without creating a second service registry.
    """
    events: list[str] = []
    settings = Settings(app_name="Builder")
    customizer = _CountingCustomizer()

    def startup() -> None:
        """Record the builder's startup hook.

        The event order confirms the callback runs during application boot.
        """
        events.append("startup")

    async def shutdown() -> None:
        """Record the builder's asynchronous cleanup hook.

        The event order confirms the callback runs during shutdown.
        """
        events.append("shutdown")

    def operation() -> str:
        """Resolve a native service and initialize configured logging.

        Returns:
            A marker contributed by the configured provider.
        """
        application.logging.channel()
        return application.make(_DiscoveredService).value

    application = (
        Application.builder()
        .with_base_path(".")
        .with_settings(settings)
        .with_service_provider(_DiscoveredProvider())
        .with_logging(
            {
                "default": "memory",
                "channels": {
                    "memory": {
                        "driver": "memory",
                        "tap": ["count"],
                    },
                },
            }
        )
        .with_logging_customizer("count", customizer)
        .on_startup(startup)
        .on_shutdown(shutdown)
        .build()
    )

    assert application.settings is settings
    assert await application.run(operation) == "plugin"
    assert customizer.calls == 1
    assert events == ["startup", "shutdown"]


@pytest.mark.anyio
async def test_application_rejects_invalid_environment_values() -> None:
    """Reject invalid application environment values at construction.

    Environment names are configuration metadata and must remain non-empty
    strings for stable environment checks.
    """
    with pytest.raises(ConfigValueError, match=r"app\.env"):
        Application(config={"app": {"env": 12}})

    with pytest.raises(ValueError, match="environment"):
        Application(config={"app": {"env": "  "}})

    application = Application()
    with pytest.raises(ValueError, match="environment"):
        application.is_environment("")
    await application.shutdown()


def test_application_builder_entry_point_load_failure_is_actionable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wrap entry-point import failures in a native discovery error.

    The diagnostic names the selected entry point and preserves its original
    cause for trusted application troubleshooting.
    """
    entry_point = EntryPoint(
        name="missing",
        value="missing_titanspan_provider.module:Provider",
        group="example.missing.providers",
    )

    def fake_entry_points(*, group: str | None = None) -> EntryPoints:
        """Return an entry point that cannot be imported.

        Args:
            group: Entry-point group requested by the builder.

        Returns:
            One entry point with an unavailable module target.
        """
        assert group == "example.missing.providers"
        return EntryPoints([entry_point])

    monkeypatch.setattr(builder_module, "entry_points", fake_entry_points)

    with pytest.raises(ProviderDiscoveryError, match="missing") as error:
        Application.builder().discover_providers(
            group="example.missing.providers"
        )

    assert isinstance(error.value.__cause__, ModuleNotFoundError)


def test_application_builder_rejects_invalid_provider_entry_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject entry points that do not produce a service provider.

    Discovery fails before an application is constructed and identifies the
    selected entry point without exposing provider internals.
    """
    entry_point = EntryPoint(
        name="invalid",
        value=f"{__name__}:{_DiscoveredService.__name__}",
        group="example.invalid.providers",
    )

    def fake_entry_points(*, group: str | None = None) -> EntryPoints:
        """Return one invalid provider for the selected group.

        Args:
            group: Entry-point group requested by the builder.

        Returns:
            One invalid class entry point.
        """
        assert group == "example.invalid.providers"
        return EntryPoints([entry_point])

    monkeypatch.setattr(builder_module, "entry_points", fake_entry_points)

    with pytest.raises(ProviderDiscoveryError, match="invalid"):
        Application.builder().discover_providers(
            group="example.invalid.providers"
        )
