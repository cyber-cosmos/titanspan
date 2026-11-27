"""Verify cache maintenance commands use the native Console registrar.
"""  # fmt: skip

import pytest

from titanspan.cache.commands import register_cache_commands
from titanspan.console import Console
from titanspan.console.exceptions import CommandRegistrationError

pytestmark = pytest.mark.integration


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
