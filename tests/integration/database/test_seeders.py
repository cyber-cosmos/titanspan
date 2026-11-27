"""Verify seeders use native Container and Database lifecycles.

Both execution modes write to isolated SQLite databases.
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.console import Console
from titanspan.console.testing import ConsoleTester
from titanspan.database import DatabaseServiceProvider, Model, Schema, Seeder
from titanspan.database.commands import register_database_commands
from titanspan.facades.database import DB
from titanspan.foundation import Application
from titanspan.testing import ApplicationTest, AsyncApplicationTest

if TYPE_CHECKING:
    from pathlib import Path

    from titanspan.contracts.foundation import ServiceProvider

pytestmark = pytest.mark.integration
_FAILURE_MESSAGE = "seed rollback"
_SYNC_ROW = "sync seed"
_ASYNC_ROW = "async seed"
_CLI_SYNC_ROW = "console sync seed"
_CLI_ASYNC_ROW = "console async seed"
_SYNC_COMMITTED_ROWS = 2


class SeedRecord(Model):
    """Represent one row written by the test seeders.

    The model is shared by sync and async seeder cases.
    """

    table = "seed_records"
    fillable = ("name",)

    name: Mapped[str] = mapped_column(String(120))


class AddSyncRecordSeeder(Seeder):
    """Insert one record through the sync Active Record API.

    This child seeder participates in its parent transaction.
    """

    def run(self) -> None:
        """Create the synchronous seed record.

        The write uses the active synchronous Unit of Work.
        """
        SeedRecord.create({"name": _SYNC_ROW})


class AddAsyncRecordSeeder(Seeder):
    """Insert one record through the async Active Record API.

    This child seeder participates in its parent task transaction.
    """

    async def run_async(self) -> None:
        """Create the asynchronous seed record.

        The write uses the active task-owned Unit of Work.
        """
        await SeedRecord.create_async({"name": _ASYNC_ROW})


class NonTransactionalSyncSeeder(Seeder):
    """Persist a record without wrapping the seeder in a transaction.

    The test verifies the explicit non-transactional policy.
    """

    transactional = False

    def run(self) -> None:
        """Create a record through the native sync model API.

        The record remains committed when the seeder returns.
        """
        SeedRecord.create({"name": "sync non-transactional seed"})


class NonTransactionalAsyncSeeder(Seeder):
    """Persist an asynchronous record without an outer transaction.

    The test verifies task-owned non-transactional execution.
    """

    transactional = False

    async def run_async(self) -> None:
        """Create a record through the native async model API.

        The record remains committed when the seeder returns.
        """
        await SeedRecord.create_async({"name": "async non-transactional seed"})


class CompositeSeeder(Seeder):
    """Run a nested synchronous seeder in the parent's transaction.

    The test confirms child work commits with the root seeder.
    """

    def run(self) -> None:
        """Delegate its record creation to one child seeder.

        The child remains inside this seeder transaction.
        """
        self.call(AddSyncRecordSeeder)


class FailingSeeder(Seeder):
    """Raise after nested writes to verify root rollback.

    The error path must remove every row from the composition.
    """

    def run(self) -> None:
        """Insert one row and fail the owning transaction.

        The exception tests rollback after child writes.
        """
        self.call(AddSyncRecordSeeder)
        raise RuntimeError(_FAILURE_MESSAGE)


class AsyncCompositeSeeder(Seeder):
    """Run nested asynchronous seeders through the active task.

    The database session remains owned by the current task.
    """

    async def run_async(self) -> None:
        """Delegate row creation to one asynchronous child seeder.

        The child remains inside the active task transaction.
        """
        await self.call_async(AddAsyncRecordSeeder)


class ConsoleSyncSeeder(Seeder):
    """Represent one sync seeder loaded by the native Console command.

    The command executes it through the application container.
    """

    def run(self) -> None:
        """Create one row through Active Record.

        The test command reads the resulting row from SQLite.
        """
        SeedRecord.create({"name": _CLI_SYNC_ROW})


class ConsoleAsyncSeeder(Seeder):
    """Represent one async seeder loaded by the native Console command.

    The command awaits it within the current execution task.
    """

    async def run_async(self) -> None:
        """Create one row through asynchronous Active Record.

        The test command awaits persistence before returning.
        """
        await SeedRecord.create_async({"name": _CLI_ASYNC_ROW})


def _test_config() -> dict[str, object]:
    """Return isolated SQLite settings shared by seeder tests.

    Each test receives its own file-backed database path.
    """
    return {
        "database": {
            "default": "sqlite",
            "connections": {
                "sqlite": {
                    "driver": "sqlite",
                    "database": "database/seeders.sqlite",
                },
            },
        },
    }


def test_sync_seeders_compose_inside_one_transaction() -> None:
    """Commit nested seeders and roll back all work on failure.

    Assertions query persisted rows after both outcomes.
    """
    test_app = ApplicationTest(
        config=_test_config(),
        service_providers=(DatabaseServiceProvider(),),
    )
    with test_app, test_app.application.context():
        with Schema.create("seed_records") as table:
            table.id()
            table.string("name", length=120)
            table.timestamps()

        CompositeSeeder().execute()
        NonTransactionalSyncSeeder().execute()

        assert DB.table("seed_records").count() == _SYNC_COMMITTED_ROWS
        with pytest.raises(RuntimeError, match=_FAILURE_MESSAGE):
            FailingSeeder().execute()
        assert DB.table("seed_records").count() == _SYNC_COMMITTED_ROWS


@pytest.mark.anyio
async def test_async_seeders_compose_inside_one_task_transaction() -> None:
    """Run async seeders with the application's task-owned Unit of Work.

    The test verifies commit and rollback through the async path.
    """
    test_app = AsyncApplicationTest(
        config=_test_config(),
        service_providers=(DatabaseServiceProvider(),),
    )
    async with test_app:
        with test_app.application.context():
            async with Schema.create("seed_records") as table:
                table.id()
                table.string("name", length=120)
                table.timestamps()

            await AsyncCompositeSeeder().execute_async()
            await NonTransactionalAsyncSeeder().execute_async()

            names = await (
                DB.table("seed_records").order_by("name").pluck_async("name")
            )
            assert names == [
                "async non-transactional seed",
                _ASYNC_ROW,
            ]


@pytest.mark.parametrize(
    ("seeder_class", "expected_name"),
    [
        ("ConsoleSyncSeeder", _CLI_SYNC_ROW),
        ("ConsoleAsyncSeeder", _CLI_ASYNC_ROW),
    ],
)
def test_seed_command_runs_sync_and_async_seeders(
    tmp_path: Path,
    seeder_class: str,
    expected_name: str,
) -> None:
    """Run selected app seeders through Console and real SQLite.

    Args:
        tmp_path: Isolated application root and disposable SQLite file.
        seeder_class: Seeder class selected by the native command.
        expected_name: Value persisted by the selected seeder.
    """
    database_path = tmp_path / "database" / "seeders.sqlite"
    database_path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(database_path)) as database, database:
        database.execute(
            "CREATE TABLE seed_records ("
            "id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL, "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
        )

    def application_factory(provider: ServiceProvider) -> Application:
        """Build one isolated testing application for Console injection.

        The root path and database file are unique to this test.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config({"app": {"env": "testing"}, **_test_config()})
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    register_database_commands(console)
    result = ConsoleTester(console).invoke(
        [
            "db:seed",
            "--class",
            f"{__name__}:{seeder_class}",
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert "Database seeding completed." in result.stdout
    with closing(sqlite3.connect(database_path)) as database:
        rows = database.execute(
            "SELECT name FROM seed_records",
        ).fetchall()
    assert rows == [(expected_name,)]


def test_seed_command_requires_force_in_production(
    tmp_path: Path,
) -> None:
    """Refuse production seeding before a database connection is opened.

    The guard runs before trusted seeder code is loaded.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build a production application with a disposable SQLite target.

        The command policy is checked without touching real data.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config({"app": {"env": "production"}, **_test_config()})
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    register_database_commands(console)
    result = ConsoleTester(console).invoke(
        [
            "db:seed",
            "--class",
            f"{__name__}:ConsoleSyncSeeder",
        ],
    )

    assert result.exit_code == 1
    assert "requires --force" in result.stderr
    assert not (tmp_path / "database" / "seeders.sqlite").exists()


def test_seed_command_discovers_default_seeder_from_application_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve the conventional DatabaseSeeder module by its class name.

    Args:
        tmp_path: Isolated application root containing the generated module.
        monkeypatch: Adds the application package root for trusted imports.
    """
    seeder_path = tmp_path / "database" / "seeders" / "database_seeder.py"
    seeder_path.parent.mkdir(parents=True)
    seeder_path.write_text(
        '"""Define the application root seeder.\n\n'
        "This module is loaded by the operator's explicit seed command.\n"
        '"""\n\n'
        "from titanspan.database import Seeder\n\n\n"
        "class DatabaseSeeder(Seeder):\n"
        '    """Provide an empty baseline seeder for this test.\n\n'
        "    This class intentionally writes no application data.\n"
        '    """\n\n'
        "    def run(self) -> None:\n"
        '        """Leave the disposable test database unchanged.\n\n'
        "        This starter seeder has no baseline rows.\n"
        '        """\n'
        "        pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])

    def application_factory(provider: ServiceProvider) -> Application:
        """Build one app that owns this root and its Database provider.

        Seeder discovery uses the conventional application directory.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config({"app": {"env": "testing"}, **_test_config()})
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    register_database_commands(console)
    result = ConsoleTester(console).invoke(["db:seed", "--force"])

    assert result.exit_code == 0
    assert "Database seeding completed." in result.stdout


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("bad/name", "Select a Seeder class"),
        ("../unsafe:ConsoleSyncSeeder", "Select a Seeder class"),
        ("builtins:object", "inherit from Seeder"),
        (
            "titanspan.database.seeder:Seeder",
            "inherit from Seeder",
        ),
        ("missing_seed_module:Seeder", "could not be imported"),
    ],
)
def test_seed_command_rejects_unsafe_or_unavailable_targets(
    tmp_path: Path,
    target: str,
    message: str,
) -> None:
    """Fail closed when seeder names are unsafe or cannot be trusted.

    Args:
        tmp_path: Isolated application root and disposable database target.
        target: Seeder import syntax supplied to the Console command.
        message: Safe diagnostic expected from the native command.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build an isolated testing app for a failed seeder lookup.

        Args:
            provider: Console-owned provider for this command invocation.

        Returns:
            An application with no pre-opened Database connection.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config({"app": {"env": "testing"}, **_test_config()})
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    register_database_commands(console)
    result = ConsoleTester(console).invoke(
        ["db:seed", "--class", target, "--force"],
    )

    assert result.exit_code == 1
    assert message in result.stderr
    assert not (tmp_path / "database" / "seeders.sqlite").exists()


def test_seed_command_accepts_testing_confirmation_without_force(
    tmp_path: Path,
) -> None:
    """Run a trusted seeder after an explicit non-production confirmation.

    Args:
        tmp_path: Isolated application root and disposable SQLite target.
    """
    database_path = tmp_path / "database" / "seeders.sqlite"
    database_path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(database_path)) as database, database:
        database.execute(
            "CREATE TABLE seed_records ("
            "id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL, "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
        )

    def application_factory(provider: ServiceProvider) -> Application:
        """Build the testing app that owns the disposable target.

        Args:
            provider: Console-owned provider for this command invocation.

        Returns:
            An application configured for explicit confirmation.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config({"app": {"env": "testing"}, **_test_config()})
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    register_database_commands(console)
    result = ConsoleTester(console).invoke(
        ["db:seed", "--class", f"{__name__}:ConsoleSyncSeeder"],
        stdin="y\n",
    )

    assert result.exit_code == 0
    assert "Confirm database seeding" in result.stdout
    with closing(sqlite3.connect(database_path)) as database:
        rows = database.execute(
            "SELECT name FROM seed_records",
        ).fetchall()
    assert rows == [(_CLI_SYNC_ROW,)]
