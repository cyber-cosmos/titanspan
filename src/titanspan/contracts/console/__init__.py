"""Define shared command registration and terminal output contracts.

The contracts expose native Python values and do not depend on a CLI backend.
"""

from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

type CommandHandler = Callable[..., object]


@runtime_checkable
class ConsoleCommand(Protocol):
    """Describe an injectable command object with one ``handle`` method.

    The Container constructs command instances for each invocation.
    """

    handle: CommandHandler


@runtime_checkable
class CommandRegistrar(Protocol):
    """Describe the shared command registration boundary.

    Component providers use this protocol to add commands without depending
    on Typer or the concrete Console implementation.
    """

    def register_command(
        self,
        name: str,
        handler: CommandHandler | type[ConsoleCommand],
        *,
        description: str | None = None,
        with_application: bool = True,
    ) -> None:
        """Register a function or injectable command class.

        Args:
            name: Unique command name within the selected group.
            handler: Callable or class with an injectable ``handle`` method.
            description: Optional text shown in command help.
            with_application: Whether to use Application startup and cleanup.

        Raises:
            ValueError: If the name or handler is invalid or already exists.
        """
        ...


@runtime_checkable
class ProgressTask(Protocol):
    """Describe a progress handle exposed to command handlers.

    The output provider owns the display for the surrounding context lifetime.
    """

    def advance(self, amount: int = 1) -> None:
        """Advance the displayed task by a positive number of steps.

        Args:
            amount: Number of completed steps to add.
        """
        ...

    def complete(self) -> None:
        """Mark the displayed task as complete.

        Implementations set progress to the configured total.
        """
        ...


@runtime_checkable
class ConsoleOutput(Protocol):
    """Write terminal output and manage command prompts.

    Implementations must treat supplied strings as plain text.
    """

    def write(self, message: str) -> None:
        """Write plain text to standard output without markup parsing.

        Args:
            message: Text displayed to the user.
        """
        ...

    def write_error(self, message: str) -> None:
        """Write plain text to standard error without markup parsing.

        Args:
            message: Error text displayed to the user.
        """
        ...

    def table(
        self,
        headers: Sequence[str],
        rows: Iterable[Sequence[str]],
    ) -> None:
        """Render a table with one value for each header per row.

        Args:
            headers: Ordered column labels.
            rows: Rows whose values correspond to ``headers``.

        Raises:
            ValueError: If a row has a different number of values.
        """
        ...

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        """Ask for confirmation using a safe, explicit default.

        Args:
            prompt: Question displayed to the user.
            default: Answer used when the user submits an empty response.

        Returns:
            The user's answer or the supplied default.
        """
        ...

    def progress(
        self,
        total: int,
        description: str,
    ) -> AbstractContextManager[ProgressTask]:
        """Create a bounded progress display for a known amount of work.

        Args:
            total: Non-negative number of expected steps.
            description: Short task description.

        Returns:
            A context manager that owns the terminal progress display.

        Raises:
            ValueError: If ``total`` is negative.
        """
        ...


__all__ = [
    "CommandHandler",
    "CommandRegistrar",
    "ConsoleCommand",
    "ConsoleOutput",
    "ProgressTask",
]
