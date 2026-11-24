"""Tests for the installed Titanspan command line interface."""

import runpy

from pytest import MonkeyPatch
from typer.testing import CliRunner

import titanspan.console.cli as cli
from titanspan.console.cli import _show_version, app, root_command


def test_help_lists_the_version_option() -> None:
    """Show usage and the version option in the top-level help."""
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.stdout
    assert "--version" in result.stdout


def test_version_prints_the_distribution_version() -> None:
    """Print the distribution version and exit successfully."""
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "Titanspan 0.1.0.dev0" in result.stdout


def test_main_runs_the_typer_application(monkeypatch: MonkeyPatch) -> None:
    """Run the configured Typer application from the console entry point."""
    calls: list[bool] = []
    monkeypatch.setattr(cli, "app", lambda: calls.append(True))

    cli.main()

    assert calls == [True]


def test_version_callback_does_not_exit_when_flag_is_false() -> None:
    """Leave normal CLI startup unchanged when version is not requested."""
    _show_version(False)


def test_root_command_accepts_the_default_option_value() -> None:
    """Accept normal startup when the eager version flag is false."""
    root_command(False)


def test_package_module_entry_point_calls_the_cli(
    monkeypatch: MonkeyPatch,
) -> None:
    """Dispatch python -m titanspan through the console entry point."""
    calls: list[bool] = []
    monkeypatch.setattr(cli, "main", lambda: calls.append(True))

    runpy.run_module("titanspan.__main__", run_name="__main__")

    assert calls == [True]
