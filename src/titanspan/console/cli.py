"""Expose the initial Titanspan command-line application.

Typer provides command parsing and Rich provides terminal presentation; the
framework only adds its own version option and project help text.
"""

import json
from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console

from titanspan import __version__
from titanspan.config import (
    ConfigCache,
    ConfigManager,
    ConfigurationError,
)
from titanspan.support.arr import Arr

__all__ = ["app", "main", "root_command"]

app: typer.Typer = typer.Typer(
    add_completion=False,
    help="Engineer beyond limits.",
    no_args_is_help=True,
)
console: Console = Console()
error_console: Console = Console(stderr=True)
_MISSING = object()


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


@app.command("config:show")
def show_config(
    key: str | None = typer.Argument(
        None,
        help="Optional dotted configuration path to display.",
    ),
) -> None:
    """Show a safe configuration snapshot or one selected value.

    Args:
        key: Optional dotted path within the application configuration.

    Raises:
        typer.Exit: If configuration loading fails or the key is missing.
    """
    try:
        repository = ConfigManager(Path.cwd()).validate()
    except ConfigurationError as error:
        _configuration_error(error)

    safe_values = dict(repository.redacted())
    displayed: object = safe_values
    if key is not None:
        displayed = Arr.get(safe_values, key, _MISSING)
        if displayed is _MISSING:
            error_console.print(
                f"Configuration path [{key}] was not found.",
                style="red",
                markup=False,
            )
            raise typer.Exit(code=1)

    console.print(
        json.dumps(displayed, ensure_ascii=False, indent=2),
        markup=False,
    )


@app.command("config:cache")
def cache_config() -> None:
    """Validate and safely cache the current application configuration.

    Raises:
        typer.Exit: If a source is invalid or a value is not safely
            serializable.
    """
    try:
        cache_path = ConfigManager(Path.cwd()).cache_configuration()
    except ConfigurationError as error:
        _configuration_error(error)
    console.print(f"Configuration cached at {cache_path.name}.")


@app.command("config:clear")
def clear_config_cache() -> None:
    """Remove only the generated application configuration cache.

    Raises:
        typer.Exit: If the cache cannot be safely cleared.
    """
    cache = ConfigCache(Path.cwd() / "bootstrap" / "cache" / "config.json")
    try:
        cache.clear()
    except ConfigurationError as error:
        _configuration_error(error)
    console.print("Configuration cache cleared.")


@app.command("config:validate")
def validate_config() -> None:
    """Load all trusted configuration sources and report their validity.

    Raises:
        typer.Exit: If configuration cannot be loaded or validated.
    """
    try:
        ConfigManager(Path.cwd()).validate()
    except ConfigurationError as error:
        _configuration_error(error)
    console.print("Configuration is valid.")


def _configuration_error(error: ConfigurationError) -> NoReturn:
    """Report a native configuration failure without exposing source values.

    Args:
        error: Safe Titanspan configuration diagnostic.

    Raises:
        typer.Exit: Always, with an unsuccessful command status.
    """
    error_console.print(str(error), style="red", markup=False)
    raise typer.Exit(code=1) from error


def main() -> None:
    """Run the configured Typer application against process arguments.

    This function is used by both the installed console script and the module
    entry point, preserving one command registration path.
    """
    app()
