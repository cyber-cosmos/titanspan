"""Define captured results from native command invocation.

The result stores only process status and terminal text.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConsoleResult:
    """Store a command's process status and captured text streams.

    The result is immutable and suitable for CLI integration assertions.
    """

    exit_code: int
    stdout: str
    stderr: str


__all__ = ["ConsoleResult"]
