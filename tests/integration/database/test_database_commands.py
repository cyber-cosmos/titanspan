"""Verify Database migration commands use native Console composition.

The cases exercise application-aware command registration.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titanspan.config.repository import Repository
from titanspan.console import Console
from titanspan.console.exceptions import ConsoleExitError
from titanspan.console.output import TerminalOutput
from titanspan.console.testing import ConsoleTester
from titanspan.database import (
    DatabaseServiceProvider,
    Migration,
    MigrationManager,
    Model,
    ModelQueryBuilder,
    Schema,
    Seeder,
)
from titanspan.database.commands import (
    prune_models,
    register_database_commands,
    run_migrations,
    seed_database,
)
from titanspan.database.exceptions import DatabaseSchemaError
from titanspan.facades import DB
from titanspan.foundation import Application
from titanspan.testing import ApplicationTest

if TYPE_CHECKING:
    from pathlib import Path

    from titanspan.contracts.foundation import ServiceProvider

pytestmark = pytest.mark.integration
_SCHEMA_WIPE_FAILURE = "schema wipe failed safely"
_FRESH_SCHEMA_FAILURE = "fresh schema failed safely"


class _CommandPruneRecord(Model):
    """Represent the explicit model selected by the prune command test.

    Its query selects only records that are eligible for deletion.
    """

    table = "command_prune_records"
    name: Mapped[str] = mapped_column(String(40))
    eligible: Mapped[bool]

    def prunable(
        self: _CommandPruneRecord,
    ) -> ModelQueryBuilder[_CommandPruneRecord]:
        """Select the one test record eligible for pruning.

        Returns:
            A query restricted to eligible records.
        """
        return _CommandPruneRecord.query().where("eligible", True)


class _CommandShownRecord(Model):
    """Represent a model with a mapped relation for inspection output.

    The relationship is inspected without opening a database connection.
    """

    table = "command_shown_records"
    name: Mapped[str]
    comments: Mapped[list[_CommandShownComment]] = relationship(
        back_populates="record",
    )


class _CommandShownComment(Model):
    """Represent one comment row related to the inspection model.

    The model is mapped only to exercise relationship display behavior.
    """

    table = "command_shown_comments"
    record_id: Mapped[int] = mapped_column(
        ForeignKey("command_shown_records.id"),
    )
    record: Mapped[_CommandShownRecord] = relationship(
        back_populates="comments",
    )


class _MigrationFreshSeeder(Seeder):
    """Create a row after a fresh migration command completes.
    """  # fmt: skip

    async def run_async(self) -> None:
        """Build one table and insert a marker row in the new schema.
        """  # fmt: skip
        async with Schema.create("migration_seed_rows") as table:
            table.id()
            table.string("name", length=40)
        await DB.table("migration_seed_rows").insert_async(
            {"name": "fresh-seeded"},
        )


def test_database_commands_register_with_console() -> None:
    """Expose the practical native migration command set.
    """  # fmt: skip
    console = Console()

    register_database_commands(console)

    assert console.command_names == (
        "db:seed",
        "db:show",
        "db:table",
        "db:wipe",
        "make:migration",
        "make:model",
        "make:seeder",
        "migrate",
        "migrate:fresh",
        "migrate:install",
        "migrate:refresh",
        "migrate:reset",
        "migrate:rollback",
        "migrate:status",
        "model:prune",
        "model:show",
    )


def test_model_show_inspects_mapping_without_opening_database(
    tmp_path: Path,
) -> None:
    """Display mapped model metadata without opening a physical connection.

    Args:
        tmp_path: Isolated application root for command composition.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build the standard app used by this Console invocation.

        Args:
            provider: Console provider installed for the command.

        Returns:
            Application with its built-in Database provider.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    model_path = f"{_CommandShownRecord.__module__}:_CommandShownRecord"

    result = ConsoleTester(console).invoke(["model:show", model_path])

    assert result.exit_code == 0
    assert f"Model: {__name__}._CommandShownRecord" in result.stdout
    assert "Table: command_shown_records" in result.stdout
    assert "Primary key: id" in result.stdout
    assert "name" in result.stdout
    assert "comments: _CommandShownComment (onetomany)" in result.stdout
    assert result.stderr == ""
    assert not (tmp_path / "database").exists()

    model_without_relationships = (
        f"{_CommandPruneRecord.__module__}:_CommandPruneRecord"
    )
    without_relationships = ConsoleTester(console).invoke(
        ["model:show", model_without_relationships],
    )
    assert without_relationships.exit_code == 0
    assert "Relationships:\n  (none)" in without_relationships.stdout

    invalid = ConsoleTester(console).invoke(["model:show", "os:system"])

    assert invalid.exit_code == 1
    assert "trusted module:Class path" in invalid.stderr

    invalid_path = ConsoleTester(console).invoke(
        ["model:show", "../outside:Model"],
    )
    assert invalid_path.exit_code == 1
    assert "trusted module:Class path" in invalid_path.stderr


def test_model_prune_command_requires_explicit_model_and_reports_count(
    tmp_path: Path,
) -> None:
    """Run pruning through the application Console and SQLite lifecycle.

    Args:
        tmp_path: Isolated application root and SQLite database path.
    """

    async def initialize_database() -> None:
        """Create one candidate row before Console command execution.

        The schema and record are created through their public APIs.
        """
        if await Schema.has_table_async("command_prune_records"):
            return
        async with Schema.create("command_prune_records") as table:
            table.id()
            table.string("name", length=40)
            table.boolean("eligible")
            table.timestamps()
        await _CommandPruneRecord.factory().create_async(
            {"name": "expired", "eligible": True},
        )

    def application_factory(provider: ServiceProvider) -> Application:
        """Build the normal application with one test Console provider.

        Args:
            provider: Console-owned provider supplied during composition.

        Returns:
            An application using a disposable SQLite file.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "app": {"env": "testing"},
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "driver": "sqlite",
                                "database": "database/pruning-command.sqlite",
                            },
                        },
                    },
                },
            )
            .with_service_provider(provider)
            .on_startup(initialize_database)
            .build()
        )

    console = Console(application_factory=application_factory)
    model_path = f"{__name__}:_CommandPruneRecord"
    declined = ConsoleTester(console).invoke(
        ["model:prune", "--model", model_path],
        stdin="n\n",
    )
    assert declined.exit_code == 1
    assert "Confirm pruning" in declined.stdout

    result = ConsoleTester(console).invoke(
        [
            "model:prune",
            "--model",
            model_path,
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert "1 _CommandPruneRecord records pruned." in result.stdout
    with sqlite3.connect(
        tmp_path / "database" / "pruning-command.sqlite",
    ) as database:
        assert database.execute(
            "SELECT COUNT(*) FROM command_prune_records",
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    ("environment", "model_path", "force", "expected_error"),
    [
        (
            "testing",
            "malformed",
            True,
            "trusted module:Class",
        ),
        (
            "testing",
            "builtins:str",
            True,
            "trusted module:Class",
        ),
        (
            "production",
            f"{__name__}:_CommandPruneRecord",
            False,
            "requires --force",
        ),
    ],
)
def test_prune_command_rejects_invalid_target_or_environment(
    tmp_path: Path,
    environment: object,
    model_path: str,
    force: bool,
    expected_error: str,
) -> None:
    """Fail closed for untrusted model paths and unsafe environments.

    Args:
        tmp_path: Isolated application root selected by pytest.
        environment: Invalid or production environment value.
        model_path: Candidate model path supplied through Console.
        force: Whether the test explicitly authorizes destructive work.
        expected_error: Diagnostic expected from the authorization boundary.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build an application with the selected environment value.

        Args:
            provider: Console-owned provider for this invocation.

        Returns:
            An unopened application with the native Database provider.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config({"app": {"env": environment}})
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    arguments = ["model:prune", "--model", model_path]
    if force:
        arguments.append("--force")
    result = ConsoleTester(console).invoke(arguments)

    assert result.exit_code == 1
    assert expected_error in result.stderr


@pytest.mark.anyio
async def test_prune_command_rejects_non_string_environment() -> None:
    """Reject a non-string environment through the command boundary.

    The real configuration repository preserves explicit ``None`` values.
    """
    config = Repository({"app": {"env": None}})
    with pytest.raises(ConsoleExitError):
        await prune_models(
            TerminalOutput(),
            config,
            f"{__name__}:_CommandPruneRecord",
        )


@pytest.mark.anyio
async def test_seeder_command_rejects_non_string_environment() -> None:
    """Reject invalid environment values before resolving a seeder.

    The command must fail before opening a connection or importing a target.
    """
    config = Repository({"app": {"env": None}})
    with pytest.raises(ConsoleExitError):
        await seed_database(TerminalOutput(), config)


@pytest.mark.anyio
async def test_migration_command_rejects_non_string_environment(
    tmp_path: Path,
) -> None:
    """Reject invalid migration environments before running Alembic.

    Args:
        tmp_path: Isolated application root used by the Database provider.
    """
    application = Application(
        base_path=tmp_path,
        config={
            "app": {"env": "testing"},
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/migration-policy.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )
    async with application:
        manager = application.container.make(MigrationManager)
        with pytest.raises(ConsoleExitError):
            run_migrations(
                manager,
                TerminalOutput(),
                Repository({"app": {"env": None}}),
            )


def test_database_show_inspects_tables_and_optional_counts(
    tmp_path: Path,
) -> None:
    """Inspect a real SQLite table through default Database registration.

    Args:
        tmp_path: Isolated application root for the SQLite file.
    """

    async def initialize_database() -> None:
        """Create the table observed by the command.

        The application startup hook owns initialization for this test app.
        """
        await DB.statement_async(
            "CREATE TABLE IF NOT EXISTS command_parents ("
            "id INTEGER PRIMARY KEY)",
        )
        await DB.statement_async(
            "CREATE TABLE IF NOT EXISTS command_rows ("
            "id INTEGER PRIMARY KEY, name VARCHAR(40) NOT NULL, "
            "parent_id INTEGER NOT NULL REFERENCES command_parents(id))",
        )
        await DB.statement_async(
            "CREATE TABLE IF NOT EXISTS command_standalone ("
            "id INTEGER PRIMARY KEY, label VARCHAR(40))",
        )
        await DB.statement_async(
            "CREATE INDEX IF NOT EXISTS ix_command_rows_name "
            "ON command_rows (name)",
        )
        await DB.statement_async(
            "CREATE VIEW IF NOT EXISTS command_view "
            "AS SELECT id FROM command_rows",
        )

    def application_factory(provider: ServiceProvider) -> Application:
        """Build a standard Database application for command execution.

        Args:
            provider: Test Console provider for this command invocation.

        Returns:
            An app with automatic Database provider registration.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "app": {"env": "testing"},
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "driver": "sqlite",
                                "database": "database/commands.sqlite",
                            },
                        },
                    },
                },
            )
            .with_service_provider(provider)
            .on_startup(initialize_database)
            .build()
        )

    console = Console(application_factory=application_factory)
    result = ConsoleTester(console).invoke(
        ["db:show", "--counts", "--views"],
    )

    assert result.exit_code == 0
    assert "sqlite" in result.stdout
    assert "command_rows" in result.stdout
    assert "command_view" in result.stdout
    assert "0" in result.stdout

    basic_result = ConsoleTester(console).invoke(["db:show"])
    assert basic_result.exit_code == 0
    assert "command_rows" in basic_result.stdout
    assert "Views" not in basic_result.stdout

    table_result = ConsoleTester(console).invoke(
        ["db:table", "command_rows"],
    )
    assert table_result.exit_code == 0
    assert "id" in table_result.stdout
    assert "INTEGER" in table_result.stdout
    assert "PRIMARY KEY" in table_result.stdout
    assert "name" in table_result.stdout
    assert "VARCHAR(40)" in table_result.stdout
    assert "ix_command_rows_name" in table_result.stdout
    assert "Foreign keys" in table_result.stdout
    assert "command_parents.id" in table_result.stdout

    standalone_result = ConsoleTester(console).invoke(
        ["db:table", "command_standalone"],
    )
    assert standalone_result.exit_code == 0
    assert "Indexes" not in standalone_result.stdout
    assert "Foreign keys" not in standalone_result.stdout

    wipe_result = ConsoleTester(console).invoke(["db:wipe", "--force"])
    assert wipe_result.exit_code == 0
    assert "Database tables wiped." in wipe_result.stdout
    with sqlite3.connect(tmp_path / "database/commands.sqlite") as database:
        remaining_tables = database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'",
        ).fetchall()
    assert remaining_tables == []


def test_migration_status_runs_through_application_lifecycle(
    tmp_path: Path,
) -> None:
    """Inspect an empty SQLite revision graph through Console injection.
    """  # fmt: skip

    def application_factory(provider: ServiceProvider) -> Application:
        """Build one isolated application for the command invocation.

        The factory keeps command tests on a temporary SQLite database.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "app": {"env": "testing"},
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "driver": "sqlite",
                                "database": "database/test.sqlite",
                            },
                        },
                    },
                },
            )
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)

    result = ConsoleTester(console).invoke(["migrate:status"])

    assert result.exit_code == 0
    assert "No migrations found." in result.stdout
    assert (tmp_path / "database" / "test.sqlite").exists()


def test_migration_status_lists_pending_revisions(
    tmp_path: Path,
) -> None:
    """Show discovered Alembic revisions that remain unapplied.

    Args:
        tmp_path: Isolated application root and SQLite target.
    """
    config = {
        "app": {"env": "testing"},
        "database": {
            "default": "sqlite",
            "connections": {
                "sqlite": {
                    "driver": "sqlite",
                    "database": "database/status.sqlite",
                },
            },
        },
    }
    migration_app = (
        Application.builder()
        .with_base_path(tmp_path)
        .with_config(config)
        .with_service_provider(DatabaseServiceProvider())
        .build()
    )

    async def create_pending_revision() -> None:
        """Create the revision while its owning application is active.

        The application exposes an asynchronous lifecycle context, so this
        helper initializes and closes it without inventing sync semantics.
        """
        async with migration_app:
            manager = migration_app.container.make(MigrationManager)
            assert manager.create_revision("pending status").exists()
            await DB.statement_async(
                "CREATE TABLE unmanaged_rows (id INTEGER PRIMARY KEY)",
            )

    anyio.run(create_pending_revision)

    def application_factory(provider: ServiceProvider) -> Application:
        """Build the command app against the generated revision path.

        Args:
            provider: Console-owned provider for this invocation.

        Returns:
            An application configured with the same temporary database.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(config)
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    result = ConsoleTester(console).invoke(["migrate:status"])

    assert result.exit_code == 0
    assert "Pending" in result.stdout

    seeder_path = (
        f"{_MigrationFreshSeeder.__module__}:{_MigrationFreshSeeder.__name__}"
    )
    fresh = ConsoleTester(console).invoke(
        [
            "migrate:fresh",
            "--force",
            "--seed",
            "--seeder",
            seeder_path,
        ],
    )
    assert fresh.exit_code == 0
    assert "Fresh migration run completed." in fresh.stdout
    with sqlite3.connect(tmp_path / "database/status.sqlite") as database:
        remaining_unmanaged = database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("unmanaged_rows",),
        ).fetchone()
        migration_version = database.execute(
            "SELECT version_num FROM alembic_version",
        ).fetchone()
        seeded_rows = database.execute(
            "SELECT name FROM migration_seed_rows",
        ).fetchall()
    assert remaining_unmanaged is None
    assert migration_version is not None
    assert seeded_rows == [("fresh-seeded",)]

    fresh_without_seed = ConsoleTester(console).invoke(
        ["migrate:fresh", "--force"],
    )
    assert fresh_without_seed.exit_code == 0
    with sqlite3.connect(tmp_path / "database/status.sqlite") as database:
        seeder_table = database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("migration_seed_rows",),
        ).fetchone()
    assert seeder_table is None


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("db:seed", ("--force",)),
        ("migrate:reset", ()),
    ],
)
def test_database_commands_reject_invalid_environment_values(
    tmp_path: Path,
    command: str,
    arguments: tuple[str, ...],
) -> None:
    """Fail closed before database access on malformed env configuration.

    Args:
        tmp_path: Isolated app root and disposable SQLite target.
        command: Seeder or migration command guarded by environment policy.
        arguments: Explicit command options for the selected command.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build an application with a non-string environment value.

        Args:
            provider: Console-owned provider for command execution.

        Returns:
            An application that must fail before opening its database.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "app": {"env": 7},
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "driver": "sqlite",
                                "database": "database/invalid-env.sqlite",
                            },
                        },
                    },
                },
            )
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    result = ConsoleTester(console).invoke([command, *arguments])

    assert result.exit_code == 1
    assert "ConfigValueError" in result.stderr
    assert not (tmp_path / "database" / "invalid-env.sqlite").exists()


@pytest.mark.parametrize(
    "command",
    ["migrate:reset", "db:wipe", "migrate:fresh"],
)
def test_destructive_database_command_fails_closed_in_production(
    tmp_path: Path,
    command: str,
) -> None:
    """Refuse destructive database commands before opening the database.

    Args:
        tmp_path: Isolated application root used for path safety.
        command: Destructive command guarded by the production policy.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build a production-configured, isolated application.

        The disposable database prevents access to application data.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "app": {"env": "production"},
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "driver": "sqlite",
                                "database": "database/production.sqlite",
                            },
                        },
                    },
                },
            )
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)

    result = ConsoleTester(console).invoke([command])

    assert result.exit_code == 1
    assert "require --force in production" in result.stderr
    assert "database/production.sqlite" in "".join(result.stderr.split())
    assert not (tmp_path / "database" / "production.sqlite").exists()


def test_database_wipe_reports_schema_failure_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Convert a schema failure into a safe Console error.

    Args:
        tmp_path: Isolated application root for command composition.
        monkeypatch: Replaces the schema operation with a controlled failure.
    """

    def fail_drop_all(
        cls: type[Schema],
        *,
        connection: str | None = None,
    ) -> None:
        """Raise a native schema error without backend details.

        Args:
            cls: Schema class bound by the classmethod descriptor.
            connection: Selected connection accepted by the real operation.
        """
        del cls, connection
        raise DatabaseSchemaError(_SCHEMA_WIPE_FAILURE)

    monkeypatch.setattr(Schema, "drop_all", classmethod(fail_drop_all))

    def application_factory(provider: ServiceProvider) -> Application:
        """Build an isolated Database application for command execution.

        Args:
            provider: Console-owned provider for this invocation.

        Returns:
            An app with the native Database provider registered.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "app": {"env": "testing"},
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "driver": "sqlite",
                                "database": "database/command-errors.sqlite",
                            },
                        },
                    },
                },
            )
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    result = ConsoleTester(console).invoke(["db:wipe", "--force"])

    assert result.exit_code == 1
    assert _SCHEMA_WIPE_FAILURE in result.stderr
    assert "sqlite" not in result.stderr


def test_migrate_fresh_reports_schema_failure_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Convert a fresh-migration schema failure into Console output.

    Args:
        tmp_path: Isolated application root for command composition.
        monkeypatch: Replaces the async schema operation with a failure.
    """

    async def fail_drop_all_async(
        cls: type[Schema],
        *,
        connection: str | None = None,
    ) -> None:
        """Raise a native schema error without backend details.

        Args:
            cls: Schema class bound by the classmethod descriptor.
            connection: Selected connection accepted by the real operation.
        """
        del cls, connection
        raise DatabaseSchemaError(_FRESH_SCHEMA_FAILURE)

    monkeypatch.setattr(
        Schema,
        "drop_all_async",
        classmethod(fail_drop_all_async),
    )

    def application_factory(provider: ServiceProvider) -> Application:
        """Build an isolated Database application for command execution.

        Args:
            provider: Console-owned provider for this invocation.

        Returns:
            An app with the native Database provider registered.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "app": {"env": "testing"},
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "driver": "sqlite",
                                "database": (
                                    "database/command-fresh-errors.sqlite"
                                ),
                            },
                        },
                    },
                },
            )
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    result = ConsoleTester(console).invoke(["migrate:fresh", "--force"])

    assert result.exit_code == 1
    assert _FRESH_SCHEMA_FAILURE in result.stderr
    assert "sqlite" not in result.stderr


def test_migrate_rollback_exposes_isolated_option(
    tmp_path: Path,
) -> None:
    """Forward explicit isolation requests to the migration manager.

    Args:
        tmp_path: Isolated application root used for a disposable database.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build a test application with an isolated SQLite database.

        Args:
            provider: Console-owned provider for command invocation.

        Returns:
            An application configured for a disposable SQLite target.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "app": {"env": "testing"},
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "driver": "sqlite",
                                "database": "database/isolated.sqlite",
                            },
                        },
                    },
                },
            )
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)

    result = ConsoleTester(console).invoke(
        ["migrate:rollback", "--isolated"],
        stdin="y\n",
    )

    assert result.exit_code == 1
    assert "require PostgreSQL or MySQL" in result.stderr
    with sqlite3.connect(tmp_path / "database" / "isolated.sqlite") as db:
        version_table = db.execute(
            "SELECT name FROM sqlite_master WHERE type = ? AND name = ?",
            ("table", "alembic_version"),
        ).fetchone()

    assert version_table is None
    for command in (
        "migrate:rollback",
        "migrate:reset",
        "migrate:refresh",
    ):
        declined = ConsoleTester(console).invoke([command], stdin="n\n")
        assert declined.exit_code == 1

    with sqlite3.connect(tmp_path / "database" / "isolated.sqlite") as db:
        version_table = db.execute(
            "SELECT name FROM sqlite_master WHERE type = ? AND name = ?",
            ("table", "alembic_version"),
        ).fetchone()
    assert version_table is None

    reset = ConsoleTester(console).invoke(["migrate:reset", "--force"])
    refreshed = ConsoleTester(console).invoke(
        ["migrate:refresh", "--force"],
    )
    assert reset.exit_code == 0
    assert "Migration reset completed." in reset.stdout
    assert refreshed.exit_code == 0
    assert "Migration refresh completed." in refreshed.stdout


def test_migrate_requires_force_in_production_and_force_runs(
    tmp_path: Path,
) -> None:
    """Require explicit force for ordinary production migration execution.

    Args:
        tmp_path: Isolated application root used for database safety.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build a production app with one disposable SQLite database.

        Args:
            provider: Console-owned provider for output and invocation.

        Returns:
            An application configured with a non-existing database target.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "app": {"env": "production"},
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "driver": "sqlite",
                                "database": "database/ordinary.sqlite",
                            },
                        },
                    },
                },
            )
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)

    refused = ConsoleTester(console).invoke(["migrate"])
    database_path = tmp_path / "database" / "ordinary.sqlite"

    assert refused.exit_code == 1
    assert "require --force in production" in refused.stderr
    assert "database/ordinary.sqlite" in "".join(refused.stderr.split())
    assert not database_path.exists()

    authorized = ConsoleTester(console).invoke(["migrate", "--force"])

    assert authorized.exit_code == 0
    assert "Migration run completed." in authorized.stdout
    assert database_path.exists()


def test_migrate_confirmation_identifies_target_without_credentials(
    tmp_path: Path,
) -> None:
    """Show the configured database destination without URL credentials.

    Args:
        tmp_path: Isolated application root used for path safety.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build a test app whose SQLite URL includes a secret option.

        Args:
            provider: Console-owned provider for output and invocation.

        Returns:
            An application that will decline before connecting.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "app": {"env": "testing"},
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "url": (
                                    "sqlite:///database/[confirmed].sqlite"
                                    "?password=synthetic-placeholder"
                                ),
                            },
                        },
                    },
                },
            )
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)

    result = ConsoleTester(console).invoke(["migrate"], stdin="n\n")
    output = result.stdout + result.stderr
    normalized_output = "".join(output.split())

    assert result.exit_code == 1
    assert "database/%5Bconfirmed%5D.sqlite" in normalized_output
    assert "synthetic-placeholder" not in normalized_output
    assert "password=" not in normalized_output
    assert not (tmp_path / "database" / "[confirmed].sqlite").exists()


def test_migrate_refuses_an_unconfigured_target_before_prompting(
    tmp_path: Path,
) -> None:
    """Refuse unknown connection names without connecting to a database.

    Args:
        tmp_path: Isolated application root used for database safety.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build a test app with only the default SQLite target.

        Args:
            provider: Console-owned provider for command invocation.

        Returns:
            An application with one disposable configured connection.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "app": {"env": "testing"},
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "driver": "sqlite",
                                "database": "database/configured.sqlite",
                            },
                        },
                    },
                },
            )
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)

    result = ConsoleTester(console).invoke(
        ["migrate", "--database", "missing"],
    )

    assert result.exit_code == 1
    assert "requested database connection is not configured" in result.stderr
    assert not (tmp_path / "database" / "configured.sqlite").exists()


def test_seeder_generator_runs_through_native_console(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generate, import, and execute a Seeder through application APIs.

    Args:
        tmp_path: Isolated application root selected by pytest.
        monkeypatch: Cleanup for the generated module registration.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build one application for the component command.

        The command receives the service through native injection.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "driver": "sqlite",
                                "database": "database/test.sqlite",
                            },
                        },
                    },
                },
            )
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)

    result = ConsoleTester(console).invoke(["make:seeder", "Article"])
    target = tmp_path / "database" / "seeders" / "article_seeder.py"
    source = target.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Generated database/seeders/article_seeder.py." in result.stdout
    assert "class ArticleSeeder(Seeder):" in source
    compile(source, target, "exec")

    module_name = "_titanspan_generated_article_seeder"
    spec = importlib.util.spec_from_file_location(module_name, target)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    seeder_type = getattr(module, "ArticleSeeder", None)
    assert isinstance(seeder_type, type)
    assert issubclass(seeder_type, Seeder)

    test_app = ApplicationTest(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/test.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )
    with test_app, test_app.application.context():
        seeder_type().execute()


def test_model_generator_imports_a_conventional_database_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generate an importable Model under the application root.

    Args:
        tmp_path: Isolated application root selected by pytest.
        monkeypatch: Cleanup for the generated module registration.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build a Console app that relies on default providers.

        Args:
            provider: Console-owned provider for this command invocation.

        Returns:
            A built-in Database application without an opened connection.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config({"app": {"env": "testing"}})
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    result = ConsoleTester(console).invoke(["make:model", "Invoice"])
    target = tmp_path / "app" / "models" / "invoice_model.py"
    source = target.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Generated app/models/invoice_model.py." in result.stdout
    assert "class Invoice(Model):" in source
    compile(source, target, "exec")

    module_name = "_titanspan_generated_invoice_model"
    spec = importlib.util.spec_from_file_location(module_name, target)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    model_type = getattr(module, "Invoice", None)
    assert isinstance(model_type, type)
    assert issubclass(model_type, Model)
    assert model_type.__tablename__ == "invoices"


def test_migration_generator_creates_an_importable_native_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create a native migration revision without opening a database.

    Args:
        tmp_path: Isolated application root selected by pytest.
        monkeypatch: Cleanup for the generated module registration.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build a Console app that relies on default providers.

        Args:
            provider: Console-owned provider for this command invocation.

        Returns:
            A built-in Database application with lazy SQLite resources.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "app": {"env": "testing"},
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "driver": "sqlite",
                                "database": "database/migrations.sqlite",
                            },
                        },
                    },
                },
            )
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    result = ConsoleTester(console).invoke(
        ["make:migration", "create invoice table"],
    )
    versions = tmp_path / "database" / "migrations" / "versions"
    revision_paths = tuple(versions.glob("*.py"))

    assert result.exit_code == 0
    assert len(revision_paths) == 1
    source = revision_paths[0].read_text(encoding="utf-8")
    assert "class CreateInvoiceTableMigration(Migration):" in source
    compile(source, revision_paths[0], "exec")

    module_name = "_titanspan_generated_invoice_migration"
    spec = importlib.util.spec_from_file_location(
        module_name,
        revision_paths[0],
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    migration_type = getattr(module, "CreateInvoiceTableMigration", None)
    assert isinstance(migration_type, type)
    assert issubclass(migration_type, Migration)
    assert not (tmp_path / "database" / "migrations.sqlite").exists()
