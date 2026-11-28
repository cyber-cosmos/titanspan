"""Verify one-of-many model relationships through the real ORM loader.

The tests select one related row per parent using isolated SQLite storage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import (
    DatabaseServiceProvider,
    Model,
    latest_of_many,
    of_many,
    oldest_of_many,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


class _OneOfManyChild(Model):
    """Represent a sortable child row related to one parent.

    Scores and identifiers verify aggregate selection and tie-breaking.
    """

    table = "database_one_of_many_children"
    fillable = ("parent_id", "parent_slug", "label", "score")

    parent_id: Mapped[int] = mapped_column(
        ForeignKey("database_one_of_many_parents.id"),
    )
    parent_slug: Mapped[str] = mapped_column(
        ForeignKey("database_one_of_many_parents.slug"),
    )
    label: Mapped[str]
    score: Mapped[int | None]
    _titanspan_one_of_many_rank: Mapped[int | None]


class _OneOfManyParent(Model):
    """Represent parents with several read-only one-of-many views.

    Each relation selects at most one child for its own aggregate ordering.
    """

    table = "database_one_of_many_parents"
    fillable = ("name", "slug")

    name: Mapped[str]
    slug: Mapped[str] = mapped_column(unique=True)
    latest_child: Mapped[_OneOfManyChild | None] = latest_of_many(
        _OneOfManyChild,
        "parent_id",
    )
    oldest_child: Mapped[_OneOfManyChild | None] = oldest_of_many(
        _OneOfManyChild,
        "parent_id",
    )
    highest_scored_child: Mapped[_OneOfManyChild | None] = of_many(
        _OneOfManyChild,
        "parent_id",
        aggregates={"score": "max", "label": "min"},
    )
    highest_scored_child_by_slug: Mapped[_OneOfManyChild | None] = (
        latest_of_many(
            _OneOfManyChild,
            "parent_slug",
            column="score",
            owner_key="slug",
        )
    )
    latest_child_by_score_and_label: Mapped[_OneOfManyChild | None] = (
        latest_of_many(
            _OneOfManyChild,
            "parent_id",
            column=("score", "label"),
        )
    )
    oldest_scored_child: Mapped[_OneOfManyChild | None] = oldest_of_many(
        _OneOfManyChild,
        "parent_id",
        column="score",
    )
    default_of_many_child: Mapped[_OneOfManyChild | None] = of_many(
        _OneOfManyChild,
        "parent_id",
    )


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with an isolated SQLite database.

    Args:
        tmp_path: Temporary application root managed by Pytest.

    Returns:
        An unopened application with the native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/one_of_many.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_one_of_many_relationships_select_deterministic_rows(
    application: Application,
) -> None:
    """Load max, min, and custom aggregate rows for multiple parents.

    Args:
        application: Isolated SQLite application for the test.
    """
    async with application:
        await _create_schema()
        populated = await _OneOfManyParent.create_async(
            {"name": "Populated", "slug": "populated"},
        )
        other = await _OneOfManyParent.create_async(
            {"name": "Other", "slug": "other"},
        )
        await _OneOfManyParent.create_async({"name": "Empty", "slug": "empty"})
        unscored = await _OneOfManyParent.create_async(
            {"name": "Unscored", "slug": "unscored"},
        )

        first = await _OneOfManyChild.create_async(
            {
                "parent_id": populated.id,
                "parent_slug": populated.slug,
                "label": "First",
                "score": 20,
            },
        )
        await _OneOfManyChild.create_async(
            {
                "parent_id": populated.id,
                "parent_slug": populated.slug,
                "label": "Middle",
                "score": 35,
            },
        )
        best = await _OneOfManyChild.create_async(
            {
                "parent_id": populated.id,
                "parent_slug": populated.slug,
                "label": "Best",
                "score": 35,
            },
        )
        other_latest = await _OneOfManyChild.create_async(
            {
                "parent_id": other.id,
                "parent_slug": other.slug,
                "label": "Other",
                "score": 5,
            },
        )
        null_score = await _OneOfManyChild.create_async(
            {
                "parent_id": unscored.id,
                "parent_slug": unscored.slug,
                "label": "Null score",
                "score": None,
            },
        )

        parents = await (
            _OneOfManyParent.query()
            .with_(
                "latest_child",
                "oldest_child",
                "highest_scored_child",
                "highest_scored_child_by_slug",
                "latest_child_by_score_and_label",
                "oldest_scored_child",
                "default_of_many_child",
            )
            .order_by("id")
            .get_async()
        )

        assert parents[0].latest_child is not None
        assert parents[0].latest_child.id == best.id
        assert parents[0].oldest_child is not None
        assert parents[0].oldest_child.id == first.id
        assert parents[0].highest_scored_child is not None
        assert parents[0].highest_scored_child.id == best.id
        assert parents[0].highest_scored_child_by_slug is not None
        assert parents[0].highest_scored_child_by_slug.id == best.id
        assert parents[0].latest_child_by_score_and_label is not None
        assert parents[0].latest_child_by_score_and_label.label == "Middle"
        assert parents[0].oldest_scored_child is not None
        assert parents[0].oldest_scored_child.id == first.id
        assert parents[0].default_of_many_child is not None
        assert parents[0].default_of_many_child.id == best.id
        assert parents[1].latest_child is not None
        assert parents[1].latest_child.id == other_latest.id
        assert parents[1].oldest_child is not None
        assert parents[1].oldest_child.id == other_latest.id
        assert parents[1].highest_scored_child is not None
        assert parents[1].highest_scored_child.id == other_latest.id
        assert parents[2].latest_child is None
        assert parents[2].oldest_child is None
        assert parents[2].highest_scored_child is None
        assert parents[3].latest_child is not None
        assert parents[3].latest_child.id == null_score.id
        assert parents[3].highest_scored_child is None
        assert parents[3].oldest_scored_child is None

        sync_parent = await anyio.to_thread.run_sync(
            _load_sync_parent,
            populated.id,
        )
        assert sync_parent.latest_child is not None
        assert sync_parent.latest_child.id == best.id
        assert sync_parent.highest_scored_child is not None
        assert sync_parent.highest_scored_child.id == best.id


def _load_sync_parent(identifier: int) -> _OneOfManyParent:
    """Load one parent and one-of-many relations through the sync API.

    Args:
        identifier: Persisted parent identifier selected by the async test.

    Returns:
        A parent with both selected related rows eagerly loaded.
    """
    return (
        _OneOfManyParent.query()
        .with_("latest_child", "highest_scored_child")
        .where("id", identifier)
        .first_or_fail()
    )


async def _create_schema() -> None:
    """Create parent and child tables with a real foreign-key constraint.

    The mapper uses this link to establish the one-of-many owner join.
    """
    await DB.statement_async(
        "CREATE TABLE database_one_of_many_parents ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "slug TEXT NOT NULL UNIQUE, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE database_one_of_many_children ("
        "id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, "
        "parent_slug TEXT NOT NULL, label TEXT NOT NULL, score INTEGER, "
        "_titanspan_one_of_many_rank INTEGER, "
        "created_at TIMESTAMP, updated_at TIMESTAMP, "
        "FOREIGN KEY(parent_id) "
        "REFERENCES database_one_of_many_parents(id), "
        "FOREIGN KEY(parent_slug) "
        "REFERENCES database_one_of_many_parents(slug))"
    )
