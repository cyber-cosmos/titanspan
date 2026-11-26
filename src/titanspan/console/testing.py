"""Provide native command invocation helpers for tests.

The helper delegates parsing and execution to the production Console.
"""

from collections.abc import Sequence

from titanspan.console.application import Console
from titanspan.console.results import ConsoleResult


class ConsoleTester:
    """Run commands through the production parser with captured output.

    This helper does not replace command registration or dispatch behavior.
    """

    def __init__(self, console: Console) -> None:
        """Retain the command host whose real parser will be exercised.

        Args:
            console: Native command registry under test.
        """
        self._console = console

    def invoke(
        self,
        arguments: Sequence[str],
        *,
        stdin: str | None = None,
    ) -> ConsoleResult:
        """Invoke the real parser and return captured terminal streams.

        Args:
            arguments: CLI argument vector, excluding the executable name.
            stdin: Optional input supplied to interactive prompts.

        Returns:
            A result with exit code, stdout, and stderr.
        """
        return self._console.invoke(arguments, stdin=stdin)

    _console: Console


__all__ = ["ConsoleTester"]
