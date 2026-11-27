"""Exercise synchronous model helpers and transient collection behavior.

The tests use a real SQLite database through the application service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import (
    DatabaseQueryError,
    DatabaseServiceProvider,
    Model,
    ModelCollection,
    ModelNotFoundError,
    MultipleModelsFoundError,
    SoftDeletes,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_EXPECTED_HELPER_NAMES = (
    "Ada",
    "Ada",
    "Grace",
    "Grace Hopper",
    "Katherine Johnson",
    "Force created",
    "Fallback",
)
_EXPECTED_INCREMENTED_VALUE = 4
_EXPECTED_PREPARED_VALUE = 3
_EXPECTED_RESTORED_VALUE = 1
_MISSING_IDENTIFIER = 99_999


class ModelEdgeRecord(Model):
    """Represent a unique record for Active Record edge cases.
    """  # fmt: skip

    table = "model_edge_records"
    fillable = ("name", "email", "counter")
    timestamps = False

    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
    counter: Mapped[int] = mapped_column(default=0)
    is_admin: Mapped[bool] = mapped_column(default=False)


class ModelEdgeSoftRecord(SoftDeletes, Model):
    """Represent a soft-deletable row for synchronous helpers.
    """  # fmt: skip

    table = "model_edge_soft_records"
    fillable = ("name",)
    timestamps = False

    name: Mapped[str]


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with isolated synchronous and async SQLite IO.

    Args:
        tmp_path: Temporary application root owned by Pytest.

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
                        "database": "database/model_edges.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_sync_retrieval_and_creation_helpers_handle_edge_cases(
    application: Application,
) -> None:
    """Exercise synchronous fallbacks, unique races, and upsert helpers.

    Args:
        application: Application configured by the SQLite fixture.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE model_edge_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT NOT NULL UNIQUE, counter INTEGER NOT NULL DEFAULT 0, "
            "is_admin BOOLEAN NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        observed = await anyio.to_thread.run_sync(
            _exercise_sync_retrieval_and_creation,
        )

    assert observed == _EXPECTED_HELPER_NAMES


async def test_sync_soft_delete_and_increment_operations(
    application: Application,
) -> None:
    """Exercise restore outcomes and atomic model increments synchronously.

    Args:
        application: Application configured by the SQLite fixture.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE model_edge_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT NOT NULL UNIQUE, counter INTEGER NOT NULL DEFAULT 0, "
            "is_admin BOOLEAN NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        await DB.statement_async(
            "CREATE TABLE model_edge_soft_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "deleted_at TIMESTAMP, created_at TIMESTAMP, "
            "updated_at TIMESTAMP)"
        )
        observed = await anyio.to_thread.run_sync(
            _exercise_sync_soft_delete_and_increments,
        )

    assert observed == (_EXPECTED_INCREMENTED_VALUE, True, False, True, True)


async def test_transient_and_empty_model_collections_are_safe(
    application: Application,
) -> None:
    """Keep transient identity operations and refreshes free of database IO.

    Args:
        application: Application configured by the SQLite fixture.
    """
    async with application:
        empty = ModelCollection[ModelEdgeRecord]()
        transient = ModelEdgeRecord(name="Transient", email="transient@test")
        models = ModelCollection([transient, transient])

        assert not await empty.fresh_async()
        assert not empty.fresh()
        assert not await models.fresh_async()
        assert not models.fresh()
        assert models.contains(transient)
        assert not models.contains(
            ModelEdgeRecord(name="Transient", email="transient@test"),
        )
        assert models.find(transient) is None
        assert models.intersection().model_keys() == (None,)
        assert empty.load() is empty
        assert await empty.load_async("posts") is empty
        assert models.load_missing() is models


async def test_model_original_fresh_refresh_and_delete_transitions(
    application: Application,
) -> None:
    """Preserve prior values and reload rows only while they still exist.

    Args:
        application: Application configured by the SQLite fixture.
    """
    async with application:
        await _create_edge_record_table()
        record = await ModelEdgeRecord.create_async(
            {"name": "Ada", "email": "ada@example.test"},
        )
        record.name = "Grace"
        assert record.original()["name"] == "Ada"

        fresh = await record.fresh_async()
        assert fresh is not None
        assert fresh is not record
        assert fresh.name == "Ada"

        await record.save_async()
        await record.refresh_async()
        assert record.name == "Grace"
        assert await record.delete_async()
        assert await record.fresh_async() is None
        with pytest.raises(ModelNotFoundError):
            await record.refresh_async()
        with pytest.raises(ModelNotFoundError):
            await anyio.to_thread.run_sync(record.refresh)
        with pytest.raises(ModelNotFoundError):
            await ModelEdgeRecord.find_or_fail_async(_MISSING_IDENTIFIER)


async def test_async_soft_delete_and_transient_delete_outcomes(
    application: Application,
) -> None:
    """Return accurate outcomes for repeated and transient deletions.

    Args:
        application: Application configured by the SQLite fixture.
    """
    async with application:
        await _create_edge_record_table()
        await DB.statement_async(
            "CREATE TABLE model_edge_soft_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "deleted_at TIMESTAMP, created_at TIMESTAMP, "
            "updated_at TIMESTAMP)"
        )
        transient = ModelEdgeRecord(name="Transient", email="unused@test")
        assert not await transient.delete_async()
        assert not await anyio.to_thread.run_sync(transient.delete)

        soft = await ModelEdgeSoftRecord.create_async({"name": "Soft"})
        assert not await soft.restore_async()
        assert await soft.delete_async()
        assert not await soft.delete_async()
        assert await soft.restore_async()
        assert not await soft.restore_async()
        assert await soft.force_delete_async()


async def test_increment_rejects_non_numeric_and_boolean_attributes(
    application: Application,
) -> None:
    """Reject invalid increment fields before assigning transient values.

    Args:
        application: Application configured by the SQLite fixture.
    """
    async with application:
        await _create_edge_record_table()
        record = ModelEdgeRecord(
            name="Counter",
            email="counter@example.test",
            counter=1,
        )
        await _assert_invalid_async_increments(record)
        await anyio.to_thread.run_sync(_assert_invalid_sync_increments, record)


async def _assert_invalid_async_increments(
    record: ModelEdgeRecord,
) -> None:
    """Reject string and boolean attributes through async increment APIs.

    Args:
        record: Transient model with invalid increment candidates.
    """
    with pytest.raises(DatabaseQueryError, match="numeric column"):
        await record.increment_async("name")
    with pytest.raises(DatabaseQueryError, match="numeric column"):
        await record.increment_async("is_admin")


def _assert_invalid_sync_increments(record: ModelEdgeRecord) -> None:
    """Reject string and boolean attributes through sync increment APIs.

    Args:
        record: Transient model with invalid increment candidates.
    """
    with pytest.raises(DatabaseQueryError, match="numeric column"):
        record.increment("name")
    with pytest.raises(DatabaseQueryError, match="numeric column"):
        record.increment("is_admin")


async def test_empty_upserts_and_destroy_batches_are_noops(
    application: Application,
) -> None:
    """Return zero for empty sync and async bulk model operations.

    Args:
        application: Application configured by the SQLite fixture.
    """
    async with application:
        await _create_edge_record_table()
        assert (
            await ModelEdgeRecord.upsert_async(
                [],
                unique_by=("email",),
            )
            == 0
        )
        assert await ModelEdgeRecord.destroy_async([]) == 0
        assert await anyio.to_thread.run_sync(_empty_sync_bulk_operations) == (
            0,
            0,
        )


async def _create_edge_record_table() -> None:
    """Create the typed table used by model edge-case tests.
    """  # fmt: skip
    await DB.statement_async(
        "CREATE TABLE model_edge_records ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "email TEXT NOT NULL UNIQUE, counter INTEGER NOT NULL DEFAULT 0, "
        "is_admin BOOLEAN NOT NULL DEFAULT 0, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )


def _empty_sync_bulk_operations() -> tuple[int, int]:
    """Return results from empty synchronous upsert and destroy calls.

    Returns:
        A zero count for each operation.
    """
    return (
        ModelEdgeRecord.upsert([], unique_by=("email",)),
        ModelEdgeRecord.destroy([]),
    )


def _exercise_sync_retrieval_and_creation() -> tuple[str, ...]:
    """Return names observed through synchronous Active Record helpers.

    Returns:
        Names from fallback, unique-conflict, and update-or-create paths.
    """
    initial = ModelEdgeRecord.create(
        {"name": "Ada", "email": "ada@example.test"},
    )
    assert ModelEdgeRecord.find_or_fail(initial.id).id == initial.id
    assert not ModelEdgeRecord.find_many([])

    fallback_calls: list[bool] = []
    fallback = ModelEdgeRecord.find_or(
        _MISSING_IDENTIFIER,
        lambda: _fallback_model(fallback_calls),
    )
    assert fallback_calls == [True]
    with pytest.raises(ModelNotFoundError):
        ModelEdgeRecord.find_or_fail(_MISSING_IDENTIFIER)
    with pytest.raises(ModelNotFoundError):
        ModelEdgeRecord.query().where("email", "missing").first_or_fail()
    existing = ModelEdgeRecord.first_or_new(
        {"email": "ada@example.test"},
        {"name": "Ignored"},
    )
    pending = ModelEdgeRecord.first_or_new(
        {"email": "grace@example.test"},
        {"name": "Grace"},
    )
    assert existing.id == initial.id
    assert not pending.exists

    grace = ModelEdgeRecord.first_or_create(
        {"email": "grace@example.test"},
        {"name": "Grace"},
    )
    grace_again = ModelEdgeRecord.first_or_create(
        {"email": "grace@example.test"},
        {"name": "Ignored"},
    )
    duplicate = ModelEdgeRecord.create_or_first(
        {"email": "grace@example.test"},
        {"name": "Ignored"},
    )
    assert grace.id == grace_again.id == duplicate.id
    with pytest.raises(MultipleModelsFoundError):
        ModelEdgeRecord.query().sole()

    updated = ModelEdgeRecord.update_or_create(
        {"email": "grace@example.test"},
        {"name": "Grace Hopper"},
    )
    unchanged = ModelEdgeRecord.update_or_create(
        {"email": "grace@example.test"},
        {},
    )
    inserted = ModelEdgeRecord.update_or_create(
        {"email": "katherine@example.test"},
        {"name": "Katherine Johnson"},
    )
    forced = ModelEdgeRecord.force_create(
        {
            "name": "Force created",
            "email": "forced@example.test",
            "is_admin": True,
        },
    )
    assert forced.is_admin
    assert updated.id == unchanged.id == grace.id
    assert updated.name == "Grace Hopper"
    assert inserted.exists
    return (
        initial.name,
        existing.name,
        grace.name,
        updated.name,
        inserted.name,
        forced.name,
        fallback.name,
    )


def _fallback_model(calls: list[bool]) -> ModelEdgeRecord:
    """Create one trusted fallback and record that it was invoked.

    Args:
        calls: Mutable test-owned list recording callback execution.

    Returns:
        A transient model created by the fallback callback.
    """
    calls.append(True)
    return ModelEdgeRecord(name="Fallback", email="fallback@example.test")


def _exercise_sync_soft_delete_and_increments() -> tuple[
    int,
    bool,
    bool,
    bool,
    bool,
]:
    """Exercise synchronous soft-delete and increment state transitions.

    Returns:
        Final counter and persistence outcomes for the operation sequence.
    """
    pending = ModelEdgeRecord(
        name="Counter",
        email="counter@example.test",
        counter=1,
    )
    assert pending.increment("counter", 2)
    assert pending.counter == _EXPECTED_PREPARED_VALUE
    assert pending.increment("counter")
    assert pending.decrement("counter")
    counter = ModelEdgeRecord.find_or_fail(pending.id)

    soft = ModelEdgeSoftRecord.create({"name": "soft"})
    not_restored = soft.restore()
    deleted = soft.delete()
    assert soft.trashed()
    hidden_by_default = ModelEdgeSoftRecord.query().first() is None
    restored = soft.restore()
    force_deleted = soft.force_delete()

    assert counter.increment("counter")
    return (
        counter.counter,
        deleted,
        not_restored,
        restored,
        force_deleted and hidden_by_default,
    )
