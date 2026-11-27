"""Verify cache maintenance commands use the native Console registrar.
"""  # fmt: skip

from pathlib import Path

import pytest

from titanspan.cache.commands import register_cache_commands
from titanspan.console import Console
from titanspan.console.cli import console as framework_console
from titanspan.console.exceptions import CommandRegistrationError
from titanspan.console.testing import ConsoleTester

pytestmark = pytest.mark.integration


def test_framework_cli_exposes_cache_commands() -> None:
    """Register cache commands in the installed framework command host.
    """  # fmt: skip
    assert {
        "cache:clear",
        "cache:forget",
        "cache:status",
    }.issubset(framework_console.command_names)


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        pytest.param(
            ["cache:clear"],
            "The default cache namespace was cleared.",
            id="clear",
        ),
        pytest.param(
            ["cache:forget", "missing"],
            "Cache key missing.",
            id="forget",
        ),
        pytest.param(
            ["cache:status"],
            "memory",
            id="status",
        ),
    ],
)
def test_framework_cli_runs_cache_commands(
    arguments: list[str],
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Execute cache commands through the production Console lifecycle.

    Args:
        arguments: Command path and any explicit arguments.
        expected: Safe text produced by the command.
        monkeypatch: Isolate the command's effective application directory.
        tmp_path: Isolated filesystem location supplied by pytest.
    """
    monkeypatch.chdir(tmp_path)

    result = ConsoleTester(framework_console).invoke(arguments)

    assert result.exit_code == 0
    assert expected in result.stdout


def test_cache_commands_register_with_console() -> None:
    """Register maintenance commands through Console's public contract.
    """  # fmt: skip
    console = Console()

    register_cache_commands(console)

    assert console.command_names == (
        "cache:clear",
        "cache:forget",
        "cache:status",
    )


def test_cache_command_registration_rejects_duplicate_names() -> None:
    """Keep duplicate maintenance commands under Console's own policy.
    """  # fmt: skip
    console = Console()
    register_cache_commands(console)

    with pytest.raises(CommandRegistrationError):
        register_cache_commands(console)
