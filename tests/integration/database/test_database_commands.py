"""Verify Database migration commands use native Console composition.

The cases exercise application-aware command registration.
"""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import anyio
import pytest

from titanspan.console import Console
from titanspan.console.testing import ConsoleTester
from titanspan.contracts.foundation import ServiceProvider
from titanspan.database import (
    DatabaseServiceProvider,
    MigrationManager,
    Seeder,
)
from titanspan.database.commands import register_database_commands
from titanspan.foundation import Application
from titanspan.testing import ApplicationTest

pytestmark = pytest.mark.integration


def test_database_commands_register_with_console() -> None:
    """Expose the practical native migration command set.
    """  # fmt: skip
    console = Console()

    register_database_commands(console)

    assert console.command_names == (
        "db:seed",
        "make:seeder",
        "migrate",
        "migrate:install",
        "migrate:refresh",
        "migrate:reset",
        "migrate:rollback",
        "migrate:status",
    )


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
    register_database_commands(console)

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
    register_database_commands(console)
    result = ConsoleTester(console).invoke(["migrate:status"])

    assert result.exit_code == 0
    assert "Pending" in result.stdout


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
    register_database_commands(console)
    result = ConsoleTester(console).invoke([command, *arguments])

    assert result.exit_code == 1
    assert "ConfigValueError" in result.stderr
    assert not (tmp_path / "database" / "invalid-env.sqlite").exists()


def test_destructive_migration_command_fails_closed_in_production(
    tmp_path: Path,
) -> None:
    """Refuse a destructive migration before opening the database.

    Args:
        tmp_path: Isolated application root used for path safety.
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
    register_database_commands(console)

    result = ConsoleTester(console).invoke(["migrate:reset"])

    assert result.exit_code == 1
    assert "require --force in production" in result.stderr
    assert "database/production.sqlite" in "".join(result.stderr.split())
    assert not (tmp_path / "database" / "production.sqlite").exists()


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
    register_database_commands(console)

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
    register_database_commands(console)

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
    register_database_commands(console)

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
    register_database_commands(console)

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
    register_database_commands(console)

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
