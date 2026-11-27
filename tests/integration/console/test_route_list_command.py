"""Verify route inspection uses the shared Console and Application lifecycles.

The test uses the production command registry, Router, Container, and
Foundation startup path.
"""

import json
import sys
from collections.abc import Iterable, Sequence
from contextlib import AbstractContextManager
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from titanspan._application_context import active_application_context
from titanspan.console.cli import console
from titanspan.console.testing import ConsoleTester
from titanspan.contracts import ProgressTask, ServiceProvider
from titanspan.foundation import Application

pytestmark = pytest.mark.integration
_HTTP_OK = 200


class _RecordingOutput:
    """Capture native Console output during a real command invocation.

    The production parser and Foundation lifecycle remain active.
    """

    def __init__(self) -> None:
        """Create empty buffers for command output.

        The registered route command uses the table buffer.
        """
        self.tables: list[
            tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]
        ] = []
        self.messages: list[str] = []
        self.errors: list[str] = []

    def write(self, message: str) -> None:
        """Accept plain text written by a command.

        Args:
            message: Text supplied through the shared Console contract.
        """
        self.messages.append(message)

    def write_error(self, message: str) -> None:
        """Capture plain error text written by a command.

        Args:
            message: Error text supplied through the shared Console contract.
        """
        self.errors.append(message)

    def table(
        self,
        headers: Sequence[str],
        rows: Iterable[Sequence[str]],
    ) -> None:
        """Store an immutable snapshot of a rendered table.

        Args:
            headers: Ordered native table headings.
            rows: Values emitted by the route inspection command.
        """
        self.tables.append(
            (
                tuple(headers),
                tuple(tuple(row) for row in rows),
            )
        )

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        """Return the supplied default for unused confirmation prompts.

        Args:
            prompt: Confirmation text that the command would display.
            default: Safe answer used by this non-interactive test output.

        Returns:
            The explicit default answer.
        """
        _ = prompt
        return default

    def progress(
        self,
        total: int,
        description: str,
    ) -> AbstractContextManager[ProgressTask]:
        """Reject progress displays because this test does not use them.

        Args:
            total: Number of expected steps.
            description: Human-readable progress label.

        Raises:
            AssertionError: Progress output is not part of this test.
        """
        _ = total, description
        raise AssertionError

    tables: list[tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]]
    messages: list[str]
    errors: list[str]


def cached_health() -> dict[str, str]:
    """Return a small payload for route-cache command coverage.

    Its module-level identity can be represented in the JSON snapshot.
    """
    return {"status": "ready"}


def test_route_list_uses_the_application_route_catalog(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """List routes registered on the same Router used by Foundation.

    The real Console starts an Application and injects its route catalog.
    """
    assert "route:list" in console.command_names
    output = _RecordingOutput()
    applications: list[Application] = []
    lifecycle: list[str] = []

    def make_application(provider: ServiceProvider) -> Application:
        """Build one real application and add a route before startup.

        Args:
            provider: Console provider that owns the output contract.

        Returns:
            An application whose route collection is ready for inspection.
        """
        application = (
            Application.builder()
            .with_base_path(tmp_path)
            .with_service_provider(provider)
            .on_shutdown(lambda: lifecycle.append("shutdown"))
            .build()
        )
        application.router.get("/health", health).name("health")
        applications.append(application)
        return application

    def health() -> dict[str, str]:
        """Return a stable value for the registered test endpoint.

        Returns:
            A small response value that the route list never evaluates.
        """
        return {"status": "ready"}

    monkeypatch.setattr(console, "_output", output)
    monkeypatch.setattr(console, "_application_factory", make_application)

    result = ConsoleTester(console).invoke(["route:list"])

    assert result.exit_code == 0
    assert output.tables == [
        (
            (
                "METHOD",
                "DOMAIN",
                "URI",
                "NAME",
                "ACTION",
                "MIDDLEWARE",
            ),
            (("GET", "-", "/health", "health", "health", "-"),),
        )
    ]
    assert len(applications) == 1
    assert lifecycle == ["shutdown"]
    assert active_application_context() is None


def test_about_command_reports_framework_and_python_versions() -> None:
    """Run the application-free command through the native parser.

    The command reports framework metadata without building an Application.
    """
    result = ConsoleTester(console).invoke(["about"])

    assert result.exit_code == 0
    assert "Titanspan " in result.stdout
    assert "Python " in result.stdout


def test_route_cache_commands_use_the_active_application_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Write and clear metadata through the production Console lifecycle.

    The cache is an inspection snapshot and does not replace route discovery.
    """
    output = _RecordingOutput()

    def make_application(provider: ServiceProvider) -> Application:
        """Build an application with one stable route action.

        Args:
            provider: Console provider contributing the output service.

        Returns:
            An application rooted in the isolated test directory.
        """
        application = (
            Application.builder()
            .with_base_path(tmp_path)
            .with_service_provider(provider)
            .build()
        )
        application.router.get("/health", cached_health).name("health")
        return application

    monkeypatch.setattr(console, "_output", output)
    monkeypatch.setattr(console, "_application_factory", make_application)

    cached = ConsoleTester(console).invoke(["route:cache"])
    cache_path = tmp_path / "bootstrap" / "cache" / "routes.json"
    document = json.loads(cache_path.read_text(encoding="utf-8"))

    assert cached.exit_code == 0
    assert document["routes"][0]["path"] == "/health"
    assert any("still runs at startup" in item for item in output.messages)

    cleared = ConsoleTester(console).invoke(["route:clear"])

    assert cleared.exit_code == 0
    assert not cache_path.exists()
    assert active_application_context() is None


def test_event_commands_use_configured_modules_and_application_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Use the Events APIs through the shared Console lifecycle.

    Discovery and manifest commands use the selected application's root.
    """
    (tmp_path / "routes").mkdir()
    output = _RecordingOutput()
    configuration = {
        "events": {
            "discovery_modules": [
                "tests.unit.events._discovery_fixture",
            ],
            "manifest_path": "bootstrap/cache/events.json",
        },
    }

    def make_application(provider: ServiceProvider) -> Application:
        """Build one command application with trusted event declarations.

        Args:
            provider: Console provider for the shared output service.

        Returns:
            Application rooted in the isolated test project.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(configuration)
            .with_service_provider(provider)
            .build()
        )

    monkeypatch.setattr(console, "_output", output)
    monkeypatch.setattr(console, "_application_factory", make_application)
    manifest_path = tmp_path / "bootstrap" / "cache" / "events.json"

    listed = ConsoleTester(console).invoke(["event:list"])
    cached = ConsoleTester(console).invoke(["event:cache"])
    manifest_created = manifest_path.is_file()
    cleared = ConsoleTester(console).invoke(["event:clear"])

    assert listed.exit_code == 0
    assert output.tables[-1][0] == ("EVENT", "LISTENER", "KIND")
    assert any("FixtureEvent" in row[0] for row in output.tables[-1][1])
    assert cached.exit_code == 0
    assert "cached" in output.messages[-2]
    assert manifest_created
    assert cleared.exit_code == 0
    assert not manifest_path.exists()
    assert active_application_context() is None


def test_event_cache_commands_require_a_configured_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reject event cache operations when no path is configured.

    The commands do not invent a second cache location.
    """
    (tmp_path / "routes").mkdir()
    output = _RecordingOutput()

    def make_application(provider: ServiceProvider) -> Application:
        """Build an app with the normal empty Events configuration.

        Args:
            provider: Console provider for the shared output service.

        Returns:
            Application rooted in the isolated test directory.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_service_provider(provider)
            .build()
        )

    monkeypatch.setattr(console, "_output", output)
    monkeypatch.setattr(console, "_application_factory", make_application)

    cached = ConsoleTester(console).invoke(["event:cache"])
    cleared = ConsoleTester(console).invoke(["event:clear"])

    assert cached.exit_code == 1
    assert cleared.exit_code == 1
    assert output.errors == [
        "Set events.manifest_path before caching event discovery.",
        "Set events.manifest_path before clearing event discovery.",
    ]
    assert active_application_context() is None


def test_controller_generator_creates_an_executable_application_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Generate and execute a controller through real Foundation routing.

    The generated module uses native HTTP contracts and the selected root.
    """
    (tmp_path / "routes").mkdir()
    output = _RecordingOutput()

    def make_application(provider: ServiceProvider) -> Application:
        """Build a Console application rooted in the test project.

        Args:
            provider: Console provider for the shared output service.

        Returns:
            An application used for one generator command lifecycle.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_service_provider(provider)
            .build()
        )

    monkeypatch.setattr(console, "_output", output)
    monkeypatch.setattr(console, "_application_factory", make_application)

    generated = ConsoleTester(console).invoke(
        ["make:controller", "reports.ReportController"],
    )
    controller_path = (
        tmp_path / "app" / "controllers" / "reports" / "report_controller.py"
    )
    assert generated.exit_code == 0
    assert controller_path.is_file()

    specification = spec_from_file_location(
        "_generated_report_controller",
        controller_path,
    )
    assert specification is not None
    assert specification.loader is not None
    module = module_from_spec(specification)
    monkeypatch.setitem(sys.modules, specification.name, module)
    specification.loader.exec_module(module)

    application = Application(base_path=tmp_path)
    application.router.get("/reports", (module.ReportController, "index"))
    with TestClient(application.asgi) as client:
        response = client.get("/reports")

    assert response.status_code == _HTTP_OK
    assert response.json() == {"resource": "Report"}
    assert active_application_context() is None


@pytest.mark.parametrize(
    ("command", "name", "event_option", "relative_path"),
    [
        (
            "make:middleware",
            "RequestId",
            (),
            "app/middleware/request_id_middleware.py",
        ),
        (
            "make:provider",
            "Metrics",
            (),
            "app/providers/metrics_service_provider.py",
        ),
        (
            "make:command",
            "Reindex",
            (),
            "app/commands/reindex_command.py",
        ),
        (
            "make:event",
            "DocumentReady",
            (),
            "app/events/document_ready_event.py",
        ),
        (
            "make:listener",
            "SendNotice",
            ("--event", "app.events.DocumentReadyEvent"),
            "app/listeners/send_notice_listener.py",
        ),
        ("make:test", "documents", (), "tests/test_documents.py"),
    ],
)
def test_artifact_commands_generate_under_the_selected_application_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    name: str,
    event_option: tuple[str, ...],
    relative_path: str,
) -> None:
    """Run each built-in generator through real Console composition.

    Args:
        monkeypatch: Isolate the Console output and app factory.
        tmp_path: Application root supplied by pytest.
        command: Registered native artifact command.
        name: Artifact name passed through the real parser.
        event_option: Optional listener event declaration.
        relative_path: Expected path under the active application root.
    """
    (tmp_path / "routes").mkdir()
    output = _RecordingOutput()

    def make_application(provider: ServiceProvider) -> Application:
        """Build a real application with the selected root and output.

        Args:
            provider: Console provider registered before Container setup.

        Returns:
            An unstarted application for one command invocation.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_service_provider(provider)
            .build()
        )

    monkeypatch.setattr(console, "_output", output)
    monkeypatch.setattr(console, "_application_factory", make_application)

    result = ConsoleTester(console).invoke(
        [command, name, *event_option],
    )

    assert result.exit_code == 0
    assert (tmp_path / relative_path).is_file()
    assert active_application_context() is None


def test_artifact_command_reports_collision_without_replacing_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Return a failing status when a generated file already exists.

    Args:
        monkeypatch: Isolate the Console output and application factory.
        tmp_path: Application root supplied by pytest.
    """
    (tmp_path / "routes").mkdir()
    output = _RecordingOutput()

    def make_application(provider: ServiceProvider) -> Application:
        """Build one application with the test root and output service.

        Args:
            provider: Console provider registered before Container setup.

        Returns:
            Application used by the real generator command.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_service_provider(provider)
            .build()
        )

    monkeypatch.setattr(console, "_output", output)
    monkeypatch.setattr(console, "_application_factory", make_application)
    arguments = ["make:event", "DocumentReady"]
    generated_path = tmp_path / "app/events/document_ready_event.py"

    first = ConsoleTester(console).invoke(arguments)
    original_source = generated_path.read_text(encoding="utf-8")
    duplicate = ConsoleTester(console).invoke(arguments)

    assert first.exit_code == 0
    assert duplicate.exit_code == 1
    assert output.errors == [
        "The generated file already exists; it was not replaced.",
    ]
    assert generated_path.read_text(encoding="utf-8") == original_source
    assert active_application_context() is None
