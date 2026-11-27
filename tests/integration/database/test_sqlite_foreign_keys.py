"""Verify SQLite foreign-key enforcement through owned database engines.

The tests exercise sync and async SQLite connections, transactional DML, and
Alembic-backed batch alteration through isolated Applications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest

from titanspan.database import (
    DatabaseServiceProvider,
    DatabaseTransactionError,
    Schema,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_MISSING_PARENT_ID = 997
_ROLLBACK_PARENT_ID = 19
_RESTRICT_PARENT_ID = 31
_CASCADE_PARENT_ID = 47
_ROLLBACK_MESSAGE = "rollback foreign key transaction"


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with an isolated SQLite database.

    Args:
        tmp_path: Pytest-owned temporary directory.

    Returns:
        An unopened application configured with the Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/foreign-keys.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_sqlite_foreign_keys_reject_orphans_on_sync_and_async_engines(
    application: Application,
) -> None:
    """Reject orphan rows through both owned SQLite engine modes.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_relationship_tables()
        assert await DB.scalar_async("PRAGMA foreign_keys") == 1
        assert await anyio.to_thread.run_sync(_sync_foreign_keys_enabled) == 1

        with pytest.raises(DatabaseTransactionError):
            await DB.table("restrict_children").insert_async(
                {"parent_id": _MISSING_PARENT_ID},
            )

        with pytest.raises(DatabaseTransactionError):
            await anyio.to_thread.run_sync(_insert_sync_orphan)

        assert await DB.table("restrict_children").count_async() == 0


async def test_sqlite_foreign_keys_enforce_restrict_and_cascade_actions(
    application: Application,
) -> None:
    """Apply restrictive and cascading foreign-key actions in SQLite.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_relationship_tables()
        await DB.table("parents").insert_async({"id": _RESTRICT_PARENT_ID})
        await DB.table("restrict_children").insert_async(
            {"parent_id": _RESTRICT_PARENT_ID},
        )

        with pytest.raises(DatabaseTransactionError):
            await (
                DB.table("parents")
                .where(
                    "id",
                    _RESTRICT_PARENT_ID,
                )
                .delete_async()
            )

        assert (
            await DB.table("parents")
            .where(
                "id",
                _RESTRICT_PARENT_ID,
            )
            .exists_async()
        )

        await DB.table("parents").insert_async({"id": _CASCADE_PARENT_ID})
        await DB.table("cascade_children").insert_async(
            {"parent_id": _CASCADE_PARENT_ID},
        )
        await (
            DB.table("parents")
            .where(
                "id",
                _CASCADE_PARENT_ID,
            )
            .delete_async()
        )

        assert await DB.table("cascade_children").count_async() == 0


async def test_sqlite_foreign_keys_survive_rollback_and_batch_alteration(
    application: Application,
) -> None:
    """Keep constraints effective after rollback and Alembic batch DDL.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_relationship_tables()
        with pytest.raises(RuntimeError, match=_ROLLBACK_MESSAGE):
            await _insert_relationship_rows_then_fail()

        assert await DB.table("parents").count_async() == 0
        assert await DB.table("cascade_children").count_async() == 0

        async with Schema.alter("cascade_children") as table:
            table.string("label", length=32).nullable()

        assert await DB.scalar_async("PRAGMA foreign_keys") == 1
        await DB.table("parents").insert_async({"id": _CASCADE_PARENT_ID})
        await DB.table("cascade_children").insert_async(
            {
                "parent_id": _CASCADE_PARENT_ID,
                "label": "preserved constraint",
            },
        )

        with pytest.raises(DatabaseTransactionError):
            await DB.table("cascade_children").insert_async(
                {"parent_id": _MISSING_PARENT_ID},
            )


async def _create_relationship_tables() -> None:
    """Create related tables with real SQLite referential actions.

    The DDL is test-owned and executes through the application Connection.
    """
    await DB.statement_async("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
    await DB.statement_async(
        "CREATE TABLE restrict_children ("
        "id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, "
        "FOREIGN KEY (parent_id) REFERENCES parents(id) ON DELETE RESTRICT)"
    )
    await DB.statement_async(
        "CREATE TABLE cascade_children ("
        "id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, "
        "FOREIGN KEY (parent_id) REFERENCES parents(id) ON DELETE CASCADE)"
    )


def _sync_foreign_keys_enabled() -> int:
    """Read the connection-local SQLite enforcement setting synchronously.

    Returns:
        The value returned by SQLite's ``foreign_keys`` pragma.
    """
    value = DB.scalar("PRAGMA foreign_keys")
    assert isinstance(value, int)
    return value


def _insert_sync_orphan() -> None:
    """Attempt a synchronous child insert without a matching parent.
    """  # fmt: skip
    DB.table("restrict_children").insert(
        {"parent_id": _MISSING_PARENT_ID},
    )


async def _insert_relationship_rows_then_fail() -> None:
    """Insert valid related rows and roll the transaction back.

    Raises:
        RuntimeError: Always, to verify transaction rollback with FK checks on.
    """
    async with DB.transaction_async():
        await DB.table("parents").insert_async(
            {"id": _ROLLBACK_PARENT_ID},
        )
        await DB.table("cascade_children").insert_async(
            {"parent_id": _ROLLBACK_PARENT_ID},
        )
        raise RuntimeError(_ROLLBACK_MESSAGE)
