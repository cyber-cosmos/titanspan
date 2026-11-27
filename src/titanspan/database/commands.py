"""Register native migration operations with the shared Console service.

All command execution and output remain within the application's Console.
"""

from __future__ import annotations

import re
from importlib import import_module
from typing import TYPE_CHECKING, Annotated, NoReturn

import anyio

from titanspan.console.exceptions import (
    CommandGenerationError,
    ConsoleExitError,
)
from titanspan.console.generators import generate_artifact
from titanspan.console.parameters import Argument, Option
from titanspan.contracts.config import ConfigRepository  # noqa: TC001
from titanspan.contracts.console import ConsoleOutput  # noqa: TC001
from titanspan.contracts.foundation import ApplicationPaths  # noqa: TC001
from titanspan.database.exceptions import (
    DatabaseError,
    DatabaseSeederError,
)
from titanspan.database.migration_manager import MigrationManager  # noqa: TC001
from titanspan.database.seeder import Seeder
from titanspan.foundation import app

if TYPE_CHECKING:
    from collections.abc import Callable

    from titanspan.contracts.console import CommandRegistrar

_CAMEL_BOUNDARY = re.compile(r"(.)([A-Z][a-z]+)")
_LOWER_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_INVALID_SEEDER_TARGET = (
    "Select a Seeder class name or a trusted module:Class path."
)
_SEEDER_IMPORT_ERROR = "The selected application seeder could not be imported."
_INVALID_SEEDER_CLASS = "The selected class must inherit from Seeder."


def register_database_commands(registrar: CommandRegistrar) -> None:
    """Register migration commands on the native application Console.

    Args:
        registrar: Shared registrar that owns parsing and application startup.
    """
    registrar.register_command(
        "migrate",
        run_migrations,
        description="Apply pending database migrations.",
    )
    registrar.register_command(
        "migrate:install",
        install_migrations,
        description="Create the database migration version table.",
    )
    registrar.register_command(
        "migrate:status",
        show_migration_status,
        description="Show database migration status.",
    )
    registrar.register_command(
        "migrate:rollback",
        rollback_migrations,
        description="Reverse recent database migrations.",
    )
    registrar.register_command(
        "migrate:reset",
        reset_migrations,
        description="Reverse all applied database migrations.",
    )
    registrar.register_command(
        "migrate:refresh",
        refresh_migrations,
        description="Reverse and reapply database migrations.",
    )
    registrar.register_command(
        "db:seed",
        seed_database,
        description="Run trusted application database seeders.",
    )
    registrar.register_command(
        "make:seeder",
        make_seeder,
        description="Generate an application database seeder.",
    )


def run_migrations(
    manager: MigrationManager,
    output: ConsoleOutput,
    database: Annotated[
        str | None,
        Option(
            "--database",
            description="Named database connection to migrate.",
        ),
    ] = None,
) -> None:
    """Apply pending Alembic revisions to the selected connection.

    Args:
        manager: Application-owned migration service.
        output: Native Console output for this invocation.
        database: Optional configured connection name.
    """
    _run_migration(
        lambda: manager.upgrade(connection=database),
        output,
        "Migration run completed.",
    )


def install_migrations(
    manager: MigrationManager,
    output: ConsoleOutput,
    database: Annotated[
        str | None,
        Option(
            "--database",
            description="Named database connection to install.",
        ),
    ] = None,
) -> None:
    """Create Alembic's revision table without applying revisions.

    Args:
        manager: Application-owned migration service.
        output: Native Console output for this invocation.
        database: Optional configured connection name.
    """
    _run_migration(
        lambda: manager.install(database),
        output,
        "Migration repository installed.",
    )


def show_migration_status(
    manager: MigrationManager,
    output: ConsoleOutput,
    database: Annotated[
        str | None,
        Option(
            "--database",
            description="Named database connection to inspect.",
        ),
    ] = None,
) -> None:
    """Show the Alembic revision graph and selected database state.

    Args:
        manager: Application-owned migration service.
        output: Native Console output for this invocation.
        database: Optional configured connection name.
    """
    try:
        revisions = manager.status(database)
    except DatabaseError as error:
        _report_migration_error(output, error)
    if not revisions:
        output.write("No migrations found.")
        return
    rows = [
        (
            revision.revision,
            "Applied" if revision.applied else "Pending",
            "Yes" if revision.current_head else "No",
        )
        for revision in revisions
    ]
    output.table(("Revision", "Status", "Current head"), rows)


def rollback_migrations(
    manager: MigrationManager,
    output: ConsoleOutput,
    config: ConfigRepository,
    database: Annotated[
        str | None,
        Option(
            "--database",
            description="Named database connection to roll back.",
        ),
    ] = None,
    step: Annotated[
        int,
        Option("--step", description="Number of revisions to reverse."),
    ] = 1,
    force: Annotated[
        bool,
        Option(
            "--force",
            description="Skip the destructive-operation confirmation.",
        ),
    ] = False,
) -> None:
    """Reverse recent revisions after the destructive-operation guard.

    Args:
        manager: Application-owned migration service.
        output: Native Console output for this invocation.
        config: Application configuration used for environment policy.
        database: Optional configured connection name.
        step: Positive count of Alembic revisions to reverse.
        force: Whether to bypass confirmation explicitly.
    """
    if not _confirm_destructive(
        output,
        config,
        database,
        force,
        "roll back database migrations",
    ):
        raise ConsoleExitError(1)
    _run_migration(
        lambda: manager.rollback(step, connection=database),
        output,
        "Migration rollback completed.",
    )


def reset_migrations(
    manager: MigrationManager,
    output: ConsoleOutput,
    config: ConfigRepository,
    database: Annotated[
        str | None,
        Option(
            "--database",
            description="Named database connection to reset.",
        ),
    ] = None,
    force: Annotated[
        bool,
        Option(
            "--force",
            description="Skip the destructive-operation confirmation.",
        ),
    ] = False,
) -> None:
    """Reverse all applied revisions after an environment guard.

    Args:
        manager: Application-owned migration service.
        output: Native Console output for this invocation.
        config: Application configuration used for environment policy.
        database: Optional configured connection name.
        force: Whether to bypass confirmation explicitly.
    """
    if not _confirm_destructive(
        output,
        config,
        database,
        force,
        "reset database migrations",
    ):
        raise ConsoleExitError(1)
    _run_migration(
        lambda: manager.reset(database),
        output,
        "Migration reset completed.",
    )


def refresh_migrations(
    manager: MigrationManager,
    output: ConsoleOutput,
    config: ConfigRepository,
    database: Annotated[
        str | None,
        Option(
            "--database",
            description="Named database connection to refresh.",
        ),
    ] = None,
    force: Annotated[
        bool,
        Option(
            "--force",
            description="Skip the destructive-operation confirmation.",
        ),
    ] = False,
) -> None:
    """Reverse and reapply revisions after an environment guard.

    Args:
        manager: Application-owned migration service.
        output: Native Console output for this invocation.
        config: Application configuration used for environment policy.
        database: Optional configured connection name.
        force: Whether to bypass confirmation explicitly.
    """
    if not _confirm_destructive(
        output,
        config,
        database,
        force,
        "refresh database migrations",
    ):
        raise ConsoleExitError(1)
    _run_migration(
        lambda: manager.refresh(database),
        output,
        "Migration refresh completed.",
    )


async def seed_database(
    output: ConsoleOutput,
    config: ConfigRepository,
    seeder: Annotated[
        str,
        Option(
            "--class",
            description="Seeder class name or trusted module:Class path.",
        ),
    ] = "DatabaseSeeder",
    database: Annotated[
        str | None,
        Option(
            "--database",
            description="Named database connection for the seeder tree.",
        ),
    ] = None,
    force: Annotated[
        bool,
        Option(
            "--force",
            description="Skip the database seeding confirmation.",
        ),
    ] = False,
) -> None:
    """Run one trusted seeder and its nested seeders.

    Synchronous seeder bodies run in a worker thread. Async seeder bodies run
    in the command task and keep their task-owned database session.

    Args:
        output: Native Console output for this invocation.
        config: Application configuration used for production policy.
        seeder: Simple class name or trusted import path.
        database: Optional selected connection inherited by child seeders.
        force: Whether to bypass the non-production confirmation prompt.

    Raises:
        ConsoleExitError: If the target or database operation is invalid.
    """
    if not _confirm_seeding(output, config, database, force):
        raise ConsoleExitError(1)
    try:
        seeder_type = _resolve_seeder(seeder)
        if seeder_type.run_async is Seeder.run_async:
            await anyio.to_thread.run_sync(
                _execute_sync_seeder,
                seeder_type,
                database,
                abandon_on_cancel=False,
            )
        else:
            instance = await app().container.make_async(seeder_type)
            await instance.execute_async(database)
    except DatabaseError as error:
        output.write_error(str(error))
        raise ConsoleExitError(1) from error
    output.write("Database seeding completed.")


def make_seeder(
    name: Annotated[str, Argument(description="Seeder class name.")],
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Generate one typed database seeder beneath the application root.

    Args:
        name: Seeder name or dotted application module path.
        paths: Foundation-owned application paths.
        output: Native Console output for this invocation.

    Raises:
        ConsoleExitError: If the name or destination is unsafe or unavailable.
    """
    try:
        target = generate_artifact(paths, "seeder", name)
    except CommandGenerationError as error:
        output.write_error(str(error))
        raise ConsoleExitError(1) from error
    output.write(f"Generated {target.relative_to(paths.base_path)}.")


def _execute_sync_seeder(
    seeder_type: type[Seeder],
    database: str | None,
) -> None:
    """Resolve and execute a sync seeder in Console's worker thread.

    Args:
        seeder_type: Trusted Seeder subclass selected by the command caller.
        database: Optional connection inherited by this seeder tree.
    """
    app().container.make(seeder_type).execute(database)


def _resolve_seeder(target: str) -> type[Seeder]:
    """Resolve one explicitly selected application seeder class.

    Args:
        target: Class name or trusted ``module:Class`` import path.

    Returns:
        The selected application-defined Seeder subclass.

    Raises:
        DatabaseSeederError: If the target is malformed or unavailable.
    """
    module_name, separator, class_name = target.partition(":")
    if not separator:
        class_name = target
        if not _is_identifier(class_name):
            raise DatabaseSeederError(_INVALID_SEEDER_TARGET)
        module_name = f"database.seeders.{_snake_case(class_name)}"
    elif not _is_module_path(module_name) or not _is_identifier(class_name):
        raise DatabaseSeederError(_INVALID_SEEDER_TARGET)

    try:
        module = import_module(module_name)
        selected = getattr(module, class_name)
    except (AttributeError, ImportError, ValueError) as error:
        raise DatabaseSeederError(_SEEDER_IMPORT_ERROR) from error
    if not isinstance(selected, type) or not issubclass(selected, Seeder):
        raise DatabaseSeederError(_INVALID_SEEDER_CLASS)
    if selected is Seeder:
        raise DatabaseSeederError(_INVALID_SEEDER_CLASS)
    return selected


def _confirm_seeding(
    output: ConsoleOutput,
    config: ConfigRepository,
    database: str | None,
    force: bool,
) -> bool:
    """Enforce environment policy before running application data code.

    Args:
        output: Console prompt and diagnostic boundary.
        config: Application configuration repository.
        database: Selected connection name, if supplied.
        force: Whether the caller explicitly bypassed confirmation.

    Returns:
        Whether the seeding operation is authorized by the environment.
    """
    environment = config.get("app.env", "production")
    if not isinstance(environment, str):
        output.write_error("The application environment is invalid.")
        return False
    if environment.casefold() == "production" and not force:
        output.write_error(
            "Production database seeding requires --force.",
        )
        return False
    if force:
        return True
    target = "default" if database is None else database
    return output.confirm(
        f"Confirm database seeding on connection [{target}]?",
        default=False,
    )


def _is_identifier(value: str) -> bool:
    """Return whether one import component is a safe Python identifier.

    Args:
        value: Candidate module or class identifier.

    Returns:
        Whether the candidate contains only a valid identifier shape.
    """
    return value.isidentifier()


def _is_module_path(value: str) -> bool:
    """Validate every identifier in an explicit seeder module path.

    Args:
        value: Dotted Python module path selected by the operator.

    Returns:
        Whether the path is a non-empty sequence of identifiers.
    """
    parts = value.split(".")
    return bool(parts) and all(_is_identifier(part) for part in parts)


def _snake_case(value: str) -> str:
    """Convert a CamelCase seeder type to its conventional module stem.

    Args:
        value: Valid Python class identifier.

    Returns:
        Lowercase underscore-separated class name.
    """
    first = _CAMEL_BOUNDARY.sub(r"\1_\2", value)
    return _LOWER_BOUNDARY.sub(r"\1_\2", first).lower()


def _confirm_destructive(
    output: ConsoleOutput,
    config: ConfigRepository,
    database: str | None,
    force: bool,
    operation: str,
) -> bool:
    """Apply production refusal and explicit confirmation to DDL changes.

    Args:
        output: Native Console output for this invocation.
        config: Canonical configuration repository.
        database: Selected connection name, if supplied.
        force: Whether the caller explicitly bypassed confirmation.
        operation: Short action description shown to the user.

    Returns:
        Whether the operation was authorized by policy.
    """
    environment = config.get("app.env", "production")
    if not isinstance(environment, str):
        output.write_error("The application environment is invalid.")
        return False
    if environment.casefold() == "production" and not force:
        output.write_error(
            "Destructive migration commands require --force in production."
        )
        return False
    if force:
        return True
    target = "default" if database is None else database
    return output.confirm(
        f"Confirm {operation} on connection [{target}]?",
        default=False,
    )


def _run_migration(
    operation: Callable[[], None],
    output: ConsoleOutput,
    success_message: str,
) -> None:
    """Run one migration operation and show only its native safe error.

    Args:
        operation: Synchronous operation delegated to Alembic.
        output: Native Console output for this invocation.
        success_message: Plain-text message displayed after success.

    Raises:
        ConsoleExitError: If the Database boundary reports a failure.
    """
    try:
        operation()
    except DatabaseError as error:
        _report_migration_error(output, error)
    output.write(success_message)


def _report_migration_error(
    output: ConsoleOutput,
    error: DatabaseError,
) -> NoReturn:
    """Display a safe Database error and return a failing process status.

    Args:
        output: Native Console output for this invocation.
        error: Native error with backend details retained only as its cause.

    Raises:
        ConsoleExitError: Always, with status one.
    """
    output.write_error(str(error))
    raise ConsoleExitError(1) from error


__all__ = ["register_database_commands"]
