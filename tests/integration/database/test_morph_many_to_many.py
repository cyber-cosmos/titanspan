"""Verify polymorphic many-to-many relations against real SQLite.

The tests cover app-scoped aliases, mapped query behavior, and pivot writes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped  # noqa: TC002  # Declarative resolves it.

from titanspan.database import (
    DatabaseConfigurationError,
    DatabaseQueryError,
    DatabaseServiceProvider,
    Model,
    MorphPivot,
    morph_to_many,
    morphed_by_many,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

_TAGGABLES = Table(
    "database_morph_many_to_many_taggables",
    Model.metadata,
    Column("taggable_id", Integer, primary_key=True),
    Column("taggable_type", String, primary_key=True),
    Column(
        "tag_id",
        Integer,
        ForeignKey("database_morph_many_to_many_tags.id"),
        primary_key=True,
    ),
    Column("label", String, nullable=True),
    Column("created_at", String, nullable=True),
    Column("updated_at", String, nullable=True),
)


class _MorphManyTag(Model):
    """Represent one tag shared by multiple polymorphic owner types.

    Separate owner aliases can point to the same tag row.
    """

    table = "database_morph_many_to_many_tags"
    fillable = ("name",)

    name: Mapped[str]
    posts: Mapped[list[_MorphManyPost]] = morphed_by_many(
        lambda: _MorphManyPost,
        _TAGGABLES,
        MorphPivot(
            type_column="taggable_type",
            morph_key="taggable_id",
            other_key="tag_id",
        ),
        back_populates="tags",
    )


class _MorphManyPost(Model):
    """Represent one owner type with tags through a morph pivot.

    The mapped pivot stores the configured post alias with each association.
    """

    table = "database_morph_many_to_many_posts"
    fillable = ("title",)

    title: Mapped[str]
    tags: Mapped[list[_MorphManyTag]] = morph_to_many(
        _MorphManyTag,
        _TAGGABLES,
        MorphPivot(
            type_column="taggable_type",
            morph_key="taggable_id",
            other_key="tag_id",
        ),
        back_populates="posts",
    )


class _MorphManyVideo(Model):
    """Represent a distinct polymorphic owner that shares tag identities.

    Its rows use a different trusted alias from the post model.
    """

    table = "database_morph_many_to_many_videos"
    fillable = ("title",)

    title: Mapped[str]
    tags: Mapped[list[_MorphManyTag]] = morph_to_many(
        _MorphManyTag,
        _TAGGABLES,
        MorphPivot(
            type_column="taggable_type",
            morph_key="taggable_id",
            other_key="tag_id",
        ),
    )


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an isolated app with trusted aliases for both owner models.

    Args:
        tmp_path: Temporary root provided by Pytest.

    Returns:
        An unopened SQLite application with its native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/morph_many_to_many.sqlite",
                    },
                },
                "morph_map": {
                    "post": _MorphManyPost,
                    "video": _MorphManyVideo,
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_morph_many_to_many_reads_and_mutates_scoped_pivots(
    application: Application,
) -> None:
    """Filter both owner types and persist their discriminator on writes.

    Args:
        application: Isolated SQLite application for this integration test.
    """
    async with application:
        await _create_schema()
        post = await _MorphManyPost.create_async({"title": "Post"})
        video = await _MorphManyVideo.create_async({"title": "Video"})
        first = await _MorphManyTag.create_async({"name": "first"})
        second = await _MorphManyTag.create_async({"name": "second"})

        assert post.id == video.id
        assert await post.relation("tags").attach_async(
            {first.id: {"label": "post first"}},
        ) == (first.id,)
        assert await video.relation("tags").attach_async(
            {second.id: {"label": "video second"}},
        ) == (second.id,)
        assert await post.relation("tags").attach_async(
            {second.id: {"label": "post second"}},
        ) == (second.id,)
        assert (
            await post.relation("tags").update_existing_pivot_async(
                first.id,
                {"label": "featured"},
            )
            == 1
        )
        with pytest.raises(DatabaseQueryError):
            await post.relation("tags").update_existing_pivot_async(
                first.id,
                {"taggable_type": "video"},
            )

        loaded_posts = await _MorphManyPost.query().with_("tags").get_async()
        loaded_videos = await _MorphManyVideo.query().with_("tags").get_async()
        assert [tag.name for tag in loaded_posts[0].tags] == [
            "first",
            "second",
        ]
        assert [tag.name for tag in loaded_videos[0].tags] == ["second"]

        matching_posts = await (
            _MorphManyPost.query()
            .where_has("tags", lambda query: query.where("name", "first"))
            .count_async()
        )
        assert matching_posts == 1

        tag = await _MorphManyTag.query().with_("posts").find_async(first.id)
        assert tag is not None
        assert [post.title for post in tag.posts] == [
            "Post",
        ]

        changes = await post.relation("tags").sync_async(
            {second.id: {"label": "synced post second"}},
        )
        assert changes.detached == (first.id,)
        assert (
            await DB.table(_TAGGABLES.name)
            .where("taggable_id", post.id)
            .where("taggable_type", "post")
            .where("tag_id", second.id)
            .value_async("label")
            == "synced post second"
        )
        assert await _MorphManyPost.query().where_has("tags").count_async() == 1
        assert (
            await _MorphManyVideo.query().where_has("tags").count_async() == 1
        )

        changes = await video.relation("tags").toggle_async(
            {second.id: {"label": "ignored while detaching"}},
        )
        assert changes.detached == (second.id,)
        assert (
            await _MorphManyVideo.query().where_has("tags").count_async() == 0
        )
        changes = await video.relation("tags").toggle_async(second.id)
        assert changes.attached == (second.id,)


async def test_morph_many_to_many_sync_operations_use_active_alias(
    tmp_path: Path,
) -> None:
    """Use sync pivot writes and a different alias from another app map.

    Args:
        tmp_path: Isolated root for the application under test.
    """
    application = Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/morph_many_to_many_sync.sqlite",
                    },
                },
                "morph_map": {"article": _MorphManyPost},
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )
    async with application:
        await _create_schema()
        post = await _MorphManyPost.create_async({"title": "Article"})
        tag = await _MorphManyTag.create_async({"name": "shared"})

        def attach_with_pivot_values() -> tuple[object, ...]:
            """Attach one tag with a sync pivot row value.

            Returns:
                The related identifier added by the relation manager.
            """
            return post.relation("tags").attach(
                {tag.id: {"label": "sync first"}},
            )

        assert await anyio.to_thread.run_sync(
            attach_with_pivot_values,
        ) == (tag.id,)
        assert await DB.table(_TAGGABLES.name).value_async("label") == (
            "sync first"
        )

        def sync_existing_pivot_value() -> None:
            """Update the existing sync pivot row through sync semantics.

            Returns:
                None.
            """
            changes = post.relation("tags").sync(
                {tag.id: {"label": "sync updated"}},
            )
            assert not changes.attached
            assert not changes.detached
            assert changes.updated == (tag.id,)

        await anyio.to_thread.run_sync(sync_existing_pivot_value)
        assert await DB.table(_TAGGABLES.name).value_async("label") == (
            "sync updated"
        )
        loaded = await (
            _MorphManyPost.query()
            .with_("tags")
            .where("id", post.id)
            .first_or_fail_async()
        )
        assert [related.name for related in loaded.tags] == ["shared"]
        video = await _MorphManyVideo.create_async({"title": "Unmapped"})
        with pytest.raises(DatabaseConfigurationError):
            await video.relation("tags").attach_async(tag.id)


async def _create_schema() -> None:
    """Create model and pivot tables used by the real SQLite integration.

    The polymorphic owner key intentionally has no foreign key constraint.
    """
    await DB.statement_async(
        "CREATE TABLE database_morph_many_to_many_posts ("
        "id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE database_morph_many_to_many_videos ("
        "id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE database_morph_many_to_many_tags ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE database_morph_many_to_many_taggables ("
        "taggable_id INTEGER NOT NULL, taggable_type TEXT NOT NULL, "
        "tag_id INTEGER NOT NULL, label TEXT, created_at TIMESTAMP, "
        "updated_at TIMESTAMP, "
        "PRIMARY KEY(taggable_id, taggable_type, tag_id), "
        "FOREIGN KEY(tag_id) REFERENCES database_morph_many_to_many_tags(id))"
    )
