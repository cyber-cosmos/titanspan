"""Verify Console uses the canonical application service registry.

Tests exercise the production parser, provider, Container, and Foundation
lifecycle together.
"""

from types import SimpleNamespace
from typing import Annotated

import pytest

from titanspan.console import Argument, Console, TerminalOutput
from titanspan.console.testing import ConsoleTester
from titanspan.contracts import (
    CommandRegistrar,
    ConfigRepository,
    ConsoleOutput,
    ServiceProvider,
    ServiceRegistry,
)
from titanspan.foundation import Application

pytestmark = pytest.mark.integration
_APPLICATION_NAME = "Console integration"


class _CommandDependency:
    """Represent one service owned by an installed application provider.

    The Console command resolves this service through Foundation's Container.
    """

    def __init__(self, value: str) -> None:
        """Retain the value returned by the provider-owned service.

        Args:
            value: Stable value used by the integration assertion.
        """
        self.value = value

    value: str


class _CommandProvider:
    """Register a service required by an installed Console command.

    Foundation discovers this provider through its public entry-point API.
    """

    def __init__(self, dependency: _CommandDependency) -> None:
        """Retain the instance registered during application composition.

        Args:
            dependency: Shared service instance used by the command.
        """
        self._dependency = dependency

    def register(self, container: ServiceRegistry) -> None:
        """Register the command dependency in the application Container.

        Args:
            container: Canonical registration boundary for this Application.
        """
        container.instance(_CommandDependency, self._dependency)

    _dependency: _CommandDependency


def test_command_resolves_services_from_its_application() -> None:
    """Run an injected command inside one complete application lifecycle.

    The test checks shared service identity and startup cleanup.
    """
    lifecycle: list[str] = []
    resolved_outputs: list[ConsoleOutput] = []
    output = TerminalOutput()

    def make_application(provider: ServiceProvider) -> Application:
        """Build an app with Console services in its canonical Container.

        The command host supplies its output provider before composition.
        """
        return (
            Application.builder()
            .with_config({"app": {"name": _APPLICATION_NAME}})
            .with_service_provider(provider)
            .on_startup(lambda: lifecycle.append("startup"))
            .on_shutdown(lambda: lifecycle.append("shutdown"))
            .build()
        )

    console = Console(
        output=output,
        application_factory=make_application,
    )
    registrar: CommandRegistrar = console

    @console.command("inspect")
    def inspect_application(
        label: Annotated[str, Argument()],
        config: ConfigRepository,
        terminal: ConsoleOutput,
    ) -> None:
        """Observe injected services and report one configured value.

        The test records the resolved output service for identity checks.
        """
        resolved_outputs.append(terminal)
        terminal.write(f"{label}: {config.get('app.name')}")

    assert callable(registrar.register_command)
    result = ConsoleTester(console).invoke(["inspect", "ready"])

    assert result.exit_code == 0
    assert len(resolved_outputs) == 1
    assert resolved_outputs[0] is output
    assert lifecycle == ["startup", "shutdown"]


def test_default_factory_loads_application_provider_entry_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve installed component services through the default factory.

    The test uses real Foundation provider discovery and Container resolution.
    """
    dependency = _CommandDependency("provider service")
    provider: ServiceProvider = _CommandProvider(dependency)
    entry = SimpleNamespace(
        name="application-services",
        value="application.providers:provider",
        load=lambda: provider,
    )

    def load_entries(*, group: str) -> list[SimpleNamespace]:
        """Return one trusted provider from the framework entry-point group.

        The test replaces only package metadata lookup.
        """
        assert group == "titanspan.providers"
        return [entry]

    monkeypatch.setattr(
        "titanspan.foundation.builder.entry_points",
        load_entries,
    )
    console = Console()

    @console.command("provider")
    def show_provider_service(
        command_dependency: _CommandDependency,
        output: ConsoleOutput,
    ) -> None:
        """Write a value from the installed provider service.

        Args:
            command_dependency: Instance registered during app composition.
            output: Console output resolved from the same application.
        """
        output.write(command_dependency.value)

    result = ConsoleTester(console).invoke(["provider"])

    assert result.exit_code == 0
    assert "provider service" in result.stdout
