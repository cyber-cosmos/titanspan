"""Verify database assertions query through the active service.

The helpers share Foundation, SQLAlchemy, the native Query Builder, and
temporary SQLite databases instead of creating another test lifecycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy.orm import Mapped  # noqa: TC002

from titanspan.database import (
    DatabaseServiceProvider,
    Model,
    SoftDeletes,
    assert_database_count,
    assert_database_count_async,
    assert_database_empty,
    assert_database_empty_async,
    assert_database_has,
    assert_database_has_async,
    assert_database_missing,
    assert_database_missing_async,
    assert_model_exists,
    assert_model_exists_async,
    assert_model_missing,
    assert_model_missing_async,
    assert_not_soft_deleted,
    assert_not_soft_deleted_async,
    assert_query_count,
    assert_query_count_async,
    assert_soft_deleted,
    assert_soft_deleted_async,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


class DatabaseAssertionRecord(Model):
    """Represent one row for native database assertion tests.

    Its table contains only the fields exercised by test helpers.
    """

    table = "testing_records"
    fillable = ("name",)

    name: Mapped[str]


class SoftTestingRecord(SoftDeletes, Model):
    """Represent a soft-deletable row for visibility assertions.

    The mixin owns the mapped deletion timestamp and query scope.
    """

    table = "soft_testing_records"
    fillable = ("name",)

    name: Mapped[str]


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an isolated application-owned SQLite database.

    Args:
        tmp_path: Pytest-owned temporary directory.

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
                        "database": "database/assertions.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_database_assertions_use_async_queries(
    application: Application,
) -> None:
    """Assert row presence, absence, counts, and empty tables asynchronously.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_tables()
        first = await DatabaseAssertionRecord.create_async({"name": "first"})
        await DatabaseAssertionRecord.create_async({"name": "second"})
        with pytest.raises(TypeError, match="require SoftDeletes"):
            assert_soft_deleted(first)
        with pytest.raises(TypeError, match="require SoftDeletes"):
            await assert_soft_deleted_async(first)

        await assert_database_has_async(
            "testing_records",
            {"name": "first"},
        )
        await assert_database_missing_async(
            "testing_records",
            {"name": "missing"},
        )
        with pytest.raises(AssertionError, match="Expected no row"):
            await assert_database_missing_async(
                "testing_records",
                {"name": "first"},
            )
        await assert_database_count_async("testing_records", 2)
        await assert_database_empty_async("empty_records")
        await assert_model_exists_async(first)
        with pytest.raises(AssertionError, match="row to be absent"):
            await assert_model_missing_async(first)
        assert await first.delete_async()
        await assert_model_missing_async(first)
        with pytest.raises(AssertionError, match="row to exist"):
            await assert_model_exists_async(first)

        with pytest.raises(AssertionError, match="supplied attributes"):
            await assert_database_has_async(
                "testing_records",
                {"name": "missing"},
            )
        with pytest.raises(AssertionError, match="Expected 3"):
            await assert_database_count_async("testing_records", 3)


async def test_soft_delete_assertions_query_the_database(
    application: Application,
) -> None:
    """Distinguish active and soft-deleted rows through ORM scopes.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_tables()
        active = await SoftTestingRecord.create_async({"name": "active"})
        deleted = await SoftTestingRecord.create_async({"name": "deleted"})
        assert await deleted.delete_async()

        await assert_not_soft_deleted_async(active)
        await assert_soft_deleted_async(deleted)
        with pytest.raises(AssertionError, match="soft deleted"):
            await assert_soft_deleted_async(active)
        with pytest.raises(AssertionError, match="not soft deleted"):
            await assert_not_soft_deleted_async(deleted)


async def test_query_count_assertions_count_real_sync_and_async_queries(
    application: Application,
) -> None:
    """Count real statements through both native database execution paths.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_tables()
        await DatabaseAssertionRecord.create_async({"name": "counted"})

        with (
            pytest.raises(ValueError, match="non-negative integer"),
            assert_query_count(-1),
        ):
            pass
        with (
            pytest.raises(ValueError, match="non-negative integer"),
            assert_query_count(True),
        ):
            pass
        with pytest.raises(ValueError, match="non-negative integer"):
            async with assert_query_count_async(-1):
                pass

        await anyio.to_thread.run_sync(_assert_sync_query_count)
        async with assert_query_count_async(1):
            assert await DB.table("testing_records").count_async() == 1
        with pytest.raises(
            AssertionError,
            match="Expected 0 SQL statements but observed 1",
        ):
            async with assert_query_count_async(0):
                await DB.table("testing_records").count_async()
        async with assert_query_count_async(1):
            assert await DB.table("testing_records").count_async() == 1


def _assert_sync_query_count() -> None:
    """Assert one synchronous SQL statement in an owned worker thread.

    The real engine listener must be removed after the assertion exits.
    """
    with assert_query_count(1):
        assert DB.table("testing_records").count() == 1
    with (
        pytest.raises(
            AssertionError,
            match="Expected 0 SQL statements but observed 1",
        ),
        assert_query_count(0),
    ):
        DB.table("testing_records").count()
    with assert_query_count(1):
        assert DB.table("testing_records").count() == 1


async def test_sync_database_assertions_use_worker_owned_sessions(
    application: Application,
) -> None:
    """Use synchronous assertions from an AnyIO-managed worker thread.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_tables()
        record = await DatabaseAssertionRecord.create_async({"name": "sync"})
        soft_record = await SoftTestingRecord.create_async(
            {"name": "sync soft"},
        )

        await anyio.to_thread.run_sync(
            _assert_sync_database_state,
            record,
            soft_record,
        )
        assert await soft_record.delete_async()
        await anyio.to_thread.run_sync(_assert_sync_soft_deleted, soft_record)
        assert await record.delete_async()
        await anyio.to_thread.run_sync(_assert_sync_model_missing, record)


async def _create_tables() -> None:
    """Create the tables used by the real SQLite assertions.

    The test setup uses explicit SQL while assertions use native builders.
    """
    await DB.statement_async(
        "CREATE TABLE testing_records ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE soft_testing_records ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, deleted_at TIMESTAMP, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE empty_records (id INTEGER PRIMARY KEY)"
    )


def _assert_sync_database_state(
    record: DatabaseAssertionRecord,
    soft_record: SoftTestingRecord,
) -> None:
    """Verify sync helpers through one worker-owned database scope.

    Args:
        record: Existing row used by model assertions.
        soft_record: Active row used by soft-delete assertions.
    """
    assert_database_has("testing_records", {"name": "sync"})
    assert_database_missing("testing_records", {"name": "absent"})
    assert_database_count("testing_records", 1)
    assert_database_empty("empty_records")
    assert_model_exists(record)
    assert_not_soft_deleted(soft_record)
    with pytest.raises(AssertionError, match="supplied attributes"):
        assert_database_has("testing_records", {"name": "absent"})
    with pytest.raises(AssertionError, match="Expected no row"):
        assert_database_missing("testing_records", {"name": "sync"})
    with pytest.raises(AssertionError, match="Expected 2 rows"):
        assert_database_count("testing_records", 2)
    with pytest.raises(AssertionError, match="row to be absent"):
        assert_model_missing(record)
    with pytest.raises(AssertionError, match="soft deleted"):
        assert_soft_deleted(soft_record)


def _assert_sync_soft_deleted(record: SoftTestingRecord) -> None:
    """Check a committed soft delete through the sync query path.

    Args:
        record: Model whose deleted row must still be present.
    """
    assert_soft_deleted(record)
    with pytest.raises(AssertionError, match="not soft deleted"):
        assert_not_soft_deleted(record)


def _assert_sync_model_missing(record: DatabaseAssertionRecord) -> None:
    """Check a hard-deleted model through the sync query path.

    Args:
        record: Model whose primary-key row must be absent.
    """
    assert_model_missing(record)
    with pytest.raises(AssertionError, match="row to exist"):
        assert_model_exists(record)
