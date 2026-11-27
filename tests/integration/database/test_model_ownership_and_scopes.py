"""Verify model ownership and soft-delete scopes across ORM loads.

These tests use real SQLAlchemy sessions and isolated application databases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titanspan.database import (
    DatabaseServiceProvider,
    DatabaseTransactionOwnershipError,
    Model,
    ModelCollection,
    SoftDeletes,
    assert_model_exists_async,
    has_many,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_EXPECTED_VISIBLE_CHILDREN = 1
_EXPECTED_VISIBLE_NESTED = 1
_EXPECTED_TWO_MODEL_IDENTITIES = 2
_EXPECTED_TWO_MATCHING_PARENTS = 2


class OwnedChild(Model):
    """Represent a child used to verify eager graph ownership.
    """  # fmt: skip

    table = "ownership_children"
    fillable = ("parent_id", "name")

    parent_id: Mapped[int] = mapped_column(
        ForeignKey("ownership_parents.id"),
    )
    name: Mapped[str]
    parent: Mapped[OwnedParent] = relationship(back_populates="children")


class OwnedParent(Model):
    """Represent an owner-scoped model with mapped children.
    """  # fmt: skip

    table = "ownership_parents"
    fillable = ("name",)

    name: Mapped[str]
    children: Mapped[list[OwnedChild]] = has_many(
        OwnedChild,
        back_populates="parent",
    )


class AnalyticsRecord(Model):
    """Represent a model explicitly bound to a named connection.
    """  # fmt: skip

    table = "ownership_analytics"
    connection = "analytics"
    fillable = ("name",)

    name: Mapped[str]


class ScopedGrandchild(SoftDeletes, Model):
    """Represent a soft-deletable nested relationship target.
    """  # fmt: skip

    table = "scope_grandchildren"
    fillable = ("child_id", "name")

    child_id: Mapped[int] = mapped_column(
        ForeignKey("scope_children.id"),
    )
    name: Mapped[str]
    child: Mapped[ScopedChild] = relationship(
        back_populates="grandchildren",
    )


class ScopedChild(SoftDeletes, Model):
    """Represent a soft-deletable child and nested relationship.
    """  # fmt: skip

    table = "scope_children"
    fillable = ("parent_id", "name")

    parent_id: Mapped[int] = mapped_column(ForeignKey("scope_parents.id"))
    name: Mapped[str]
    parent: Mapped[ScopedParent] = relationship(back_populates="children")
    grandchildren: Mapped[list[ScopedGrandchild]] = has_many(
        ScopedGrandchild,
        back_populates="child",
    )


class ScopedParent(SoftDeletes, Model):
    """Represent a soft-deletable parent with nested relationships.
    """  # fmt: skip

    table = "scope_parents"
    fillable = ("name",)

    name: Mapped[str]
    children: Mapped[list[ScopedChild]] = has_many(
        ScopedChild,
        back_populates="parent",
    )


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an isolated app-owned SQLite database.

    Args:
        tmp_path: Pytest-owned temporary directory.

    Returns:
        An application configured with the native Database provider.
    """
    return _new_application(tmp_path)


async def test_collections_and_related_models_keep_application_ownership(
    application: Application,
    tmp_path: Path,
) -> None:
    """Reject cross-app collection reads and distinguish matching keys.

    Args:
        application: First application that loads the parent graph.
        tmp_path: Temporary location for the independent second app.
    """
    async with application:
        await _create_ownership_tables()
        parent = await OwnedParent.create_async({"name": "first app"})
        await OwnedChild.create_async(
            {"parent_id": parent.id, "name": "first child"},
        )
        first_collection = await (
            OwnedParent.query().with_("children").get_async()
        )
        await DB.connection("analytics").statement_async(
            "CREATE TABLE ownership_analytics ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        analytics_record = await AnalyticsRecord.create_async(
            {"name": "first analytics"},
        )
        analytics_collection = await AnalyticsRecord.query().get_async()

    second_base_path = tmp_path / "second"
    (second_base_path / "routes").mkdir(parents=True)
    second_application = _new_application(second_base_path)
    async with second_application:
        await _create_ownership_tables()
        second_parent = await OwnedParent.create_async(
            {"name": "second app"},
        )
        await OwnedChild.create_async(
            {"parent_id": second_parent.id, "name": "second child"},
        )
        second_collection = ModelCollection([second_parent])
        await DB.connection("analytics").statement_async(
            "CREATE TABLE ownership_analytics ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        second_analytics = await AnalyticsRecord.create_async(
            {"name": "second analytics"},
        )

        assert parent.id == second_parent.id
        assert analytics_record.id == second_analytics.id
        assert not second_collection.contains(parent)
        assert second_collection.find(parent) is None
        assert (
            len(ModelCollection([parent, second_parent]).unique())
            == _EXPECTED_TWO_MODEL_IDENTITIES
        )
        assert not ModelCollection([second_analytics]).contains(
            analytics_record
        )

        with pytest.raises(DatabaseTransactionOwnershipError):
            await first_collection.fresh_async()
        with pytest.raises(DatabaseTransactionOwnershipError):
            await first_collection.load_async("children")
        with pytest.raises(DatabaseTransactionOwnershipError):
            await first_collection[0].children[0].save_async()
        with pytest.raises(DatabaseTransactionOwnershipError):
            await assert_model_exists_async(parent)
        with pytest.raises(DatabaseTransactionOwnershipError):
            await analytics_collection.fresh_async()


async def test_soft_delete_visibility_applies_to_nested_orm_loads(
    application: Application,
) -> None:
    """Filter deleted models in eager, lazy collection, and existence paths.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_soft_delete_tables()
        active_parent = await ScopedParent.create_async(
            {"name": "active parent"},
        )
        deleted_parent = await ScopedParent.create_async(
            {"name": "deleted parent"},
        )
        await deleted_parent.delete_async()
        hidden_parent = await ScopedParent.create_async(
            {"name": "active parent with only deleted children"},
        )

        active_child = await ScopedChild.create_async(
            {"parent_id": active_parent.id, "name": "active child"},
        )
        deleted_child = await ScopedChild.create_async(
            {"parent_id": active_parent.id, "name": "deleted child"},
        )
        await deleted_child.delete_async()
        hidden_only_child = await ScopedChild.create_async(
            {"parent_id": hidden_parent.id, "name": "hidden child"},
        )
        await hidden_only_child.delete_async()
        deleted_parent_child = await ScopedChild.create_async(
            {"parent_id": deleted_parent.id, "name": "deleted parent child"},
        )
        await deleted_parent_child.delete_async()

        active_nested = await ScopedGrandchild.create_async(
            {"child_id": active_child.id, "name": "active nested"},
        )
        deleted_nested = await ScopedGrandchild.create_async(
            {"child_id": active_child.id, "name": "deleted nested"},
        )
        await deleted_nested.delete_async()
        await ScopedGrandchild.create_async(
            {"child_id": hidden_only_child.id, "name": "hidden nested"},
        )

        eager = await (
            ScopedParent.query().with_("children.grandchildren").get_async()
        )
        eager_by_id = {model.id: model for model in eager}
        assert set(eager_by_id) == {active_parent.id, hidden_parent.id}
        active_loaded = eager_by_id[active_parent.id]
        assert len(active_loaded.children) == _EXPECTED_VISIBLE_CHILDREN
        assert active_loaded.children[0].id == active_child.id
        assert (
            len(active_loaded.children[0].grandchildren)
            == _EXPECTED_VISIBLE_NESTED
        )
        assert active_loaded.children[0].grandchildren[0].id == active_nested.id
        assert active_loaded.to_dict()["children"]
        assert eager_by_id[hidden_parent.id].children == []

        included_parent = await (
            ScopedParent.query()
            .with_trashed()
            .with_("children.grandchildren")
            .where("id", deleted_parent.id)
            .first_async()
        )
        assert included_parent is not None
        assert included_parent.id == deleted_parent.id
        assert included_parent.children == []

        loaded = await ScopedParent.query().with_trashed().get_async()
        await loaded.load_async("children.grandchildren")
        loaded_by_id = {model.id: model for model in loaded}
        active_loaded = loaded_by_id[active_parent.id]
        assert active_loaded.children[0].id == active_child.id
        assert [
            model.id for model in active_loaded.children[0].grandchildren
        ] == [
            active_nested.id,
        ]
        assert loaded_by_id[hidden_parent.id].children == []
        assert loaded_by_id[deleted_parent.id].children == []
        refreshed = await loaded.fresh_async()
        assert {model.id for model in refreshed} == {
            active_parent.id,
            hidden_parent.id,
            deleted_parent.id,
        }

        assert await ScopedParent.query().has("children").count_async() == 1
        assert (
            await ScopedParent.query()
            .where_has("children.grandchildren")
            .count_async()
            == 1
        )
        assert (
            await ScopedParent.query()
            .where_has("children", lambda query: query.with_trashed())
            .count_async()
            == _EXPECTED_TWO_MATCHING_PARENTS
        )
        assert (
            await ScopedParent.query()
            .with_trashed()
            .where_has("children")
            .count_async()
            == 1
        )

        explicitly_included = await (
            ScopedChild.query()
            .with_trashed()
            .where("id", deleted_child.id)
            .first_async()
        )
        assert explicitly_included is not None
        assert explicitly_included.id == deleted_child.id


async def _create_ownership_tables() -> None:
    """Create ownership parent and child tables in the active app.
    """  # fmt: skip
    await DB.statement_async(
        "CREATE TABLE ownership_parents ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE ownership_children ("
        "id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, "
        "name TEXT NOT NULL, created_at TIMESTAMP, updated_at TIMESTAMP, "
        "FOREIGN KEY (parent_id) REFERENCES ownership_parents(id))"
    )


async def _create_soft_delete_tables() -> None:
    """Create the three soft-delete tables in the active app.
    """  # fmt: skip
    await DB.statement_async(
        "CREATE TABLE scope_parents ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, deleted_at TIMESTAMP, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE scope_children ("
        "id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, "
        "name TEXT NOT NULL, deleted_at TIMESTAMP, "
        "created_at TIMESTAMP, updated_at TIMESTAMP, "
        "FOREIGN KEY (parent_id) REFERENCES scope_parents(id))"
    )
    await DB.statement_async(
        "CREATE TABLE scope_grandchildren ("
        "id INTEGER PRIMARY KEY, child_id INTEGER NOT NULL, "
        "name TEXT NOT NULL, deleted_at TIMESTAMP, "
        "created_at TIMESTAMP, updated_at TIMESTAMP, "
        "FOREIGN KEY (child_id) REFERENCES scope_children(id))"
    )


def _new_application(base_path: Path) -> Application:
    """Construct an app with a fresh, named SQLite file.

    Args:
        base_path: Application root for this independent database.

    Returns:
        A lazy application with one Database manager.
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
                    "analytics": {
                        "driver": "sqlite",
                        "database": "database/analytics.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )
