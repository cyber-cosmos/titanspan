"""Test the supported command-line interface and module entry point.

The suite exercises Typer output and distribution metadata without shelling
out to an installed console script.
"""

import re
import runpy

import pytest
from typer.testing import CliRunner

from titanspan.console import cli

# The CLI false-option callback is not reachable through a registered
# command yet, so test its branch directly as a focused unit boundary.
from titanspan.console.cli import (
    _show_version,  # pyright: ignore[reportPrivateUsage]
    app,
    root_command,
)

pytestmark = pytest.mark.unit


def test_help_lists_the_version_option() -> None:
    """Show usage and the supported global version option.

    The output comes from the real Typer application with color disabled.
    """
    result = CliRunner().invoke(app, ["--help"], color=False)
    output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", result.stdout)

    assert result.exit_code == 0
    assert "Usage:" in output
    assert "--version" in output


def test_version_prints_distribution_metadata() -> None:
    """Display the installed Titanspan version and exit successfully.

    The application reads version metadata from the built distribution.
    """
    result = CliRunner().invoke(app, ["--version"], color=False)
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
    calls: list[bool] = []
    monkeypatch.setattr(cli, "app", lambda: calls.append(True))

    cli.main()

    assert calls == [True]


def test_normal_invocation_handles_the_false_version_option() -> None:
    """Continue into normal help behavior when version was not requested.

    Invoking with no command exercises Typer's default false option value.
    """
    result = CliRunner().invoke(app, [], color=False)

    assert result.exit_code in {0, 2}
    assert "Usage:" in result.stdout


def test_root_callback_accepts_its_default_version_value() -> None:
    """Accept the default option value without exiting normal dispatch.

    This covers the callback body independently from Typer option parsing.
    """
    root_command(False)


def test_version_callback_returns_when_option_is_false() -> None:
    """Leave command dispatch unchanged when the option is not selected.

    The callback has no subcommand invocation path yet, so this directly
    verifies its false branch without making the helper part of the API.
    """
    _show_version(False)


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
