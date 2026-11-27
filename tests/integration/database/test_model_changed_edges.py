"""Exercise remaining changed ORM paths through public SQLite behavior.

The tests verify soft-delete graph visibility, collection ownership, and
successful or failed model save outcomes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import anyio
import pytest
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titanspan.database import (
    DatabaseServiceProvider,
    DatabaseTransactionError,
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
_EXPECTED_ACTIVE_CHILD = "active child"
_EXPECTED_ACTIVE_GRANDCHILD = "active grandchild"
_EXPECTED_SAVE_COUNT = 7
_EXPECTED_SYNC_BATCH_SIZE = 2


class ChangedEdgeNode(SoftDeletes, Model):
    """Represent a soft-deletable tree with a nullable self relation.
    """  # fmt: skip

    table = "changed_edge_nodes"
    fillable = ("name", "parent_id")
    timestamps = False

    name: Mapped[str]
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("changed_edge_nodes.id"),
        nullable=True,
    )
    parent: Mapped[ChangedEdgeNode | None] = relationship(
        back_populates="children",
        remote_side=lambda: [ChangedEdgeNode.id],
    )
    children: Mapped[list[ChangedEdgeNode]] = relationship(
        back_populates="parent",
    )


class ChangedEdgeOther(Model):
    """Represent a second model type rejected by collection refresh.
    """  # fmt: skip

    table = "changed_edge_other"
    fillable = ("name",)
    timestamps = False

    name: Mapped[str]


class ChangedEdgeSave(Model):
    """Represent save-helper paths constrained by real unique indexes.
    """  # fmt: skip

    table = "changed_edge_saves"
    fillable = ("name", "email", "handle")
    timestamps = False

    name: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(unique=True)
    handle: Mapped[str] = mapped_column(unique=True)


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with an isolated SQLite database.

    Args:
        tmp_path: Temporary application root managed by Pytest.

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
                        "database": "database/model_changed_edges.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_soft_delete_collection_and_eager_loads_keep_graph_scoped(
    application: Application,
) -> None:
    """Keep trashed roots available while filtering related tree rows.

    Args:
        application: Application configured with real SQLite persistence.
    """
    async with application:
        await _create_node_table()
        active_root = await ChangedEdgeNode.create_async(
            {"name": "active root"},
        )
        active_child = await ChangedEdgeNode.create_async(
            {
                "name": _EXPECTED_ACTIVE_CHILD,
                "parent_id": active_root.id,
            },
        )
        await ChangedEdgeNode.create_async(
            {
                "name": _EXPECTED_ACTIVE_GRANDCHILD,
                "parent_id": active_child.id,
            },
        )
        deleted_root = await ChangedEdgeNode.create_async(
            {"name": "deleted root"},
        )
        await ChangedEdgeNode.create_async(
            {"name": "visible child", "parent_id": deleted_root.id},
        )
        hidden_child = await ChangedEdgeNode.create_async(
            {"name": "deleted child", "parent_id": deleted_root.id},
        )
        await hidden_child.delete_async()
        await deleted_root.delete_async()

        eager = await (
            ChangedEdgeNode.query()
            .where("id", active_root.id)
            .with_("parent", "children.parent", "children.children")
            .first_or_fail_async()
        )
        serialized = eager.to_dict()
        eager_children = cast("list[object]", serialized["children"])
        eager_child = cast("dict[str, object]", eager_children[0])

        deleted = (
            await ChangedEdgeNode.query()
            .with_trashed()
            .where(
                "id",
                deleted_root.id,
            )
            .first_or_fail_async()
        )
        collection = ModelCollection([deleted])
        observed = await anyio.to_thread.run_sync(
            _refresh_soft_collection,
            collection,
        )

        mixed = ModelCollection(
            [deleted, ChangedEdgeOther(name="unpersisted other model")],
        )
        with pytest.raises(DatabaseTransactionOwnershipError):
            await anyio.to_thread.run_sync(mixed.fresh)

    assert eager_child["name"] == _EXPECTED_ACTIVE_CHILD
    assert "parent" not in eager_child
    assert observed == (deleted_root.id, ("visible child",))


async def test_model_save_helpers_report_success_and_unrelated_conflicts(
    application: Application,
) -> None:
    """Return only persisted models and preserve unrelated uniqueness errors.

    Args:
        application: Application configured with real SQLite persistence.
    """
    async with application:
        await _create_save_table()
        saved_async = ChangedEdgeSave(
            name="async save",
            email="async@example.test",
            handle="async-handle",
        )
        assert await saved_async.save_or_fail_async()
        forced_async = await ChangedEdgeSave.force_create_async(
            {
                "name": "forced async",
                "email": "forced-async@example.test",
                "handle": "forced-async-handle",
            },
        )
        batch_async = await ChangedEdgeSave.create_many_async(
            [
                {
                    "name": "batch async",
                    "email": "batch-async@example.test",
                    "handle": "batch-async-handle",
                },
            ],
        )
        await ChangedEdgeSave.update_or_create_async(
            {"email": "async@example.test"},
            {},
        )
        with pytest.raises(DatabaseTransactionError):
            await ChangedEdgeSave.create_or_first_async(
                {"email": "missing-name@example.test"},
            )
        with pytest.raises(DatabaseTransactionError):
            await ChangedEdgeSave.create_or_first_async(
                {"email": "new-email@example.test"},
                {
                    "name": "conflicting handle",
                    "handle": "async-handle",
                },
            )

        observed = await anyio.to_thread.run_sync(_exercise_sync_save_paths)
        row_count = await DB.table("changed_edge_saves").count_async()

    assert forced_async.exists
    assert len(batch_async) == 1
    assert observed[0]
    assert observed[1] == _EXPECTED_SYNC_BATCH_SIZE
    assert observed[2] > 0
    assert observed[3]
    assert row_count == _EXPECTED_SAVE_COUNT


async def _create_node_table() -> None:
    """Create one self-referencing soft-delete table in SQLite.
    """  # fmt: skip
    await DB.statement_async(
        "CREATE TABLE changed_edge_nodes ("
        "id INTEGER PRIMARY KEY, parent_id INTEGER NULL, "
        "name TEXT NOT NULL, deleted_at TIMESTAMP, "
        "created_at TIMESTAMP, updated_at TIMESTAMP, "
        "FOREIGN KEY (parent_id) REFERENCES changed_edge_nodes(id))"
    )


async def _create_save_table() -> None:
    """Create save-helper columns and independent unique constraints.
    """  # fmt: skip
    await DB.statement_async(
        "CREATE TABLE changed_edge_saves ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "email TEXT NOT NULL UNIQUE, handle TEXT NOT NULL UNIQUE, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )


def _refresh_soft_collection(
    collection: ModelCollection[ChangedEdgeNode],
) -> tuple[int, tuple[str, ...]]:
    """Refresh a deleted root and load only its active children.

    Args:
        collection: Persisted deleted root retained from an ORM query.

    Returns:
        The fresh root key and loaded active child names.
    """
    fresh = collection.fresh()
    collection.load("children")
    return (
        fresh[0].id,
        tuple(child.name for child in collection[0].children),
    )


def _exercise_sync_save_paths() -> tuple[bool, int, int, bool]:
    """Verify synchronous success and failure paths using real constraints.

    Returns:
        Save success, batch size, preserved update count, and error handling.
    """
    saved = ChangedEdgeSave(
        name="sync save",
        email="sync@example.test",
        handle="sync-handle",
    )
    save_succeeded = saved.save_or_fail()
    forced = ChangedEdgeSave.force_create(
        {
            "name": "forced sync",
            "email": "forced-sync@example.test",
            "handle": "forced-sync-handle",
        },
    )
    batch = ChangedEdgeSave.create_many(
        [
            {
                "name": "batch one",
                "email": "batch-one@example.test",
                "handle": "batch-one-handle",
            },
            {
                "name": "batch two",
                "email": "batch-two@example.test",
                "handle": "batch-two-handle",
            },
        ],
    )
    ChangedEdgeSave.update_or_create({"email": saved.email}, {})
    with pytest.raises(DatabaseTransactionError):
        ChangedEdgeSave.create_or_first(
            {"email": "sync-missing-name@example.test"},
        )
    with pytest.raises(DatabaseTransactionError):
        ChangedEdgeSave.create_or_first(
            {"email": "sync-new-email@example.test"},
            {"name": "conflicting handle", "handle": "sync-handle"},
        )
    return save_succeeded, len(batch), saved.id, forced.exists
