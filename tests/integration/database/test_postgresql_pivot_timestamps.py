"""Verify timestamped many-to-many pivots against PostgreSQL.

This test uses the disposable PostgreSQL URL configured by the test suite.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Mapped  # noqa: TC002  # SQLAlchemy resolves types.
from tests.integration.database.postgresql_support import (
    configured_postgres_url,
)

from titanspan.database import (
    DatabaseServiceProvider,
    Model,
    belongs_to_many,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_DATABASE_PREFIX = "titanspan_codex_test_"
_PIVOT_TABLE = Table(
    "postgres_pivot_timestamps",
    Model.metadata,
    Column(
        "country_id",
        Integer,
        ForeignKey("postgres_pivot_countries.id"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("postgres_pivot_tags.id"),
        primary_key=True,
    ),
    Column("label", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class PostgreSQLPivotTag(Model):
    """Represent one tag linked through a timestamped association table.

    The test checks only relation-manager persistence on PostgreSQL.
    """

    table = "postgres_pivot_tags"
    fillable = ("name",)

    name: Mapped[str]


class PostgreSQLPivotCountry(Model):
    """Represent one country with a timestamped many-to-many relation.

    Titanspan owns pivot timestamps for explicit relation-manager writes.
    """

    table = "postgres_pivot_countries"
    fillable = ("name",)

    name: Mapped[str]
    tags: Mapped[list[PostgreSQLPivotTag]] = belongs_to_many(
        PostgreSQLPivotTag,
        _PIVOT_TABLE,
        timestamps=("created_at", "updated_at"),
    )


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application for the configured disposable PostgreSQL DB.

    Args:
        tmp_path: Temporary application root provided by Pytest.

    Returns:
        An unopened application with a native Database provider.
    """
    url = configured_postgres_url()
    database_name = make_url(url).database or ""
    if not database_name.startswith(_DATABASE_PREFIX):
        pytest.fail("PostgreSQL integration requires a disposable test DB.")
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


async def test_postgresql_relation_manager_stamps_pivot_rows(
    application: Application,
) -> None:
    """Insert and update aware pivot timestamps through the real backend.

    Args:
        application: Isolated PostgreSQL application for this test.
    """
    async with application:
        await DB.statement_async(
            "DROP TABLE IF EXISTS postgres_pivot_timestamps",
        )
        await DB.statement_async(
            "DROP TABLE IF EXISTS postgres_pivot_tags",
        )
        await DB.statement_async(
            "DROP TABLE IF EXISTS postgres_pivot_countries",
        )
        try:
            await DB.statement_async(
                "CREATE TABLE postgres_pivot_countries ("
                "id SERIAL PRIMARY KEY, name TEXT NOT NULL, "
                "created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)"
            )
            await DB.statement_async(
                "CREATE TABLE postgres_pivot_tags ("
                "id SERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, "
                "created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)"
            )
            await DB.statement_async(
                "CREATE TABLE postgres_pivot_timestamps ("
                "country_id INTEGER NOT NULL, tag_id INTEGER NOT NULL, "
                "label TEXT, created_at TIMESTAMPTZ NOT NULL, "
                "updated_at TIMESTAMPTZ NOT NULL, "
                "PRIMARY KEY(country_id, tag_id), "
                "FOREIGN KEY(country_id) "
                "REFERENCES postgres_pivot_countries(id), "
                "FOREIGN KEY(tag_id) REFERENCES postgres_pivot_tags(id))"
            )
            country = await PostgreSQLPivotCountry.create_async(
                {"name": "Example"},
            )
            tag = await PostgreSQLPivotTag.create_async(
                {"name": "featured"},
            )
            relation = country.relation("tags")

            assert await relation.attach_async(tag.id) == (tag.id,)
            created_at = await (
                DB.table("postgres_pivot_timestamps")
                .where("country_id", country.id)
                .where("tag_id", tag.id)
                .value_async("created_at")
            )
            updated_at = await (
                DB.table("postgres_pivot_timestamps")
                .where("country_id", country.id)
                .where("tag_id", tag.id)
                .value_async("updated_at")
            )
            assert isinstance(created_at, datetime)
            assert isinstance(updated_at, datetime)
            assert created_at.tzinfo is not None
            assert updated_at.tzinfo is not None
            assert created_at.astimezone(UTC) == updated_at.astimezone(UTC)

            assert (
                await relation.update_existing_pivot_async(
                    tag.id,
                    {"label": "updated"},
                )
                == 1
            )
            changed_at = await (
                DB.table("postgres_pivot_timestamps")
                .where("country_id", country.id)
                .where("tag_id", tag.id)
                .value_async("updated_at")
            )
            assert isinstance(changed_at, datetime)
            assert changed_at > created_at
        finally:
            await DB.statement_async(
                "DROP TABLE IF EXISTS postgres_pivot_timestamps",
            )
            await DB.statement_async(
                "DROP TABLE IF EXISTS postgres_pivot_tags",
            )
            await DB.statement_async(
                "DROP TABLE IF EXISTS postgres_pivot_countries",
            )
