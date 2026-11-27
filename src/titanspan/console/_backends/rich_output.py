"""Adapt Rich terminal primitives to the native output contract.

This module is private to the Console component.
"""

from collections.abc import Generator, Iterable, Sequence
from contextlib import AbstractContextManager, contextmanager

from rich.console import Console as RichConsole
from rich.progress import Progress, TaskID
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

from titanspan.console.exceptions import ConsoleOutputError
from titanspan.contracts.console import ProgressTask


class _RichProgressTask:
    """Expose one Rich progress task through the native progress contract.

    The progress context owns the Rich task's lifetime.
    """

    def __init__(
        self,
        progress: Progress,
        task_id: TaskID,
        total: int,
    ) -> None:
        """Retain the Rich task handle and its known completion count.

        Args:
            progress: Rich progress display that owns the task.
            task_id: Identifier returned when the task was created.
            total: Expected number of steps.
        """
        self._progress = progress
        self._task_id = task_id
        self._total = total

    def advance(self, amount: int = 1) -> None:
        """Advance the task by a positive number of steps.

        Args:
            amount: Number of completed steps to add.

        Raises:
            ValueError: If ``amount`` is not positive.
        """
        if amount <= 0:
            message = "Progress advances must be positive."
            raise ConsoleOutputError(message)
        self._progress.advance(self._task_id, amount)

    def complete(self) -> None:
        """Set the task's completed count to its known total.

        Rich remains responsible for updating the terminal display.
        """
        self._progress.update(self._task_id, completed=self._total)

    _progress: Progress
    _task_id: TaskID
    _total: int


class RichConsoleOutput:
    """Implement native terminal output with Rich rendering primitives.

    Supplied message text is rendered without markup interpretation.
    """

    def __init__(self) -> None:
        """Create stdout and stderr writers for current process streams.

        Rich captures the stream objects when each Console is constructed.
        """
        self._stdout = RichConsole(markup=False)
        self._stderr = RichConsole(stderr=True, markup=False)

    def write(self, message: str) -> None:
        """Write plain text to standard output.

        Args:
            message: Text displayed to the user.
        """
        self._stdout.print(Text(message))

    def write_error(self, message: str) -> None:
        """Write plain error text to standard error.

        Args:
            message: Error text displayed to the user.
        """
        self._stderr.print(Text(message, style="red"))

    def table(
        self,
        headers: Sequence[str],
        rows: Iterable[Sequence[str]],
    ) -> None:
        """Render validated rows in a Rich table.

        Args:
            headers: Ordered column labels.
            rows: Rows with one value per header.

        Raises:
            ValueError: If no headers exist or a row width differs.
        """
        if not headers:
            message = "A table requires at least one header."
            raise ConsoleOutputError(message)
        table = Table()
        for header in headers:
            table.add_column(Text(header))
        for row in rows:
            if len(row) != len(headers):
                message = "Table rows must match the header count."
                raise ConsoleOutputError(message)
            table.add_row(*(Text(value) for value in row))
        self._stdout.print(table)

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        """Ask for a terminal confirmation with an explicit default.

        Args:
            prompt: Question displayed to the user.
            default: Answer used when the user submits an empty response.

        Returns:
            The user's answer or the supplied default.
        """
        return Confirm.ask(
            Text(prompt, style="prompt"), default=default, console=self._stdout
        )

    def progress(
        self,
        total: int,
        description: str,
    ) -> AbstractContextManager[ProgressTask]:
        """Create a context-managed progress display.

        Args:
            total: Non-negative number of expected steps.
            description: Short task description.

        Returns:
            A context manager that owns the Rich progress display.

        Raises:
            ValueError: If ``total`` is negative.
        """
        if total < 0:
            message = "Progress totals cannot be negative."
            raise ConsoleOutputError(message)
        return self._progress(total, description)

    @contextmanager
    def _progress(
        self,
        total: int,
        description: str,
    ) -> Generator[ProgressTask, None, None]:
        """Own the Rich progress display for exactly one context lifetime.

        Args:
            total: Non-negative number of expected steps.
            description: Short task description.

        Yields:
            A native handle for the created Rich progress task.
        """
        with Progress(console=self._stdout) as progress:
            task_id = progress.add_task(description, total=total)
            yield _RichProgressTask(progress, task_id, total)

    _stdout: RichConsole
    _stderr: RichConsole


__all__ = ["RichConsoleOutput"]
