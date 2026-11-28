"""Verify synchronous ORM ownership and bounded model serialization paths.

The tests use application-owned SQLite databases and worker threads for
synchronous persistence operations.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, cast
from uuid import UUID

import anyio
import pytest
from sqlalchemy import JSON, ForeignKey, Numeric, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titanspan.database import (
    DatabaseServiceProvider,
    DatabaseTransactionOwnershipError,
    Model,
    ModelCollection,
    SoftDeletes,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_EXPECTED_REFRESHED_NAMES = ("second", "first")
_EXPECTED_CHILD_NAMES = ("second child", "first child")
_EXPECTED_COUNTER = 4
_EXPECTED_DECIMAL = "12.3400"
_EXPECTED_TOKEN = UUID("9822d89f-3a2c-44c7-9022-8539f6cc9486")


class ChangedLineParent(Model):
    """Represent a parent refreshed with its children in a sync worker.
    """  # fmt: skip

    table = "changed_line_parents"
    fillable = ("name",)
    timestamps = False

    name: Mapped[str]
    children: Mapped[list[ChangedLineChild]] = relationship(
        back_populates="parent",
    )


class ChangedLineChild(Model):
    """Represent a child that is attached by collection relationship loading.
    """  # fmt: skip

    table = "changed_line_children"
    fillable = ("parent_id", "name")
    timestamps = False

    parent_id: Mapped[int] = mapped_column(
        ForeignKey("changed_line_parents.id"),
    )
    name: Mapped[str]
    parent: Mapped[ChangedLineParent] = relationship(
        back_populates="children",
    )


class ChangedLineCounter(SoftDeletes, Model):
    """Represent a soft-deletable counter updated through model helpers.
    """  # fmt: skip

    table = "changed_line_counters"
    fillable = ("value",)
    timestamps = False

    value: Mapped[int] = mapped_column(default=0)


class ChangedLineStatus(StrEnum):
    """Represent an enum value supported by safe model serialization.
    """  # fmt: skip

    READY = "ready"


class ChangedLineSerialized(Model):
    """Represent supported scalar casts and cyclic JSON attributes.
    """  # fmt: skip

    table = "changed_line_serialized"
    fillable = ("payload", "amount", "token", "status")
    timestamps = False
    hidden = ("private_label",)
    visible = ("id", "payload", "amount", "token", "status", "label")
    appends = ("label", "private_label", "unlisted_label")

    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    token: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[ChangedLineStatus] = mapped_column(
        SAEnum(ChangedLineStatus),
    )

    @property
    def label(self) -> str:
        """Return the appended value allowed by the visible-field policy.
        """  # fmt: skip
        return "public label"

    @property
    def private_label(self) -> str:
        """Return an appended value explicitly hidden from serialization.
        """  # fmt: skip
        return "private label"

    @property
    def unlisted_label(self) -> str:
        """Return an appended value omitted by the visible-field policy.
        """  # fmt: skip
        return "unlisted label"


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with an isolated SQLite database.

    Args:
        tmp_path: Temporary application root managed by Pytest.

    Returns:
        An unopened application configured with the Database provider.
    """
    return _new_application(tmp_path)


async def test_sync_collection_refresh_and_load_respect_application_ownership(
    application: Application,
    tmp_path: Path,
) -> None:
    """Refresh and load real rows in a worker and reject another app owner.

    Args:
        application: First application that owns the loaded models.
        tmp_path: Pytest-owned root used for an independent second app.
    """
    async with application:
        await _create_collection_tables()
        first = await ChangedLineParent.create_async({"name": "first"})
        second = await ChangedLineParent.create_async({"name": "second"})
        await ChangedLineChild.create_async(
            {"parent_id": first.id, "name": "first child"},
        )
        await ChangedLineChild.create_async(
            {"parent_id": second.id, "name": "second child"},
        )
        collection = ModelCollection([second, first])
        first.name = "stale in-memory value"

        observed = await anyio.to_thread.run_sync(
            _refresh_and_load_collection,
            collection,
        )

    assert observed == (
        _EXPECTED_REFRESHED_NAMES,
        _EXPECTED_CHILD_NAMES,
        "stale in-memory value",
    )

    second_base_path = tmp_path / "second"
    (second_base_path / "routes").mkdir(parents=True)
    second_application = _new_application(second_base_path)
    async with second_application:
        await _create_collection_tables()
        await anyio.to_thread.run_sync(
            _assert_collection_owner_rejected,
            collection,
        )
        with pytest.raises(DatabaseTransactionOwnershipError):
            await collection.refresh_async()


async def test_model_collection_refreshes_existing_instances(
    application: Application,
) -> None:
    """Refresh collection members in place through sync and async APIs.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_collection_tables()
        first = await ChangedLineParent.create_async({"name": "first"})
        second = await ChangedLineParent.create_async({"name": "second"})
        collection = await ChangedLineParent.query().order_by("id").get_async()
        first_member, second_member = collection
        first_member.name = "stale first"
        second_member.name = "stale second"
        await (
            DB.table("changed_line_parents")
            .where("id", first.id)
            .update_async({"name": "async first"})
        )
        await (
            DB.table("changed_line_parents")
            .where("id", second.id)
            .update_async({"name": "async second"})
        )

        refreshed = await collection.refresh_async()

        assert refreshed is collection
        assert collection[0] is first_member
        assert collection[1] is second_member
        assert [model.name for model in collection] == [
            "async first",
            "async second",
        ]

        await (
            DB.table("changed_line_parents")
            .where("id", first.id)
            .update_async({"name": "sync first"})
        )
        await (
            DB.table("changed_line_parents")
            .where("id", second.id)
            .update_async({"name": "sync second"})
        )
        for model in collection:
            model.name = "stale sync"
        sync_values = await anyio.to_thread.run_sync(
            _refresh_collection_synchronously,
            collection,
        )

        assert sync_values == ("sync first", "sync second")
        assert collection[0] is first_member
        assert collection[1] is second_member


async def test_sync_soft_delete_counter_updates_are_scoped_to_active_rows(
    application: Application,
) -> None:
    """Keep deleted counters unchanged during synchronous atomic updates.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE changed_line_counters ("
            "id INTEGER PRIMARY KEY, value INTEGER NOT NULL, "
            "deleted_at TIMESTAMP, created_at TIMESTAMP, "
            "updated_at TIMESTAMP)"
        )
        counter = await ChangedLineCounter.create_async({"value": 2})
        observed = await anyio.to_thread.run_sync(
            _exercise_soft_delete_counter,
            counter.id,
        )

    assert observed == (True, True, False, False, _EXPECTED_COUNTER)


async def test_model_serialization_omits_cycles_and_respects_visibility(
    application: Application,
) -> None:
    """Serialize cyclic JSON values and typed scalars without hidden fields.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE changed_line_serialized ("
            "id INTEGER PRIMARY KEY, payload JSON NOT NULL, "
            "amount NUMERIC(10, 4) NOT NULL, token CHAR(32) NOT NULL, "
            "status VARCHAR(16) NOT NULL, created_at TIMESTAMP, "
            "updated_at TIMESTAMP)"
        )
        model = await ChangedLineSerialized.create_async(
            {
                "payload": {"state": "ready"},
                "amount": Decimal(_EXPECTED_DECIMAL),
                "token": _EXPECTED_TOKEN,
                "status": ChangedLineStatus.READY,
            },
        )
        loaded = await ChangedLineSerialized.find_or_fail_async(model.id)
        mapping: dict[str, object] = {"state": "ready"}
        sequence: list[object] = ["item"]
        mapping["self"] = mapping
        mapping["sequence"] = sequence
        sequence.append(sequence)
        loaded.payload = mapping

        observed = await anyio.to_thread.run_sync(
            _serialize_model_and_collection,
            loaded,
        )

    assert observed == (
        {"state": "ready", "sequence": ["item"]},
        _EXPECTED_DECIMAL,
        str(_EXPECTED_TOKEN),
        "ready",
        "public label",
        False,
        False,
    )


async def _create_collection_tables() -> None:
    """Create collection tables with an enforced SQLite foreign key.
    """  # fmt: skip
    await DB.statement_async(
        "CREATE TABLE changed_line_parents ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE changed_line_children ("
        "id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, "
        "name TEXT NOT NULL, created_at TIMESTAMP, updated_at TIMESTAMP, "
        "FOREIGN KEY (parent_id) "
        "REFERENCES changed_line_parents(id))"
    )


def _refresh_and_load_collection(
    collection: ModelCollection[ChangedLineParent],
) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """Refresh selected rows and attach their children synchronously.

    Args:
        collection: Detached, application-owned parents in reversed order.

    Returns:
        Database names, loaded child names, and retained scalar state.
    """
    refreshed = collection.fresh()
    collection.load("children")
    child_names = tuple(parent.children[0].name for parent in collection)
    return (
        tuple(parent.name for parent in refreshed),
        child_names,
        collection[1].name,
    )


def _refresh_collection_synchronously(
    collection: ModelCollection[ChangedLineParent],
) -> tuple[str, ...]:
    """Refresh a collection through the synchronous model API.

    Args:
        collection: Models whose persisted values must replace stale values.

    Returns:
        Refreshed names in collection order.
    """
    refreshed = collection.refresh()
    assert refreshed is collection
    return tuple(parent.name for parent in collection)


def _assert_collection_owner_rejected(
    collection: ModelCollection[ChangedLineParent],
) -> None:
    """Reject sync refresh and relationship loading through another app.

    Args:
        collection: Models retained from a different application service.
    """
    with pytest.raises(DatabaseTransactionOwnershipError):
        collection.fresh()
    with pytest.raises(DatabaseTransactionOwnershipError):
        collection.load("children")
    with pytest.raises(DatabaseTransactionOwnershipError):
        collection.refresh()


def _exercise_soft_delete_counter(
    identifier: int,
) -> tuple[bool, bool, bool, bool, int]:
    """Update one active counter and reject changes after soft deletion.

    Args:
        identifier: Counter key created through the async application API.

    Returns:
        Update outcomes and the value persisted before and after deletion.
    """
    counter = ChangedLineCounter.find_or_fail(identifier)
    increased = counter.increment("value", 3)
    decreased = counter.decrement("value", 1)
    assert counter.value == _EXPECTED_COUNTER
    assert counter.delete()
    increased_after_delete = counter.increment("value")
    decreased_after_delete = counter.decrement("value")
    persisted = (
        ChangedLineCounter.query()
        .with_trashed()
        .where("id", identifier)
        .first_or_fail()
    )
    return (
        increased,
        decreased,
        increased_after_delete,
        decreased_after_delete,
        persisted.value,
    )


def _serialize_model_and_collection(
    model: ChangedLineSerialized,
) -> tuple[dict[str, object], str, str, str, str, bool, bool]:
    """Return public scalar and visibility values from both serializers.

    Args:
        model: Loaded model whose JSON mapping contains mapping and list cycles.

    Returns:
        Serialized payload, typed scalar strings, enum value, visible append,
        and visibility results for the hidden and unlisted appends.
    """
    serialized = model.to_dict()
    payload = serialized["payload"]
    assert isinstance(payload, dict)
    payload = cast("dict[str, object]", payload)
    collection_json = ModelCollection([model]).to_json()
    return (
        payload,
        str(serialized["amount"]),
        str(serialized["token"]),
        str(serialized["status"]),
        str(serialized["label"]),
        "private_label" in serialized or "private label" in collection_json,
        "unlisted_label" in serialized or "unlisted label" in collection_json,
    )


def _new_application(base_path: Path) -> Application:
    """Create an application with independent named SQLite databases.

    Args:
        base_path: Application root used to resolve SQLite database paths.

    Returns:
        A lazy application with the native Database provider.
    """
    return Application(
        base_path=base_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/database.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )
