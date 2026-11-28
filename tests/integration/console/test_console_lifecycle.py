"""Verify Console uses the canonical application service registry.

Tests exercise the production parser, provider, Container, and Foundation
lifecycle together.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Annotated

import anyio
import pytest

from titanspan import app
from titanspan._application_context import (
    active_application_context,
    bind_application_context,
)
from titanspan.console import (
    Argument,
    CommandInvocationError,
    Console,
    ConsoleExitError,
    ConsoleRuntimeError,
    ConsoleServiceProvider,
    TerminalOutput,
)
from titanspan.console.testing import ConsoleTester
from titanspan.contracts import (
    CommandRegistrar,
    ConfigRepository,
    ConsoleOutput,
    ServiceProvider,
    ServiceRegistry,
)
from titanspan.facades import Config
from titanspan.foundation import Application

pytestmark = pytest.mark.integration
_APPLICATION_NAME = "Console integration"
_UNEXPECTED_FACTORY_MESSAGE = "Active execution created another app."
_COMMAND_FAILURE_SENTINEL = "synthetic-command-error-marker"
_PROGRAMMATIC_EXIT_CODE = 17


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
    resolved_configurations: list[ConfigRepository] = []
    active_applications: list[Application] = []
    applications: list[Application] = []
    output = TerminalOutput()

    def make_application(provider: ServiceProvider) -> Application:
        """Build an app with Console services in its canonical Container.

        The command host supplies its output provider before composition.
        """
        application = (
            Application.builder()
            .with_config({"app": {"name": _APPLICATION_NAME}})
            .with_service_provider(provider)
            .on_startup(lambda: lifecycle.append("startup"))
            .on_shutdown(lambda: lifecycle.append("shutdown"))
            .build()
        )
        applications.append(application)
        return application

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

        The test compares injected, facade, and helper service access.
        """
        resolved_outputs.append(terminal)
        resolved_configurations.append(Config.repository())
        active_applications.append(app())
        terminal.write(f"{label}: {Config.get('app.name')}")
        assert config.get("app.name") == Config.get("app.name")

    assert callable(registrar.register_command)
    result = ConsoleTester(console).invoke(["inspect", "ready"])

    assert result.exit_code == 0
    assert len(resolved_outputs) == 1
    assert resolved_outputs[0] is output
    assert resolved_configurations == [applications[0].config]
    assert active_applications == applications
    assert active_application_context() is None
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


def test_default_factory_uses_conventional_application_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Execute commands through the application's canonical factory.

    The fixed bootstrap convention keeps Console and HTTP composition aligned.
    """
    app_source = '''"""Build the Console integration application."""

from pathlib import Path

from titanspan import Application
from titanspan.contracts import ServiceProvider

from .settings import APPLICATION_NAME


def create_application(
    *additional_providers: ServiceProvider,
) -> Application:
    """Build one application with trusted providers and test settings.

    Args:
        *additional_providers: Host providers registered by Console.

    Returns:
        One unstarted application owned by Foundation.
    """
    builder = (
        Application.builder()
        .with_base_path(Path(__file__).resolve().parents[1])
        .with_config({"app": {"name": APPLICATION_NAME}})
        .discover_providers()
    )
    for provider in additional_providers:
        builder.with_service_provider(provider)
    return builder.build()
'''
    applications: list[Application] = []
    for application_name in ("console-first", "console-second"):
        application_root = tmp_path / application_name
        bootstrap = application_root / "bootstrap"
        bootstrap.mkdir(parents=True)
        (bootstrap / "settings.py").write_text(
            f'"""Define settings for {application_name}."""\n'
            f'APPLICATION_NAME: str = "{application_name}"\n',
            encoding="utf-8",
        )
        (bootstrap / "app.py").write_text(
            app_source,
            encoding="utf-8",
        )
        monkeypatch.chdir(application_root)
        console = Console()

        @console.command("inspect")
        def inspect_application(
            config: ConfigRepository,
            output: ConsoleOutput,
        ) -> None:
            """Write the application name selected by its bootstrap.

            Args:
                config: Configuration composed by the selected factory.
                output: Output service registered in that same application.
            """
            active = active_application_context()
            assert active is not None
            assert isinstance(active.application, Application)
            applications.append(active.application)
            output.write(str(config.get("app.name")))

        result = ConsoleTester(console).invoke(["inspect"])
        cached_console = Console()
        cached_console.command("inspect")(inspect_application)
        cached_result = ConsoleTester(cached_console).invoke(["inspect"])

        assert result.exit_code == 0
        assert application_name in result.stdout
        assert cached_result.exit_code == 0
        assert application_name in cached_result.stdout
        assert applications[0] is not applications[1]
        assert active_application_context() is None


@pytest.mark.parametrize(
    ("application_source", "expected_message"),
    [
        (
            '"""Omit the required factory export."""\n'
            'APPLICATION_NAME: str = "invalid"\n',
            "must define a callable create_application",
        ),
        (
            '"""Fail while loading the trusted bootstrap."""\n'
            'raise RuntimeError("bootstrap failed")\n',
            "The application bootstrap could not be loaded",
        ),
        (
            '"""Return an invalid application value."""\n'
            "from titanspan.contracts import ServiceProvider\n\n"
            "def create_application(\n"
            "    *additional_providers: ServiceProvider,\n"
            ") -> object:\n"
            '    """Return a value that Foundation cannot run."""\n'
            "    return object()\n",
            "must return a native Application",
        ),
    ],
)
def test_default_factory_rejects_invalid_application_bootstraps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_source: str,
    expected_message: str,
) -> None:
    """Fail safely when the selected application bootstrap is invalid.

    Args:
        tmp_path: Isolated application root for one failure case.
        monkeypatch: Restores process working-directory state.
        application_source: Source loaded from the fixed bootstrap path.
        expected_message: Safe framework-owned failure description.
    """
    bootstrap = tmp_path / "bootstrap"
    bootstrap.mkdir()
    (bootstrap / "app.py").write_text(
        application_source,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    console = Console(show_exception_details=True)

    @console.command("inspect")
    def inspect_application(output: ConsoleOutput) -> None:
        """Run after bootstrap validation succeeds.

        Args:
            output: Console output owned by the command application.
        """
        output.write("inspected")

    result = ConsoleTester(console).invoke(["inspect"])

    assert result.exit_code == 1
    assert expected_message in " ".join(result.stderr.split())


def test_default_factory_rejects_bootstrap_symlinks_outside_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a conventional bootstrap file that escapes its root.

    The Console must not execute a file reached through an external symlink.
    """
    external_file = tmp_path / "external_app.py"
    external_file.write_text(
        '"""A bootstrap outside the selected application root."""\n'
        'raise RuntimeError("outside bootstrap executed")\n',
        encoding="utf-8",
    )
    application_root = tmp_path / "application"
    bootstrap = application_root / "bootstrap"
    bootstrap.mkdir(parents=True)
    (bootstrap / "app.py").symlink_to(external_file)
    monkeypatch.chdir(application_root)
    console = Console()

    @console.command("inspect")
    def inspect_application(output: ConsoleOutput) -> None:
        """Run only when no invalid bootstrap file exists.

        Args:
            output: Console output owned by the command application.
        """
        output.write("inspected")

    result = ConsoleTester(console).invoke(["inspect"])

    assert result.exit_code == 1
    assert "ConsoleRuntimeError" in result.stderr
    assert "outside bootstrap executed" not in result.stderr


@pytest.mark.anyio
async def test_async_execution_reuses_the_active_application() -> None:
    """Execute a registered command without bootstrapping another graph.

    The command runs inside the existing app and resolves its current services.
    """
    dependency = _CommandDependency("active application")
    output = TerminalOutput()
    application = (
        Application.builder()
        .with_service_provider(ConsoleServiceProvider(output))
        .with_service_provider(_CommandProvider(dependency))
        .build()
    )
    factory_calls: list[bool] = []
    observations: list[
        tuple[int, _CommandDependency, ConsoleOutput, Application]
    ] = []

    def unexpected_application_factory(
        provider: ServiceProvider,
    ) -> Application:
        """Fail if active execution builds an unrelated application.

        Args:
            provider: Console service provider that should not be installed.

        Raises:
            AssertionError: If active execution requests a new application.
        """
        del provider
        factory_calls.append(True)
        message = _UNEXPECTED_FACTORY_MESSAGE
        raise AssertionError(message)

    console = Console(
        output=output,
        application_factory=unexpected_application_factory,
    )
    commands = console.add_group("maintenance")

    @commands.command("inspect")
    def inspect(
        value: Annotated[int, Argument()],
        command_dependency: _CommandDependency,
        command_output: ConsoleOutput,
    ) -> None:
        """Record values and the active app from a sync command.

        Args:
            value: Explicitly supplied command input.
            command_dependency: Application-owned dependency.
            command_output: Output registered in the active application.
        """
        observations.append(
            (value, command_dependency, command_output, app()),
        )

    async with application:
        status = await console.execute_async(
            "maintenance inspect",
            {"value": 17},
        )

    assert status == 0
    assert observations == [(17, dependency, output, application)]
    assert factory_calls == []


@pytest.mark.anyio
async def test_async_execution_owns_standalone_lifecycle_and_exit_status() -> (
    None
):
    """Use Foundation startup and shutdown outside the CLI entry point.

    An explicit command exit status remains available to async callers.
    """
    lifecycle: list[str] = []
    invoked_output: list[ConsoleOutput] = []
    output = TerminalOutput()

    def make_application(provider: ServiceProvider) -> Application:
        """Build an application with Console output and lifecycle hooks.

        Args:
            provider: Output provider owned by this Console instance.

        Returns:
            Application used for one programmatic command execution.
        """
        return (
            Application.builder()
            .with_service_provider(provider)
            .on_startup(lambda: lifecycle.append("startup"))
            .on_shutdown(lambda: lifecycle.append("shutdown"))
            .build()
        )

    console = Console(
        output=output,
        application_factory=make_application,
    )

    @console.command("stop", with_application=True)
    async def stop(command_output: ConsoleOutput) -> None:
        """Request one process status from an async command handler.

        Args:
            command_output: Output service from the Console provider.
        """
        invoked_output.append(command_output)
        raise ConsoleExitError(_PROGRAMMATIC_EXIT_CODE)

    status = await console.execute_async("stop")

    assert status == _PROGRAMMATIC_EXIT_CODE
    assert invoked_output == [console.output]
    assert invoked_output[0] is console.output
    assert lifecycle == ["startup", "shutdown"]


@pytest.mark.anyio
async def test_async_execution_rejects_unknown_and_missing_values() -> None:
    """Reject invalid programmatic input before application startup.

    Python callers must provide every required declared command value.
    """
    console = Console()

    @console.command("inspect", with_application=False)
    def inspect(label: Annotated[str, Argument()]) -> None:
        """Accept one declared value for validation of invocation metadata.

        Args:
            label: Required command input.
        """
        del label

    with pytest.raises(CommandInvocationError):
        await console.execute_async("missing")
    with pytest.raises(CommandInvocationError):
        await console.execute_async("inspect")
    with pytest.raises(CommandInvocationError):
        await console.execute_async("inspect", {"other": "value"})


@pytest.mark.anyio
async def test_async_execution_reports_safe_failure_status(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Return status one without printing arbitrary exception text.

    Foundation reports the failure while Console keeps its terminal message
    limited to the command path and exception type.
    """
    console = Console()

    @console.command("fail")
    async def fail() -> None:
        """Raise an error containing a synthetic sensitive marker.

        The command output must not include the exception message.
        """
        raise RuntimeError(_COMMAND_FAILURE_SENTINEL)

    status = await console.execute_async("fail")
    terminal = capsys.readouterr()

    assert status == 1
    assert "RuntimeError" in terminal.err
    assert _COMMAND_FAILURE_SENTINEL not in terminal.err


@pytest.mark.anyio
async def test_async_execution_rejects_an_invalid_active_app_context() -> None:
    """Reject an active context that does not own its Container.

    Programmatic execution must not silently create a second service graph.
    """
    application = Application()
    other_application = Application()
    console = Console()

    @console.command("noop")
    async def noop() -> None:
        """Provide a command that cannot run in an invalid context.

        The test asserts that Console rejects the active app first.
        """
        pytest.fail("The invalid active context reached the command.")

    with (
        bind_application_context(application, other_application.container),
        pytest.raises(ConsoleRuntimeError, match="invalid active"),
    ):
        await console.execute_async("noop")


@pytest.mark.anyio
async def test_async_execution_cancellation_shuts_down_owned_application() -> (
    None
):
    """Propagate cancellation after the command application cleans up.

    The command remains application-owned until its async handler exits.
    """
    lifecycle: list[str] = []
    started = anyio.Event()

    def make_application(provider: ServiceProvider) -> Application:
        """Create an application whose cleanup is visible to the test.

        Args:
            provider: Console output service for the command execution.

        Returns:
            A fresh application with startup and shutdown callbacks.
        """
        return (
            Application.builder()
            .with_service_provider(provider)
            .on_startup(lambda: lifecycle.append("startup"))
            .on_shutdown(lambda: lifecycle.append("shutdown"))
            .build()
        )

    console = Console(application_factory=make_application)

    @console.command("wait")
    async def wait_for_cancellation() -> None:
        """Wait until the command receives cancellation.

        The test uses an event to signal command startup.
        """
        started.set()
        await anyio.sleep_forever()

    async def invoke() -> None:
        """Run one command inside the task group.

        Cancellation must pass through the Console API.
        """
        _ = await console.execute_async("wait")

    with anyio.CancelScope() as cancellation:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(invoke)
            await started.wait()
            cancellation.cancel()

    assert cancellation.cancel_called
    assert lifecycle == ["startup", "shutdown"]
