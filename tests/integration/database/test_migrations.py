"""Verify Alembic revision orchestration through real SQLite databases.

The tests cover generated revisions and migration round trips.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, cast

import anyio
import pytest
from sqlalchemy import String
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.contracts.database import DatabaseService
from titanspan.database import (
    DatabaseManager,
    DatabaseMigrationError,
    DatabaseServiceProvider,
    MigrationManager,
    Schema,
)
from titanspan.database.model import Model
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.engine import Connection

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_UP_BODY = '''    def up(self) -> None:
        """Apply this revision's schema changes."""
        with Schema.create("notes") as table:
            table.id()
            table.string("title")
'''
_DOWN_BODY = '''    def down(self) -> None:
        """Reverse this revision's schema changes."""
        with Schema.drop_if_exists("notes"):
            pass
'''
_FAILURE_BODY = '''    def up(self) -> None:
        """Apply this revision's schema changes."""
        raise RuntimeError("migration failed")
'''


class MigrationAutogenRecord(Model):
    """Provide one mapped table for Alembic autogeneration.

    Its metadata is compared with the disposable database schema.
    """

    table: ClassVar[str | None] = "migration_autogen_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100))


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an app with an isolated SQLite migration database.

    Args:
        tmp_path: Temporary application root provided by Pytest.

    Returns:
        An application with the Database provider installed.
    """
    return Application(
        base_path=tmp_path,
        config={
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
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_generated_native_migration_upgrades_and_rolls_back(
    application: Application,
) -> None:
    """Use Alembic to execute and reverse a generated native migration.

    Args:
        application: Isolated Database application fixture.
    """
    async with application:
        manager = await application.container.make_async(MigrationManager)
        path = manager.create_revision("create notes")
        source = path.read_text(encoding="utf-8")
        source = source.replace(
            "from titanspan.database import Migration, run_migration",
            "from titanspan.database import Migration, Schema, run_migration",
        )
        source = source.replace(
            "    def up(self) -> None:\n"
            '        """Apply this revision\'s schema changes."""\n'
            "        pass\n",
            _UP_BODY,
        )
        source = source.replace(
            "    def down(self) -> None:\n"
            '        """Reverse this revision\'s schema changes."""\n'
            "        pass\n",
            _DOWN_BODY,
        )
        path.write_text(source, encoding="utf-8")

        await manager.upgrade_async()

        assert await Schema.has_table_async("notes")
        statuses = await manager.status_async()
        assert len(statuses) == 1
        assert statuses[0].applied
        assert statuses[0].current_head

        await manager.rollback_async()

        assert not await Schema.has_table_async("notes")
        assert not (await manager.status_async())[0].applied


async def test_revision_names_handle_empty_and_numeric_messages(
    application: Application,
) -> None:
    """Generate valid class names for unusual migration descriptions.

    Args:
        application: Isolated application with its migration paths configured.
    """
    async with application:
        manager = await application.container.make_async(MigrationManager)
        empty_name_path = manager.create_revision("!!!")
        numeric_name_path = manager.create_revision("123 initial users")

    empty_source = empty_name_path.read_text(encoding="utf-8")
    numeric_source = numeric_name_path.read_text(encoding="utf-8")
    assert "class DatabaseMigration" in empty_source
    assert "class Revision123InitialUsersMigration" in numeric_source


async def test_sync_migration_runs_in_a_worker_thread(
    application: Application,
) -> None:
    """Support explicit synchronous Alembic execution outside the loop.

    Args:
        application: Isolated Database application fixture.
    """
    async with application:
        manager = await application.container.make_async(MigrationManager)
        manager.create_revision("empty sync revision")
        await anyio.to_thread.run_sync(manager.upgrade)

        statuses = await manager.status_async()

        assert statuses[0].applied


async def test_migration_paths_cannot_escape_the_application(
    tmp_path: Path,
) -> None:
    """Reject a custom migration directory outside the app root.

    Args:
        tmp_path: Temporary path used as the trust boundary.
    """
    application = Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": ":memory:",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )
    async with application:
        service = await application.container.make_async(DatabaseService)
        with pytest.raises(
            DatabaseMigrationError,
            match="inside the application",
        ):
            MigrationManager(service, tmp_path, Path("../outside"))


async def test_failed_revision_rolls_back_its_version_state(
    application: Application,
) -> None:
    """Keep a failed revision out of Alembic's applied revision state.

    Args:
        application: Isolated Database application fixture.
    """
    async with application:
        manager = await application.container.make_async(MigrationManager)
        path = manager.create_revision("failing revision")
        source = path.read_text(encoding="utf-8")
        source = source.replace(
            "    def up(self) -> None:\n"
            '        """Apply this revision\'s schema changes."""\n'
            "        pass\n",
            _FAILURE_BODY,
        )
        path.write_text(source, encoding="utf-8")

        with pytest.raises(RuntimeError, match="migration failed"):
            await manager.upgrade_async()

        assert not (await manager.status_async())[0].applied


async def test_isolated_migration_fails_closed_on_sqlite(
    application: Application,
) -> None:
    """Reject explicit isolation when SQLite has no migration lock API.

    Args:
        application: Isolated SQLite Database application fixture.
    """
    async with application:
        manager = await application.container.make_async(MigrationManager)
        path = manager.create_revision("isolated sqlite revision")
        assert path.exists()

        with pytest.raises(
            DatabaseMigrationError,
            match="require PostgreSQL or MySQL",
        ):
            await manager.upgrade_async(isolated=True)

        assert not await Schema.has_table_async("alembic_version")


async def test_failed_named_lock_release_invalidates_its_connection(
    application: Application,
) -> None:
    """Discard a physical connection when a named lock cannot be released.

    Args:
        application: Isolated SQLite Database application fixture.
    """
    async with application:
        manager = await application.container.make_async(DatabaseManager)
        connection = manager.engine("sqlite").connect()
        release_method = "_release_mysql_lock"
        release_lock = cast(
            "Callable[[Connection, str], None]",
            getattr(MigrationManager, release_method),
        )
        try:
            with pytest.raises(SQLAlchemyError):
                # Exercise invalidation at the real SQLAlchemy connection.
                release_lock(
                    connection,
                    "test-migration-lock",
                )

            assert connection.invalidated
            rows = await DB.connection("sqlite").select_async(
                "SELECT 1 AS value",
            )
            assert rows[0]["value"] == 1
        finally:
            connection.close()


async def test_autogeneration_uses_native_model_metadata(
    application: Application,
) -> None:
    """Generate and execute DDL from Titanspan's SQLAlchemy model metadata.

    Args:
        application: Isolated Database application fixture.
    """
    async with application:
        manager = await application.container.make_async(MigrationManager)
        path = await manager.create_revision_async(
            "create autogen records",
            autogenerate=True,
        )
        generated = path.read_text(encoding="utf-8")

        assert "op.create_table" in generated
        await manager.upgrade_async()

        assert await Schema.has_table_async("migration_autogen_records")
