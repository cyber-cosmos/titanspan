"""Verify application artifact templates and destination safety.

Tests compile generated source and exercise the production path contract.
"""

from pathlib import Path

import pytest

from titanspan.console.exceptions import CommandGenerationError
from titanspan.console.generators import ArtifactKind, generate_artifact
from titanspan.foundation import Application

pytestmark = pytest.mark.unit

_GENERATED_ARTIFACTS: tuple[
    tuple[ArtifactKind, str, str | None, str, str], ...
] = (
    (
        "controller",
        "reports.ReportController",
        None,
        "app/controllers/reports/report_controller.py",
        "class ReportController:",
    ),
    (
        "middleware",
        "RequestId",
        None,
        "app/middleware/request_id_middleware.py",
        "class RequestIdMiddleware:",
    ),
    (
        "provider",
        "Metrics",
        None,
        "app/providers/metrics_service_provider.py",
        "class MetricsServiceProvider:",
    ),
    (
        "command",
        "Reindex",
        None,
        "app/commands/reindex_command.py",
        "class ReindexCommand:",
    ),
    (
        "event",
        "DocumentReady",
        None,
        "app/events/document_ready_event.py",
        "class DocumentReadyEvent:",
    ),
    (
        "listener",
        "SendNotice",
        "app.events.DocumentReadyEvent",
        "app/listeners/send_notice_listener.py",
        "from app.events import DocumentReadyEvent",
    ),
    (
        "job",
        "ProcessDocument",
        None,
        "app/jobs/process_document_job.py",
        "class ProcessDocumentJob(Job):",
    ),
    (
        "job_middleware",
        "AuditJobMiddleware",
        None,
        "app/job_middleware/audit_job_middleware.py",
        "class AuditJobMiddleware:",
    ),
    (
        "test",
        "documents",
        None,
        "tests/test_documents.py",
        "def test_application_uses_its_root",
    ),
)


@pytest.mark.parametrize(
    ("kind", "name", "event_type", "relative_path", "source_marker"),
    _GENERATED_ARTIFACTS,
)
def test_generated_templates_compile_under_application_root(
    tmp_path: Path,
    kind: ArtifactKind,
    name: str,
    event_type: str | None,
    relative_path: str,
    source_marker: str,
) -> None:
    """Render every supported artifact as importable Python source.

    Args:
        tmp_path: Isolated application root supplied by pytest.
        kind: Artifact template under test.
        name: Native class name or module path.
        event_type: Optional trusted listener event class path.
        relative_path: Expected application-relative output path.
        source_marker: Declaration expected in generated source.
    """
    paths = Application(base_path=tmp_path)

    target = generate_artifact(
        paths,
        kind,
        name,
        event_type=event_type,
    )
    source = target.read_text(encoding="utf-8")

    assert target == tmp_path / relative_path
    assert source_marker in source
    compile(source, target, "exec")


def test_generator_rejects_path_traversal_without_writing_outside_root(
    tmp_path: Path,
) -> None:
    """Reject names that attempt to escape the application root.

    Args:
        tmp_path: Isolated application root supplied by pytest.
    """
    paths = Application(base_path=tmp_path)

    with pytest.raises(CommandGenerationError):
        generate_artifact(paths, "controller", "../../escape")

    assert not (tmp_path.parent / "escape_controller.py").exists()


def test_generator_rejects_symlink_destination_outside_application_root(
    tmp_path: Path,
) -> None:
    """Reject an existing destination parent that resolves outside the root.

    Args:
        tmp_path: Isolated parent directory supplied by pytest.
    """
    application_root = tmp_path / "application"
    external_root = tmp_path / "external"
    application_root.mkdir()
    external_root.mkdir()
    application_directory = application_root / "app"
    application_directory.mkdir()
    (application_directory / "controllers").symlink_to(
        external_root,
        target_is_directory=True,
    )
    paths = Application(base_path=application_root)

    with pytest.raises(CommandGenerationError):
        generate_artifact(paths, "controller", "Report")

    assert tuple(external_root.iterdir()) == ()


def test_generator_does_not_replace_existing_artifact(
    tmp_path: Path,
) -> None:
    """Preserve existing source when an artifact name is reused.

    Args:
        tmp_path: Isolated application root supplied by pytest.
    """
    paths = Application(base_path=tmp_path)
    target = generate_artifact(paths, "event", "DocumentReady")
    target.write_text("preserve this file\n", encoding="utf-8")

    with pytest.raises(CommandGenerationError):
        generate_artifact(paths, "event", "DocumentReady")

    assert target.read_text(encoding="utf-8") == "preserve this file\n"


def test_generator_reports_non_directory_parent_as_safe_write_failure(
    tmp_path: Path,
) -> None:
    """Reject a file that blocks a required application directory.

    Args:
        tmp_path: Isolated application root supplied by pytest.
    """
    blocker = tmp_path / "app"
    blocker.write_text("not a directory\n", encoding="utf-8")
    paths = Application(base_path=tmp_path)

    with pytest.raises(
        CommandGenerationError,
        match="could not be written",
    ):
        generate_artifact(paths, "controller", "Report")

    assert blocker.read_text(encoding="utf-8") == "not a directory\n"


@pytest.mark.parametrize(
    "event_type",
    [None, "", "app.events.Event;os.system", "app..Event"],
)
def test_listener_requires_trusted_dotted_event_type(
    tmp_path: Path,
    event_type: str | None,
) -> None:
    """Reject listener imports that are missing or not valid identifiers.

    Args:
        tmp_path: Isolated application root supplied by pytest.
        event_type: Candidate event type import path.
    """
    paths = Application(base_path=tmp_path)

    with pytest.raises(CommandGenerationError):
        generate_artifact(
            paths,
            "listener",
            "SendNotice",
            event_type=event_type,
        )
