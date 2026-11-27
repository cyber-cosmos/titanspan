"""Verify mapped relationships through an intermediate model.

The tests use SQLAlchemy's relationship loader and real SQLite foreign keys.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy import Column, ForeignKey, Integer, Table
from sqlalchemy.orm import Mapped, mapped_column, query_expression

from titanspan.database import (
    DatabaseQueryError,
    DatabaseServiceProvider,
    Model,
    belongs_to_many,
    has_many_through,
    has_one_through,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
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


class ThroughPost(Model):
    """Represent a post related to a country through its author.
    """  # fmt: skip

    table = "through_posts"
    fillable = ("user_id", "title")

    user_id: Mapped[int] = mapped_column(ForeignKey("through_users.id"))
    title: Mapped[str]


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
            {"user_id": user.id, "title": "Public"},
        )

        countries = await ThroughCountry.query().with_count("posts").get_async()

        counts = {country.name: country.posts_count for country in countries}
        assert counts == {"Populated": 1, "Empty": 0}

        sync_counts = await anyio.to_thread.run_sync(_read_country_counts)
        assert sync_counts == counts


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
        "title TEXT NOT NULL, created_at TIMESTAMP, updated_at TIMESTAMP, "
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
