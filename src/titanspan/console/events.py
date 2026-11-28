"""Define metadata-only lifecycle events for Console commands.

Events omit command input and exception messages to avoid retaining secrets.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandStarting:
    """Identify an application-aware command before its handler runs.

    Attributes:
        command_path: Registered command path without user-supplied values.
    """

    command_path: str


@dataclass(frozen=True, slots=True)
class CommandFinished:
    """Describe the outcome of an application-aware command.

    Attributes:
        command_path: Registered command path without user-supplied values.
        exit_code: Process status, or ``None`` when no status was produced.
        exception_type: Exception class name without message or payload data.
    """

    command_path: str
    exit_code: int | None
    exception_type: str | None = None


__all__ = ["CommandFinished", "CommandStarting"]
