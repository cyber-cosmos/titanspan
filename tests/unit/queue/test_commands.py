"""Verify Queue commands use the native Console and application lifecycle."""

import inspect
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from sys import modules
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import anyio
import pytest

from titanspan.console import Console
from titanspan.console.testing import ConsoleTester
from titanspan.contracts.foundation import ServiceProvider
from titanspan.foundation import Application
from titanspan.queue.commands import register_queue_commands
from titanspan.queue.job import Job

if TYPE_CHECKING:
    from collections.abc import Awaitable

pytestmark = pytest.mark.unit


def test_queue_worker_commands_register_through_console() -> None:
    """Register worker commands without introducing another CLI registry."""
    console = Console()

    register_queue_commands(console)

    assert "queue:listen" in console.command_names
    assert "queue:work" in console.command_names
    assert "make:job" in console.command_names
    assert "make:job-middleware" in console.command_names


@pytest.mark.parametrize(
    ("command", "name", "relative_path", "source_marker"),
    [
        (
            "make:job",
            "IndexDocument",
            Path("app/jobs/index_document_job.py"),
            "class IndexDocumentJob(Job):",
        ),
        (
            "make:job-middleware",
            "AuditJobMiddleware",
            Path("app/job_middleware/audit_job_middleware.py"),
            "class AuditJobMiddleware:",
        ),
    ],
)
def test_queue_generators_run_through_console_application(
    tmp_path: Path,
    command: str,
    name: str,
    relative_path: Path,
    source_marker: str,
) -> None:
    """Generate artifacts under the active application's effective root.

    Args:
        tmp_path: Isolated application root.
        command: Registered generation command.
        name: Requested Python class name.
        relative_path: Expected path relative to the application root.
        source_marker: Declaration expected in generated source.
    """

    def build_application(provider: ServiceProvider) -> Application:
        """Create the normal Foundation application with the selected root.

        Args:
            provider: Console output provider supplied by Console.

        Returns:
            An unstarted native application using the test root.
        """
        return Application(
            base_path=tmp_path,
            service_providers=(provider,),
        )

    console = Console(application_factory=build_application)
    register_queue_commands(console)

    result = ConsoleTester(console).invoke([command, name])

    target = tmp_path / relative_path
    source = target.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert target.is_file()
    assert source_marker in source
    compile(source, target, "exec")
    if command == "make:job":
        _import_and_run_generated_job(target)


def _import_and_run_generated_job(path: Path) -> None:
    """Import and execute one trusted job produced by the native generator.

    Args:
        path: Generated Queue job module under the test application root.
    """
    module_name = f"titanspan_generated_job_{uuid4().hex}"
    spec = spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        pytest.fail("The generated job module could not be imported.")
    module = module_from_spec(spec)
    modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        job_type = getattr(module, "IndexDocumentJob", None)
        if not isinstance(job_type, type):
            pytest.fail("The generated job class was not found.")
        job = job_type()
        if not isinstance(job, Job):
            pytest.fail("The generated class does not inherit from Job.")
        handler = getattr(job, "handle", None)
        if not callable(handler):
            pytest.fail("The generated job has no callable handler.")

        async def execute() -> None:
            """Run the generated async handler without an application graph."""
            result = handler()
            if not inspect.isawaitable(result):
                pytest.fail(
                    "The generated handler did not return an awaitable."
                )
            await cast("Awaitable[object]", result)

        anyio.run(execute)
    finally:
        modules.pop(module_name, None)
