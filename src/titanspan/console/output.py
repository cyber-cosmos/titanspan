"""Expose terminal output through the native Console contract.

Rich rendering is delegated to a private backend adapter.
"""

from collections.abc import Iterable, Sequence
from contextlib import AbstractContextManager, nullcontext

from titanspan.console._backends.rich_output import RichConsoleOutput
from titanspan.console.exceptions import ConsoleOutputError
from titanspan.contracts.console import ConsoleOutput, ProgressTask

_TABLE_HEADERS_ERROR = "A table requires at least one header."
_TABLE_ROW_WIDTH_ERROR = "Table rows must match the header count."
_PROGRESS_TOTAL_ERROR = "Progress totals cannot be negative."


class _SilentProgressTask:
    """Accept progress updates without rendering terminal state.

    Silent command calls retain the same context-managed task lifetime.
    """

    def advance(self, amount: int = 1) -> None:
        """Ignore an update while preserving the ProgressTask contract.

        Args:
            amount: Number of steps the command completed.
        """
        del amount

    def complete(self) -> None:
        """Accept completion without rendering terminal state.

        Progress output remains suppressed until this task context closes.
        """


class SilentConsoleOutput:
    """Suppress command output while preserving interactive confirmations.

    The wrapped output remains responsible for reading user input.
    """

    def __init__(self, interactive_output: ConsoleOutput) -> None:
        """Retain the output service used for interactive confirmation.

        Args:
            interactive_output: Configured Console output implementation.
        """
        self._interactive_output = interactive_output

    def write(self, message: str) -> None:
        """Suppress one standard output message.

        Args:
            message: Message that a normal call would render.
        """
        del message

    def write_error(self, message: str) -> None:
        """Suppress one standard error message.

        Args:
            message: Error that a normal call would render.
        """
        del message

    def table(
        self,
        headers: Sequence[str],
        rows: Iterable[Sequence[str]],
    ) -> None:
        """Validate and suppress a table.

        Args:
            headers: Ordered column labels.
            rows: Rows whose values correspond to the headers.

        Raises:
            ConsoleOutputError: If the header list or a row is invalid.
        """
        if not headers:
            raise ConsoleOutputError(_TABLE_HEADERS_ERROR)
        for row in rows:
            if len(row) != len(headers):
                raise ConsoleOutputError(_TABLE_ROW_WIDTH_ERROR)

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        """Keep confirmation prompts interactive during silent execution.

        Args:
            prompt: Question displayed to the user.
            default: Answer used when the user submits an empty response.

        Returns:
            The user's answer or the supplied default.
        """
        return self._interactive_output.confirm(prompt, default=default)

    def progress(
        self,
        total: int,
        description: str,
    ) -> AbstractContextManager[ProgressTask]:
        """Provide a silent progress task with the normal lifetime.

        Args:
            total: Non-negative number of expected steps.
            description: Short task description, omitted from the terminal.

        Returns:
            A context manager that yields a no-output progress handle.

        Raises:
            ConsoleOutputError: If the expected total is negative.
        """
        del description
        if total < 0:
            raise ConsoleOutputError(_PROGRESS_TOTAL_ERROR)
        return nullcontext(_SilentProgressTask())

    _interactive_output: ConsoleOutput


class TerminalOutput:
    """Render terminal text, tables, prompts, and progress indicators.

    This adapter exposes the shared `ConsoleOutput` contract.
    """

    def __init__(self) -> None:
        """Create an output adapter for the active process streams.

        The private adapter delegates stream selection to Rich.
        """
        self._backend = RichConsoleOutput()

    def write(self, message: str) -> None:
        """Write plain text to standard output.

        Args:
            message: Text displayed to the user without markup parsing.
        """
        self._backend.write(message)

    def write_error(self, message: str) -> None:
        """Write plain text to standard error.

        Args:
            message: Error text displayed without markup parsing.
        """
        self._backend.write_error(message)

    def table(
        self,
        headers: Sequence[str],
        rows: Iterable[Sequence[str]],
    ) -> None:
        """Render a table after checking each row's width.

        Args:
            headers: Ordered column labels.
            rows: Rows whose values correspond to the headers.

        Raises:
            ValueError: If the table has no columns or a row width differs.
        """
        self._backend.table(headers, rows)

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        """Ask a terminal confirmation with an explicit default answer.

        Args:
            prompt: Question displayed to the user.
            default: Answer used when the user submits an empty response.

        Returns:
            The user's answer or the supplied default.
        """
        return self._backend.confirm(prompt, default=default)

    def progress(
        self,
        total: int,
        description: str,
    ) -> AbstractContextManager[ProgressTask]:
        """Create a context-managed progress indicator.

        Args:
            total: Non-negative number of expected steps.
            description: Short task description.

        Returns:
            A context manager that owns the progress display.

        Raises:
            ValueError: If the expected total is negative.
        """
        return self._backend.progress(total, description)

    _backend: RichConsoleOutput


__all__ = ["TerminalOutput"]
