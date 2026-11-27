"""Verify schema construction through SQLAlchemy and Alembic APIs.

These tests apply real DDL to isolated application-owned SQLite databases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest

from titanspan.database import DatabaseServiceProvider, Schema
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_SCHEMA_BODY_FAILURE = "schema body failed"


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with a temporary SQLite database.

    Args:
        tmp_path: Test-owned application directory.

    Returns:
        An application with the native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/schema.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_async_schema_create_alter_and_inspection(
    application: Application,
) -> None:
    """Create and alter tables through native async schema builders.

    Args:
        application: Isolated application fixture.
    """
    async with application:
        async with Schema.create("users") as table:
            table.id()
            table.string("email", length=320).unique()
            table.boolean("active").default(True)
            table.timestamps()

        assert await Schema.has_table_async("users")
        assert await Schema.has_column_async("users", "email")
        assert await Schema.list_tables_async() == ["users"]

        async with Schema.alter("users") as table:
            table.string("display_name", length=120).nullable()

        assert await Schema.has_column_async("users", "display_name")
        assert await Schema.has_columns_async(
            "users",
            ("email", "display_name"),
        )
        await DB.table("users").insert_async(
            {"email": "ada@example.test", "active": True},
        )
        assert await DB.table("users").count_async() == 1


async def test_sync_schema_operations_use_the_application_session(
    application: Application,
) -> None:
    """Keep synchronous schema changes inside the sync Unit of Work.

    Args:
        application: Isolated application fixture.
    """
    async with application:
        await anyio.to_thread.run_sync(_create_sync_table)

        assert await Schema.has_table_async("sync_entries")


async def test_schema_context_does_not_apply_after_body_failure(
    application: Application,
) -> None:
    """Avoid applying partially declared DDL when builder code raises.

    Args:
        application: Isolated application fixture.
    """
    async with application:
        with pytest.raises(RuntimeError, match=_SCHEMA_BODY_FAILURE):
            await _raise_inside_schema_context()

        assert not await Schema.has_table_async("discarded")


async def _raise_inside_schema_context() -> None:
    """Raise inside a schema declaration before the async context exits.
    """  # fmt: skip
    async with Schema.create("discarded") as table:
        table.id()
        raise RuntimeError(_SCHEMA_BODY_FAILURE)


def _create_sync_table() -> None:
    """Create a table through the sync schema facade in a worker thread.
    """  # fmt: skip
    with Schema.create("sync_entries") as table:
        table.id()
        table.string("name").nullable()
