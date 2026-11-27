"""Verify cache command behavior with the shared registration contract.
"""  # fmt: skip

from collections.abc import Iterable, Sequence
from contextlib import AbstractContextManager
from typing import cast

import pytest

from titanspan.cache import CacheManager
from titanspan.cache.commands import register_cache_commands
from titanspan.contracts.console import (
    CommandHandler,
    ConsoleCommand,
    ConsoleOutput,
    ProgressTask,
)

pytestmark = pytest.mark.unit
_COMMAND_CLASS_ERROR = "Cache command test helpers accept functions only."


class RecordingRegistrar:
    """Retain component commands as inspectable native callables.
    """  # fmt: skip

    def __init__(self) -> None:
        """Create an empty handler mapping.
        """  # fmt: skip
        self.handlers: dict[str, CommandHandler] = {}

    def register_command(
        self,
        name: str,
        handler: CommandHandler | type[ConsoleCommand],
        *,
        description: str | None = None,
        with_application: bool = True,
    ) -> None:
        """Retain the command and enforce the shared registrar type.
        """  # fmt: skip
        _ = description, with_application
        if isinstance(handler, type):
            raise TypeError(_COMMAND_CLASS_ERROR)
        self.handlers[name] = handler


class Output:
    """Capture plain text and tabular status for command assertions.
    """  # fmt: skip

    def __init__(self) -> None:
        """Initialize empty terminal output collections.
        """  # fmt: skip
        self.messages: list[str] = []
        self.tables: list[tuple[Sequence[str], list[Sequence[str]]]] = []

    def write(self, message: str) -> None:
        """Retain one plain text success message.
        """  # fmt: skip
        self.messages.append(message)

    def write_error(self, message: str) -> None:
        """Retain one plain text error message.
        """  # fmt: skip
        self.messages.append(message)

    def table(
        self,
        headers: Sequence[str],
        rows: Iterable[Sequence[str]],
    ) -> None:
        """Retain a fully materialized table.
        """  # fmt: skip
        self.tables.append((headers, list(rows)))

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        """Return the configured default for the unused prompt contract.
        """  # fmt: skip
        _ = prompt
        return default

    def progress(
        self,
        total: int,
        description: str,
    ) -> AbstractContextManager[ProgressTask]:
        """Reject progress output because cache commands do not use it.
        """  # fmt: skip
        _ = total, description
        raise NotImplementedError


def test_cache_commands_clear_forget_and_report_safe_status() -> None:
    """Run all maintenance handlers against one real memory manager.
    """  # fmt: skip
    registrar = RecordingRegistrar()
    register_cache_commands(registrar)
    captured = registrar
    manager = CacheManager()
    output = Output()
    console_output = cast("ConsoleOutput", output)
    repository = manager.store()
    repository.put("command-key", "not shown in diagnostics")

    captured.handlers["cache:forget"](
        "command-key",
        manager,
        console_output,
    )
    assert repository.missing("command-key")
    captured.handlers["cache:clear"](manager, console_output)
    captured.handlers["cache:status"](manager, console_output)

    assert output.messages == [
        "Cache key removed.",
        "The default cache namespace was cleared.",
    ]
    assert len(output.tables) == 1
    assert output.tables[0][0] == (
        "Store",
        "Driver",
        "Details",
    )
    assert "not shown in diagnostics" not in repr(output.tables)
