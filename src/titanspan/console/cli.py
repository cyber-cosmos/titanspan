"""Configure the installed command entry point and bootstrap commands.

Application commands register through the native Console API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NoReturn

from titanspan import __version__
from titanspan.config import ConfigCache, ConfigManager, ConfigurationError
from titanspan.console import Argument, Console, ConsoleExitError
from titanspan.support.arr import Arr

if TYPE_CHECKING:
    from titanspan.contracts.config import ConfigDiagnostics

__all__ = ["console", "main"]

console = Console(
    name="titanspan",
    description="Engineer beyond limits.",
    version=__version__,
)
_MISSING = object()


@console.command("config:show", with_application=False)
def show_config(
    key: Annotated[
        str | None,
        Argument(description="Optional dotted configuration path to display."),
    ] = None,
) -> None:
    """Show a safe configuration snapshot or one selected value.

    Args:
        key: Optional dotted path within the application configuration.

    Raises:
        ConsoleExitError: If configuration loading fails or the key is missing.
    """
    try:
        diagnostics: ConfigDiagnostics = ConfigManager(Path.cwd()).validate()
    except ConfigurationError as error:
        _configuration_error(error)

    safe_values = dict(diagnostics.redacted())
    displayed: object = safe_values
    if key is not None:
        displayed = Arr.get(safe_values, key, _MISSING)
        if displayed is _MISSING:
            console.output.write_error(
                f"Configuration path [{key}] was not found."
            )
            raise ConsoleExitError(1)

    console.output.write(json.dumps(displayed, ensure_ascii=False, indent=2))


@console.command("config:cache", with_application=False)
def cache_config() -> None:
    """Validate and safely cache the current application configuration.

    Raises:
        ConsoleExitError: If a source is invalid or a value cannot be encoded.
    """
    try:
        cache_path = ConfigManager(Path.cwd()).cache_configuration()
    except ConfigurationError as error:
        _configuration_error(error)
    console.output.write(f"Configuration cached at {cache_path.name}.")


@console.command("config:clear", with_application=False)
def clear_config_cache() -> None:
    """Remove only the generated application configuration cache.

    Raises:
        ConsoleExitError: If the cache cannot be safely cleared.
    """
    cache = ConfigCache(Path.cwd() / "bootstrap" / "cache" / "config.json")
    try:
        cache.clear()
    except ConfigurationError as error:
        _configuration_error(error)
    console.output.write("Configuration cache cleared.")


@console.command("config:validate", with_application=False)
def validate_config() -> None:
    """Load trusted configuration sources and report their validity.

    Raises:
        ConsoleExitError: If configuration cannot be loaded or validated.
    """
    try:
        ConfigManager(Path.cwd()).validate()
    except ConfigurationError as error:
        _configuration_error(error)
    console.output.write("Configuration is valid.")


def main() -> None:
    """Run the configured Console against process arguments.

    Installed component commands load through trusted entry points.
    """
    console.discover_commands().run()


def _configuration_error(error: ConfigurationError) -> NoReturn:
    """Report one safe configuration failure with a failing exit code.

    Args:
        error: Native configuration diagnostic with safe source details.

    Raises:
        ConsoleExitError: Always, with a non-zero status.
    """
    console.output.write_error(str(error))
    raise ConsoleExitError(1) from error
