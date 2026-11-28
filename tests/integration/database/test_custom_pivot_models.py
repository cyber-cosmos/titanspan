"""Verify relation-manager mutations through mapped pivot models.

The integration cases use SQLAlchemy association proxies and real SQLite
transactions so custom pivot state remains under ORM ownership.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy import ForeignKey, String
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titanspan.database import (
    DatabaseQueryError,
    DatabaseServiceProvider,
    Model,
    ModelPersistenceCancelledError,
    RelationshipChanges,
)
from titanspan.database.events import ModelCreating, ModelUpdating
from titanspan.facades.database import DB
from titanspan.facades.event import Event
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


class _CustomPivotTag(Model):
    """Represent a related row attached through a custom pivot model.

    The owner relationship is available through the mapped pivot model.
    """

    table = "custom_pivot_tags"
    fillable = ("name",)

    name: Mapped[str] = mapped_column(String(80))
    memberships: Mapped[list[_CustomPivotMembership]] = relationship(
        back_populates="tag",
    )


class _CustomPivotMembership(Model):
    """Represent custom pivot attributes with normal model timestamps.

    The timestamps are assigned by the ordinary Model save lifecycle.
    """

    table = "custom_pivot_memberships"
    fillable = ("owner_id", "tag_id", "role")

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("custom_pivot_owners.id"),
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("custom_pivot_tags.id"),
    )
    role: Mapped[str] = mapped_column(String(80), default="member")
    owner: Mapped[_CustomPivotOwner] = relationship(
        back_populates="memberships",
    )
    tag: Mapped[_CustomPivotTag] = relationship(
        back_populates="memberships",
    )


def _membership_for_tag(
    tag: _CustomPivotTag,
) -> _CustomPivotMembership:
    """Create the association object used by the public proxy.

    Args:
        tag: Related model assigned through the association proxy.

    Returns:
        A transient pivot model linking the tag.
    """
    return _CustomPivotMembership(tag=tag)


def _cancel_custom_pivot_creation(
    event: ModelCreating[_CustomPivotMembership],
) -> None:
    """Reject a custom pivot insert through the Model lifecycle event.

    Args:
        event: Event emitted before the association model is persisted.
    """
    event.cancel()


def _cancel_custom_pivot_update(
    event: ModelUpdating[_CustomPivotMembership],
) -> None:
    """Reject a custom pivot update through the Model lifecycle event.

    Args:
        event: Event emitted before the association model is updated.
    """
    event.cancel()


@pytest.mark.parametrize(
    ("attribute", "invalid_value"),
    [("save_async", None), ("created_at_name", None)],
)
def test_relation_rejects_invalid_custom_pivot_contract(
    attribute: str,
    invalid_value: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a mapped association model with invalid Model lifecycle data.

    Args:
        attribute: Required association-model attribute to invalidate.
        invalid_value: Value that violates the model contract.
        monkeypatch: Fixture that restores the class metadata after the test.
    """
    monkeypatch.setattr(
        _CustomPivotMembership,
        attribute,
        invalid_value,
    )
    owner = _CustomPivotOwner(name="Owner")
    with pytest.raises(DatabaseQueryError, match="writable many-to-many"):
        owner.relation("tags")


class _CustomPivotOwner(Model):
    """Represent a parent whose tags use a mapped association object.

    The association proxy exposes related models to application code.
    """

    table = "custom_pivot_owners"
    fillable = ("name",)

    name: Mapped[str] = mapped_column(String(80))
    memberships: Mapped[list[_CustomPivotMembership]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    tags: AssociationProxy[list[_CustomPivotTag]] = association_proxy(
        "memberships",
        "tag",
        creator=_membership_for_tag,
    )
    roles: AssociationProxy[list[str]] = association_proxy(
        "memberships",
        "role",
    )
    unmapped_tags: AssociationProxy[list[_CustomPivotTag]] = association_proxy(
        "missing_memberships",
        "tag",
    )


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an isolated SQLite application with native Database support.

    Args:
        tmp_path: Temporary application directory supplied by Pytest.

    Returns:
        An unopened application configured for this integration test.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/custom_pivots.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_async_many_to_many_operations_preserve_custom_pivot_models(
    application: Application,
) -> None:
    """Attach, synchronize, and detach through mapped pivot instances.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        owner = await _CustomPivotOwner.create_async({"name": "Async"})
        first = await _CustomPivotTag.create_async({"name": "first"})
        second = await _CustomPivotTag.create_async({"name": "second"})
        third = await _CustomPivotTag.create_async({"name": "third"})
        cancelled = await _CustomPivotTag.create_async(
            {"name": "cancelled"},
        )
        relation = owner.relation("tags")
        with pytest.raises(DatabaseQueryError, match="writable many-to-many"):
            owner.relation("roles")
        with pytest.raises(DatabaseQueryError, match="writable many-to-many"):
            owner.relation("unmapped_tags")

        async with DB.transaction_async():
            assert await relation.attach_async(
                {
                    first.id: {"role": "editor"},
                    second.id: {"role": "viewer"},
                },
            ) == (first.id, second.id)
            assert (
                await relation.attach_async(
                    {first.id: {"role": "ignored"}},
                )
                == ()
            )

            changes = await relation.sync_async(
                {
                    first.id: {"role": "owner"},
                    third.id: {"role": "guest"},
                },
            )
            assert changes == RelationshipChanges(
                attached=(third.id,),
                detached=(second.id,),
                updated=(first.id,),
            )
            assert (
                await relation.update_existing_pivot_async(
                    first.id,
                    {"role": "maintainer"},
                )
                == 1
            )
            with pytest.raises(DatabaseQueryError, match="non-key association"):
                await relation.update_existing_pivot_async(first.id, {})
            with pytest.raises(
                DatabaseQueryError,
                match="non-key association",
            ):
                await relation.update_existing_pivot_async(
                    first.id,
                    {"tag_id": second.id},
                )
            assert await relation.detach_async(third.id) == (third.id,)
            assert (
                await relation.update_existing_pivot_async(
                    second.id,
                    {"role": "ignored"},
                )
                == 0
            )

        with (
            Event.listen(ModelCreating, _cancel_custom_pivot_creation),
            pytest.raises(ModelPersistenceCancelledError),
        ):
            await relation.attach_async({cancelled.id: {"role": "blocked"}})
        with (
            Event.listen(ModelUpdating, _cancel_custom_pivot_update),
            pytest.raises(ModelPersistenceCancelledError),
        ):
            await relation.update_existing_pivot_async(
                first.id,
                {"role": "blocked"},
            )

        rows = await DB.table("custom_pivot_memberships").get_async()
        assert len(rows) == 1
        assert rows[0]["role"] == "maintainer"
        pivot = await _CustomPivotMembership.query().first_async()
        assert pivot is not None
        assert pivot.created_at is not None
        assert pivot.updated_at is not None
        assert [tag.id for tag in owner.tags] == [first.id]
        assert owner.memberships[0].owner is owner
        assert owner.memberships[0].role == "maintainer"


async def test_sync_many_to_many_operations_preserve_custom_pivot_models(
    application: Application,
) -> None:
    """Exercise custom pivot mutations through the sync ORM interface.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        owner = await _CustomPivotOwner.create_async({"name": "Sync"})
        tag = await _CustomPivotTag.create_async({"name": "shared"})
        cancelled = await _CustomPivotTag.create_async(
            {"name": "cancelled"},
        )

        def mutate_sync_pivot() -> tuple[RelationshipChanges, int]:
            """Attach and update one custom pivot in synchronous sessions.

            Returns:
                Synchronization changes and the updated row count.
            """
            with DB.transaction():
                relation = owner.relation("tags")
                changes = relation.sync(tag.id)
                updated = relation.update_existing_pivot(
                    tag.id,
                    {"role": "admin"},
                )
                with pytest.raises(
                    DatabaseQueryError,
                    match="non-key association",
                ):
                    relation.update_existing_pivot(tag.id, {})
                assert relation.detach(tag.id) == (tag.id,)
                assert (
                    relation.update_existing_pivot(
                        tag.id,
                        {"role": "missing"},
                    )
                    == 0
                )
                assert relation.attach(tag.id) == (tag.id,)
                assert (
                    relation.update_existing_pivot(
                        tag.id,
                        {"role": "admin"},
                    )
                    == 1
                )
            return changes, updated

        def reject_cancelled_pivot() -> None:
            """Verify event cancellation rolls back a sync pivot insert.

            Returns:
                None.
            """
            with (
                Event.listen(ModelCreating, _cancel_custom_pivot_creation),
                pytest.raises(ModelPersistenceCancelledError),
            ):
                owner.relation("tags").attach(cancelled.id)

        def reject_cancelled_pivot_update() -> None:
            """Verify a cancelled update leaves persisted pivot values intact.

            Returns:
                None.
            """
            with (
                Event.listen(ModelUpdating, _cancel_custom_pivot_update),
                pytest.raises(ModelPersistenceCancelledError),
            ):
                owner.relation("tags").update_existing_pivot(
                    tag.id,
                    {"role": "blocked"},
                )

        changes, updated = await anyio.to_thread.run_sync(mutate_sync_pivot)
        await anyio.to_thread.run_sync(reject_cancelled_pivot)
        await anyio.to_thread.run_sync(reject_cancelled_pivot_update)
        assert changes == RelationshipChanges(attached=(tag.id,))
        assert updated == 1
        assert [related.id for related in owner.tags] == [tag.id]
        assert owner.memberships[0].role == "admin"
        pivot = await _CustomPivotMembership.query().first_async()
        assert pivot is not None
        assert pivot.role == "admin"


async def _create_schema() -> None:
    """Create the parent, target, and custom pivot tables.

    The pivot table has real foreign keys and a unique endpoint pair.
    """
    await DB.statement_async(
        "CREATE TABLE custom_pivot_owners ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE custom_pivot_tags ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE custom_pivot_memberships ("
        "id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, "
        "tag_id INTEGER NOT NULL, role TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP, "
        "UNIQUE(owner_id, tag_id), "
        "FOREIGN KEY(owner_id) REFERENCES custom_pivot_owners(id), "
        "FOREIGN KEY(tag_id) REFERENCES custom_pivot_tags(id))"
    )
