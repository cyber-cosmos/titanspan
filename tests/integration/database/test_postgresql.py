"""Verify PostgreSQL behavior when an isolated test URL is configured.

The required CI flag turns a missing URL into a test failure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Mapped, mapped_column
from tests.integration.database.postgresql_support import (
    configured_postgres_url,
)

from titanspan.database import (
    DatabaseServiceProvider,
    MigrationManager,
    Model,
    Schema,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_DATABASE_PREFIX = "titanspan_codex_test_"
_CONCURRENT_TASK_COUNT = 2
_EXPECTED_UPSERTED_SCORE = 2
_EXPECTED_INCREMENT_VALUES = [1, 2]
_UNKNOWN_ROWCOUNT = -1
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


class PostgreSQLAtomicCounter(Model):
    """Represent a counter row updated by independent PostgreSQL sessions.
    """  # fmt: skip

    table = "postgres_atomic_counters"
    fillable = ("value",)
    timestamps = False

    value: Mapped[int] = mapped_column(default=0)


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
        await migrations.upgrade_async(isolated=True)

        assert await Schema.has_table_async("postgres_migration_rows")

        await migrations.rollback_async()

        assert not await Schema.has_table_async("postgres_migration_rows")


async def test_postgresql_model_increments_are_atomic(
    application: Application,
) -> None:
    """Preserve both increments through competing real database sessions.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async(
            "DROP TABLE IF EXISTS postgres_atomic_counters",
        )
        await DB.statement_async(
            "CREATE TABLE postgres_atomic_counters ("
            "id BIGSERIAL PRIMARY KEY, value BIGINT NOT NULL, "
            "created_at TIMESTAMPTZ NULL, updated_at TIMESTAMPTZ NULL)"
        )
        counter = await PostgreSQLAtomicCounter.create_async({"value": 0})
        first = await PostgreSQLAtomicCounter.find_async(counter.id)
        second = await PostgreSQLAtomicCounter.find_async(counter.id)
        assert first is not None
        assert second is not None

        ready = anyio.Event()
        rendezvous_lock = anyio.Lock()
        ready_count = 0
        observed_values: list[int] = []

        async def increment(model: PostgreSQLAtomicCounter) -> None:
            """Run one instance increment after both models are ready.

            Args:
                model: Detached model loaded in an independent operation.
            """
            nonlocal ready_count
            async with rendezvous_lock:
                ready_count += 1
                if ready_count == _CONCURRENT_TASK_COUNT:
                    ready.set()
            await ready.wait()
            assert await model.increment_async("value")
            observed_values.append(model.value)

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(increment, first)
            tasks.start_soon(increment, second)

        assert sorted(observed_values) == _EXPECTED_INCREMENT_VALUES
        assert (
            await PostgreSQLAtomicCounter.query().value_async("value")
            == _CONCURRENT_TASK_COUNT
        )
        await DB.statement_async(
            "DROP TABLE postgres_atomic_counters",
        )


async def test_postgresql_upsert_and_insert_or_ignore_are_atomic(
    application: Application,
) -> None:
    """Use PostgreSQL ON CONFLICT for native insert-or-update operations.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async("DROP TABLE IF EXISTS postgres_upsert_rows")
        await DB.statement_async(
            "CREATE TABLE postgres_upsert_rows ("
            "id BIGSERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL, "
            "name TEXT NOT NULL, score INTEGER NOT NULL)"
        )
        query = DB.table("postgres_upsert_rows")

        inserted = await query.upsert_async(
            [{"email": "ada@example.test", "name": "Ada", "score": 1}],
            unique_by=("email",),
        )
        updated = await query.upsert_async(
            [
                {
                    "email": "ada@example.test",
                    "name": "Ada Lovelace",
                    "score": 2,
                },
            ],
            unique_by=("email",),
        )
        ignored = await query.insert_or_ignore_async(
            [
                {
                    "email": "ada@example.test",
                    "name": "Ignored",
                    "score": 99,
                },
            ],
        )
        row = await query.where("email", "ada@example.test").first_async()

        assert inserted in (1, _UNKNOWN_ROWCOUNT)
        assert updated in (1, _UNKNOWN_ROWCOUNT)
        assert ignored in (0, _UNKNOWN_ROWCOUNT)
        assert row is not None
        assert row["name"] == "Ada Lovelace"
        assert row["score"] == _EXPECTED_UPSERTED_SCORE
        assert await query.count_async() == 1
        await DB.statement_async("DROP TABLE postgres_upsert_rows")


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
