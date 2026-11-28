"""Verify mapped relationships through an intermediate model.

The tests use SQLAlchemy's relationship loader and real SQLite foreign keys.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, cast

import anyio
import pytest
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, query_expression, relationship

from titanspan.database import (
    DatabaseQueryError,
    DatabaseServiceProvider,
    DatabaseTransactionOwnershipError,
    Model,
    ModelNotFoundError,
    RelationshipChanges,
    Schema,
    SoftDeletes,
    belongs_to_many,
    has_many_through,
    has_one_through,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
type _AggregateForTesting = Literal[
    "count",
    "exists",
    "sum",
    "avg",
    "min",
    "max",
]
_RELATIONSHIP_ROLLBACK_MESSAGE = "rollback relationship update"

_COUNTRY_TAGS = Table(
    "through_country_tags",
    Model.metadata,
    Column(
        "country_id",
        Integer,
        ForeignKey("through_countries.id"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("through_tags.id"),
        primary_key=True,
    ),
    Column("label", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
)
_LEGACY_COUNTRY_TAGS = Table(
    "through_legacy_country_tags",
    Model.metadata,
    Column(
        "country_id",
        Integer,
        ForeignKey("through_legacy_countries.id"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("through_tags.id"),
        primary_key=True,
    ),
)


class SoftAggregateCountry(SoftDeletes, Model):
    """Represent a soft-deletable parent for deferred aggregate loading.

    The query expression keeps aggregate assignment on the original instance.
    """

    table = "through_soft_aggregate_countries"
    fillable = ("name",)
    name: Mapped[str]
    posts_count: Mapped[int | None] = query_expression()
    posts: Mapped[list[SoftAggregatePost]] = relationship(
        back_populates="country",
    )


class SoftAggregatePost(Model):
    """Represent one related row owned by a soft-deletable country.

    This mapped relation exercises aggregate loading with deleted parents.
    """

    table = "through_soft_aggregate_posts"
    fillable = ("country_id",)
    country_id: Mapped[int] = mapped_column(
        ForeignKey("through_soft_aggregate_countries.id"),
    )
    country: Mapped[SoftAggregateCountry] = relationship(
        back_populates="posts",
    )


class ThroughUser(SoftDeletes, Model):
    """Represent an intermediate model between a country and posts.

    This mapped table contains foreign keys to the parent and final models.
    """

    table = "through_users"
    fillable = ("country_id", "name")

    country_id: Mapped[int] = mapped_column(
        ForeignKey("through_countries.id"),
    )
    name: Mapped[str]
    country_tags_count: Mapped[int | None] = query_expression()
    country: Mapped[ThroughCountry] = relationship(back_populates="users")
    posts: Mapped[list[ThroughPost]] = relationship(back_populates="user")


class ThroughPost(SoftDeletes, Model):
    """Represent a post related to a country through its author.
    """  # fmt: skip

    table = "through_posts"
    fillable = ("user_id", "title", "amount")

    user_id: Mapped[int] = mapped_column(ForeignKey("through_users.id"))
    title: Mapped[str]
    amount: Mapped[int] = mapped_column(default=0)
    user: Mapped[ThroughUser] = relationship(back_populates="posts")


class ThroughTag(Model):
    """Represent a tag associated with countries through a pivot table.
    """  # fmt: skip

    table = "through_tags"
    fillable = ("name",)

    name: Mapped[str]


class ThroughCountry(Model):
    """Represent a country with one and many through relationships.
    """  # fmt: skip

    table = "through_countries"
    fillable = ("name",)

    name: Mapped[str]
    posts_count: Mapped[int | None] = query_expression()
    users_posts_count: Mapped[int | None] = query_expression()
    posts_exists: Mapped[bool | None] = query_expression()
    posts_sum_amount: Mapped[int | None] = query_expression()
    posts_avg_amount: Mapped[float | None] = query_expression()
    posts_min_amount: Mapped[int | None] = query_expression()
    posts_max_amount: Mapped[int | None] = query_expression()
    posts: Mapped[list[ThroughPost]] = has_many_through(
        ThroughPost,
        ThroughUser,
    )
    users: Mapped[list[ThroughUser]] = relationship(back_populates="country")
    first_post: Mapped[ThroughPost] = has_one_through(
        ThroughPost,
        ThroughUser,
    )
    tags: Mapped[list[ThroughTag]] = belongs_to_many(
        ThroughTag,
        _COUNTRY_TAGS,
        timestamps=("created_at", "updated_at"),
    )


class LegacyThroughCountry(Model):
    """Represent a country using ordinary SQLAlchemy pivot persistence.

    Its relation omits Titanspan-managed pivot timestamps.
    """

    table = "through_legacy_countries"
    fillable = ("name",)

    name: Mapped[str]
    tags: Mapped[list[ThroughTag]] = belongs_to_many(
        ThroughTag,
        _LEGACY_COUNTRY_TAGS,
    )


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with an isolated SQLite database.

    Args:
        tmp_path: Temporary application root managed by Pytest.

    Returns:
        An unopened application with its native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/through_relationships.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_through_relationships_load_and_filter_models(
    application: Application,
) -> None:
    """Load one and many related models through an intermediate table.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        country = await ThroughCountry.create_async({"name": "Example"})
        user = await ThroughUser.create_async(
            {"country_id": country.id, "name": "Ada"},
        )
        await ThroughPost.create_async(
            {"user_id": user.id, "title": "Public"},
        )

        loaded = await (
            ThroughCountry.query()
            .with_("posts", "first_post")
            .where("id", country.id)
            .first_or_fail_async()
        )
        matching = (
            await ThroughCountry.query()
            .where_has(
                "posts",
                lambda query: query.where("title", "Public"),
            )
            .count_async()
        )
        missing = (
            await ThroughCountry.query()
            .where_doesnt_have(
                "posts",
            )
            .count_async()
        )

        assert [post.title for post in loaded.posts] == ["Public"]
        assert loaded.first_post.title == "Public"
        assert matching == 1
        assert missing == 0


async def test_many_to_many_collection_changes_persist_through_sqlalchemy(
    application: Application,
) -> None:
    """Persist native association collection append and removal operations.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        country = await ThroughCountry.create_async({"name": "Example"})
        tag = await ThroughTag.create_async({"name": "featured"})
        loaded = await (
            ThroughCountry.query()
            .with_("tags")
            .where("id", country.id)
            .first_or_fail_async()
        )
        loaded.tags.append(tag)
        await loaded.save_async()

        loaded = await (
            ThroughCountry.query()
            .with_("tags")
            .where("id", country.id)
            .first_or_fail_async()
        )
        assert [item.name for item in loaded.tags] == ["featured"]
        loaded.tags.remove(loaded.tags[0])
        await loaded.save_async()

        assert await DB.table("through_country_tags").count_async() == 0


async def test_many_to_many_relationship_operations_are_transactional(
    application: Application,
) -> None:
    """Attach, detach, sync, and toggle mapped related models.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        country = await ThroughCountry.create_async({"name": "Example"})
        first = await ThroughTag.create_async({"name": "first"})
        second = await ThroughTag.create_async({"name": "second"})
        relation = country.relation("tags")
        empty_ids: list[object] = []

        assert await relation.attach_async([]) == ()
        assert (
            await anyio.to_thread.run_sync(
                relation.attach,
                empty_ids,
            )
            == ()
        )
        assert (
            await relation.sync_async(
                [],
                detaching=False,
            )
            == RelationshipChanges()
        )
        assert (
            await anyio.to_thread.run_sync(
                relation.sync_without_detaching,
                empty_ids,
            )
            == RelationshipChanges()
        )
        assert await relation.toggle_async([]) == RelationshipChanges()
        assert (
            await anyio.to_thread.run_sync(
                relation.toggle,
                empty_ids,
            )
            == RelationshipChanges()
        )

        assert await anyio.to_thread.run_sync(
            relation.attach,
            first.id,
        ) == (first.id,)
        assert await relation.attach_async(first.id) == ()

        async def rollback_relation_change() -> None:
            """Attach a tag in a transaction that deliberately rolls back.

            The parent cache and association table must retain committed state.
            """
            async with DB.transaction_async():
                await relation.attach_async(second.id)
                raise RuntimeError(_RELATIONSHIP_ROLLBACK_MESSAGE)

        with pytest.raises(RuntimeError, match=_RELATIONSHIP_ROLLBACK_MESSAGE):
            await rollback_relation_change()
        assert [tag.id for tag in country.tags] == [first.id]
        assert await DB.table("through_country_tags").count_async() == 1

        assert await relation.attach_async([first.id, second]) == (second.id,)
        assert await relation.attach_async([first.id, first.id]) == ()
        assert (
            await anyio.to_thread.run_sync(
                relation.attach,
                second.id,
            )
            == ()
        )
        assert [tag.id for tag in country.tags] == [first.id, second.id]

        changes = await relation.sync_async([second.id])
        assert (changes.attached, changes.detached) == ((), (first.id,))
        assert [tag.id for tag in country.tags] == [second.id]

        changes = await anyio.to_thread.run_sync(
            relation.sync_without_detaching,
            [first.id],
        )
        assert (changes.attached, changes.detached) == ((first.id,), ())
        assert [tag.id for tag in country.tags] == [second.id, first.id]

        changes = await relation.toggle_async([first.id, second.id])
        assert (changes.attached, changes.detached) == (
            (),
            (first.id, second.id),
        )
        assert country.tags == []

        assert await relation.attach_async([first.id, second.id]) == (
            first.id,
            second.id,
        )
        assert await anyio.to_thread.run_sync(relation.detach) == (
            first.id,
            second.id,
        )
        assert await relation.attach_async([first.id, second.id]) == (
            first.id,
            second.id,
        )
        assert await anyio.to_thread.run_sync(
            relation.detach,
            first.id,
        ) == (first.id,)
        assert await relation.detach_async() == (second.id,)
        assert await DB.table("through_country_tags").count_async() == 0


async def test_many_to_many_operations_manage_pivot_timestamps(
    application: Application,
) -> None:
    """Stamp new pivots and preserve times for unchanged associations.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        country = await ThroughCountry.create_async({"name": "Example"})
        tag = await ThroughTag.create_async({"name": "featured"})
        sync_tag = await ThroughTag.create_async({"name": "popular"})
        relation = country.relation("tags")
        assert await relation.attach_async(tag.id) == (tag.id,)

        created_at = await (
            DB.table("through_country_tags")
            .where("country_id", country.id)
            .where("tag_id", tag.id)
            .value_async("created_at")
        )
        updated_at = await (
            DB.table("through_country_tags")
            .where("country_id", country.id)
            .where("tag_id", tag.id)
            .value_async("updated_at")
        )
        assert isinstance(created_at, str)
        assert isinstance(updated_at, str)
        assert created_at == updated_at
        assert await relation.sync_async(tag.id) == RelationshipChanges()
        assert (
            await DB.table("through_country_tags")
            .where("country_id", country.id)
            .where("tag_id", tag.id)
            .value_async("created_at")
            == created_at
        )
        assert (
            await DB.table("through_country_tags")
            .where("country_id", country.id)
            .where("tag_id", tag.id)
            .value_async("updated_at")
            == updated_at
        )

        old_timestamp = datetime(2000, 1, 1, tzinfo=UTC)
        await (
            DB.table("through_country_tags")
            .where("country_id", country.id)
            .where("tag_id", tag.id)
            .update_async({"updated_at": old_timestamp})
        )
        assert (
            await relation.update_existing_pivot_async(
                tag.id,
                {"label": "new label"},
            )
            == 1
        )
        changed_at = await (
            DB.table("through_country_tags")
            .where("country_id", country.id)
            .where("tag_id", tag.id)
            .value_async("updated_at")
        )
        assert isinstance(changed_at, str)
        assert datetime.fromisoformat(changed_at).year > old_timestamp.year

        def manage_sync_pivot_timestamp() -> None:
            """Exercise synchronous pivot writes in a worker thread.

            Synchronous SQLAlchemy sessions must not block the async test task.
            """
            assert relation.attach(sync_tag.id) == (sync_tag.id,)
            sync_created_at = (
                DB.table("through_country_tags")
                .where("country_id", country.id)
                .where("tag_id", sync_tag.id)
                .value("created_at")
            )
            sync_updated_at = (
                DB.table("through_country_tags")
                .where("country_id", country.id)
                .where("tag_id", sync_tag.id)
                .value("updated_at")
            )
            assert isinstance(sync_created_at, str)
            assert sync_created_at == sync_updated_at

            (
                DB.table("through_country_tags")
                .where("country_id", country.id)
                .where("tag_id", sync_tag.id)
                .update({"updated_at": old_timestamp})
            )
            assert (
                relation.update_existing_pivot(
                    sync_tag.id,
                    {"label": "sync label"},
                )
                == 1
            )
            sync_changed_at = (
                DB.table("through_country_tags")
                .where("country_id", country.id)
                .where("tag_id", sync_tag.id)
                .value("updated_at")
            )
            assert isinstance(sync_changed_at, str)
            assert (
                datetime.fromisoformat(sync_changed_at).year
                > old_timestamp.year
            )

        await anyio.to_thread.run_sync(manage_sync_pivot_timestamp)


async def test_timestamped_pivot_mutations_refresh_async_transaction_state(
    application: Application,
) -> None:
    """Observe Core pivot mutations through one async Unit of Work.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        country = await ThroughCountry.create_async({"name": "Async UoW"})
        first = await ThroughTag.create_async({"name": "first"})
        second = await ThroughTag.create_async({"name": "second"})
        third = await ThroughTag.create_async({"name": "third"})
        rolled_back = await ThroughTag.create_async({"name": "rolled back"})
        relation = country.relation("tags")

        async with DB.transaction_async():
            assert await relation.attach_async(first.id) == (first.id,)
            assert await relation.attach_async(second.id) == (second.id,)
            assert await relation.attach_async(first.id) == ()
            assert await relation.detach_async(second.id) == (second.id,)
            assert await relation.attach_async(second.id) == (second.id,)
            assert await relation.sync_async([first.id, third.id]) == (
                RelationshipChanges(
                    attached=(third.id,),
                    detached=(second.id,),
                )
            )
            assert await relation.toggle_async(first.id) == (
                RelationshipChanges(detached=(first.id,))
            )
            assert await relation.toggle_async(first.id) == (
                RelationshipChanges(attached=(first.id,))
            )

            async with DB.transaction_async():
                assert await relation.attach_async(second.id) == (second.id,)

            async def rollback_nested_changes() -> None:
                """Roll back two changes to the active savepoint.

                Returns:
                    None.
                """
                async with DB.transaction_async():
                    assert await relation.detach_async(third.id) == (third.id,)
                    assert await relation.attach_async(rolled_back.id) == (
                        rolled_back.id,
                    )
                    raise RuntimeError(_RELATIONSHIP_ROLLBACK_MESSAGE)

            with pytest.raises(
                RuntimeError,
                match=_RELATIONSHIP_ROLLBACK_MESSAGE,
            ):
                await rollback_nested_changes()

            assert (
                await relation.sync_async(
                    [first.id, second.id, third.id],
                )
                == RelationshipChanges()
            )

        persisted_ids = await (
            DB.table("through_country_tags")
            .where("country_id", country.id)
            .pluck_async("tag_id")
        )
        assert isinstance(persisted_ids, list)
        assert set(persisted_ids) == {first.id, second.id, third.id}
        assert {tag.id for tag in country.tags} == set(persisted_ids)


async def test_timestamped_pivot_mutations_refresh_sync_transaction_state(
    application: Application,
) -> None:
    """Observe sync Core pivot mutations through one Unit of Work.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        country = await ThroughCountry.create_async({"name": "Sync UoW"})
        first = await ThroughTag.create_async({"name": "first"})
        second = await ThroughTag.create_async({"name": "second"})
        third = await ThroughTag.create_async({"name": "third"})
        rolled_back = await ThroughTag.create_async({"name": "rolled back"})
        relation = country.relation("tags")

        def mutate_relationships() -> None:
            """Exercise repeated writes, savepoints, and rollback in one thread.

            Returns:
                None.
            """
            with DB.transaction():
                assert relation.attach(first.id) == (first.id,)
                assert relation.attach(second.id) == (second.id,)
                assert relation.attach(first.id) == ()
                assert relation.detach(second.id) == (second.id,)
                assert relation.attach(second.id) == (second.id,)
                assert relation.sync([first.id, third.id]) == (
                    RelationshipChanges(
                        attached=(third.id,),
                        detached=(second.id,),
                    )
                )
                assert relation.toggle(first.id) == RelationshipChanges(
                    detached=(first.id,),
                )
                assert relation.toggle(first.id) == RelationshipChanges(
                    attached=(first.id,),
                )

                with DB.transaction():
                    assert relation.attach(second.id) == (second.id,)

                def rollback_nested_changes() -> None:
                    """Roll back two changes to the active savepoint.

                    Returns:
                        None.
                    """
                    with DB.transaction():
                        assert relation.detach(third.id) == (third.id,)
                        assert relation.attach(rolled_back.id) == (
                            rolled_back.id,
                        )
                        raise RuntimeError(_RELATIONSHIP_ROLLBACK_MESSAGE)

                with pytest.raises(
                    RuntimeError,
                    match=_RELATIONSHIP_ROLLBACK_MESSAGE,
                ):
                    rollback_nested_changes()

                assert (
                    relation.sync(
                        [first.id, second.id, third.id],
                    )
                    == RelationshipChanges()
                )

        await anyio.to_thread.run_sync(mutate_relationships)
        persisted_ids = await (
            DB.table("through_country_tags")
            .where("country_id", country.id)
            .pluck_async("tag_id")
        )
        assert isinstance(persisted_ids, list)
        assert set(persisted_ids) == {first.id, second.id, third.id}
        assert {tag.id for tag in country.tags} == set(persisted_ids)


async def test_many_to_many_without_timestamps_uses_orm_collections(
    application: Application,
) -> None:
    """Keep existing sync and async collection operations for plain pivots.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        await DB.statement_async(
            "CREATE TABLE through_legacy_countries ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        await DB.statement_async(
            "CREATE TABLE through_legacy_country_tags ("
            "country_id INTEGER NOT NULL, tag_id INTEGER NOT NULL, "
            "PRIMARY KEY(country_id, tag_id), "
            "FOREIGN KEY(country_id) "
            "REFERENCES through_legacy_countries(id), "
            "FOREIGN KEY(tag_id) REFERENCES through_tags(id))"
        )
        country = await LegacyThroughCountry.create_async(
            {"name": "Legacy"},
        )
        async_tag = await ThroughTag.create_async({"name": "async"})
        sync_tag = await ThroughTag.create_async({"name": "sync"})
        relation = country.relation("tags")

        assert await relation.attach_async(async_tag.id) == (async_tag.id,)
        assert await relation.detach_async(async_tag.id) == (async_tag.id,)

        def mutate_sync_collection() -> None:
            """Exercise sync collection changes in a worker thread.

            The synchronous session stays off the async test task.
            """
            assert relation.attach(sync_tag.id) == (sync_tag.id,)
            assert relation.detach(sync_tag.id) == (sync_tag.id,)

        await anyio.to_thread.run_sync(mutate_sync_collection)
        assert await DB.table("through_legacy_country_tags").count_async() == 0


async def test_many_to_many_relationship_operations_validate_mapping_and_ids(
    application: Application,
) -> None:
    """Reject unsupported relations, transient parents, and unknown IDs.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        country = await ThroughCountry.create_async({"name": "Example"})

        with pytest.raises(DatabaseQueryError, match="many-to-many"):
            country.relation("posts")
        with pytest.raises(DatabaseQueryError, match="mapped relation"):
            country.relation("unknown")

        transient = ThroughCountry(name="Transient")
        with pytest.raises(DatabaseQueryError, match="persisted"):
            await transient.relation("tags").attach_async(1)

        with pytest.raises(ModelNotFoundError, match="related model"):
            await country.relation("tags").attach_async(999)
        with pytest.raises(DatabaseQueryError, match="hashable"):
            await country.relation("tags").attach_async([[1]])

        assert await DB.table("through_country_tags").count_async() == 0


async def test_many_to_many_relationship_updates_existing_pivot_attributes(
    application: Application,
) -> None:
    """Update only an existing association row's non-key attributes.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        country = await ThroughCountry.create_async({"name": "Example"})
        first = await ThroughTag.create_async({"name": "first"})
        second = await ThroughTag.create_async({"name": "second"})
        relation = country.relation("tags")
        await relation.attach_async([first.id, second.id])

        for invalid_related in (None, [], [first.id, second.id]):
            with pytest.raises(
                DatabaseQueryError,
                match="exactly one related identifier",
            ):
                await relation.update_existing_pivot_async(
                    invalid_related,
                    {"label": "invalid"},
                )

        assert (
            await relation.update_existing_pivot_async(
                first.id,
                {"label": "featured"},
            )
            == 1
        )
        assert (
            await anyio.to_thread.run_sync(
                relation.update_existing_pivot,
                second,
                {"label": "review"},
            )
            == 1
        )
        assert (
            await relation.update_existing_pivot_async(
                999,
                {"label": "missing"},
            )
            == 0
        )
        with pytest.raises(DatabaseQueryError, match="non-key association"):
            await relation.update_existing_pivot_async(
                first.id,
                {"tag_id": second.id},
            )
        with pytest.raises(DatabaseQueryError, match="non-key association"):
            await relation.update_existing_pivot_async(
                first.id,
                {"unknown": "value"},
            )
        with pytest.raises(DatabaseQueryError, match="non-key association"):
            await relation.update_existing_pivot_async(first.id, {})

        async def rollback_pivot_update() -> None:
            """Change an association inside a transaction that rolls back.

            The previous pivot value must remain committed after failure.
            """
            async with DB.transaction_async():
                await relation.update_existing_pivot_async(
                    first.id,
                    {"label": "rolled back"},
                )
                raise RuntimeError(_RELATIONSHIP_ROLLBACK_MESSAGE)

        with pytest.raises(RuntimeError, match=_RELATIONSHIP_ROLLBACK_MESSAGE):
            await rollback_pivot_update()

        assert (
            await DB.table("through_country_tags")
            .where("country_id", country.id)
            .where("tag_id", first.id)
            .value_async("label")
        ) == "featured"
        assert (
            await DB.table("through_country_tags")
            .where("country_id", country.id)
            .where("tag_id", second.id)
            .value_async("label")
        ) == "review"

        orphaned = await ThroughCountry.create_async({"name": "Removed"})
        await (
            DB.table("through_countries")
            .where("id", orphaned.id)
            .delete_async()
        )
        with pytest.raises(ModelNotFoundError):
            await orphaned.relation("tags").attach_async(1)
        with pytest.raises(ModelNotFoundError):
            await anyio.to_thread.run_sync(
                orphaned.relation("tags").attach,
                1,
            )


async def test_many_to_many_operations_preserve_application_ownership(
    application: Application,
    tmp_path: Path,
) -> None:
    """Reject old parent and related instances in a different application.

    Args:
        application: First isolated SQLite application.
        tmp_path: Shared application root for both service instances.
    """
    async with application:
        await _create_schema()
        country = await ThroughCountry.create_async({"name": "Example"})
        tag = await ThroughTag.create_async({"name": "shared"})
        assert await country.relation("tags").attach_async(tag.id) == (tag.id,)

    second_application = Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/through_relationships.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )
    async with second_application:
        with pytest.raises(DatabaseTransactionOwnershipError):
            await country.relation("tags").attach_async(tag.id)
        with pytest.raises(DatabaseTransactionOwnershipError):
            await country.relation("tags").update_existing_pivot_async(
                tag.id,
                {"label": "foreign"},
            )

        current_country = await ThroughCountry.find_async(country.id)
        assert current_country is not None
        with pytest.raises(DatabaseTransactionOwnershipError):
            await current_country.relation("tags").attach_async(tag)
        with pytest.raises(DatabaseTransactionOwnershipError):
            await current_country.relation("tags").update_existing_pivot_async(
                tag,
                {"label": "foreign"},
            )


async def test_relationship_count_uses_mapped_query_expression(
    application: Application,
) -> None:
    """Load a related-row count through SQLAlchemy's ORM expression option.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        with pytest.raises(DatabaseQueryError, match="query_expression"):
            ThroughCountry.query().with_count("posts", attribute="name")

        populated = await ThroughCountry.create_async({"name": "Populated"})
        await ThroughCountry.create_async({"name": "Empty"})
        user = await ThroughUser.create_async(
            {"country_id": populated.id, "name": "Ada"},
        )
        await ThroughPost.create_async(
            {"user_id": user.id, "title": "Public", "amount": 7},
        )
        await ThroughPost.create_async(
            {"user_id": user.id, "title": "Another", "amount": 9},
        )
        deleted = await ThroughPost.create_async(
            {"user_id": user.id, "title": "Deleted", "amount": 100},
        )
        assert await deleted.delete_async()

        countries = await (
            ThroughCountry.query()
            .with_count("posts")
            .with_exists("posts")
            .with_sum("posts", "amount")
            .with_avg("posts", "amount")
            .with_min("posts", "amount")
            .with_max("posts", "amount")
            .get_async()
        )

        counts = {
            country.name: (
                country.posts_count,
                country.posts_exists,
                country.posts_sum_amount,
                country.posts_avg_amount,
                country.posts_min_amount,
                country.posts_max_amount,
            )
            for country in countries
        }
        assert counts == {
            "Populated": (2, True, 16, 8.0, 7, 9),
            "Empty": (0, False, None, None, None, None),
        }

        deferred = await ThroughCountry.query().order_by("id").get_async()
        populated_deferred = deferred.find(populated.id)
        assert populated_deferred is not None
        assert populated_deferred.posts_count is None
        await deferred.load_aggregate_async("posts", "count")
        await deferred.load_aggregate_async("posts", "exists")
        await deferred.load_aggregate_async(
            "posts",
            "sum",
            column_name="amount",
        )
        await deferred.load_aggregate_async(
            "posts",
            "avg",
            column_name="amount",
        )
        await deferred.load_aggregate_async(
            "posts",
            "min",
            column_name="amount",
        )
        await deferred.load_aggregate_async(
            "posts",
            "max",
            column_name="amount",
        )

        assert (
            populated_deferred.posts_count,
            populated_deferred.posts_exists,
            populated_deferred.posts_sum_amount,
            populated_deferred.posts_avg_amount,
            populated_deferred.posts_min_amount,
            populated_deferred.posts_max_amount,
        ) == (2, True, 16, 8.0, 7, 9)

        sync_deferred = await ThroughCountry.query().order_by("id").get_async()
        await anyio.to_thread.run_sync(
            sync_deferred.load_aggregate,
            "posts",
            "count",
        )
        sync_populated = sync_deferred.find(populated.id)
        assert sync_populated is not None
        assert sync_populated.posts_count == counts["Populated"][0]

        with pytest.raises(DatabaseQueryError, match="require a mapped column"):
            await deferred.load_aggregate_async("posts", "sum")
        with pytest.raises(DatabaseQueryError, match="query_expression"):
            await deferred.load_aggregate_async(
                "posts",
                "count",
                attribute="name",
            )
        with pytest.raises(DatabaseQueryError, match="aggregate is invalid"):
            await deferred.load_aggregate_async(
                "posts",
                cast("_AggregateForTesting", "median"),
                column_name="amount",
            )

        empty = (
            await ThroughCountry.query()
            .where(
                "name",
                "Not present",
            )
            .get_async()
        )
        await anyio.to_thread.run_sync(
            empty.load_aggregate,
            "posts",
            "count",
        )
        await empty.load_aggregate_async("posts", "count")

        sync_counts = await anyio.to_thread.run_sync(_read_country_counts)
        assert sync_counts == {
            name: values[0] for name, values in counts.items()
        }

        stale_collection = (
            await ThroughCountry.query()
            .where(
                "name",
                "Empty",
            )
            .get_async()
        )
        stale_model = stale_collection[0]
        await (
            DB.table("through_countries")
            .where(
                "id",
                stale_model.id,
            )
            .delete_async()
        )
        await anyio.to_thread.run_sync(
            stale_collection.load_aggregate,
            "posts",
            "count",
        )
        await stale_collection.load_aggregate_async("posts", "count")
        assert stale_model.posts_count is None


async def test_nested_relationship_aggregates_apply_intermediate_scopes(
    application: Application,
) -> None:
    """Aggregate nested paths while applying each model's visibility scope.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        populated = await ThroughCountry.create_async({"name": "Populated"})
        await ThroughCountry.create_async({"name": "Empty"})
        scoped = await ThroughCountry.create_async({"name": "Scoped"})
        user = await ThroughUser.create_async(
            {"country_id": populated.id, "name": "Ada"},
        )
        deleted_user = await ThroughUser.create_async(
            {"country_id": scoped.id, "name": "Deleted owner"},
        )
        await ThroughPost.create_async(
            {"user_id": user.id, "title": "First", "amount": 7},
        )
        await ThroughPost.create_async(
            {"user_id": user.id, "title": "Second", "amount": 9},
        )
        deleted_post = await ThroughPost.create_async(
            {"user_id": user.id, "title": "Deleted", "amount": 50},
        )
        await ThroughPost.create_async(
            {
                "user_id": deleted_user.id,
                "title": "Hidden owner",
                "amount": 100,
            },
        )
        assert await deleted_post.delete_async()
        assert await deleted_user.delete_async()

        expected = {
            "Populated": (2, 16),
            "Empty": (0, None),
            "Scoped": (0, None),
        }
        loaded = await (
            ThroughCountry.query()
            .with_count("users.posts")
            .with_sum(
                "users.posts",
                "amount",
                attribute="posts_sum_amount",
            )
            .get_async()
        )
        assert {
            country.name: (
                country.users_posts_count,
                country.posts_sum_amount,
            )
            for country in loaded
        } == expected

        deferred = await ThroughCountry.query().get_async()
        await deferred.load_aggregate_async("users.posts", "count")
        await deferred.load_aggregate_async(
            "users.posts",
            "sum",
            column_name="amount",
            attribute="posts_sum_amount",
        )
        assert {
            country.name: (
                country.users_posts_count,
                country.posts_sum_amount,
            )
            for country in deferred
        } == expected


async def test_nested_aggregate_joins_a_secondary_relationship(
    application: Application,
) -> None:
    """Aggregate a nested path that ends in a many-to-many relation.

    Args:
        application: Isolated SQLite application for this test.
    """
    async with application:
        await _create_schema()
        tagged = await ThroughCountry.create_async({"name": "Tagged"})
        empty = await ThroughCountry.create_async({"name": "Empty"})
        tag = await ThroughTag.create_async({"name": "featured"})
        await tagged.relation("tags").attach_async(tag)
        await ThroughUser.create_async(
            {"country_id": tagged.id, "name": "Tagged owner"},
        )
        await ThroughUser.create_async(
            {"country_id": empty.id, "name": "Empty owner"},
        )

        loaded = await (
            ThroughUser.query().with_count("country.tags").get_async()
        )
        assert {user.name: user.country_tags_count for user in loaded} == {
            "Tagged owner": 1,
            "Empty owner": 0,
        }

        deferred = await ThroughUser.query().get_async()
        await deferred.load_aggregate_async("country.tags", "count")
        assert {user.name: user.country_tags_count for user in deferred} == {
            "Tagged owner": 1,
            "Empty owner": 0,
        }


async def test_deferred_aggregates_include_soft_deleted_parent_models(
    application: Application,
) -> None:
    """Load relationship aggregates onto soft-deleted parent instances.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_schema()
        async with Schema.create("through_soft_aggregate_countries") as table:
            table.id()
            table.string("name", length=80)
            table.soft_deletes()
            table.timestamps()
        async with Schema.create("through_soft_aggregate_posts") as table:
            table.id()
            table.foreign_id("country_id").references(
                "through_soft_aggregate_countries",
            )
            table.timestamps()

        country = await SoftAggregateCountry.create_async({"name": "Hidden"})
        await SoftAggregatePost.create_async({"country_id": country.id})
        assert await country.delete_async()

        collection = await (
            SoftAggregateCountry.query().with_trashed().get_async()
        )
        await collection.load_aggregate_async("posts", "count")
        assert collection[0].posts_count == 1
        await anyio.to_thread.run_sync(
            collection.load_aggregate,
            "posts",
            "count",
        )
        assert collection[0].posts_count == 1


async def _create_schema() -> None:
    """Create country, user, and post tables with through foreign keys.

    The relationships rely on actual database FK metadata and enforcement.
    """
    await DB.statement_async(
        "CREATE TABLE through_countries ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE through_users ("
        "id INTEGER PRIMARY KEY, country_id INTEGER NOT NULL, "
        "name TEXT NOT NULL, deleted_at TIMESTAMP, created_at TIMESTAMP, "
        "updated_at TIMESTAMP, "
        "FOREIGN KEY(country_id) REFERENCES through_countries(id))"
    )
    await DB.statement_async(
        "CREATE TABLE through_posts ("
        "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
        "title TEXT NOT NULL, amount INTEGER NOT NULL DEFAULT 0, "
        "created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP, "
        "FOREIGN KEY(user_id) REFERENCES through_users(id))"
    )
    await DB.statement_async(
        "CREATE TABLE through_tags ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )
    await DB.statement_async(
        "CREATE TABLE through_country_tags ("
        "country_id INTEGER NOT NULL, tag_id INTEGER NOT NULL, "
        "label TEXT, created_at TIMESTAMP, updated_at TIMESTAMP, "
        "PRIMARY KEY(country_id, tag_id), "
        "FOREIGN KEY(country_id) REFERENCES through_countries(id), "
        "FOREIGN KEY(tag_id) REFERENCES through_tags(id))"
    )


def _read_country_counts() -> dict[str, int | None]:
    """Read relationship aggregates through the synchronous ORM API.

    Returns:
        Loaded country names and optional relationship counts.
    """
    countries = ThroughCountry.query().with_count("posts").get()
    return {country.name: country.posts_count for country in countries}
