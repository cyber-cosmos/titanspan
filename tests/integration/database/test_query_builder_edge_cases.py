"""Exercise less common Query Builder paths against real SQLite.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import anyio
import pytest
from sqlalchemy import select, text

from titanspan.database import DatabaseQueryError, DatabaseServiceProvider
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

    from titanspan.database.query_builder import QueryBuilder

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_TOTAL_SCORE = 19
_MINIMUM_SCORE = 5
_MAXIMUM_SCORE = 9
_TOTAL_ROWS = 4
_UPDATED_ROWS = 2
_CROSS_JOIN_ROWS = 4


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with a disposable SQLite database.

    Args:
        tmp_path: Temporary path used as the application root.

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
                        "database": "database/query_edges.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_grouped_conditions_and_subquery_inputs(
    application: Application,
) -> None:
    """Compose bound groups with Core and builder EXISTS expressions.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE entries ("
            "id INTEGER PRIMARY KEY, category TEXT NOT NULL, "
            "score INTEGER, active BOOLEAN NOT NULL)"
        )
        await DB.table("entries").insert_many_async(
            [
                {"id": 1, "category": "A", "score": 10, "active": True},
                {"id": 2, "category": "A", "score": 10, "active": True},
                {"id": 3, "category": "B", "score": 15, "active": True},
                {"id": 4, "category": "C", "score": 25, "active": False},
                {"id": 5, "category": "C", "score": None, "active": True},
            ],
        )

        matching = (
            _query("entries")
            .add_select("id as entry_id")
            .add_select("category")
            .select_raw("'category:' || category AS label")
            .where(_category_group)
            .where({"active": True})
            .when(True, lambda query: query.where("score", ">", 0))
            .when(
                False,
                lambda query: query.where("id", 0),
                lambda query: query.where("id", "<", 5),
            )
            .where_exists(
                _query("entries").select("id").where("id", 1),
            )
            .where_not_exists(
                text("SELECT 1 FROM entries WHERE id = 99"),
            )
            .or_where_exists(
                select(1).select_from(text("entries")).where(text("id = 999")),
            )
            .distinct()
            .order_by("id")
        )

        assert await matching.get_async() == [
            {"entry_id": 1, "category": "A", "label": "category:A"},
            {"entry_id": 2, "category": "A", "label": "category:A"},
            {"entry_id": 3, "category": "B", "label": "category:B"},
        ]

        raw_first = (
            await _query("entries")
            .select_raw(":prefix || category AS label", {"prefix": "!"})
            .first_async()
        )
        assert raw_first == {"label": "!A"}


async def test_sync_retrieval_and_pagination_edges(
    application: Application,
) -> None:
    """Exercise synchronous projections and result helpers in a worker.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE scores ("
            "id INTEGER PRIMARY KEY, label TEXT NOT NULL, "
            "score INTEGER, group_name TEXT NOT NULL)"
        )
        await DB.table("scores").insert_many_async(
            [
                {"id": 1, "label": "one", "score": 5, "group_name": "A"},
                {"id": 2, "label": "two", "score": 5, "group_name": "A"},
                {"id": 3, "label": "three", "score": 9, "group_name": "B"},
                {"id": 4, "label": "four", "score": None, "group_name": "B"},
            ],
        )

        await anyio.to_thread.run_sync(_exercise_sync_retrieval)


def _exercise_sync_retrieval() -> None:
    """Verify synchronous reads, aggregate nulls, and pagination metadata.
    """  # fmt: skip
    query = _query("scores")
    assert query.first() == {
        "id": 1,
        "label": "one",
        "score": 5,
        "group_name": "A",
    }
    assert query.value("label") == "one"
    assert query.pluck("label") == ["one", "two", "three", "four"]
    assert query.pluck("score", key="id") == {
        1: 5,
        2: 5,
        3: 9,
        4: None,
    }
    assert query.exists()
    assert not query.clone().where("id", 99).exists()
    assert query.clone().where("id", 99).doesnt_exist()
    assert query.clone().where("id", 99).first() is None

    assert query.clone().sum("score") == _TOTAL_SCORE
    assert query.clone().avg("score") == pytest.approx(_TOTAL_SCORE / 3)
    assert query.clone().min("score") == _MINIMUM_SCORE
    assert query.clone().max("score") == _MAXIMUM_SCORE
    assert _query("scores").where("id", 99).sum("score") is None

    distinct = (
        _query("scores")
        .select("group_name")
        .distinct()
        .order_by("group_name", descending=True)
        .reorder()
        .oldest("group_name")
        .get()
    )
    assert distinct == [{"group_name": "A"}, {"group_name": "B"}]
    assert query.clone().latest("id").first() == {
        "id": 4,
        "label": "four",
        "score": None,
        "group_name": "B",
    }

    length_aware = query.clone().limit(None).offset(0).paginate(2, page=2)
    bounded = query.clone().take(2).skip(1).get()
    simple = query.clone().simple_paginate(2, page=2)
    assert tuple(row["id"] for row in length_aware.items) == (3, 4)
    assert length_aware.total == _TOTAL_ROWS
    assert tuple(row["id"] for row in bounded) == (2, 3)
    assert tuple(row["id"] for row in simple.items) == (3, 4)
    assert not simple.has_more_pages


async def test_sync_and_async_mutation_validation_edges(
    application: Application,
) -> None:
    """Cover empty, conditional, and invalid mutation shapes.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE values_table ("
            "id INTEGER PRIMARY KEY, score INTEGER NOT NULL, "
            "label TEXT NOT NULL UNIQUE)"
        )
        await DB.table("values_table").insert_many_async(
            [
                {"id": 1, "score": 10, "label": "one"},
                {"id": 2, "score": 20, "label": "two"},
            ],
        )

        await anyio.to_thread.run_sync(_exercise_sync_mutations)
        assert (
            await _query("values_table").update_async(
                {"score": 16},
            )
            == _UPDATED_ROWS
        )
        assert (
            await _query("values_table")
            .where(
                "id",
                1,
            )
            .delete_async()
            == 1
        )
        assert await _query("values_table").count_async() == 1

        query = _query("values_table")
        assert await query.insert_many_async([]) == 0
        assert await query.insert_or_ignore_async([]) == 0
        assert await query.upsert_async([], unique_by=("id",)) == 0

        with pytest.raises(DatabaseQueryError, match="unsupported argument"):
            query.where({"id": 1}, "=", 1)
        with pytest.raises(DatabaseQueryError, match="unsupported argument"):
            query.where(_category_group, 1)
        with pytest.raises(DatabaseQueryError, match="unsupported argument"):
            query.where("id")
        with pytest.raises(DatabaseQueryError, match="unsupported argument"):
            query.where("id", object(), 1)
        with pytest.raises(DatabaseQueryError, match="operator"):
            query.where("id", "invalid", 1)
        with pytest.raises(DatabaseQueryError, match="identifier"):
            query.update({"values_table.score": 1})

        with pytest.raises(DatabaseQueryError, match="same columns"):
            query.insert_or_ignore(
                [
                    {"id": 3, "score": 30, "label": "three"},
                    {"id": 4, "score": 40},
                ],
            )
        with pytest.raises(DatabaseQueryError, match="at least one"):
            query.upsert([{}], unique_by=("id",))
        with pytest.raises(DatabaseQueryError, match="one or more"):
            query.upsert([{"id": 3, "score": 30}], unique_by="id")
        with pytest.raises(DatabaseQueryError, match="must not repeat"):
            query.upsert(
                [{"id": 3, "score": 30}],
                unique_by=("id", "id"),
            )
        with pytest.raises(DatabaseQueryError, match="must be present"):
            query.upsert(
                [{"id": 3, "score": 30}],
                unique_by=("label",),
            )
        with pytest.raises(DatabaseQueryError, match="sequence of names"):
            query.upsert(
                [{"id": 3, "score": 30}],
                unique_by=("id",),
                update="score",
            )
        with pytest.raises(DatabaseQueryError, match="must not repeat"):
            query.upsert(
                [{"id": 3, "score": 30}],
                unique_by=("id",),
                update=("score", "score"),
            )
        with pytest.raises(DatabaseQueryError, match="must be present"):
            query.upsert(
                [{"id": 3, "score": 30}],
                unique_by=("id",),
                update=("label",),
            )


def _exercise_sync_mutations() -> None:
    """Verify synchronous bulk and atomic mutation semantics on SQLite.
    """  # fmt: skip
    query = _query("values_table")
    assert query.insert_many([]) == 0
    assert (
        query.insert_many(
            [{"id": 3, "score": 30, "label": "three"}],
        )
        == 1
    )
    assert query.insert_or_ignore([]) == 0
    assert (
        query.insert_or_ignore(
            [{"id": 1, "score": 99, "label": "one"}],
        )
        == 0
    )
    assert query.upsert([], unique_by=("id",)) == 0
    assert (
        query.upsert(
            [{"id": 2, "score": 22, "label": "two"}],
            unique_by=("id",),
        )
        == 1
    )
    assert query.where("id", 3).update({"score": 31}) == 1
    assert query.where("id", 3).increment("score", 1) == 1
    assert query.where("id", 3).decrement("score", 2) == 1
    assert query.where("id", 3).delete() == 1


async def test_joins_column_comparisons_and_qualified_tables(
    application: Application,
) -> None:
    """Exercise inner, outer, cross, and schema-qualified table paths.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await DB.statement_async(
            "CREATE TABLE books ("
            "id INTEGER PRIMARY KEY, author_id INTEGER, title TEXT NOT NULL)"
        )
        await DB.statement_async(
            "CREATE TABLE genres (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await DB.table("authors").insert_many_async(
            [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}],
        )
        await DB.table("books").insert_many_async(
            [
                {"id": 1, "author_id": 1, "title": "Core"},
                {"id": 2, "author_id": 1, "title": "Async"},
                {"id": 3, "author_id": None, "title": "Unassigned"},
            ],
        )
        await DB.table("genres").insert_many_async(
            [{"id": 1, "name": "Design"}, {"id": 2, "name": "Science"}],
        )

        joined = await (
            _query("main.authors")
            .join(
                "main.books",
                "main.authors.id",
                "=",
                "main.books.author_id",
            )
            .select(
                "main.authors.name as author",
                "main.books.title as title",
            )
            .where_column(
                "main.authors.id",
                "=",
                "main.books.author_id",
            )
            .order_by("main.books.id")
            .get_async()
        )
        assert joined == [
            {"author": "Ada", "title": "Core"},
            {"author": "Ada", "title": "Async"},
        ]

        outer = await (
            _query("authors")
            .left_join("books", "authors.id", "books.author_id")
            .select("authors.name as author", "books.title as title")
            .order_by("authors.id")
            .order_by("books.id")
            .get_async()
        )
        assert outer == [
            {"author": "Ada", "title": "Core"},
            {"author": "Ada", "title": "Async"},
            {"author": "Grace", "title": None},
        ]

        cross = await (
            _query("genres")
            .cross_join("authors")
            .select("genres.name as genre", "authors.name as author")
            .count_async()
        )
        assert cross == _CROSS_JOIN_ROWS

        with pytest.raises(DatabaseQueryError, match="identifiers"):
            _query("main.archive.authors")
        with pytest.raises(DatabaseQueryError, match="qualified column"):
            _query("authors").where_column("missing.id", "=", "id")


def _query(table_name: str) -> QueryBuilder:
    """Narrow the facade protocol to its registered Core builder in tests.

    Args:
        table_name: Safe table name accepted by the public Database facade.

    Returns:
        The concrete SQLAlchemy Core-backed query builder.
    """
    return cast("QueryBuilder", DB.table(table_name))


def _category_group(group: QueryBuilder) -> QueryBuilder:
    """Match either category used by the grouped-condition fixture.

    Args:
        group: Query Builder clone that owns the nested condition group.

    Returns:
        The query group after adding its two alternatives.
    """
    return group.where("category", "A").or_where("category", "B")
