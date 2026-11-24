"""Expose the initial Titanspan command-line application.

Typer provides command parsing and Rich provides terminal presentation; the
framework only adds its own version option and project help text.
"""

import typer
from rich.console import Console

from titanspan import __version__

__all__ = ["app", "main", "root_command"]

app: typer.Typer = typer.Typer(
    add_completion=False,
    help="Engineer beyond limits.",
    no_args_is_help=True,
)
console: Console = Console()


def _show_version(value: bool) -> None:
    """Display package metadata when the eager version option is selected.

    Args:
        value: Whether the user supplied the ``--version`` option.

    Raises:
        typer.Exit: When the version is displayed, to stop normal dispatch.
    """
    if value:
        console.print(f"Titanspan {__version__}")
        raise typer.Exit


@app.callback()
def root_command(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_show_version,
        is_eager=True,
        help="Show the installed Titanspan version and exit.",
    ),
) -> None:
    """Define global CLI options shared by Titanspan commands.

    Args:
        version: Eager flag handled by ``_show_version`` before dispatch.
    """
    del version


def main() -> None:
    """Run the configured Typer application against process arguments.

    This function is used by both the installed console script and the module
    entry point, preserving one command registration path.
    """
    app()
