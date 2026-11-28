"""Verify polymorphic one-to-one and one-to-many model relations.

The tests exercise explicit sync and async access through application maps.
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
    MorphMany,
    MorphManyRelation,
    MorphOne,
    MorphOneRelation,
    morph_many,
    morph_one,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_SYNC_RELATION_COUNT = 2


class _MorphComment(Model):
    """Represent one child row owned by a post or video.

    Relationship writes set its discriminator and key through mapped fields.
    """

    table = "database_morph_one_many_comments"
    fillable = ("body",)

    body: Mapped[str]
    commentable_type: Mapped[str | None] = mapped_column(nullable=True)
    commentable_id: Mapped[int | None] = mapped_column(nullable=True)


class _StrictMorphComment(Model):
    """Represent children that cannot clear their polymorphic key columns.

    Required columns exercise safe nullability checks during dissociation.
    """

    table = "database_morph_one_many_strict_comments"
    fillable = ("body", "commentable_type", "commentable_id")

    body: Mapped[str]
    commentable_type: Mapped[str]
    commentable_id: Mapped[int]


class _StrictMorphCommentId(Model):
    """Represent children whose foreign key cannot be cleared.

    This fixture complements the required-discriminator schema above.
    """

    table = "database_morph_one_many_strict_comment_ids"
    fillable = ("body", "commentable_type", "commentable_id")

    body: Mapped[str]
    commentable_type: Mapped[str | None] = mapped_column(nullable=True)
    commentable_id: Mapped[int]


class _MorphPost(Model):
    """Represent one parent model in a polymorphic relation.

    The post and video tables intentionally share their integer identities.
    """

    table = "database_morph_one_many_posts"
    fillable = ("title",)

    title: Mapped[str]
    comments: ClassVar[MorphMany[_MorphComment]] = morph_many(
        _MorphComment,
        type_column="commentable_type",
        foreign_key="commentable_id",
    )
    featured_comment: ClassVar[MorphOne[_MorphComment]] = morph_one(
        _MorphComment,
        type_column="commentable_type",
        foreign_key="commentable_id",
    )
    strict_comments: ClassVar[MorphMany[_StrictMorphComment]] = morph_many(
        _StrictMorphComment,
        type_column="commentable_type",
        foreign_key="commentable_id",
    )
    strict_id_comments: ClassVar[MorphMany[_StrictMorphCommentId]] = morph_many(
        _StrictMorphCommentId,
        type_column="commentable_type",
        foreign_key="commentable_id",
    )


class _MorphVideo(Model):
    """Represent a different parent type using the shared comment table.

    Matching parent IDs verify that discriminator filters remain active.
    """

    table = "database_morph_one_many_videos"
    fillable = ("title",)

    title: Mapped[str]
    comments: ClassVar[MorphMany[_MorphComment]] = morph_many(
        _MorphComment,
        type_column="commentable_type",
        foreign_key="commentable_id",
    )


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an isolated app with a trusted parent-type map.

    Args:
        tmp_path: Temporary root provided by Pytest.

    Returns:
        An unopened application configured for SQLite.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/morph_one_many.sqlite",
                    },
                },
                "morph_map": {
                    "post": _MorphPost,
                    "video": _MorphVideo,
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_morph_many_and_one_query_and_persist_associations(
    application: Application,
) -> None:
    """Filter by both owner key and trusted type and persist related rows.

    Args:
        application: Isolated SQLite application for this integration test.
    """
    async with application:
        await _create_schema()
        unsaved = _MorphPost(title="Unsaved")
        assert len(await unsaved.comments.resolve_async()) == 0
        assert await unsaved.featured_comment.resolve_async() is None

        post = await _MorphPost.create_async({"title": "Post"})
        video = await _MorphVideo.create_async({"title": "Video"})
        assert post.id == video.id

        first = await post.comments.create_async(
            {
                "body": "first",
                "commentable_id": video.id,
                "commentable_type": "video",
            },
        )
        second = _MorphComment().fill({"body": "second"})
        await post.comments.save_async(second)
        await video.comments.create_async({"body": "video comment"})

        post_comments = await post.comments.resolve_async()
        video_comments = await video.comments.resolve_async()
        featured = await post.featured_comment.resolve_async()

        assert post_comments.model_keys() == (first.id, second.id)
        assert len(video_comments) == 1
        assert video_comments[0].body == "video comment"
        assert featured is not None
        assert featured.id == first.id
        assert first.commentable_type == "post"
        assert first.commentable_id == post.id

        post.comments.dissociate(second)
        assert second.commentable_type is None
        assert second.commentable_id is None
        await second.save_async()
        assert len(await post.comments.resolve_async()) == 1

        with pytest.raises(DatabaseQueryError, match="does not belong"):
            post.comments.dissociate(video_comments[0])

        wrong_child = cast(
            "_MorphComment",
            _MorphVideo(title="wrong model"),
        )
        with pytest.raises(
            DatabaseConfigurationError,
            match="incompatible model type",
        ):
            post.comments.dissociate(wrong_child)

        post.comments.dissociate(first)
        await first.save_async()
        assert await post.featured_comment.resolve_async() is None


async def test_morph_relations_support_sync_access_and_unsaved_guards(
    application: Application,
) -> None:
    """Use sync relation operations and reject missing owner identities.

    Args:
        application: Isolated SQLite application for this integration test.
    """
    async with application:
        await _create_schema()
        post = await _MorphPost.create_async({"title": "Post"})
        comment = await anyio.to_thread.run_sync(
            _create_sync_comment,
            post.id,
        )
        assert comment.commentable_type == "post"
        assert comment.commentable_id == post.id

        loaded = await anyio.to_thread.run_sync(
            _resolve_sync_comment,
            post.id,
        )
        assert loaded.id == comment.id

        unsaved = _MorphPost(title="Unsaved")
        with pytest.raises(DatabaseQueryError, match="non-null owner key"):
            unsaved.comments.create({"body": "rejected"})

        # Simulate untyped runtime input to cover the relation's type guard.
        wrong_child = cast(
            "_MorphComment",
            _MorphVideo(title="wrong model"),
        )
        with pytest.raises(
            DatabaseConfigurationError,
            match="incompatible model type",
        ):
            post.comments.save(wrong_child)


async def test_morph_relations_require_a_trusted_owner_alias(
    application: Application,
) -> None:
    """Refuse to create relationships for unregistered parent classes.

    Args:
        application: Isolated SQLite application for this integration test.

    Raises:
        DatabaseConfigurationError: If the parent class has no trusted alias.
    """

    class _UnregisteredPost(Model):
        """Represent a mapped type absent from the application map.

        Its relation declaration must reject this untrusted parent type.
        """

        table = "database_morph_one_many_unregistered"
        fillable = ("title",)

        title: Mapped[str]
        comments: ClassVar[MorphMany[_MorphComment]] = morph_many(
            _MorphComment,
            type_column="commentable_type",
            foreign_key="commentable_id",
        )

    async with application:
        post = _UnregisteredPost(title="Not mapped")
        with pytest.raises(DatabaseConfigurationError, match="trusted morph"):
            post.comments.query()


async def test_morph_relations_validate_detachment_and_declarations(
    application: Application,
) -> None:
    """Reject invalid definitions and detachment of required columns.

    Args:
        application: Isolated SQLite application for this integration test.

    Raises:
        DatabaseConfigurationError: If mapped attributes are invalid or a
            required discriminator cannot be cleared.
        ValueError: If relationship attribute names are invalid.
    """
    with pytest.raises(ValueError, match="must not be empty"):
        morph_many(
            _MorphComment,
            type_column=" ",
            foreign_key="commentable_id",
        )
    with pytest.raises(ValueError, match="must differ"):
        morph_one(
            _MorphComment,
            type_column="commentable_id",
            foreign_key="commentable_id",
        )
    with pytest.raises(
        DatabaseConfigurationError,
        match="foreign key must be a mapped column",
    ):
        morph_many(
            _MorphComment,
            type_column="commentable_type",
            foreign_key="missing_id",
        )
    with pytest.raises(DatabaseConfigurationError, match="mapped model"):
        morph_one(
            cast("type[object]", object()),
            type_column="commentable_type",
            foreign_key="commentable_id",
        )
    with pytest.raises(ValueError, match="must not be empty"):
        MorphOneRelation(
            _MorphPost(title="Post"),
            _MorphComment,
            type_column=" ",
            foreign_key="commentable_id",
            owner_key="id",
        )
    with pytest.raises(ValueError, match="must differ"):
        MorphManyRelation(
            _MorphPost(title="Post"),
            _MorphComment,
            type_column="commentable_id",
            foreign_key="commentable_id",
            owner_key="id",
        )
    with pytest.raises(
        DatabaseConfigurationError,
        match="child must be a mapped model",
    ):
        MorphOneRelation(
            _MorphPost(title="Post"),
            cast("type[_MorphComment]", object()),
            type_column="commentable_type",
            foreign_key="commentable_id",
            owner_key="id",
        )
    with pytest.raises(
        DatabaseConfigurationError,
        match="type attribute must be a mapped column",
    ):
        MorphOneRelation(
            _MorphPost(title="Post"),
            _MorphComment,
            type_column="missing_type",
            foreign_key="commentable_id",
            owner_key="id",
        )
    with pytest.raises(
        DatabaseConfigurationError,
        match="foreign key must be a mapped column",
    ):
        MorphOneRelation(
            _MorphPost(title="Post"),
            _MorphComment,
            type_column="commentable_type",
            foreign_key="missing_id",
            owner_key="id",
        )
    with pytest.raises(
        DatabaseConfigurationError,
        match="owner must be a mapped model",
    ):
        MorphOneRelation(
            object(),
            _MorphComment,
            type_column="commentable_type",
            foreign_key="commentable_id",
            owner_key="id",
        )
    with pytest.raises(
        DatabaseConfigurationError,
        match="type attribute must be a mapped column",
    ):
        morph_one(
            _MorphComment,
            type_column="missing_type",
            foreign_key="commentable_id",
        )

    invalid_owner_key = morph_one(
        _MorphComment,
        type_column="commentable_type",
        foreign_key="commentable_id",
        owner_key="missing_id",
    )
    with pytest.raises(
        DatabaseConfigurationError,
        match="owner key must be a mapped column",
    ):
        invalid_owner_key.__get__(_MorphPost(title="Post"), _MorphPost)

    invalid_owner = morph_many(
        _MorphComment,
        type_column="commentable_type",
        foreign_key="commentable_id",
    )
    with pytest.raises(
        DatabaseConfigurationError,
        match="owner must be a mapped model",
    ):
        invalid_owner.__get__(object(), object)
    comments_descriptor = cast(
        "MorphMany[_MorphComment]",
        vars(_MorphPost)["comments"],
    )
    featured_descriptor = cast(
        "MorphOne[_MorphComment]",
        vars(_MorphPost)["featured_comment"],
    )
    with pytest.raises(AttributeError, match="requires a model instance"):
        comments_descriptor.__get__(None, _MorphPost)
    with pytest.raises(AttributeError, match="requires a model instance"):
        featured_descriptor.__get__(None, _MorphPost)

    async with application:
        post = _MorphPost(id=23, title="Post")
        strict_child = _StrictMorphComment(
            body="required",
            commentable_type="post",
            commentable_id=23,
        )
        with pytest.raises(
            DatabaseConfigurationError, match="must be nullable"
        ):
            post.strict_comments.dissociate(strict_child)

        strict_id_child = _StrictMorphCommentId(
            body="required key",
            commentable_type="post",
            commentable_id=23,
        )
        with pytest.raises(
            DatabaseConfigurationError,
            match="foreign key must be nullable",
        ):
            post.strict_id_comments.dissociate(strict_id_child)


def _create_sync_comment(parent_id: int) -> _MorphComment:
    """Create one related row through the synchronous relation API.

    Args:
        parent_id: Existing owner identifier.

    Returns:
        The created comment with trusted association columns.
    """
    unsaved = _MorphPost(title="Unsaved")
    assert len(unsaved.comments.resolve()) == 0
    assert unsaved.featured_comment.resolve() is None
    post = _MorphPost.query().find(parent_id)
    assert post is not None
    created = post.comments.create({"body": "sync comment"})
    saved = _MorphComment().fill({"body": "saved sync comment"})
    post.comments.save(saved)
    assert post.comments.query().count() == _SYNC_RELATION_COUNT
    assert len(post.comments.resolve()) == _SYNC_RELATION_COUNT
    return created


def _resolve_sync_comment(parent_id: int) -> _MorphComment:
    """Resolve the first related row through sync ORM operations.

    Args:
        parent_id: Existing owner identifier.

    Returns:
        The first comment assigned to the selected post.
    """
    post = _MorphPost.query().find(parent_id)
    assert post is not None
    comment = post.featured_comment.resolve()
    assert comment is not None
    return comment


async def _create_schema() -> None:
    """Create the tables needed for morph relationship integration tests.

    Polymorphic keys cannot use a conventional single-table foreign key.
    """
    await DB.statement_async(
        "CREATE TABLE database_morph_one_many_posts ("
        "id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE database_morph_one_many_videos ("
        "id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE database_morph_one_many_comments ("
        "id INTEGER PRIMARY KEY, body TEXT NOT NULL, commentable_type TEXT, "
        "commentable_id INTEGER, created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
