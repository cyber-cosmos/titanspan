"""Verify trusted polymorphic belongs-to resolution through SQLAlchemy.

The tests use application-owned maps and isolated SQLite tables.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

import anyio
import pytest
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import (
    DatabaseConfigurationError,
    DatabaseQueryError,
    DatabaseServiceProvider,
    Model,
    MorphTo,
    MorphToRelation,
    assert_query_count,
    assert_query_count_async,
    morph_to,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_EXPECTED_MORPH_EAGER_QUERY_COUNT = 3


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
    fillable = (
        "title",
        "imageable_type",
        "imageable_id",
        "alternate_type",
        "alternate_id",
    )

    title: Mapped[str]
    imageable_type: Mapped[str | None] = mapped_column(nullable=True)
    imageable_id: Mapped[int | None] = mapped_column(nullable=True)
    alternate_type: Mapped[str | None] = mapped_column(nullable=True)
    alternate_id: Mapped[int | None] = mapped_column(nullable=True)
    imageable: ClassVar[MorphTo[_MorphedPost | _MorphedVideo]] = morph_to(
        _MorphedPost,
        _MorphedVideo,
        type_column="imageable_type",
        foreign_key="imageable_id",
    )
    alternate: ClassVar[MorphTo[_MorphedPost | _MorphedVideo]] = morph_to(
        _MorphedPost,
        _MorphedVideo,
        type_column="alternate_type",
        foreign_key="alternate_id",
    )


def test_sync_null_morph_target_needs_no_application_context() -> None:
    """Return no target for an empty relation without resolving a service.

    Returns:
        None.
    """
    asset = _MorphedAsset(
        title="Unassociated",
        imageable_type=None,
        imageable_id=None,
    )
    assert asset.imageable.resolve() is None


async def test_async_null_morph_target_needs_no_application_context() -> None:
    """Return no target asynchronously without resolving a service.

    Returns:
        None.
    """
    asset = _MorphedAsset(
        title="Unassociated",
        imageable_type=None,
        imageable_id=None,
    )
    assert await asset.imageable.resolve_async() is None


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


async def test_unbound_morph_relation_resolves_without_cache_identity(
    application: Application,
) -> None:
    """Resolve a standalone relation without a descriptor cache key.

    Args:
        application: Isolated SQLite application for the test.
    """
    async with application:
        await _create_schema()
        post = await _MorphedPost.create_async({"title": "Post"})
        asset = _MorphedAsset(title="Standalone relation")
        relation: MorphToRelation[_MorphedPost | _MorphedVideo] = (
            MorphToRelation(
                parent=asset,
                target_models=(_MorphedPost, _MorphedVideo),
                type_column="imageable_type",
                foreign_key="imageable_id",
                owner_key="id",
            )
        )

        relation.associate(post)
        relation.remember_eager_target(
            DB.resolve_service(),
            "post",
            post.id,
            post,
        )
        async with assert_query_count_async(1):
            resolved = await relation.resolve_async()

        assert isinstance(resolved, _MorphedPost)
        assert resolved.id == post.id


async def test_morph_cache_is_scoped_to_relationship_name(
    application: Application,
) -> None:
    """Resolve another relation when only one descriptor was eager-loaded.

    Args:
        application: Isolated SQLite application for the test.
    """
    async with application:
        await _create_schema()
        post = await _MorphedPost.create_async({"title": "Post"})
        asset = await _MorphedAsset.create_async(
            {
                "title": "Two relations",
                "imageable_type": "post",
                "imageable_id": post.id,
                "alternate_type": "post",
                "alternate_id": post.id,
            },
        )
        eager_assets = await (
            _MorphedAsset.query().with_("imageable").get_async()
        )
        eager_asset = eager_assets[0]
        assert eager_asset.id == asset.id

        async with assert_query_count_async(1):
            alternate = await eager_asset.alternate.resolve_async()

        assert isinstance(alternate, _MorphedPost)
        assert alternate.id == post.id


async def test_morph_mutations_clear_eager_targets(
    application: Application,
) -> None:
    """Reload a target after dissociation and reassociation.

    Args:
        application: Isolated SQLite application for the test.
    """
    async with application:
        await _create_schema()
        post = await _MorphedPost.create_async({"title": "Post"})
        await _MorphedAsset.create_async(
            {
                "title": "Mutable relation",
                "imageable_type": "post",
                "imageable_id": post.id,
            },
        )
        eager_assets = await (
            _MorphedAsset.query().with_("imageable").get_async()
        )
        eager_asset = eager_assets[0]
        eager_target = await eager_asset.imageable.resolve_async()
        assert isinstance(eager_target, _MorphedPost)

        eager_asset.imageable.dissociate()
        eager_asset.imageable.associate(post)
        async with assert_query_count_async(1):
            reloaded = await eager_asset.imageable.resolve_async()

        assert isinstance(reloaded, _MorphedPost)
        assert reloaded.id == post.id


async def test_morph_eager_loading_skips_null_associations(
    application: Application,
) -> None:
    """Avoid target queries for rows without polymorphic keys.

    Args:
        application: Isolated SQLite application for the test.
    """
    async with application:
        await _create_schema()
        await _MorphedAsset.create_async({"title": "Unassociated"})

        async with assert_query_count_async(1):
            assets = await _MorphedAsset.query().with_("imageable").get_async()
            target = await assets[0].imageable.resolve_async()

        assert target is None
        assert assets[0].imageable_type is None
        assert assets[0].imageable_id is None


async def test_morph_to_eager_loading_batches_mixed_targets(
    application: Application,
) -> None:
    """Batch mixed polymorphic targets by trusted model type.

    Args:
        application: Isolated SQLite application for the test.
    """
    async with application:
        await _create_schema()
        first_post = await _MorphedPost.create_async({"title": "First post"})
        second_post = await _MorphedPost.create_async(
            {"title": "Second post"},
        )
        video = await _MorphedVideo.create_async({"title": "Video"})
        for title, alias, identifier in (
            ("First image", "post", first_post.id),
            ("Second image", "post", second_post.id),
            ("Video image", "video", video.id),
        ):
            await _MorphedAsset.create_async(
                {
                    "title": title,
                    "imageable_type": alias,
                    "imageable_id": identifier,
                },
            )

        async with assert_query_count_async(
            _EXPECTED_MORPH_EAGER_QUERY_COUNT,
        ):
            assets = await (
                _MorphedAsset.query()
                .with_("imageable")
                .prevent_lazy_loading()
                .order_by("id")
                .get_async()
            )
            targets = [
                await asset.imageable.resolve_async() for asset in assets
            ]

        assert [asset.title for asset in assets] == [
            "First image",
            "Second image",
            "Video image",
        ]
        assert isinstance(targets[0], _MorphedPost)
        assert targets[0].id == first_post.id
        assert isinstance(targets[1], _MorphedPost)
        assert targets[1].id == second_post.id
        assert isinstance(targets[2], _MorphedVideo)
        assert targets[2].id == video.id

        async with assert_query_count_async(
            _EXPECTED_MORPH_EAGER_QUERY_COUNT,
        ):
            projected_assets = await (
                _MorphedAsset.query()
                .select("title")
                .with_("imageable")
                .get_async()
            )
            projected_targets = [
                await asset.imageable.resolve_async()
                for asset in projected_assets
            ]
        assert [target.id for target in projected_targets if target] == [
            first_post.id,
            second_post.id,
            video.id,
        ]

        assets[0].imageable_id = second_post.id
        async with assert_query_count_async(1):
            changed_target = await assets[0].imageable.resolve_async()
        assert isinstance(changed_target, _MorphedPost)
        assert changed_target.id == second_post.id

        async with (
            assert_query_count_async(
                _EXPECTED_MORPH_EAGER_QUERY_COUNT,
            ),
            _MorphedAsset.query()
            .with_("imageable")
            .order_by("id")
            .stream_async(batch_size=2) as stream,
        ):
            streamed_targets = [
                await asset.imageable.resolve_async() async for asset in stream
            ]

        assert streamed_targets[0] is not None
        assert streamed_targets[1] is not None
        assert streamed_targets[2] is not None
        assert [
            target.id for target in streamed_targets if target is not None
        ] == [
            first_post.id,
            second_post.id,
            video.id,
        ]
        sync_targets = await anyio.to_thread.run_sync(
            _load_sync_morphed_targets,
        )
        assert [target.id for target in sync_targets] == [
            first_post.id,
            second_post.id,
            video.id,
        ]


async def test_morph_to_eager_cache_is_application_scoped(
    application: Application,
    tmp_path: Path,
) -> None:
    """Resolve an eager target again when the active app changes.

    Args:
        application: First isolated SQLite application.
        tmp_path: Temporary root used for the second application's database.
    """
    async with application:
        await _create_schema()
        first_target = await _MorphedPost.create_async({"title": "First app"})
        asset = await _MorphedAsset.create_async(
            {
                "title": "Image",
                "imageable_type": "post",
                "imageable_id": first_target.id,
            },
        )
        eager_assets = await (
            _MorphedAsset.query().with_("imageable").get_async()
        )
        asset = eager_assets[0]
        first_resolved = await asset.imageable.resolve_async()
        assert isinstance(first_resolved, _MorphedPost)
        assert first_resolved.title == "First app"

    second_application = Application(
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
    async with second_application:
        async with assert_query_count_async(1):
            second_resolved = await asset.imageable.resolve_async()
        assert isinstance(second_resolved, _MorphedPost)
        assert second_resolved.title == "First app"
        assert second_resolved is not first_resolved


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


def _load_sync_morphed_targets() -> tuple[
    _MorphedPost | _MorphedVideo,
    ...,
]:
    """Eager-load each morph target type in one sync query.

    Returns:
        The targets associated with the three test assets.
    """
    with assert_query_count(_EXPECTED_MORPH_EAGER_QUERY_COUNT):
        assets = _MorphedAsset.query().with_("imageable").order_by("id").get()
        targets = tuple(asset.imageable.resolve() for asset in assets)
    assert all(target is not None for target in targets)
    with (
        assert_query_count(_EXPECTED_MORPH_EAGER_QUERY_COUNT),
        _MorphedAsset.query()
        .with_("imageable")
        .order_by("id")
        .stream(batch_size=2) as stream,
    ):
        streamed_assets = tuple(stream)
        streamed_targets = tuple(
            asset.imageable.resolve() for asset in streamed_assets
        )
    assert all(target is not None for target in streamed_targets)
    assert [target.id for target in streamed_targets if target] == [
        target.id for target in targets if target
    ]
    with (
        assert_query_count(1),
        _MorphedAsset.query().order_by("id").stream(batch_size=2) as stream,
    ):
        plain_streamed_assets = tuple(stream)
    assert [asset.id for asset in plain_streamed_assets] == [
        asset.id for asset in assets
    ]
    return cast(
        "tuple[_MorphedPost | _MorphedVideo, ...]",
        targets,
    )


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
        "alternate_type TEXT, alternate_id INTEGER, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
