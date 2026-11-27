"""Verify PostgreSQL behavior when an isolated test URL is configured.

The required CI flag turns a missing URL into a test failure.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy.engine import make_url

from titanspan.database import (
    DatabaseServiceProvider,
    MigrationManager,
    Schema,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_DATABASE_PREFIX = "titanspan_codex_test_"
_POSTGRES_URL_ENV = "TITANSPAN_TEST_POSTGRES_URL"
_REQUIRE_POSTGRES_ENV = "TITANSPAN_REQUIRE_POSTGRES"
_CONCURRENT_TASK_COUNT = 2
_ROLLBACK_MARKER = "rollback marker"
_MIGRATION_UP = '''    def up(self) -> None:
        """Apply this revision's schema changes."""
        with Schema.create("postgres_migration_rows") as table:
            table.id()
            table.string("name")
'''
_MIGRATION_DOWN = '''    def down(self) -> None:
        """Reverse this revision's schema changes."""
        with Schema.drop_if_exists("postgres_migration_rows"):
            pass
'''

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create a Postgres test application after validating its DB identity.

    Args:
        tmp_path: Temporary application root provided by Pytest.

    Returns:
        An app configured only for a named, disposable test database.
    """
    url = configured_postgres_url()
    if not (make_url(url).database or "").startswith(_DATABASE_PREFIX):
        pytest.fail("Postgres integration requires a disposable test database.")
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "postgres",
                "connections": {
                    "postgres": {
                        "url": url,
                        "async_url": url,
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


def configured_postgres_url() -> str:
    """Require the integration URL in CI and skip local runs without it.

    Returns:
        The configured URL for an isolated PostgreSQL test database.

    Raises:
        pytest.fail.Exception: If mandatory CI lacks its configured service.
    """
    url = os.environ.get(_POSTGRES_URL_ENV)
    if url is not None:
        return url
    if os.environ.get(_REQUIRE_POSTGRES_ENV) == "1":
        pytest.fail(f"{_REQUIRE_POSTGRES_ENV}=1 requires {_POSTGRES_URL_ENV}.")
    pytest.skip(f"Set {_POSTGRES_URL_ENV} to run Postgres integration.")


async def test_postgresql_transactions_and_concurrent_sessions(
    application: Application,
) -> None:
    """Verify real DDL, rollback, and isolated concurrent async sessions.

    Args:
        application: Isolated Postgres integration application.
    """
    async with application:
        async with Schema.create("database_test_rows") as table:
            table.id()
            table.string("name", length=100).unique()

        with pytest.raises(RuntimeError, match=_ROLLBACK_MARKER):
            await _insert_then_raise()

        assert await DB.table("database_test_rows").count_async() == 0

        ready = anyio.Event()
        release = anyio.Event()
        rendezvous_lock = anyio.Lock()
        ready_count = 0

        async def insert_row(name: str) -> None:
            """Insert one independent row in a synchronized transaction.

            Args:
                name: Unique row value for this concurrent task.
            """
            nonlocal ready_count
            async with DB.transaction_async():
                await DB.table("database_test_rows").insert_async(
                    {"name": name},
                )
                async with rendezvous_lock:
                    ready_count += 1
                    if ready_count == _CONCURRENT_TASK_COUNT:
                        ready.set()
                await release.wait()

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(insert_row, "first")
            tasks.start_soon(insert_row, "second")
            await ready.wait()
            release.set()

        assert (
            await DB.table("database_test_rows").count_async()
            == _CONCURRENT_TASK_COUNT
        )
        await Schema.drop_if_exists("database_test_rows").apply_async()

        migrations = await application.container.make_async(MigrationManager)
        path = migrations.create_revision("postgres migration round trip")
        source = path.read_text(encoding="utf-8")
        source = source.replace(
            "from titanspan.database import Migration, run_migration",
            "from titanspan.database import Migration, Schema, run_migration",
        )
        source = source.replace(
            "    def up(self) -> None:\n"
            '        """Apply this revision\'s schema changes."""\n'
            "        pass\n",
            _MIGRATION_UP,
        )
        source = source.replace(
            "    def down(self) -> None:\n"
            '        """Reverse this revision\'s schema changes."""\n'
            "        pass\n",
            _MIGRATION_DOWN,
        )
        path.write_text(source, encoding="utf-8")
        await migrations.upgrade_async()

        assert await Schema.has_table_async("postgres_migration_rows")

        await migrations.rollback_async()

        assert not await Schema.has_table_async("postgres_migration_rows")


async def _insert_then_raise() -> None:
    """Roll a PostgreSQL insert back through the application transaction.

    Raises:
        RuntimeError: The deliberate failure used to verify rollback.
    """
    async with DB.transaction_async():
        await DB.table("database_test_rows").insert_async(
            {"name": "rolled back"},
        )
        raise RuntimeError(_ROLLBACK_MARKER)
