"""Verify model-level upserts reuse native atomic query operations.

The tests use SQLAlchemy mapped attributes and a real isolated SQLite
database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import (
    DatabaseServiceProvider,
    MassAssignmentError,
    Model,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_EMAIL = "ada@example.test"
_INITIAL_NAME = "Ada"
_UPDATED_NAME = "Augusta"
_STALE_TIMESTAMP_YEAR = 2000


class UpsertRecord(Model):
    """Represent rows written through model-level upsert operations.

    The public ``name`` attribute intentionally maps to a differently named
    database column so the adapter must respect SQLAlchemy's mapper metadata.
    """

    table = "model_upsert_records"
    fillable = ("email", "name")

    email: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column("display_name")
    is_admin: Mapped[bool] = mapped_column(default=False)


class CustomTimestampUpsertRecord(Model):
    """Represent upsert rows with custom physical timestamp column names.

    The ORM keeps its canonical timestamp attributes while the schema uses
    the application's selected column names.
    """

    table = "custom_timestamp_upsert_records"
    created_at_name = "created_on"
    updated_at_name = "modified_on"
    fillable = ("email", "name", "version")

    email: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    version: Mapped[int] = mapped_column(default=0)


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with a temporary SQLite database.

    Args:
        tmp_path: Pytest-owned directory for the database file.

    Returns:
        An application configured with its native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/model_upsert.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_async_model_upsert_preserves_creation_timestamp(
    application: Application,
) -> None:
    """Upsert mapped values and preserve the original creation timestamp.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_schema()
        inserted = await UpsertRecord.upsert_async(
            [_attributes(_INITIAL_NAME)],
            unique_by=("email",),
        )
        created = (
            await UpsertRecord.query().where("email", _EMAIL).first_async()
        )
        assert created is not None
        original_created_at = created.created_at

        updated = await UpsertRecord.upsert_async(
            [_attributes(_UPDATED_NAME)],
            unique_by=("email",),
        )
        current = (
            await UpsertRecord.query().where("email", _EMAIL).first_async()
        )

        assert inserted == 1
        assert updated == 1
        assert current is not None
        assert current.name == _UPDATED_NAME
        assert current.is_admin is False
        assert current.created_at == original_created_at
        assert current.updated_at is not None
        assert await UpsertRecord.query().count_async() == 1


async def test_model_upsert_uses_custom_timestamp_column_names(
    application: Application,
) -> None:
    """Apply automatic timestamps during saves and native model upserts.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE custom_timestamp_upsert_records ("
            "id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
            "name TEXT NOT NULL, version INTEGER NOT NULL, "
            "created_on TIMESTAMP, "
            "modified_on TIMESTAMP)"
        )
        created = await CustomTimestampUpsertRecord.create_async(
            {"email": _EMAIL, "name": _INITIAL_NAME, "version": 0},
        )
        assert created.created_at is not None
        assert created.updated_at is not None
        stored_created = (
            await CustomTimestampUpsertRecord.query()
            .where("email", _EMAIL)
            .first_async()
        )
        assert stored_created is not None
        original_created_at = stored_created.created_at

        affected = await CustomTimestampUpsertRecord.upsert_async(
            [{"email": _EMAIL, "name": _UPDATED_NAME, "version": 0}],
            unique_by=("email",),
            update=("name", "updated_at"),
        )
        current = (
            await CustomTimestampUpsertRecord.query()
            .where("email", _EMAIL)
            .first_async()
        )

        assert affected == 1
        assert current is not None
        assert current.name == _UPDATED_NAME
        assert current.created_at == original_created_at
        assert current.updated_at is not None

        await DB.statement_async(
            "UPDATE custom_timestamp_upsert_records "
            "SET modified_on = '2000-01-01 00:00:00' WHERE id = 1"
        )
        await current.refresh_async()
        assert current.updated_at is not None
        assert current.updated_at.year == _STALE_TIMESTAMP_YEAR
        assert await current.increment_async("version")
        await current.refresh_async()
        assert current.version == 1
        assert current.updated_at is not None
        assert current.updated_at.year > _STALE_TIMESTAMP_YEAR

        replica = current.replicate()
        assert replica.created_at is None
        assert replica.updated_at is None


async def test_sync_model_upsert_uses_mapped_columns(
    application: Application,
) -> None:
    """Run the sync API against a mapped attribute with a custom column name.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_schema()
        affected = await anyio.to_thread.run_sync(
            lambda: UpsertRecord.upsert(
                [_attributes(_INITIAL_NAME)],
                unique_by=("email",),
            ),
        )
        stored = await UpsertRecord.query().where("email", _EMAIL).first_async()

        assert affected == 1
        assert stored is not None
        assert stored.name == _INITIAL_NAME
        assert stored.is_admin is False
        assert stored.created_at is not None
        assert stored.updated_at is not None


async def test_model_upsert_rejects_guarded_update_columns(
    application: Application,
) -> None:
    """Prevent explicit upsert updates from bypassing fillable policy.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_schema()

        with pytest.raises(MassAssignmentError, match="guarded"):
            await UpsertRecord.upsert_async(
                [{"email": _EMAIL, "name": _INITIAL_NAME}],
                unique_by=("email",),
                update=("is_admin",),
            )

        assert await UpsertRecord.query().count_async() == 0


async def test_model_upsert_uses_strict_mass_assignment(
    application: Application,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise on discarded attributes when strict assignment is enabled.

    Args:
        application: Isolated Database application for this test.
        monkeypatch: Pytest class-policy override restored after the test.
    """
    async with application:
        await _create_schema()
        monkeypatch.setattr(UpsertRecord, "strict_mass_assignment", True)

        with pytest.raises(MassAssignmentError, match="is_admin"):
            await UpsertRecord.upsert_async(
                [_attributes(_INITIAL_NAME)],
                unique_by=("email",),
            )

        assert await UpsertRecord.query().count_async() == 0


async def _create_schema() -> None:
    """Create the model table with a real unique conflict target.

    SQLite enforces the same conflict boundary used by model upsert tests.
    """
    await DB.statement_async(
        "CREATE TABLE model_upsert_records ("
        "id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
        "display_name TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT 0, "
        "created_at TIMESTAMP, "
        "updated_at TIMESTAMP)"
    )


def _attributes(name: str) -> Mapping[str, object]:
    """Return one model attribute mapping for a deterministic test row.

    Args:
        name: Display name supplied for the row.

    Returns:
        A mapping using public mapped attribute names.
    """
    values: dict[str, object] = {
        "email": _EMAIL,
        "name": name,
        "is_admin": True,
    }
    return values
