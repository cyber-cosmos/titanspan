"""Verify configuration commands through the real Typer application.

The command tests use isolated application roots and never print raw secrets.
"""

from pathlib import Path

import pytest

from titanspan.console.cli import console
from titanspan.console.testing import ConsoleTester

pytestmark = pytest.mark.unit


def _write_application_config(root: Path, text: str) -> None:
    """Create one trusted Python configuration file for CLI tests.

    Args:
        root: Isolated application root used as the current directory.
        text: Python module body that exports a mapping named ``config``.
    """
    directory = root / "config"
    directory.mkdir()
    (directory / "app.py").write_text(text, encoding="utf-8")


def test_config_show_redacts_secret_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Render safe diagnostics without exposing credential contents.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture that changes and restores the working directory.
    """
    _write_application_config(
        tmp_path,
        "config = {'name': 'Titanspan', '"
        "api_key"  # pragma: allowlist secret
        "': 'private-value'}\n",
    )
    monkeypatch.chdir(tmp_path)

    result = ConsoleTester(console).invoke(["config:show"])

    assert result.exit_code == 0
    assert "Titanspan" in result.stdout
    assert "[REDACTED]" in result.stdout
    assert "private-value" not in result.stdout


def test_config_cache_and_clear_manage_only_the_cache_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create a safe cache and preserve adjacent application files.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture that changes and restores the working directory.
    """
    _write_application_config(tmp_path, "config = {'name': 'Titanspan'}\n")
    monkeypatch.chdir(tmp_path)
    cache_file = tmp_path / "bootstrap" / "cache" / "config.json"
    neighbor = cache_file.with_name("keep.txt")
    neighbor.parent.mkdir(parents=True)
    neighbor.write_text("keep", encoding="utf-8")

    cached = ConsoleTester(console).invoke(["config:cache"])

    assert cached.exit_code == 0
    assert cache_file.is_file()
    assert cache_file.name in cached.stdout

    cleared = ConsoleTester(console).invoke(["config:clear"])

    assert cleared.exit_code == 0
    assert not cache_file.exists()
    assert neighbor.read_text(encoding="utf-8") == "keep"


def test_config_validate_reports_source_errors_without_source_contents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return a failure status while keeping malformed source text private.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture that changes and restores the working directory.
    """
    _write_application_config(tmp_path, "config = 'private source value'\n")
    monkeypatch.chdir(tmp_path)

    result = ConsoleTester(console).invoke(["config:validate"])

    assert result.exit_code == 1
    assert "Could not load configuration source" in result.stderr
    assert "private source value" not in result.stdout + result.stderr


def test_config_show_returns_failure_for_a_missing_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a missing key without returning a successful command status.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture that changes and restores the working directory.

    Returns:
        None.
    """
    _write_application_config(tmp_path, "config = {'name': 'Titanspan'}\n")
    monkeypatch.chdir(tmp_path)

    result = ConsoleTester(console).invoke(
        ["config:show", "missing.path"],
    )

    assert result.exit_code == 1
    assert "was not found" in result.stderr


def test_config_show_reports_source_errors_without_disclosing_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return a safe failure when trusted configuration cannot be loaded.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture that changes and restores the working directory.
    """
    _write_application_config(tmp_path, "config = 'private-value'\n")
    monkeypatch.chdir(tmp_path)

    result = ConsoleTester(console).invoke(["config:show"])

    assert result.exit_code == 1
    assert "private-value" not in result.stdout + result.stderr


def test_config_cache_reports_unsupported_values_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return an error when configuration cannot be represented as safe JSON.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture that changes and restores the working directory.

    Returns:
        None.
    """
    _write_application_config(
        tmp_path,
        "config = {'factory': lambda: 'private-value'}\n",
    )
    monkeypatch.chdir(tmp_path)

    result = ConsoleTester(console).invoke(["config:cache"])

    assert result.exit_code == 1
    assert "private-value" not in result.stderr


def test_config_clear_reports_filesystem_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report cache removal failures rather than claiming success.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture that changes and restores the working directory.

    Returns:
        None.
    """
    cache_directory = tmp_path / "bootstrap" / "cache" / "config.json"
    cache_directory.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    result = ConsoleTester(console).invoke(["config:clear"])

    assert result.exit_code == 1
    assert "Configuration cache" in result.stderr


def test_config_validate_reports_valid_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report successful validation only after loading the source files.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture that changes and restores the working directory.

    Returns:
        None.
    """
    _write_application_config(tmp_path, "config = {'name': 'Titanspan'}\n")
    monkeypatch.chdir(tmp_path)

    result = ConsoleTester(console).invoke(["config:validate"])

    assert result.exit_code == 0
    assert "Configuration is valid" in result.stdout
