"""Exercise Schema inspection and conditional DDL edge behavior.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import anyio
import pytest

from titanspan.database import (
    DatabaseSchemaError,
    DatabaseServiceProvider,
    Schema,
)
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_SYNC_SCHEMA_BODY_FAILURE = "sync schema body failed"


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with one isolated SQLite database.

    Args:
        tmp_path: Pytest-owned application root for database files.

    Returns:
        An application configured with the native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/schema-edges.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_sync_inspection_reports_existing_and_missing_schema_items(
    application: Application,
) -> None:
    """Exercise sync Inspector APIs without blocking the async event loop.

    Args:
        application: Isolated application fixture.
    """
    async with application:
        async with Schema.create("parents") as table:
            table.id()

        async with Schema.create("children") as table:
            table.id()
            table.string("name")
            table.foreign_id("parent_id").references(
                "parents",
                on_delete="cascade",
            )
            table.index("name", name="ix_children_name")

        results = await anyio.to_thread.run_sync(_inspect_children)

        assert results[0]
        assert not results[1]
        assert results[2]
        assert not results[3]
        assert results[4]
        assert not results[5]
        assert set(results[6]) == {"children", "parents"}
        assert results[7] == ("id", "name", "parent_id")

        assert (
            await Schema.has_columns_async(
                "children",
                ("id", "missing_column"),
            )
            is False
        )
        assert (
            await Schema.has_index_async(
                "children",
                "missing_index",
            )
            is False
        )


async def test_conditional_schema_operations_and_validation(
    application: Application,
) -> None:
    """Preserve existing tables and validate real SQLite DDL transitions.

    Args:
        application: Isolated application fixture.
    """
    async with application:
        async with Schema.create_if_missing("attachments") as table:
            table.id()
            table.string("name")
            table.integer("remove_me")
            table.nullable_morphs("attachable")

        async with Schema.create_if_missing("attachments") as table:
            table.string("ignored_column")

        assert not await Schema.has_column_async(
            "attachments",
            "ignored_column",
        )

        async with Schema.alter("attachments") as table:
            table.integer("version").default(1)
            table.rename_column("name", "display_name")
            table.drop_column("remove_me")
            table.index("display_name", name="ix_attachments_display_name")

        assert await Schema.has_columns_async(
            "attachments",
            (
                "display_name",
                "version",
                "attachable_type",
                "attachable_id",
            ),
        )
        assert await Schema.has_index_async(
            "attachments",
            "ix_attachments_display_name",
        )
        assert not await Schema.has_column_async(
            "attachments",
            "remove_me",
        )

        async with Schema.rename("attachments", "uploads"):
            pass

        assert await Schema.has_table_async("uploads")
        assert not await Schema.has_table_async("attachments")

        async with Schema.drop_if_exists("missing_table"):
            pass
        async with Schema.drop_if_exists("uploads"):
            pass
        assert not await Schema.has_table_async("uploads")

        with pytest.raises(DatabaseSchemaError, match="positive"):
            Schema.create("invalid_character").char("code", length=0)

        with pytest.raises(DatabaseSchemaError, match="precision or scale"):
            Schema.create("invalid_decimal").decimal(
                "amount",
                precision=2,
                scale=3,
            )

        with pytest.raises(DatabaseSchemaError, match="unique and nonempty"):
            Schema.create("invalid_enum").enum("state", "open", "open")

        with pytest.raises(DatabaseSchemaError, match="foreign-key action"):
            Schema.create("invalid_action").foreign(
                "id",
                references="uploads",
                on_delete="DROP",
            )

        with pytest.raises(DatabaseSchemaError, match="between schemas"):
            async with Schema.rename("parents", "archive.parents"):
                pass


async def test_schema_accepts_valid_types_and_rejects_invalid_blueprints(
    application: Application,
) -> None:
    """Verify valid types and reject unsafe DDL declarations.

    Args:
        application: Isolated application fixture.
    """
    async with application:
        async with Schema.create("typed_values") as table:
            table.id()
            table.char("code", length=4)
            table.string("label", length=48)
            table.decimal("amount", precision=8, scale=2)
            table.enum("state", "open", "closed")

        assert await Schema.has_columns_async(
            "typed_values",
            ("code", "label", "amount", "state"),
        )

        with pytest.raises(DatabaseSchemaError, match="positive"):
            Schema.create("invalid_string").string("label", length=0)

        with pytest.raises(DatabaseSchemaError, match="precision or scale"):
            Schema.create("invalid_precision").decimal(
                "amount",
                precision=0,
                scale=0,
            )

        with pytest.raises(DatabaseSchemaError, match="unique and nonempty"):
            Schema.create("empty_enum").enum("state")

        with pytest.raises(DatabaseSchemaError, match="counts must match"):
            Schema.create("invalid_foreign").foreign(
                "left_id",
                "right_id",
                references="typed_values",
            )

        with pytest.raises(
            DatabaseSchemaError,
            match="column name is required",
        ):
            Schema.create("invalid_unique").unique()

        with pytest.raises(DatabaseSchemaError, match="does not accept"):
            Schema.drop("typed_values").string("unused")

        with pytest.raises(DatabaseSchemaError, match="one schema qualifier"):
            Schema.create("one.two.three")

        with pytest.raises(DatabaseSchemaError, match="identifier is invalid"):
            Schema.create("unsafe table")

        with pytest.raises(DatabaseSchemaError, match="create blueprint"):
            Schema.alter("typed_values").foreign(
                "code",
                references="typed_values",
            )

        with pytest.raises(DatabaseSchemaError, match="requires a target"):
            async with Schema.rename(
                "typed_values",
                cast("str", None),
            ):
                pass

        with pytest.raises(RuntimeError, match=_SYNC_SCHEMA_BODY_FAILURE):
            await anyio.to_thread.run_sync(_raise_sync_schema_context)
        assert not await Schema.has_table_async("discarded_sync_schema")


def _raise_sync_schema_context() -> None:
    """Raise before the sync schema context can apply declared DDL.

    The worker owns the synchronous database boundary for this test.
    """
    with Schema.create("discarded_sync_schema") as table:
        table.id()
        raise RuntimeError(_SYNC_SCHEMA_BODY_FAILURE)


def _inspect_children() -> tuple[
    bool,
    bool,
    bool,
    bool,
    bool,
    bool,
    list[str],
    tuple[str, ...],
]:
    """Inspect one SQLite table through every sync Schema query helper.

    Returns:
        Existence checks, table names, and ordered child column names.
    """
    columns_exist = Schema.has_columns("children", ("id", "name"))
    missing_columns_exist = Schema.has_columns(
        "children",
        ("id", "missing_column"),
    )
    index_exists = Schema.has_index("children", "ix_children_name")
    missing_index_exists = Schema.has_index("children", "missing_index")
    foreign_key_exists = Schema.has_foreign_key(
        "children",
        "parent_id",
        "parents",
    )
    missing_foreign_key_exists = Schema.has_foreign_key(
        "children",
        "missing_id",
        "parents",
    )
    table_names = Schema.list_tables()
    columns = tuple(Schema.list_columns("children"))
    return (
        columns_exist,
        missing_columns_exist,
        index_exists,
        missing_index_exists,
        foreign_key_exists,
        missing_foreign_key_exists,
        table_names,
        columns,
    )
