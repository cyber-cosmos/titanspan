"""Expose terminal output through the native Console contract.

Rich rendering is delegated to a private backend adapter.
"""

from collections.abc import Iterable, Sequence
from contextlib import AbstractContextManager

from titanspan.console._backends.rich_output import RichConsoleOutput
from titanspan.contracts.console import ProgressTask


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
