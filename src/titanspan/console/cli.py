"""Configure the installed command entry point and bootstrap commands.

Application commands register through the native Console API.
The route command's shared contract annotations are resolved at runtime.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NoReturn, TypeGuard, cast

from titanspan import __version__
from titanspan.cache.commands import register_cache_commands
from titanspan.config import ConfigManager, ConfigurationError
from titanspan.console import (
    Argument,
    Console,
    ConsoleExitError,
    Option,
)
from titanspan.console.exceptions import CommandGenerationError
from titanspan.console.generators import ArtifactKind, generate_artifact
from titanspan.contracts import (  # noqa: TC001
    ApplicationPaths,
    ConsoleOutput,
    RouteCatalog,
)
from titanspan.contracts.config import ConfigRepository  # noqa: TC001
from titanspan.contracts.http import MiddlewareDeclaration
from titanspan.database.commands import register_database_commands
from titanspan.events import (
    DiscoveryEntry,
    EventDiscoveryError,
    EventsConfiguration,
    cache_events,
    clear_event_cache,
    inspect_events,
)
from titanspan.queue.commands import register_queue_commands
from titanspan.routing import RouteCache, RouteCacheError
from titanspan.routing.router import Router  # noqa: TC001
from titanspan.support.arr import Arr

if TYPE_CHECKING:
    from titanspan.contracts.config import ConfigDiagnostics
    from titanspan.contracts.http import MiddlewareItem
    from titanspan.contracts.routing import (
        ControllerAction,
        RouteInfo,
    )

__all__ = ["console", "main"]

console = Console(
    name="titanspan",
    description="Engineer beyond limits.",
    version=__version__,
)
register_cache_commands(console)
register_queue_commands(console)
register_database_commands(console)
_MISSING = object()
_CONTROLLER_ACTION_PARTS = 2
_ROUTE_CACHE_PARTS = ("bootstrap", "cache", "routes.json")


@console.command("about", with_application=False)
def about() -> None:
    """Display the framework and Python runtime versions.

    The command does not start an application or inspect its configuration.
    """
    console.output.write(f"Titanspan {__version__}")
    console.output.write(f"Python {platform.python_version()}")


@console.command("config:show", with_application=False)
def show_config(
    key: Annotated[
        str | None,
        Argument(description="Optional dotted configuration path to display."),
    ] = None,
    base_path: Annotated[
        Path | None,
        Option(
            "--path",
            description="Application root containing the config directory.",
        ),
    ] = None,
) -> None:
    """Show a safe configuration snapshot or one selected value.

    Args:
        key: Optional dotted path within the application configuration.
        base_path: Optional application root. Defaults to the current directory.

    Raises:
        ConsoleExitError: If configuration loading fails or the key is missing.
    """
    try:
        diagnostics: ConfigDiagnostics = ConfigManager(
            _selected_base_path(base_path),
        ).validate()
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
def cache_config(
    base_path: Annotated[
        Path | None,
        Option(
            "--path",
            description="Application root containing the config directory.",
        ),
    ] = None,
) -> None:
    """Validate and safely cache the current application configuration.

    Args:
        base_path: Optional application root. Defaults to the current directory.

    Raises:
        ConsoleExitError: If a source is invalid or a value cannot be encoded.
    """
    try:
        cache_path = ConfigManager(
            _selected_base_path(base_path),
        ).cache_configuration()
    except ConfigurationError as error:
        _configuration_error(error)
    console.output.write(f"Configuration cached at {cache_path.name}.")


@console.command("config:clear", with_application=False)
def clear_config_cache(
    base_path: Annotated[
        Path | None,
        Option(
            "--path",
            description="Application root containing the config cache.",
        ),
    ] = None,
) -> None:
    """Remove only the generated application configuration cache.

    Args:
        base_path: Optional application root. Defaults to the current directory.

    Raises:
        ConsoleExitError: If the cache cannot be safely cleared.
    """
    try:
        ConfigManager(_selected_base_path(base_path)).clear_cache()
    except ConfigurationError as error:
        _configuration_error(error)
    console.output.write("Configuration cache cleared.")


@console.command("config:validate", with_application=False)
def validate_config(
    base_path: Annotated[
        Path | None,
        Option(
            "--path",
            description="Application root containing the config directory.",
        ),
    ] = None,
) -> None:
    """Load trusted configuration sources and report their validity.

    Args:
        base_path: Optional application root. Defaults to the current directory.

    Raises:
        ConsoleExitError: If configuration cannot be loaded or validated.
    """
    try:
        ConfigManager(_selected_base_path(base_path)).validate()
    except ConfigurationError as error:
        _configuration_error(error)
    console.output.write("Configuration is valid.")


@console.command(
    "route:list",
    description="List registered application routes.",
)
def list_routes(
    catalog: RouteCatalog,
    output: ConsoleOutput,
) -> None:
    """Display the active application's registered route catalog.

    Args:
        catalog: Canonical route collection resolved from the app Container.
        output: Shared terminal output service for the current CLI run.
    """
    rows = tuple(_route_row(route) for route in catalog.all())
    output.table(
        ("METHOD", "DOMAIN", "URI", "NAME", "ACTION", "MIDDLEWARE"),
        rows,
    )


@console.command(
    "route:cache",
    description="Write a route metadata snapshot for inspection.",
)
def cache_routes(
    router: Router,
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Write validated route metadata under the active application root.

    Args:
        router: Canonical router registered by Foundation.
        paths: Effective application path provider.
        output: Shared output service for the command run.

    Raises:
        ConsoleExitError: If route metadata cannot be represented safely.
    """
    cache_path = paths.path(*_ROUTE_CACHE_PARTS)
    try:
        RouteCache(cache_path).write(router)
    except RouteCacheError as error:
        output.write_error(str(error))
        raise ConsoleExitError(1) from error
    output.write(
        "Route metadata cached. Route discovery still runs at startup."
    )


@console.command(
    "route:clear",
    description="Remove the route metadata snapshot.",
)
def clear_route_cache(
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Remove route metadata under the active application root.

    Args:
        paths: Effective application path provider.
        output: Shared output service for the command run.

    Raises:
        ConsoleExitError: If route metadata cannot be removed.
    """
    try:
        RouteCache(paths.path(*_ROUTE_CACHE_PARTS)).clear()
    except RouteCacheError as error:
        output.write_error(str(error))
        raise ConsoleExitError(1) from error
    output.write("Route metadata cache cleared.")


@console.command(
    "event:list",
    description="List trusted application event listeners.",
)
def list_events(
    repository: ConfigRepository,
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Inspect configured event modules without registering listeners.

    Args:
        repository: Canonical application configuration repository.
        paths: Effective application paths used for trusted cache settings.
        output: Shared terminal output service for this command.

    Raises:
        ConsoleExitError: If event configuration or discovery is invalid.
    """
    configuration = EventsConfiguration.from_repository(
        repository,
        base_path=paths.base_path,
    )
    try:
        entries = inspect_events(configuration.discovery_modules)
    except EventDiscoveryError as error:
        _event_discovery_error(output, error)
    output.table(
        ("EVENT", "LISTENER", "KIND"),
        _event_rows(entries),
    )


@console.command(
    "event:cache",
    description="Build the configured event discovery manifest.",
)
def cache_application_events(
    repository: ConfigRepository,
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Build the event manifest used by application startup.

    Args:
        repository: Canonical application configuration repository.
        paths: Effective application paths for relative manifest values.
        output: Shared terminal output service for this command.

    Raises:
        ConsoleExitError: If no manifest is configured or discovery fails.
    """
    configuration = EventsConfiguration.from_repository(
        repository,
        base_path=paths.base_path,
    )
    manifest_path = configuration.manifest_path
    if manifest_path is None:
        output.write_error(
            "Set events.manifest_path before caching event discovery."
        )
        raise ConsoleExitError(1)
    try:
        cache_events(configuration.discovery_modules, manifest_path)
    except EventDiscoveryError as error:
        _event_discovery_error(output, error)
    output.write("Event discovery manifest cached.")


@console.command(
    "event:clear",
    description="Remove the configured event discovery manifest.",
)
def clear_application_event_cache(
    repository: ConfigRepository,
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Remove the event manifest selected by application configuration.

    Args:
        repository: Canonical application configuration repository.
        paths: Effective application paths for relative manifest values.
        output: Shared terminal output service for this command.

    Raises:
        ConsoleExitError: If no manifest is configured or cleanup fails.
    """
    configuration = EventsConfiguration.from_repository(
        repository,
        base_path=paths.base_path,
    )
    manifest_path = configuration.manifest_path
    if manifest_path is None:
        output.write_error(
            "Set events.manifest_path before clearing event discovery."
        )
        raise ConsoleExitError(1)
    try:
        clear_event_cache(manifest_path)
    except EventDiscoveryError as error:
        _event_discovery_error(output, error)
    output.write("Event discovery manifest cleared.")


@console.command(
    "make:controller",
    description="Generate a native HTTP controller.",
)
def make_controller(
    name: Annotated[str, Argument(description="Controller class name.")],
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Generate a typed controller under the application root.

    Args:
        name: Class name or dotted application module path.
        paths: Effective application root selected during composition.
        output: Shared terminal output service for this command.

    Raises:
        ConsoleExitError: If the name or destination is invalid.
    """
    _generate_application_artifact("controller", name, paths, output)


@console.command(
    "make:middleware",
    description="Generate native HTTP middleware.",
)
def make_middleware(
    name: Annotated[str, Argument(description="Middleware class name.")],
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Generate typed request middleware under the application root.

    Args:
        name: Class name or dotted application module path.
        paths: Effective application root selected during composition.
        output: Shared terminal output service for this command.

    Raises:
        ConsoleExitError: If the name or destination is invalid.
    """
    _generate_application_artifact("middleware", name, paths, output)


@console.command(
    "make:provider",
    description="Generate a native service provider.",
)
def make_provider(
    name: Annotated[str, Argument(description="Provider class name.")],
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Generate a provider that registers an application service.

    Args:
        name: Class name or dotted application module path.
        paths: Effective application root selected during composition.
        output: Shared terminal output service for this command.

    Raises:
        ConsoleExitError: If the name or destination is invalid.
    """
    _generate_application_artifact("provider", name, paths, output)


@console.command(
    "make:command",
    description="Generate an injectable Console command.",
)
def make_command(
    name: Annotated[str, Argument(description="Command class name.")],
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Generate an injectable Console command under the application root.

    Args:
        name: Class name or dotted application module path.
        paths: Effective application root selected during composition.
        output: Shared terminal output service for this command.

    Raises:
        ConsoleExitError: If the name or destination is invalid.
    """
    _generate_application_artifact("command", name, paths, output)


@console.command(
    "make:event",
    description="Generate a typed application event.",
)
def make_event(
    name: Annotated[str, Argument(description="Event class name.")],
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Generate a typed event value under the application root.

    Args:
        name: Class name or dotted application module path.
        paths: Effective application root selected during composition.
        output: Shared terminal output service for this command.

    Raises:
        ConsoleExitError: If the name or destination is invalid.
    """
    _generate_application_artifact("event", name, paths, output)


@console.command(
    "make:listener",
    description="Generate an injected listener for an event type.",
)
def make_listener(
    name: Annotated[str, Argument(description="Listener class name.")],
    paths: ApplicationPaths,
    output: ConsoleOutput,
    event_type: Annotated[
        str | None,
        Option(
            "--event",
            description="Trusted fully qualified event class path.",
        ),
    ] = None,
) -> None:
    """Generate an injected listener for a trusted event class.

    Args:
        name: Class name or dotted application module path.
        paths: Effective application root selected during composition.
        output: Shared terminal output service for this command.
        event_type: Trusted import path such as ``app.events.DocumentReady``.

    Raises:
        ConsoleExitError: If the event path or destination is invalid.
    """
    _generate_application_artifact(
        "listener",
        name,
        paths,
        output,
        event_type=event_type,
    )


@console.command(
    "make:test",
    description="Generate an application lifecycle test.",
)
def make_test(
    name: Annotated[str, Argument(description="Test module name.")],
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Generate a pytest smoke test under the application root.

    Args:
        name: Test name or dotted application module path.
        paths: Effective application root selected during composition.
        output: Shared terminal output service for this command.

    Raises:
        ConsoleExitError: If the name or destination is invalid.
    """
    _generate_application_artifact("test", name, paths, output)


def _generate_application_artifact(
    kind: ArtifactKind,
    name: str,
    paths: ApplicationPaths,
    output: ConsoleOutput,
    *,
    event_type: str | None = None,
) -> None:
    """Generate one selected artifact and report its application-relative path.

    Args:
        kind: Artifact type selected by a registered command.
        name: Validated by the artifact generator before file creation.
        paths: Effective application path provider.
        output: Safe terminal output contract.
        event_type: Trusted event type required for listener generation.

    Raises:
        ConsoleExitError: If generation fails with a safe native error.
    """
    try:
        target = generate_artifact(
            paths,
            kind,
            name,
            event_type=event_type,
        )
    except CommandGenerationError as error:
        output.write_error(str(error))
        raise ConsoleExitError(1) from error
    output.write(f"Generated {target.relative_to(paths.base_path)}.")


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


def _selected_base_path(base_path: Path | None) -> Path:
    """Select an application root without changing the process directory.

    Args:
        base_path: Optional explicit root supplied to a config command.

    Returns:
        The explicit root or the current directory for CLI convention.
    """
    return Path.cwd() if base_path is None else base_path


def _event_rows(
    entries: tuple[DiscoveryEntry, ...],
) -> tuple[tuple[str, str, str], ...]:
    """Format trusted discovery entries as stable terminal rows.

    Args:
        entries: Descriptors returned by the Events discovery API.

    Returns:
        One row for each listener selector or subscriber.
    """
    rows: list[tuple[str, str, str]] = []
    for entry in entries:
        listener = f"{entry.module}:{entry.qualname}"
        if entry.method is not None:
            listener = f"{listener}.{entry.method}"
        if entry.is_subscriber and not entry.selectors:
            rows.append(("*", listener, "subscriber"))
            continue
        for selector in entry.selectors:
            event_name = (
                selector
                if isinstance(selector, str)
                else f"{selector.__module__}.{selector.__qualname__}"
            )
            rows.append(
                (
                    event_name,
                    listener,
                    "subscriber" if entry.is_subscriber else "listener",
                )
            )
    return tuple(rows)


def _event_discovery_error(
    output: ConsoleOutput,
    error: EventDiscoveryError,
) -> NoReturn:
    """Report an event command failure without backend details.

    Args:
        output: Safe plain-text command output.
        error: Event error classified by its native exception type.

    Raises:
        ConsoleExitError: Always, with a failing process status.
    """
    _ = error
    output.write_error("Event discovery failed; check trusted configuration.")
    raise ConsoleExitError(1)


def _route_row(route: RouteInfo) -> tuple[str, ...]:
    """Format public route metadata without invoking application code.

    Args:
        route: Read-only route view from the canonical catalog.

    Returns:
        A stable table row containing methods, domain, URI, name, action,
        and middleware labels.
    """
    action = route.action
    if action is None:
        action_name = "-"
    elif _is_controller_action(action):
        controller, method = action
        action_name = f"{controller.__qualname__}.{method}"
    elif isinstance(action, type):
        action_name = action.__qualname__
    else:
        name = getattr(action, "__name__", None)
        action_name = name if isinstance(name, str) else type(action).__name__

    middleware_names = tuple(
        _route_middleware_name(middleware)
        for middleware in route.middleware_types
    )
    return (
        ", ".join(route.methods),
        route.domain_name or "-",
        route.path,
        route.route_name or "-",
        action_name,
        ", ".join(middleware_names) or "-",
    )


def _route_middleware_name(middleware: MiddlewareItem) -> str:
    """Format middleware identity without exposing parameter values.

    Args:
        middleware: Alias, class, or immutable middleware declaration.

    Returns:
        A stable route inspection label with no configured values.
    """
    if isinstance(middleware, MiddlewareDeclaration):
        target = middleware.target
        name = target if isinstance(target, str) else target.__qualname__
        return f"{name} [parameterized]" if middleware.parameters else name
    return (
        middleware if isinstance(middleware, str) else middleware.__qualname__
    )


def _is_controller_action(action: object) -> TypeGuard[ControllerAction]:
    """Identify a controller action without trusting tuple contents.

    Args:
        action: Candidate endpoint identity from the shared route contract.

    Returns:
        Whether the value contains a controller class and method name.
    """
    if not isinstance(action, tuple):
        return False
    # The runtime check establishes tuple-ness; erase only its unknown slots.
    candidate = cast("tuple[object, ...]", action)
    return (
        len(candidate) == _CONTROLLER_ACTION_PARTS
        and isinstance(candidate[0], type)
        and isinstance(candidate[1], str)
    )
