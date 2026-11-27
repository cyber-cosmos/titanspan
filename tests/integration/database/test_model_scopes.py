"""Verify reusable model scopes apply to root and related queries.

The integration tests use real SQLite predicates and SQLAlchemy relationships.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import anyio
import pytest
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titanspan.database import (
    DatabaseServiceProvider,
    Model,
    ModelQueryBuilder,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from sqlalchemy.sql.elements import ColumnElement

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_DEFAULT_SCOPE_COUNT = 1
_ACTIVE_SCOPE_REMOVED_COUNT = 2
_ALL_SCOPES_REMOVED_COUNT = 4
_TENANT_TWO_SCOPE_COUNT = 2
_SCOPED_POST_COUNT = 1
_POST_COUNT = 2


class ScopedRecord(Model):
    """Represent rows filtered by named class-level scope expressions.

    The table includes overlapping tenant and active-state cases for scope
    removal and local scope composition.
    """

    table = "scope_records"
    fillable = ("name", "active", "tenant_id")
    global_scopes: ClassVar[
        Mapping[str, Callable[[], ColumnElement[bool]]]
    ] = {}

    name: Mapped[str]
    active: Mapped[bool]
    tenant_id: Mapped[int]


class ScopedPost(Model):
    """Represent parent rows with globally filtered comments."""

    table = "scope_posts"
    fillable = ("name",)

    name: Mapped[str]
    comments: Mapped[list[ScopedComment]] = relationship(
        back_populates="post",
    )


class ScopedComment(Model):
    """Represent comments whose visibility is enforced by a global scope."""

    table = "scope_comments"
    fillable = ("post_id", "is_public", "body")
    global_scopes: ClassVar[
        Mapping[str, Callable[[], ColumnElement[bool]]]
    ] = {}

    post_id: Mapped[int] = mapped_column(ForeignKey("scope_posts.id"))
    is_public: Mapped[bool]
    body: Mapped[str]
    post: Mapped[ScopedPost] = relationship(back_populates="comments")


def _active_scope() -> ColumnElement[bool]:
    """Return the active-row predicate for the scoped record model."""
    return ScopedRecord.active.is_(True)


def _tenant_scope() -> ColumnElement[bool]:
    """Return the default tenant predicate for scoped records."""
    return ScopedRecord.tenant_id == 1


def _visible_comment_scope() -> ColumnElement[bool]:
    """Return the visibility predicate for related comment queries."""
    return ScopedComment.is_public.is_(True)


ScopedRecord.global_scopes = {
    "active": _active_scope,
    "tenant": _tenant_scope,
}
ScopedComment.global_scopes = {"visible": _visible_comment_scope}


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
                        "database": "database/model_scopes.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_named_global_scopes_compose_and_can_be_removed(
    application: Application,
) -> None:
    """Apply named class scopes and retain explicit local transformations.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_scope_tables()
        await DB.table("scope_records").insert_many_async(
            [
                {"name": "one", "active": True, "tenant_id": 1},
                {"name": "two", "active": False, "tenant_id": 1},
                {"name": "three", "active": True, "tenant_id": 2},
                {"name": "four", "active": False, "tenant_id": 2},
            ],
        )

        root_query = ScopedRecord.query()
        assert await root_query.count_async() == _DEFAULT_SCOPE_COUNT
        assert (
            await root_query.clone()
            .without_global_scope("active")
            .count_async()
            == _ACTIVE_SCOPE_REMOVED_COUNT
        )
        assert await root_query.count_async() == _DEFAULT_SCOPE_COUNT
        assert (
            await ScopedRecord.query()
            .without_global_scope("active")
            .count_async()
            == _ACTIVE_SCOPE_REMOVED_COUNT
        )
        assert (
            await ScopedRecord.query().without_global_scopes().count_async()
            == _ALL_SCOPES_REMOVED_COUNT
        )
        assert (
            await ScopedRecord.query()
            .without_global_scopes()
            .apply(_tenant_two)
            .count_async()
            == _TENANT_TWO_SCOPE_COUNT
        )
        await ScopedRecord.query().update_async({"name": "scoped"})
        assert (
            await DB.table("scope_records")
            .where("name", "scoped")
            .count_async()
            == _DEFAULT_SCOPE_COUNT
        )


async def test_global_scopes_filter_relationship_queries_and_eager_loads(
    application: Application,
) -> None:
    """Apply related-model scopes to EXISTS predicates and select-in loads.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_scope_tables()
        await DB.table("scope_posts").insert_many_async(
            [{"name": "visible"}, {"name": "hidden"}],
        )
        await DB.table("scope_comments").insert_many_async(
            [
                {"post_id": 1, "is_public": True, "body": "published"},
                {"post_id": 1, "is_public": True, "body": "internal"},
                {"post_id": 2, "is_public": False, "body": "draft"},
            ],
        )

        assert (
            await ScopedPost.query().has("comments").count_async()
            == _SCOPED_POST_COUNT
        )
        posts = (
            await ScopedPost.query()
            .with_("comments")
            .order_by(
                "id",
            )
            .get_async()
        )

        assert len(posts) == _POST_COUNT
        assert [len(post.comments) for post in posts] == [2, 0]
        filtered = await (
            ScopedPost.query()
            .with_where("comments", _published_comment)
            .order_by("id")
            .get_async()
        )
        assert [
            [comment.body for comment in post.comments] for post in filtered
        ] == [["published"], []]


async def test_sync_global_scope_queries_accept_orm_expressions(
    application: Application,
) -> None:
    """Execute scoped Core queries through the sync Session boundary.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE scope_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "active BOOLEAN NOT NULL, tenant_id INTEGER NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        await DB.table("scope_records").insert_many_async(
            [
                {"name": "visible", "active": True, "tenant_id": 1},
                {"name": "inactive", "active": False, "tenant_id": 1},
                {"name": "other", "active": True, "tenant_id": 2},
            ],
        )
        count, names = await anyio.to_thread.run_sync(
            _run_sync_scope_queries,
        )
        assert count == _DEFAULT_SCOPE_COUNT
        assert names == ["other", "visible"]


def _run_sync_scope_queries() -> tuple[int, list[str]]:
    """Run scoped sync reads in their required worker-thread boundary.

    Returns:
        The scoped count and names visible after removing one global filter.
    """
    count = ScopedRecord.query().count()
    active_rows = (
        ScopedRecord.query()
        .without_global_scope("tenant")
        .order_by("name")
        .get()
    )
    return count, [row.name for row in active_rows]


def _tenant_two(
    query: ModelQueryBuilder[ScopedRecord],
) -> ModelQueryBuilder[ScopedRecord]:
    """Add a reusable local tenant restriction to one model query.

    Args:
        query: Typed query builder to transform.

    Returns:
        The same builder with its tenant predicate added.
    """
    return query.where("tenant_id", 2)


def _published_comment(
    query: ModelQueryBuilder[ScopedComment],
) -> ModelQueryBuilder[ScopedComment]:
    """Limit eager-loaded comments to published rows.

    Args:
        query: Typed query builder for a related comment model.

    Returns:
        The configured related query builder.
    """
    return query.where("body", "published")


async def _create_scope_tables() -> None:
    """Create tables for scoped model and relationship integration tests."""
    await DB.statement_async(
        "CREATE TABLE scope_records ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "active BOOLEAN NOT NULL, tenant_id INTEGER NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE scope_posts ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE scope_comments ("
        "id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL, "
        "is_public BOOLEAN NOT NULL, body TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP, "
        "FOREIGN KEY (post_id) REFERENCES scope_posts(id))"
    )
