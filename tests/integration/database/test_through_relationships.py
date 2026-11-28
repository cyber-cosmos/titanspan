"""Verify mapped relationships through an intermediate model.

The tests use SQLAlchemy's relationship loader and real SQLite foreign keys.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

import anyio
import pytest
from sqlalchemy import Column, ForeignKey, Integer, String, Table
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


class ThroughUser(Model):
    """Represent an intermediate model between a country and posts.

    This mapped table contains foreign keys to the parent and final models.
    """

    table = "through_users"
    fillable = ("country_id", "name")

    country_id: Mapped[int] = mapped_column(
        ForeignKey("through_countries.id"),
    )
    name: Mapped[str]


class ThroughPost(SoftDeletes, Model):
    """Represent a post related to a country through its author.
    """  # fmt: skip

    table = "through_posts"
    fillable = ("user_id", "title", "amount")

    user_id: Mapped[int] = mapped_column(ForeignKey("through_users.id"))
    title: Mapped[str]
    amount: Mapped[int] = mapped_column(default=0)


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
    posts_exists: Mapped[bool | None] = query_expression()
    posts_sum_amount: Mapped[int | None] = query_expression()
    posts_avg_amount: Mapped[float | None] = query_expression()
    posts_min_amount: Mapped[int | None] = query_expression()
    posts_max_amount: Mapped[int | None] = query_expression()
    posts: Mapped[list[ThroughPost]] = has_many_through(
        ThroughPost,
        ThroughUser,
    )
    first_post: Mapped[ThroughPost] = has_one_through(
        ThroughPost,
        ThroughUser,
    )
    tags: Mapped[list[ThroughTag]] = belongs_to_many(
        ThroughTag,
        _COUNTRY_TAGS,
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
        "name TEXT NOT NULL, created_at TIMESTAMP, updated_at TIMESTAMP, "
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
        "label TEXT, "
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
