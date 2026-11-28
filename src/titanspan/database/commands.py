"""Register native migration operations with the shared Console service.

All command execution and output remain within the application's Console.
"""

from __future__ import annotations

import re
from importlib import import_module
from typing import TYPE_CHECKING, Annotated, NoReturn, cast

import anyio
from sqlalchemy import inspect as sa_inspect

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
    DatabasePruningError,
    DatabaseQueryError,
    DatabaseSeederError,
)
from titanspan.database.manager import DatabaseManager  # noqa: TC001
from titanspan.database.migration_manager import MigrationManager  # noqa: TC001
from titanspan.database.model import Model
from titanspan.database.schema import Schema
from titanspan.database.seeder import Seeder
from titanspan.foundation import app

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Protocol

    from titanspan.contracts.console import CommandRegistrar

    class _MappedTable(Protocol):
        """Describe the SQLAlchemy table field used by model inspection.

        Model inspection receives a concrete Table through SQLAlchemy's mapper.
        """

        fullname: str


_CAMEL_BOUNDARY = re.compile(r"(.)([A-Z][a-z]+)")
_LOWER_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_INVALID_SEEDER_TARGET = (
    "Select a Seeder class name or a trusted module:Class path."
)
_SEEDER_IMPORT_ERROR = "The selected application seeder could not be imported."
_INVALID_SEEDER_CLASS = "The selected class must inherit from Seeder."
_INVALID_PRUNE_MODEL = (
    "Select a mapped model using a trusted module:Class path."
)
_INVALID_MODEL_SHOW_TARGET = (
    "Select a mapped model using a trusted module:Class path."
)


def register_database_commands(registrar: CommandRegistrar) -> None:
    """Register native Database commands on the application Console.

    Args:
        registrar: Shared registrar that owns parsing and application startup.
    """
    registrar.register_command(
        "db:show",
        show_database,
        description="Show the selected database and its tables.",
    )
    registrar.register_command(
        "db:table",
        show_table,
        description="Show one table's columns and constraints.",
    )
    registrar.register_command(
        "db:wipe",
        wipe_database,
        description="Drop every table in the selected database schema.",
    )
    registrar.register_command(
        "migrate",
        run_migrations,
        description="Apply pending database migrations.",
    )
    registrar.register_command(
        "migrate:fresh",
        migrate_fresh,
        description="Drop database tables and reapply migrations.",
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
    registrar.register_command(
        "make:model",
        make_model,
        description="Generate an application database model.",
    )
    registrar.register_command(
        "make:migration",
        make_migration,
        description="Generate an application database migration.",
    )
    registrar.register_command(
        "model:prune",
        prune_models,
        description="Prune records selected by one mapped model.",
    )
    registrar.register_command(
        "model:show",
        show_model,
        description="Show mapped columns and relations for one model.",
    )


def show_model(
    output: ConsoleOutput,
    target: Annotated[
        str,
        Argument(description="Trusted module:Class path for the model."),
    ],
) -> None:
    """Display one model's SQLAlchemy mapping without opening a connection.

    Args:
        output: Native Console output for this invocation.
        target: Trusted application module and mapped class path.

    Raises:
        ConsoleExitError: If the target is invalid or not a mapped model.
    """
    try:
        model_type = _resolve_model_to_show(target)
    except DatabaseQueryError as error:
        output.write_error(str(error))
        raise ConsoleExitError(1) from error

    mapper = sa_inspect(model_type)
    output.write(f"Model: {model_type.__module__}.{model_type.__qualname__}")
    # Titanspan models map to concrete SQLAlchemy tables.
    table_name = cast("_MappedTable", mapper.local_table).fullname
    output.write(f"Table: {table_name}")
    output.write(
        f"Connection: {model_type.connection or 'default'}",
    )
    primary_keys = ", ".join(
        column.key or column.name or "(unnamed)"
        for column in mapper.primary_key
    )
    output.write(f"Primary key: {primary_keys or '(none)'}")
    output.write("Columns:")
    for attribute in mapper.column_attrs:
        column = attribute.columns[0]
        details = ["nullable" if column.nullable else "required"]
        if column.primary_key:
            details.append("primary key")
        output.write(
            f"  {attribute.key}: {column.type} ({', '.join(details)})",
        )
    output.write("Relationships:")
    if not mapper.relationships:
        output.write("  (none)")
    for relationship in mapper.relationships:
        direction = relationship.direction.name.casefold()
        target_type = relationship.mapper.class_
        output.write(
            f"  {relationship.key}: {target_type.__name__} ({direction})",
        )


def show_database(
    manager: DatabaseManager,
    output: ConsoleOutput,
    database: Annotated[
        str | None,
        Option(
            "--database",
            description="Named database connection to inspect.",
        ),
    ] = None,
    counts: Annotated[
        bool,
        Option(
            "--counts",
            description="Query row counts for each table.",
        ),
    ] = False,
    views: Annotated[
        bool,
        Option(
            "--views",
            description="Include database views.",
        ),
    ] = False,
) -> None:
    """Display redacted connection details and reflected table names.

    Args:
        manager: Application-owned Database manager.
        output: Native Console output for this invocation.
        database: Optional configured connection name.
        counts: Whether to query a row count for each table.
        views: Whether to include reflected view names.
    """
    connection = manager.connection(database)
    output.write(f"Connection: {connection.name}")
    output.write(f"Driver: {connection.dialect_name}")
    output.write(f"Target: {connection.target_identity}")

    table_names = sorted(Schema.list_tables(connection=connection.name))
    if counts:
        rows = [
            (name, str(connection.table(name).count())) for name in table_names
        ]
        output.table(("Table", "Rows"), rows)
    else:
        output.table(
            ("Table",),
            [(name,) for name in table_names],
        )

    if views:
        view_names = sorted(Schema.list_views(connection=connection.name))
        output.write("Views")
        output.table(
            ("View",),
            [(name,) for name in view_names],
        )


def show_table(
    manager: DatabaseManager,
    output: ConsoleOutput,
    table_name: Annotated[
        str,
        Argument(description="Database table to inspect."),
    ],
    database: Annotated[
        str | None,
        Option(
            "--database",
            description="Named database connection to inspect.",
        ),
    ] = None,
) -> None:
    """Display reflected columns, indexes, and foreign keys for a table.

    Args:
        manager: Application-owned Database manager.
        output: Native Console output for this invocation.
        table_name: Table name, optionally qualified by schema.
        database: Optional configured connection name.
    """
    connection = manager.connection(database)
    description = Schema.describe_table(
        table_name,
        connection=connection.name,
    )
    output.write(f"Table: {description.name}")
    output.write(f"Connection: {connection.name}")
    output.table(
        ("Column", "Type", "Nullable", "Key"),
        [
            (
                column.name,
                column.type_name,
                "yes" if column.nullable else "no",
                "PRIMARY KEY" if column.primary_key else "",
            )
            for column in description.columns
        ],
    )
    if description.indexes:
        output.write("Indexes")
        output.table(
            ("Name", "Columns", "Unique"),
            [
                (
                    index.name or "unnamed",
                    ", ".join(index.columns),
                    "yes" if index.unique else "no",
                )
                for index in description.indexes
            ],
        )
    if description.foreign_keys:
        output.write("Foreign keys")
        output.table(
            ("Name", "Columns", "References"),
            [
                (
                    foreign_key.name or "unnamed",
                    ", ".join(foreign_key.columns),
                    (
                        f"{foreign_key.referred_table}."
                        f"{', '.join(foreign_key.referred_columns)}"
                    ),
                )
                for foreign_key in description.foreign_keys
            ],
        )


def wipe_database(
    manager: MigrationManager,
    output: ConsoleOutput,
    config: ConfigRepository,
    database: Annotated[
        str | None,
        Option(
            "--database",
            description="Named database connection to wipe.",
        ),
    ] = None,
    force: Annotated[
        bool,
        Option(
            "--force",
            description="Explicitly authorize wiping in production.",
        ),
    ] = False,
) -> None:
    """Drop all tables after explicit target and environment checks.

    Args:
        manager: Application-owned migration service for target inspection.
        output: Native Console output for this invocation.
        config: Application configuration used for environment policy.
        database: Optional configured connection name.
        force: Whether to bypass confirmation and authorize production use.

    Raises:
        ConsoleExitError: If authorization or the schema operation fails.
    """
    if not _confirm_destructive(
        manager,
        output,
        config,
        database,
        force,
        "wipe database tables",
    ):
        raise ConsoleExitError(1)
    try:
        Schema.drop_all(connection=database)
    except DatabaseError as error:
        _report_migration_error(output, error)
    output.write("Database tables wiped.")


def run_migrations(
    manager: MigrationManager,
    output: ConsoleOutput,
    config: ConfigRepository,
    database: Annotated[
        str | None,
        Option(
            "--database",
            description="Named database connection to migrate.",
        ),
    ] = None,
    force: Annotated[
        bool,
        Option(
            "--force",
            description="Explicitly authorize migrations in production.",
        ),
    ] = False,
    isolated: Annotated[
        bool,
        Option(
            "--isolated",
            description="Require database-supported migration locking.",
        ),
    ] = False,
) -> None:
    """Apply pending Alembic revisions to the selected connection.

    Args:
        manager: Application-owned migration service.
        output: Native Console output for this invocation.
        config: Application configuration used for environment policy.
        database: Optional configured connection name.
        force: Whether to bypass the confirmation policy explicitly.
        isolated: Whether supported cross-process coordination is required.
    """
    if not _confirm_destructive(
        manager,
        output,
        config,
        database,
        force,
        "apply pending database migrations",
    ):
        raise ConsoleExitError(1)
    _run_migration(
        lambda: manager.upgrade(
            connection=database,
            isolated=isolated,
        ),
        output,
        "Migration run completed.",
    )


async def migrate_fresh(  # noqa: PLR0913
    manager: MigrationManager,
    output: ConsoleOutput,
    config: ConfigRepository,
    database: Annotated[
        str | None,
        Option(
            "--database",
            description="Named database connection to rebuild.",
        ),
    ] = None,
    force: Annotated[
        bool,
        Option(
            "--force",
            description="Explicitly authorize this operation in production.",
        ),
    ] = False,
    isolated: Annotated[
        bool,
        Option(
            "--isolated",
            description="Require database-supported migration locking.",
        ),
    ] = False,
    seed: Annotated[
        bool,
        Option("--seed", description="Run a seeder after migrations."),
    ] = False,
    seeder: Annotated[
        str,
        Option(
            "--seeder",
            description="Seeder class or trusted module:Class path.",
        ),
    ] = "DatabaseSeeder",
) -> None:
    """Drop tables, apply all revisions, and optionally run a seeder.

    Args:
        manager: Application-owned migration service.
        output: Native Console output for this invocation.
        config: Application configuration used for environment policy.
        database: Optional configured connection name.
        force: Whether to bypass confirmation and authorize production use.
        isolated: Whether supported cross-process coordination is required.
        seed: Whether to execute a seeder after all revisions apply.
        seeder: Trusted seeder class name or module path.

    Raises:
        ConsoleExitError: If authorization or an operation fails.
    """
    if not _confirm_destructive(
        manager,
        output,
        config,
        database,
        force,
        "drop all database tables and reapply migrations",
    ):
        raise ConsoleExitError(1)
    try:
        await Schema.drop_all_async(connection=database)
        await manager.upgrade_async(
            connection=database,
            isolated=isolated,
        )
        if seed:
            await _execute_seeder(_resolve_seeder(seeder), database)
    except DatabaseError as error:
        _report_migration_error(output, error)
    output.write("Fresh migration run completed.")


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
    isolated: Annotated[
        bool,
        Option(
            "--isolated",
            description="Require database-supported migration locking.",
        ),
    ] = False,
) -> None:
    """Create Alembic's revision table without applying revisions.

    Args:
        manager: Application-owned migration service.
        output: Native Console output for this invocation.
        database: Optional configured connection name.
        isolated: Whether supported cross-process coordination is required.
    """
    _run_migration(
        lambda: manager.install(database, isolated=isolated),
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


# Console needs one typed parameter for each injected service and option.
def rollback_migrations(  # noqa: PLR0913
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
    isolated: Annotated[
        bool,
        Option(
            "--isolated",
            description="Require database-supported migration locking.",
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
        isolated: Whether supported cross-process coordination is required.
    """
    if not _confirm_destructive(
        manager,
        output,
        config,
        database,
        force,
        "roll back database migrations",
    ):
        raise ConsoleExitError(1)
    _run_migration(
        lambda: manager.rollback(
            step,
            connection=database,
            isolated=isolated,
        ),
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
    isolated: Annotated[
        bool,
        Option(
            "--isolated",
            description="Require database-supported migration locking.",
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
        isolated: Whether supported cross-process coordination is required.
    """
    if not _confirm_destructive(
        manager,
        output,
        config,
        database,
        force,
        "reset database migrations",
    ):
        raise ConsoleExitError(1)
    _run_migration(
        lambda: manager.reset(database, isolated=isolated),
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
    isolated: Annotated[
        bool,
        Option(
            "--isolated",
            description="Require database-supported migration locking.",
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
        isolated: Whether supported cross-process coordination is required.
    """
    if not _confirm_destructive(
        manager,
        output,
        config,
        database,
        force,
        "refresh database migrations",
    ):
        raise ConsoleExitError(1)
    _run_migration(
        lambda: manager.refresh(database, isolated=isolated),
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
        await _execute_seeder(seeder_type, database)
    except DatabaseError as error:
        output.write_error(str(error))
        raise ConsoleExitError(1) from error
    output.write("Database seeding completed.")


async def prune_models(  # noqa: PLR0913
    output: ConsoleOutput,
    config: ConfigRepository,
    model: Annotated[
        str,
        Option(
            "--model",
            description="Trusted module:Class path for the mapped model.",
        ),
    ],
    chunk_size: Annotated[
        int,
        Option(
            "--chunk-size",
            description="Maximum records loaded or deleted per batch.",
        ),
    ] = 1000,
    pretend: Annotated[
        bool,
        Option(
            "--pretend",
            description="Count eligible rows without deleting them.",
        ),
    ] = False,
    mass: Annotated[
        bool,
        Option(
            "--mass",
            description="Use set-based deletion without model events.",
        ),
    ] = False,
    force: Annotated[
        bool,
        Option(
            "--force",
            description="Authorize pruning in production.",
        ),
    ] = False,
) -> None:
    """Prune one explicitly selected model using its declared query policy.

    Args:
        output: Native Console output for progress and errors.
        config: Application configuration used for production safeguards.
        model: Trusted application module and mapped class path.
        chunk_size: Bound for each query or deletion batch.
        pretend: Whether to report eligible rows without mutation.
        mass: Whether to skip per-model hooks and lifecycle events.
        force: Whether to authorize destructive operation in production.

    Raises:
        ConsoleExitError: If authorization, selection, or pruning fails.
    """
    try:
        model_type = _resolve_prunable_model(model)
    except DatabasePruningError as error:
        output.write_error(str(error))
        raise ConsoleExitError(1) from error
    if not pretend and not _confirm_pruning(
        model_type,
        output,
        config,
        force,
    ):
        raise ConsoleExitError(1)

    prune = (
        model_type.mass_prune_all_async if mass else model_type.prune_all_async
    )
    try:
        count = await prune(chunk_size=chunk_size, pretend=pretend)
    except DatabaseError as error:
        output.write_error(str(error))
        raise ConsoleExitError(1) from error
    action = "would be pruned" if pretend else "pruned"
    output.write(f"{count} {model_type.__name__} records {action}.")


def _resolve_prunable_model(target: str) -> type[Model]:
    """Import one explicitly selected mapped application model.

    Args:
        target: Trusted ``module:Class`` path supplied by the operator.

    Returns:
        A mapped Titanspan model subclass.

    Raises:
        DatabasePruningError: If the target is malformed or not a model.
    """
    module_name, separator, class_name = target.partition(":")
    if (
        not separator
        or not _is_module_path(module_name)
        or not _is_identifier(class_name)
    ):
        raise DatabasePruningError(_INVALID_PRUNE_MODEL)
    try:
        module = import_module(module_name)
        selected = getattr(module, class_name)
    except (AttributeError, ImportError, ValueError) as error:
        raise DatabasePruningError(_INVALID_PRUNE_MODEL) from error
    if (
        not isinstance(selected, type)
        or not issubclass(selected, Model)
        or selected is Model
    ):
        raise DatabasePruningError(_INVALID_PRUNE_MODEL)
    return selected


def _resolve_model_to_show(target: str) -> type[Model]:
    """Import one explicitly selected mapped application model.

    Args:
        target: Trusted ``module:Class`` path supplied by the operator.

    Returns:
        A mapped Titanspan model subclass.

    Raises:
        DatabaseQueryError: If the target is malformed or not a model.
    """
    module_name, separator, class_name = target.partition(":")
    if (
        not separator
        or not _is_module_path(module_name)
        or not _is_identifier(class_name)
    ):
        raise DatabaseQueryError(_INVALID_MODEL_SHOW_TARGET)
    try:
        module = import_module(module_name)
        selected = getattr(module, class_name)
    except (AttributeError, ImportError, ValueError) as error:
        raise DatabaseQueryError(_INVALID_MODEL_SHOW_TARGET) from error
    if (
        not isinstance(selected, type)
        or not issubclass(selected, Model)
        or selected is Model
    ):
        raise DatabaseQueryError(_INVALID_MODEL_SHOW_TARGET)
    return selected


def _confirm_pruning(
    model: type[Model],
    output: ConsoleOutput,
    config: ConfigRepository,
    force: bool,
) -> bool:
    """Require production authorization or confirmation of the model target.

    Args:
        model: Explicit model whose pruning query will run.
        output: Console prompt boundary.
        config: Application environment configuration.
        force: Whether the operator explicitly authorized production pruning.

    Returns:
        Whether pruning is authorized.
    """
    environment = config.get("app.env", "production")
    if not isinstance(environment, str):
        output.write_error("The application environment is invalid.")
        return False
    if environment.casefold() == "production" and not force:
        output.write_error("Model pruning in production requires --force.")
        return False
    if force:
        return True
    connection = model.connection or "default"
    return output.confirm(
        f"Confirm pruning {model.__name__} on [{connection}]?",
        default=False,
    )


async def _execute_seeder(
    seeder_type: type[Seeder],
    database: str | None,
) -> None:
    """Run one selected seeder in its declared execution mode.

    Args:
        seeder_type: Trusted application-defined Seeder subclass.
        database: Optional connection inherited by nested seeders.
    """
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


def make_model(
    name: Annotated[str, Argument(description="Model class name.")],
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Generate a native Database model beneath the application root.

    Args:
        name: Model name or dotted application module path.
        paths: Foundation-owned application paths.
        output: Native Console output for this invocation.

    Raises:
        ConsoleExitError: If the name or destination is unsafe or unavailable.
    """
    try:
        target = generate_artifact(paths, "model", name)
    except CommandGenerationError as error:
        output.write_error(str(error))
        raise ConsoleExitError(1) from error
    output.write(f"Generated {target.relative_to(paths.base_path)}.")


async def make_migration(
    manager: MigrationManager,
    paths: ApplicationPaths,
    output: ConsoleOutput,
    message: Annotated[str, Argument(description="Migration description.")],
    database: Annotated[
        str | None,
        Option(
            "--database",
            description="Named database connection for autogeneration.",
        ),
    ] = None,
    autogenerate: Annotated[
        bool,
        Option(
            "--autogenerate",
            description="Compare mapped models with the selected database.",
        ),
    ] = False,
) -> None:
    """Generate a migration using the application Alembic configuration.

    Args:
        manager: Application-owned Alembic integration.
        paths: Foundation-owned application paths.
        output: Native Console output for this invocation.
        message: Human-readable description for the revision.
        database: Optional selected connection for autogeneration.
        autogenerate: Whether Alembic should compare mapped schema metadata.

    Raises:
        ConsoleExitError: If Alembic cannot generate the revision.
    """
    try:
        target = await manager.create_revision_async(
            message,
            autogenerate=autogenerate,
            connection=database,
        )
    except DatabaseError as error:
        _report_migration_error(output, error)
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
    manager: MigrationManager,
    output: ConsoleOutput,
    config: ConfigRepository,
    database: str | None,
    force: bool,
    operation: str,
) -> bool:
    """Apply production refusal and confirmation to migration operations.

    Args:
        manager: Application-owned service used to identify the real target.
        output: Native Console output for this invocation.
        config: Canonical configuration repository.
        database: Selected connection name, if supplied.
        force: Whether the caller explicitly bypassed confirmation.
        operation: Short action description shown to the user.

    Returns:
        Whether the operation was authorized by policy.
    """
    try:
        target = manager.target_identity(database)
    except DatabaseError as error:
        output.write_error(str(error))
        return False

    environment = config.get("app.env", "production")
    if not isinstance(environment, str):
        output.write_error("The application environment is invalid.")
        return False
    if environment.casefold() == "production" and not force:
        output.write_error(
            "Database migration commands require --force in production "
            f"for target ({target})."
        )
        return False
    if force:
        return True
    return output.confirm(
        f"Confirm {operation} on database ({target})?",
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
