"""Verify trusted polymorphic belongs-to resolution through SQLAlchemy.

The tests use application-owned maps and isolated SQLite tables.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import anyio
import pytest
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import (
    DatabaseConfigurationError,
    DatabaseQueryError,
    DatabaseServiceProvider,
    Model,
    MorphTo,
    morph_to,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


class _MorphedPost(Model):
    """Represent one permitted polymorphic target model.

    Its mapped table is resolved only through the trusted application map.
    """

    table = "database_morph_posts"
    fillable = ("title",)

    title: Mapped[str]


class _MorphedVideo(Model):
    """Represent another permitted polymorphic target model.

    It uses a separate table to verify per-alias target selection.
    """

    table = "database_morph_videos"
    fillable = ("title",)

    title: Mapped[str]


class _MorphedComment(Model):
    """Represent a mapped type excluded from one polymorphic relation.

    The test uses its alias to verify the declaration allowlist.
    """

    table = "database_morph_comments"
    title: Mapped[str]


class _MorphedAsset(Model):
    """Represent a row that belongs to one mapped model type.

    The descriptor performs explicit lookup and association operations.
    """

    table = "database_morph_assets"
    fillable = ("title", "imageable_type", "imageable_id")

    title: Mapped[str]
    imageable_type: Mapped[str | None] = mapped_column(nullable=True)
    imageable_id: Mapped[int | None] = mapped_column(nullable=True)
    imageable: ClassVar[MorphTo[_MorphedPost | _MorphedVideo]] = morph_to(
        _MorphedPost,
        _MorphedVideo,
        type_column="imageable_type",
        foreign_key="imageable_id",
    )


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an app with an isolated SQLite morph map.

    Args:
        tmp_path: Temporary application root provided by Pytest.

    Returns:
        An unopened app configured with explicit mapped model types.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/morph_to.sqlite",
                    },
                },
                "morph_map": {
                    "post": _MorphedPost,
                    "video": _MorphedVideo,
                    "comment": _MorphedComment,
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_morph_to_resolves_associates_and_dissociates(
    application: Application,
) -> None:
    """Resolve mapped targets and update their type and key columns.

    Args:
        application: Isolated SQLite application for the test.
    """
    async with application:
        await _create_schema()
        post = await _MorphedPost.create_async({"title": "Post"})
        video = await _MorphedVideo.create_async({"title": "Video"})
        post_asset = await _MorphedAsset.create_async(
            {
                "title": "Post image",
                "imageable_type": "post",
                "imageable_id": post.id,
            },
        )
        video_asset = await _MorphedAsset.create_async(
            {
                "title": "Video image",
                "imageable_type": "video",
                "imageable_id": video.id,
            },
        )
        unassociated = await _MorphedAsset.create_async(
            {"title": "Unassociated"},
        )

        resolved_post = await post_asset.imageable.resolve_async()
        resolved_video = await video_asset.imageable.resolve_async()

        assert isinstance(resolved_post, _MorphedPost)
        assert resolved_post.id == post.id
        assert isinstance(resolved_video, _MorphedVideo)
        assert resolved_video.id == video.id
        assert await unassociated.imageable.resolve_async() is None
        assert (
            await anyio.to_thread.run_sync(
                _resolve_sync_unassociated_asset,
                unassociated.id,
            )
            is None
        )

        unsaved_post = _MorphedPost()
        with pytest.raises(DatabaseQueryError, match="non-null owner key"):
            unassociated.imageable.associate(unsaved_post)

        unassociated.imageable.associate(post)
        assert unassociated.imageable_type == "post"
        assert unassociated.imageable_id == post.id
        await unassociated.save_async()

        reloaded = await _MorphedAsset.query().find_async(unassociated.id)
        assert reloaded is not None
        loaded_target = await reloaded.imageable.resolve_async()
        assert isinstance(loaded_target, _MorphedPost)

        reloaded.imageable.dissociate()
        assert reloaded.imageable_type is None
        assert reloaded.imageable_id is None
        await reloaded.save_async()
        assert await reloaded.imageable.resolve_async() is None

        sync_asset = await anyio.to_thread.run_sync(
            _resolve_sync_asset,
            post_asset.id,
        )
        assert isinstance(sync_asset, _MorphedPost)


async def test_morph_to_rejects_unknown_persisted_types(
    application: Application,
) -> None:
    """Reject unknown discriminators without importing stored values.

    Args:
        application: Isolated SQLite application for the test.

    Raises:
        DatabaseConfigurationError: If an alias is not explicitly trusted.
    """
    async with application:
        await _create_schema()
        post = await _MorphedPost.create_async({"title": "Post"})
        asset = await _MorphedAsset.create_async(
            {
                "title": "Unknown image",
                "imageable_type": "os.path:Path",
                "imageable_id": post.id,
            },
        )

        with pytest.raises(DatabaseConfigurationError, match="trusted"):
            await asset.imageable.resolve_async()

        incomplete = await _MorphedAsset.create_async(
            {
                "title": "Incomplete target",
                "imageable_type": "post",
            },
        )
        with pytest.raises(DatabaseQueryError, match="both be set"):
            await incomplete.imageable.resolve_async()

        disallowed = await _MorphedAsset.create_async(
            {
                "title": "Disallowed target",
                "imageable_type": "comment",
                "imageable_id": 1,
            },
        )
        with pytest.raises(DatabaseConfigurationError, match="not allowed"):
            await disallowed.imageable.resolve_async()


def _resolve_sync_unassociated_asset(identifier: int) -> None:
    """Resolve a nullable morph association through the sync API.

    Args:
        identifier: Persisted asset primary key to load.

    Returns:
        None when the asset has no target association.
    """
    asset = _MorphedAsset.query().find(identifier)
    assert asset is not None
    assert asset.imageable.resolve() is None


async def test_morph_maps_follow_the_active_application(
    application: Application,
    tmp_path: Path,
) -> None:
    """Restore each application's trusted aliases across nested scopes.

    Args:
        application: Isolated SQLite application for the test.
        tmp_path: Temporary root for the nested application.
    """
    route_root = tmp_path / "second_application" / "routes"
    route_root.mkdir(parents=True)
    second_application = Application(
        base_path=route_root.parent,
        config={
            "database": {
                "morph_map": {
                    "clip": _MorphedVideo,
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )

    async with application:
        first_service = DB.resolve_service()
        assert first_service.morph_model_for("post") is _MorphedPost

        async with second_application:
            second_service = DB.resolve_service()
            assert second_service is not first_service
            assert second_service.morph_model_for("post") is None
            assert second_service.morph_model_for("clip") is _MorphedVideo
            with pytest.raises(DatabaseConfigurationError, match="alias"):
                _MorphedAsset().imageable.associate(_MorphedPost())

        assert DB.resolve_service() is first_service
        assert first_service.morph_alias_for(_MorphedPost) == "post"


def _resolve_sync_asset(identifier: int) -> _MorphedPost | _MorphedVideo:
    """Resolve one polymorphic target through the synchronous API.

    Args:
        identifier: Persisted asset primary key to load.

    Returns:
        The mapped post or video associated with the selected asset.

    Raises:
        AssertionError: If the loaded asset has no mapped target.
    """
    asset = _MorphedAsset.query().find(identifier)
    assert asset is not None
    target = asset.imageable.resolve()
    assert target is not None
    return target


async def _create_schema() -> None:
    """Create the target and polymorphic source tables.

    A polymorphic key has no SQL foreign-key constraint because it targets
    more than one table.
    """
    await DB.statement_async(
        "CREATE TABLE database_morph_posts ("
        "id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE database_morph_videos ("
        "id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE database_morph_assets ("
        "id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
        "imageable_type TEXT, imageable_id INTEGER, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
