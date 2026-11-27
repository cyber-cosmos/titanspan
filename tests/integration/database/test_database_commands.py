"""Verify Database migration commands use native Console composition.

The cases exercise application-aware command registration.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from titanspan.console import Console
from titanspan.console.testing import ConsoleTester
from titanspan.contracts.foundation import ServiceProvider
from titanspan.database import DatabaseServiceProvider, Seeder
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
    assert not (tmp_path / "database" / "production.sqlite").exists()


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
