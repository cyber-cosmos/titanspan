"""Define native metadata for command-line arguments and options.

The private CLI adapter translates these values into parser parameters.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Argument:
    """Mark one typed command parameter as a positional argument.

    Args:
        description: Optional text shown for this argument. The parser uses
            the Python parameter name when this value is omitted.
        metavar: Optional placeholder shown in command usage. The parser
            derives the placeholder from the parameter name when omitted.
    """

    description: str | None = None
    metavar: str | None = None


@dataclass(frozen=True, slots=True, init=False)
class Option:
    """Mark one typed command parameter as a named option.

    Args:
        *names: One or more option names such as ``--limit`` or ``-l``.
        description: Optional help text shown for this option.
    """

    names: tuple[str, ...]
    description: str | None

    def __init__(
        self,
        *names: str,
        description: str | None = None,
    ) -> None:
        """Create option metadata and validate its explicit names.

        Args:
            *names: At least one option name beginning with a hyphen.
            description: Optional text shown for this option.

        Raises:
            ValueError: If a name is empty or does not begin with a hyphen.
        """
        if not names or any(
            not name.startswith("-") or name == "-" for name in names
        ):
            message = "Command option names must begin with a hyphen."
            raise ValueError(message)
        object.__setattr__(self, "names", names)
        object.__setattr__(self, "description", description)


__all__ = ["Argument", "Option"]
