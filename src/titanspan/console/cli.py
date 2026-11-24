"""Typer command line entry point for Titanspan."""

import typer
from rich.console import Console

from titanspan import __version__

app = typer.Typer(
    add_completion=False,
    help="Engineer beyond limits.",
    no_args_is_help=True,
)
console = Console()


def _show_version(value: bool) -> None:
    """Print the installed Titanspan version when requested."""
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
    """Run Titanspan commands."""
    del version


def main() -> None:
    """Execute the CLI application."""
    app()


if __name__ == "__main__":
    main()
