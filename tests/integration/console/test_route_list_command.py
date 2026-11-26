"""Verify route inspection uses the shared Console and Application lifecycles.

The test uses the production command registry, Router, Container, and
Foundation startup path.
"""

from collections.abc import Iterable, Sequence
from contextlib import AbstractContextManager
from pathlib import Path

import pytest

from titanspan._application_context import active_application_context
from titanspan.console.cli import console
from titanspan.console.testing import ConsoleTester
from titanspan.contracts import ProgressTask, ServiceProvider
from titanspan.foundation import Application

pytestmark = pytest.mark.integration


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

    def write(self, message: str) -> None:
        """Accept plain text written by a command.

        Args:
            message: Text supplied through the shared Console contract.
        """

    def write_error(self, message: str) -> None:
        """Accept plain error text written by a command.

        Args:
            message: Error text supplied through the shared Console contract.
        """

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
