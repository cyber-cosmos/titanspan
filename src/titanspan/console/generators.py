"""Generate small, executable Titanspan application artifacts.

The generator writes only to the active application root and never replaces
an existing file.
"""

from __future__ import annotations

import re
from textwrap import dedent
from typing import TYPE_CHECKING, Literal

from titanspan.console.exceptions import CommandGenerationError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from titanspan.contracts.foundation import ApplicationPaths

type ArtifactKind = Literal[
    "controller",
    "middleware",
    "provider",
    "command",
    "event",
    "listener",
    "job",
    "job_middleware",
    "model",
    "seeder",
    "test",
]

_ARTIFACT_LAYOUT: dict[ArtifactKind, tuple[tuple[str, ...], str, str]] = {
    "controller": (("app", "controllers"), "", "_controller"),
    "middleware": (("app", "middleware"), "", "_middleware"),
    "provider": (("app", "providers"), "", "_service_provider"),
    "command": (("app", "commands"), "", "_command"),
    "event": (("app", "events"), "", "_event"),
    "listener": (("app", "listeners"), "", "_listener"),
    "job": (("app", "jobs"), "", "_job"),
    "job_middleware": (
        ("app", "job_middleware"),
        "",
        "_job_middleware",
    ),
    "model": (("app", "models"), "", "_model"),
    "seeder": (("database", "seeders"), "", "_seeder"),
    "test": (("tests",), "test_", ""),
}
_NAME_SEGMENT = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z", re.ASCII)
_IMPORT_SEGMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)
_FIRST_CAPITAL_BOUNDARY = re.compile(r"(.)([A-Z][a-z]+)")
_CAPITAL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_INVALID_NAME_ERROR = "Use a class name or dotted application module path."
_INVALID_EVENT_TYPE_ERROR = (
    "The listener event must use a trusted dotted Python class path."
)
_OUTSIDE_ROOT_ERROR = "Generated files must stay inside the application root."
_EXISTS_ERROR = "The generated file already exists; it was not replaced."
_WRITE_ERROR = "The generated file could not be written."


def generate_artifact(
    paths: ApplicationPaths,
    kind: ArtifactKind,
    name: str,
    *,
    event_type: str | None = None,
) -> Path:
    """Create one typed starter artifact under the selected application root.

    Args:
        paths: Canonical application path service.
        kind: Artifact type selected by the native Console command.
        name: Class name or dotted application module path.
        event_type: Trusted dotted event class path for listeners.

    Returns:
        The generated file path.

    Raises:
        CommandGenerationError: If input, path safety, or file creation fails.
    """
    name_parts = _validated_name(name)
    root = paths.base_path.resolve()
    directories, prefix, suffix = _ARTIFACT_LAYOUT[kind]
    artifact_name = _snake_case(name_parts[-1])
    strip_suffix = _class_suffix(kind)
    if artifact_name.endswith(strip_suffix.lower()):
        artifact_name = artifact_name[: -len(strip_suffix)]
    class_name = _class_name(artifact_name)
    class_suffix = _generated_class_suffix(kind)
    if class_suffix:
        class_name += class_suffix

    module_parts = tuple(_snake_case(part) for part in name_parts[:-1])
    file_name = f"{prefix}{artifact_name}{suffix}.py"
    path_parts = (*directories, *module_parts, file_name)
    target = paths.path(*path_parts)
    _require_path_within_root(target, root)

    source = _render_source(kind, class_name, artifact_name, event_type)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        _require_path_within_root(target.parent, root)
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(source)
    except FileExistsError:
        if target.exists() or target.is_symlink():
            raise CommandGenerationError(_EXISTS_ERROR) from None
        raise CommandGenerationError(_WRITE_ERROR) from None
    except OSError:
        raise CommandGenerationError(_WRITE_ERROR) from None
    return target


def _require_path_within_root(path: Path, root: Path) -> None:
    """Reject a resolved path outside the selected application root.

    Args:
        path: Candidate path after joining trusted application segments.
        root: Resolved root selected by Foundation.

    Raises:
        CommandGenerationError: If symlinks or traversal escape the root.
    """
    if not path.resolve().is_relative_to(root):
        raise CommandGenerationError(_OUTSIDE_ROOT_ERROR)


def _validated_name(name: str) -> tuple[str, ...]:
    """Validate a class name or dotted module path.

    Args:
        name: User-supplied artifact name.

    Returns:
        Safe name segments used only as path components.

    Raises:
        CommandGenerationError: If any segment is unsafe or empty.
    """
    parts = tuple(name.split("."))
    if not parts or any(
        _NAME_SEGMENT.fullmatch(part) is None for part in parts
    ):
        raise CommandGenerationError(_INVALID_NAME_ERROR)
    return parts


def _snake_case(value: str) -> str:
    """Convert one validated Python identifier to a file-name segment.

    Args:
        value: Validated class or module name.

    Returns:
        Lowercase underscore-separated identifier.
    """
    first = _FIRST_CAPITAL_BOUNDARY.sub(r"\1_\2", value)
    return _CAPITAL_BOUNDARY.sub(r"\1_\2", first).lower()


def _class_name(value: str) -> str:
    """Convert one normalized identifier to a PascalCase class name.

    Args:
        value: Lowercase underscore-separated identifier.

    Returns:
        PascalCase class name without a component suffix.
    """
    return "".join(part.capitalize() for part in value.split("_"))


def _class_suffix(kind: ArtifactKind) -> str:
    """Return the file-name suffix removed before generation.

    Args:
        kind: Artifact type selected by the command.

    Returns:
        Lowercase suffix used to avoid duplicate names.
    """
    return {
        "controller": "_controller",
        "middleware": "_middleware",
        "provider": "_service_provider",
        "command": "_command",
        "event": "_event",
        "listener": "_listener",
        "job": "_job",
        "job_middleware": "_job_middleware",
        "model": "_model",
        "seeder": "_seeder",
        "test": "_test",
    }[kind]


def _generated_class_suffix(kind: ArtifactKind) -> str:
    """Return the conventional class suffix for generated classes.

    Args:
        kind: Artifact type selected by the command.

    Returns:
        PascalCase suffix, or an empty value for test modules.
    """
    return {
        "controller": "Controller",
        "middleware": "Middleware",
        "provider": "ServiceProvider",
        "command": "Command",
        "event": "Event",
        "listener": "Listener",
        "job": "Job",
        "job_middleware": "JobMiddleware",
        "model": "",
        "seeder": "Seeder",
        "test": "",
    }[kind]


def _render_source(
    kind: ArtifactKind,
    class_name: str,
    artifact_name: str,
    event_type: str | None,
) -> str:
    """Render one executable artifact using native public contracts.

    Args:
        kind: Artifact type selected by the command.
        class_name: Validated PascalCase type name.
        artifact_name: Validated lowercase file-name stem.
        event_type: Optional trusted class path for listener artifacts.

    Returns:
        Complete source text with a final newline.

    Raises:
        CommandGenerationError: If listener metadata is incomplete or unsafe.
    """
    if kind == "model":
        return dedent(_model_source(class_name)).lstrip() + "\n"
    if kind == "test":
        return dedent(_test_source(artifact_name)).lstrip() + "\n"
    renderers: dict[ArtifactKind, Callable[[], str]] = {
        "controller": lambda: _controller_source(
            class_name,
            artifact_name,
        ),
        "middleware": lambda: _middleware_source(class_name),
        "provider": lambda: _provider_source(class_name, artifact_name),
        "command": lambda: _command_source(class_name, artifact_name),
        "event": lambda: _event_source(class_name),
        "listener": lambda: _listener_source(class_name, event_type),
        "job": lambda: _job_source(class_name, artifact_name),
        "job_middleware": lambda: _job_middleware_source(class_name),
        "seeder": lambda: _seeder_source(class_name),
    }
    source = renderers[kind]()
    return dedent(source).lstrip() + "\n"


def _controller_source(class_name: str, resource_name: str) -> str:
    """Render a controller that returns a native JSON response.

    Args:
        class_name: Generated controller class name.
        resource_name: Lowercase resource identifier.

    Returns:
        Importable controller source.
    """
    return f'''\
    """Provide the generated {class_name} HTTP controller.

    This module uses native Titanspan response contracts.
    """

    from titanspan.contracts.http import HttpResponse, ResponseFactory


    class {class_name}:
        """Handle requests for the {resource_name} resource.

        The controller resolves through the application Container.
        """

        def index(self, response: ResponseFactory) -> HttpResponse:
            """Return a small JSON response for the resource.

            Args:
                response: Application-owned response factory.

            Returns:
                Native response with the resource name.
            """
            return response.json({{"resource": "{_class_name(resource_name)}"}})
'''


def _middleware_source(class_name: str) -> str:
    """Render a request middleware that delegates to the next handler.

    Args:
        class_name: Generated middleware class name.

    Returns:
        Importable middleware source.
    """
    return f'''\
    """Provide the generated {class_name} HTTP middleware.

    This middleware uses Titanspan's native request and response contracts.
    """

    from titanspan.contracts.http import (
        HttpRequest,
        HttpResponse,
        RequestHandler,
    )


    class {class_name}:
        """Continue each request through the configured middleware chain.

        The middleware does not mutate request or response state.
        """

        async def handle(
            self,
            request: HttpRequest,
            next_handler: RequestHandler,
        ) -> HttpResponse:
            """Pass a request to the next handler.

            Args:
                request: Request-scoped native HTTP interface.
                next_handler: Remaining middleware and route handler.

            Returns:
                Response produced by the downstream handler.
            """
            return await next_handler(request)
'''


def _provider_source(class_name: str, service_name: str) -> str:
    """Render a provider that registers one usable application service.

    Args:
        class_name: Generated provider class name.
        service_name: Generated service type name.

    Returns:
        Importable provider and service source.
    """
    return f'''\
    """Provide the generated {class_name} application provider.

    The provider registers one application-owned service.
    """

    from titanspan.contracts.container import ServiceRegistry


    class {service_name}Service:
        """Expose a stable service label for application composition.

        The generated type can be replaced through a native provider.
        """

        def label(self) -> str:
            """Return this service's generated label.

            Returns:
                Lowercase service identifier.
            """
            return "{service_name.lower()}"


    class {class_name}:
        """Register the generated service through the native Container.

        The provider contributes no separate service registry.
        """

        def register(self, container: ServiceRegistry) -> None:
            """Bind the service as an application-owned singleton.

            Args:
                container: Canonical application service registry.
            """
            container.singleton({service_name}Service)
'''


def _command_source(class_name: str, command_name: str) -> str:
    """Render an injectable Console command class.

    Args:
        class_name: Generated command class name.
        command_name: Lowercase command label.

    Returns:
        Importable command source.
    """
    return f'''\
    """Provide the generated {class_name} Console command.

    Register this command through the native CommandRegistrar contract.
    """

    from titanspan.contracts.console import ConsoleOutput


    class {class_name}:
        """Write one stable status message to the active Console.

        The command resolves its output through the application Container.
        """

        def handle(self, output: ConsoleOutput) -> None:
            """Write the command status.

            Args:
                output: Application-owned Console output service.
            """
            output.write("{command_name} command is ready.")
'''


def _event_source(class_name: str) -> str:
    """Render a frozen dataclass event with a typed payload.

    Args:
        class_name: Generated event class name.

    Returns:
        Importable event source.
    """
    return f'''\
    """Provide the generated {class_name} event value.

    Event payloads remain ordinary Python values.
    """

    from dataclasses import dataclass


    @dataclass(frozen=True, slots=True)
    class {class_name}:
        """Carry one application event payload.

        Attributes:
            payload: Event data selected by the caller.
        """

        payload: object = None
'''


def _job_source(class_name: str, job_name: str) -> str:
    """Render an importable dataclass job using the native Queue API.

    Args:
        class_name: Generated job class name.
        job_name: Lowercase job identifier used in its docstring.

    Returns:
        Typed Queue job source with a serializable empty payload.
    """
    return f'''\
    """Provide the generated {class_name} Queue job.

    Register this trusted type with QueueServiceProvider.
    """

    from dataclasses import dataclass

    from titanspan.queue import Job


    @dataclass
    class {class_name}(Job):
        """Run the {job_name} job through the application Container."""

        async def handle(self) -> None:
            """Process this job using injected application services."""
            return None
'''


def _job_middleware_source(class_name: str) -> str:
    """Render async job middleware with an explicit continuation.

    Args:
        class_name: Generated job middleware class name.

    Returns:
        Importable middleware source using the Queue contracts.
    """
    return f'''\
    """Provide the generated {class_name} Queue middleware.

    Add this type to a job's middleware declaration.
    """

    from titanspan.contracts.queue import JobContext, JobNext


    class {class_name}:
        """Wrap one attempt without storing request-specific state."""

        async def handle(
            self,
            context: JobContext,
            next_handler: JobNext,
        ) -> object:
            """Continue the attempt through the remaining middleware.

            Args:
                context: Immutable metadata for this job attempt.
                next_handler: Async continuation for the next stage.

            Returns:
                The downstream job result.
            """
            _ = context
            return await next_handler()
'''


def _seeder_source(class_name: str) -> str:
    """Render a sync seeder that uses Titanspan's transaction boundary.

    Args:
        class_name: Generated Seeder subclass name.

    Returns:
        Importable application seeder source.
    """
    return f'''\
    """Provide the generated {class_name} database seeder.

    The seeder runs through the application Database service.
    """

    from titanspan.database import Seeder


    class {class_name}(Seeder):
        """Insert trusted baseline records for the application.

        Add application-specific model factories to ``run``.
        """

        def run(self) -> None:
            """Create initial database records in one transaction.

            This starter seeder intentionally has no initial data.
            """
            pass
'''


def _model_source(class_name: str) -> str:
    """Render a minimal application model using native conventions.

    Args:
        class_name: Generated Model subclass name.

    Returns:
        Importable application model source.
    """
    return f'''\
    """Provide the generated {class_name} database model."""

    from titanspan.database import Model


    class {class_name}(Model):
        """Represent {class_name} records in the application database."""

        pass
'''


def _listener_source(
    class_name: str,
    event_type: str | None,
) -> str:
    """Render an injected listener for one trusted event type.

    Args:
        class_name: Generated listener class name.
        event_type: Fully qualified event class supplied by the caller.

    Returns:
        Importable listener source.

    Raises:
        CommandGenerationError: If the event type is missing or invalid.
    """
    if event_type is None:
        raise CommandGenerationError(_INVALID_EVENT_TYPE_ERROR)
    module_name, separator, event_name = event_type.rpartition(".")
    module_parts = module_name.split(".")
    if (
        not separator
        or any(_IMPORT_SEGMENT.fullmatch(part) is None for part in module_parts)
        or _NAME_SEGMENT.fullmatch(event_name) is None
    ):
        raise CommandGenerationError(_INVALID_EVENT_TYPE_ERROR)
    return f'''\
    """Provide the generated {class_name} event listener.

    Discovery resolves this class through the application Container.
    """

    from {module_name} import {event_name}
    from titanspan.contracts.logging import LogWriter


    class {class_name}:
        """Record safe metadata when the selected event is dispatched.

        The listener does not retain or log event payload values.
        """

        async def handle(
            self,
            event: {event_name},
            logger: LogWriter,
        ) -> None:
            """Log the event type without retaining its payload.

            Args:
                event: Typed event selected during listener discovery.
                logger: Application-owned structured logger.
            """
            logger.info(
                "Application event handled",
                event_type=type(event).__qualname__,
            )
'''


def _test_source(test_name: str) -> str:
    """Render a pytest smoke test for application path and lifecycle setup.

    Args:
        test_name: Lowercase test identifier.

    Returns:
        Importable pytest module source.
    """
    return f'''\
    """Verify the generated {test_name} application smoke test.

    The test starts a real Titanspan Application.
    """

    from pathlib import Path

    import pytest

    from titanspan import Application


    @pytest.mark.anyio
    async def test_application_uses_its_root(tmp_path: Path) -> None:
        """Start an application rooted at the supplied temporary directory.

        Args:
            tmp_path: Isolated application directory provided by pytest.
        """
        (tmp_path / "routes").mkdir()
        application = Application(base_path=tmp_path)

        async with application:
            assert application.base_path == tmp_path.resolve()
'''


__all__ = ["ArtifactKind", "generate_artifact"]
