"""Test the supported command-line interface and module entry point.

The suite exercises Typer output and distribution metadata without shelling
out to an installed console script.
"""

import re
import runpy

import pytest

from titanspan.console import cli
from titanspan.console.cli import console
from titanspan.console.testing import ConsoleTester

pytestmark = pytest.mark.unit


def test_help_lists_the_version_option() -> None:
    """Show usage and the supported global version option.

    The output comes from the real Typer application with color disabled.
    """
    result = ConsoleTester(console).invoke(["--help"])
    output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", result.stdout)

    assert result.exit_code == 0
    assert "Usage:" in output
    assert "--version" in output


def test_version_prints_distribution_metadata() -> None:
    """Display the installed Titanspan version and exit successfully.

    The application reads version metadata from the built distribution.
    """
    result = ConsoleTester(console).invoke(["--version"])
    output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", result.stdout)

    assert result.exit_code == 0
    assert "Titanspan 0.1.0.dev0" in output


def test_main_runs_the_typer_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dispatch the configured Typer application from the console script.

    Args:
        monkeypatch: Fixture that replaces the application during the test.
    """
    calls: list[str] = []

    def discover_commands() -> object:
        """Record the discovery phase before process parsing begins.

        The real Console instance remains available to the following phase.
        """
        calls.append("discover")
        return cli.console

    def run() -> None:
        """Record the parser phase without reading process arguments.

        The unit test controls both phases explicitly.
        """
        calls.append("run")

    monkeypatch.setattr(
        cli.console,
        "discover_commands",
        discover_commands,
    )
    monkeypatch.setattr(cli.console, "run", run)

    cli.main()

    assert calls == ["discover", "run"]


def test_normal_invocation_handles_the_false_version_option() -> None:
    """Continue into normal help behavior when version was not requested.

    Invoking with no command exercises Typer's default false option value.
    """
    result = ConsoleTester(console).invoke([])

    assert result.exit_code in {0, 2}
    assert "Usage:" in result.stdout


def test_package_module_entry_point_calls_the_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dispatch ``python -m titanspan`` through the console entry point.

    Args:
        monkeypatch: Fixture that replaces the imported CLI main function.
    """
    calls: list[bool] = []
    monkeypatch.setattr(cli, "main", lambda: calls.append(True))

    runpy.run_module("titanspan.__main__", run_name="__main__")

    assert calls == [True]
