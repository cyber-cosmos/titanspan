"""Define native errors for Console registration and command execution.

The CLI adapter translates these errors into process statuses.
"""


class ConsoleError(RuntimeError):
    """Represent a native command registration or execution failure.

    This base class groups framework-owned Console errors.
    """


class CommandRegistrationError(ConsoleError, ValueError):
    """Report an invalid or conflicting command definition.

    Invalid definitions fail before the CLI parser is invoked.
    """


class CommandInvocationError(ConsoleError, ValueError):
    """Report an invalid programmatic command name or input mapping.

    The error omits arbitrary supplied values.
    """


class CommandDiscoveryError(ConsoleError, ImportError):
    """Report a trusted command entry point that failed to load.

    The message omits the imported object's representation.
    """


class ConsoleRuntimeError(ConsoleError):
    """Report an unsupported Console runtime or lifecycle state.

    Synchronous process entry points must run outside an active async task.
    """


class ConsoleOutputError(ConsoleError, ValueError):
    """Report invalid output or progress configuration.

    This error is raised before Rich receives invalid display metadata.
    """


class CommandGenerationError(ConsoleError, ValueError):
    """Report an unsafe or unavailable application artifact generation.

    The error message contains only framework-owned diagnostics.
    """


class ConsoleExitError(Exception):
    """Stop a command with an explicit process exit code.

    Args:
        code: Process status from zero through ``_MAX_EXIT_CODE``.
    """

    def __init__(self, code: int = 0) -> None:
        """Validate and retain the requested process status.

        Args:
            code: Process status from zero through ``_MAX_EXIT_CODE``.

        Raises:
            ValueError: If ``code`` is outside the supported status range.
        """
        if not 0 <= code <= _MAX_EXIT_CODE:
            message = "Command exit codes must be between 0 and 255."
            raise ValueError(message)
        self.code = code
        super().__init__(code)


__all__ = [
    "CommandDiscoveryError",
    "CommandGenerationError",
    "CommandInvocationError",
    "CommandRegistrationError",
    "ConsoleError",
    "ConsoleExitError",
    "ConsoleOutputError",
    "ConsoleRuntimeError",
]

_MAX_EXIT_CODE = 255
