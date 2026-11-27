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


async def test_row_locks_reject_unsupported_sqlite(
    application: Application,
) -> None:
    """Reject row-lock requests on SQLite instead of silently ignoring them.

    Args:
        application: Application configured by this test.
    """
    async with application:
        with pytest.raises(DatabaseQueryError, match="row locks"):
            DB.table("entries").lock_for_update()


async def test_right_and_full_outer_joins_preserve_unmatched_rows(
    application: Application,
) -> None:
    """Preserve unmatched rows on the appropriate SQLite join sides.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE join_users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await DB.statement_async(
            "CREATE TABLE join_posts ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "title TEXT NOT NULL)"
        )
        await DB.table("join_users").insert_many_async(
            [
                {"id": 1, "name": "Ada"},
                {"id": 2, "name": "Grace"},
            ],
        )
        await DB.table("join_posts").insert_many_async(
            [
                {"id": 1, "user_id": 1, "title": "matched"},
                {"id": 2, "user_id": 3, "title": "orphan"},
            ],
        )

        right_rows = await (
            DB.table("join_users")
            .right_join(
                "join_posts",
                "join_users.id",
                "join_posts.user_id",
            )
            .select("join_users.name", "join_posts.title")
            .order_by("join_posts.id")
            .get_async()
        )
        full_rows = await (
            DB.table("join_users")
            .full_outer_join(
                "join_posts",
                "join_users.id",
                "join_posts.user_id",
            )
            .select("join_users.name", "join_posts.title")
            .get_async()
        )

        assert right_rows == [
            {"name": "Ada", "title": "matched"},
            {"name": None, "title": "orphan"},
        ]
        assert {(row["name"], row["title"]) for row in full_rows} == {
            ("Ada", "matched"),
            ("Grace", None),
            (None, "orphan"),
        }


async def test_scalar_projection_and_membership_subqueries(
    application: Application,
) -> None:
    """Compose scalar projections and value membership with builders.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE query_people ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await DB.statement_async(
            "CREATE TABLE eligible_people (id INTEGER PRIMARY KEY)"
        )
        await DB.statement_async(
            "CREATE TABLE query_scores ("
            "id INTEGER PRIMARY KEY, person_id INTEGER, score INTEGER)"
        )
        await DB.table("query_people").insert_many_async(
            [
                {"id": 1, "name": "Ada"},
                {"id": 2, "name": "Grace"},
                {"id": 3, "name": "Linus"},
            ],
        )
        await DB.table("eligible_people").insert_many_async(
            [{"id": 2}, {"id": 3}],
        )
        await DB.table("query_scores").insert_many_async(
            [
                {"id": 1, "person_id": 1, "score": 10},
                {"id": 2, "person_id": 2, "score": 20},
                {"id": 3, "person_id": 2, "score": 22},
            ],
        )
        eligible = DB.table("eligible_people").select("id")
        score = (
            DB.table("query_scores")
            .select("score")
            .where("person_id", 1)
            .limit(1)
        )
        people = DB.table("query_people")
        latest_score = (
            people.subquery("query_scores")
            .select("score")
            .where_column(
                "query_scores.person_id",
                "=",
                "query_people.id",
            )
            .order_by("score", descending=True)
            .limit(1)
        )

        selected = await (
            DB.table("query_people")
            .select_sub(score, "score")
            .add_select("id", "name")
            .where_in("id", eligible)
            .order_by("id")
            .get_async()
        )
        sync_selected = await anyio.to_thread.run_sync(
            lambda: (
                DB.table("query_people")
                .select_sub(
                    DB.table("query_scores")
                    .select("score")
                    .where("person_id", 1)
                    .limit(1),
                    "score",
                )
                .add_select("id", "name")
                .where_in(
                    "id",
                    DB.table("eligible_people").select("id"),
                )
                .order_by("id")
                .get()
            ),
        )
        appended = await (
            DB.table("query_people")
            .select("id")
            .add_select_sub(score, "score")
            .where("id", 2)
            .first_async()
        )
        correlated = await (
            people.select("id")
            .add_select_sub(latest_score, "latest_score")
            .order_by("id")
            .get_async()
        )
        people_with_scores = DB.table("query_people")
        high_scores = (
            people_with_scores.subquery("query_scores")
            .select("person_id")
            .where_column(
                "query_scores.person_id",
                "=",
                "query_people.id",
            )
            .where("query_scores.score", ">", 15)
        )
        with_high_scores = await (
            people_with_scores.where_exists(high_scores)
            .order_by("id")
            .pluck_async("id")
        )
        excluded = await (
            DB.table("query_people")
            .where_not_in("id", eligible)
            .pluck_async("name")
        )
        either = await (
            DB.table("query_people")
            .where("id", 3)
            .or_where_in("id", eligible)
            .order_by("id")
            .pluck_async("id")
        )
        outside_or_selected = await (
            DB.table("query_people")
            .where("id", 3)
            .or_where_not_in("id", eligible)
            .order_by("id")
            .pluck_async("id")
        )

        assert selected == [
            {"score": 10, "id": 2, "name": "Grace"},
            {"score": 10, "id": 3, "name": "Linus"},
        ]
        assert sync_selected == selected
        assert appended == {"id": 2, "score": 10}
        assert correlated == [
            {"id": 1, "latest_score": 10},
            {"id": 2, "latest_score": 22},
            {"id": 3, "latest_score": None},
        ]
        assert with_high_scores == [2]
        assert excluded == ["Ada"]
        assert either == [2, 3]
        assert outside_or_selected == [1, 3]
        with pytest.raises(DatabaseQueryError):
            DB.table("query_people").select_sub(score, "unsafe alias")


async def test_random_ordering_rejects_unstable_cursor_pages(
    application: Application,
) -> None:
    """Execute randomized ordering and reject incompatible cursor paging.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE random_rows (id INTEGER PRIMARY KEY)"
        )
        await DB.table("random_rows").insert_many_async(
            [{"id": 1}, {"id": 2}, {"id": 3}],
        )
        query = DB.table("random_rows").in_random_order()

        statement = str(query.to_statement()).casefold()
        rows = await query.get_async()

        assert "random()" in statement
        assert {row["id"] for row in rows} == {1, 2, 3}
        with pytest.raises(DatabaseQueryError, match="stable ordering"):
            await query.cursor_paginate_async(per_page=2)


async def test_row_value_comparisons_bind_values_and_preserve_groups(
    application: Application,
) -> None:
    """Compare row tuples using SQL ordering and explicit OR grouping.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE tuple_rows ("
            "id INTEGER PRIMARY KEY, first_value INTEGER, "
            "second_value INTEGER)"
        )
        await DB.table("tuple_rows").insert_many_async(
            [
                {"id": 1, "first_value": 1, "second_value": 2},
                {"id": 2, "first_value": 1, "second_value": 3},
                {"id": 3, "first_value": 2, "second_value": 0},
                {"id": 4, "first_value": 0, "second_value": 9},
            ],
        )

        greater = await (
            DB.table("tuple_rows")
            .where_row_values(
                ("first_value", "second_value"),
                ">",
                (1, 2),
            )
            .order_by("id")
            .pluck_async("id")
        )
        either = await (
            DB.table("tuple_rows")
            .where_row_values(
                ("first_value", "second_value"),
                "=",
                (1, 2),
            )
            .or_where_row_values(
                ("first_value", "second_value"),
                ">=",
                (2, 0),
            )
            .order_by("id")
            .pluck_async("id")
        )

        assert greater == [2, 3]
        assert either == [1, 3]
        with pytest.raises(DatabaseQueryError, match="same number"):
            DB.table("tuple_rows").where_row_values(
                ("first_value", "second_value"),
                "=",
                (1,),
            )


async def test_outer_and_cross_joins_accept_subqueries(
    application: Application,
) -> None:
    """Join a selected subquery with right, full, and cross semantics.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE join_users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await DB.statement_async(
            "CREATE TABLE join_posts ("
            "id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT NOT NULL)"
        )
        await DB.table("join_users").insert_many_async(
            [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}],
        )
        await DB.table("join_posts").insert_many_async(
            [
                {"id": 1, "user_id": 1, "title": "matched"},
                {"id": 2, "user_id": 3, "title": "orphan"},
            ],
        )
        posts = DB.table("join_posts").select("user_id", "title")

        right_rows = await (
            DB.table("join_users")
            .right_join_sub(
                posts,
                "posts",
                "join_users.id",
                "posts.user_id",
            )
            .select("join_users.name", "posts.title")
            .get_async()
        )
        full_rows = await (
            DB.table("join_users")
            .full_outer_join_sub(
                posts,
                "posts",
                "join_users.id",
                "posts.user_id",
            )
            .select("join_users.name", "posts.title")
            .get_async()
        )
        cross_count = await (
            DB.table("join_users")
            .cross_join_sub(
                DB.table("join_posts").select("title"),
                "post_titles",
            )
            .count_async()
        )

        assert {(row["name"], row["title"]) for row in right_rows} == {
            ("Ada", "matched"),
            (None, "orphan"),
        }
        assert {(row["name"], row["title"]) for row in full_rows} == {
            ("Ada", "matched"),
            ("Grace", None),
            (None, "orphan"),
        }
        assert cross_count == _CROSS_JOIN_ROWS
        with pytest.raises(DatabaseQueryError, match="only by PostgreSQL"):
            DB.table("join_users").join_lateral(
                posts,
                "lateral_posts",
            )


async def test_join_clause_supports_bound_nested_on_conditions(
    application: Application,
) -> None:
    """Keep value filters in ON so left joins retain unmatched parents.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE clause_users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await DB.statement_async(
            "CREATE TABLE clause_posts ("
            "id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT NOT NULL)"
        )
        await DB.table("clause_users").insert_many_async(
            [
                {"id": 1, "name": "Ada"},
                {"id": 2, "name": "Grace"},
                {"id": 3, "name": "Linus"},
            ],
        )
        await DB.table("clause_posts").insert_many_async(
            [
                {"id": 1, "user_id": 1, "title": "public"},
                {"id": 2, "user_id": 1, "title": "private"},
                {"id": 3, "user_id": 2, "title": "private"},
            ],
        )

        rows = await (
            DB.table("clause_users")
            .join_with(
                "clause_posts",
                lambda join: (
                    join.on(
                        "clause_users.id",
                        "=",
                        "clause_posts.user_id",
                    ).where_group(
                        lambda nested: nested.where(
                            "clause_posts.title",
                            "public",
                        ).or_where("clause_posts.user_id", 2),
                    )
                ),
                join_type="left",
            )
            .select("clause_users.name", "clause_posts.title")
            .order_by("clause_users.id")
            .get_async()
        )

        assert rows == [
            {"name": "Ada", "title": "public"},
            {"name": "Grace", "title": "private"},
            {"name": "Linus", "title": None},
        ]
        with pytest.raises(DatabaseQueryError, match="at least one ON"):
            DB.table("clause_users").join_with(
                "clause_posts",
                lambda _join: None,
            )


async def test_date_and_time_predicates_use_database_expressions(
    application: Application,
) -> None:
    """Filter temporal values through SQLAlchemy expressions on SQLite.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE date_rows ("
            "id INTEGER PRIMARY KEY, occurred_at TEXT NOT NULL)"
        )
        await DB.table("date_rows").insert_many_async(
            [
                {"id": 1, "occurred_at": "2026-11-27 08:30:00"},
                {"id": 2, "occurred_at": "2026-11-27 14:45:00"},
                {"id": 3, "occurred_at": "2026-11-28 08:30:00"},
            ],
        )

        date_rows = (
            await DB.table("date_rows")
            .where_date(
                "occurred_at",
                "2026-11-27",
            )
            .order_by("id")
            .get_async()
        )
        assert [row["id"] for row in date_rows] == [1, 2]

        time_rows = (
            await DB.table("date_rows")
            .where_time(
                "occurred_at",
                ">=",
                "12:00:00",
            )
            .get_async()
        )
        assert [row["id"] for row in time_rows] == [2]

        component_rows = (
            await DB.table("date_rows")
            .where_year(
                "occurred_at",
                2026,
            )
            .where_month("occurred_at", 11)
            .where_day(
                "occurred_at",
                28,
            )
            .get_async()
        )
        assert [row["id"] for row in component_rows] == [3]


async def test_json_path_predicates_bind_values_and_validate_paths(
    application: Application,
) -> None:
    """Compare JSON scalar values without treating paths as SQL syntax.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE json_rows ("
            "id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
        )
        await DB.table("json_rows").insert_many_async(
            [
                {
                    "id": 1,
                    "payload": '{"profile":{"name":"Ada",'
                    '"active":true,"score":12}}',
                },
                {
                    "id": 2,
                    "payload": '{"profile":{"name":"Grace",'
                    '"active":false,"score":8}}',
                },
            ],
        )

        active = (
            await DB.table("json_rows")
            .where_json_value(
                "payload",
                "profile.active",
                True,
            )
            .first_async()
        )
        high_score = (
            await DB.table("json_rows")
            .where_json_value(
                "payload",
                "profile.score",
                ">=",
                10,
            )
            .first_async()
        )
        assert active is not None
        assert active["id"] == 1
        assert high_score is not None
        assert high_score["id"] == 1

        with pytest.raises(DatabaseQueryError, match="JSON path"):
            DB.table("json_rows").where_json_value(
                "payload",
                "profile.name); DROP TABLE users; --",
                "Ada",
            )


async def test_cursor_pagination_stabilizes_order_and_supports_reverse_pages(
    application: Application,
) -> None:
    """Navigate forward and backward over duplicate ordering values.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE cursor_rows ("
            "id INTEGER PRIMARY KEY, category TEXT NOT NULL, "
            "payload TEXT NOT NULL)"
        )
        await DB.table("cursor_rows").insert_many_async(
            [
                {"id": 1, "category": "A", "payload": "one"},
                {"id": 2, "category": "A", "payload": "two"},
                {"id": 3, "category": "B", "payload": "three"},
                {"id": 4, "category": "B", "payload": "four"},
                {"id": 5, "category": "C", "payload": "five"},
            ],
        )
        query = DB.table("cursor_rows").select("category", "payload")

        first = (
            await query.clone()
            .order_by("category")
            .cursor_paginate_async(
                2,
            )
        )
        assert [row["payload"] for row in first.items] == ["one", "two"]
        assert first.has_more_pages
        assert first.next_cursor is not None
        assert first.previous_cursor is None

        second = (
            await query.clone()
            .order_by("category")
            .cursor_paginate_async(
                2,
                cursor=first.next_cursor,
            )
        )
        assert [row["payload"] for row in second.items] == ["three", "four"]
        assert second.next_cursor is not None
        assert second.previous_cursor is not None

        prior = (
            await query.clone()
            .order_by("category")
            .cursor_paginate_async(
                2,
                cursor=second.previous_cursor,
            )
        )
        assert [row["payload"] for row in prior.items] == ["one", "two"]
        assert prior.next_cursor is not None

        descending_query = (
            DB.table("cursor_rows")
            .select("category", "payload")
            .order_by("category", descending=True)
        )
        descending = await descending_query.cursor_paginate_async(2)
        assert [row["payload"] for row in descending.items] == [
            "five",
            "three",
        ]
        assert descending.next_cursor is not None
        descending_next = await descending_query.cursor_paginate_async(
            2,
            cursor=descending.next_cursor,
        )
        assert [row["payload"] for row in descending_next.items] == [
            "four",
            "one",
        ]

        with pytest.raises(DatabaseQueryError, match="cursor token"):
            await query.cursor_paginate_async(2, cursor="not-a-token")


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
            "rank INTEGER NOT NULL DEFAULT 0, "
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
            .where("id", 2)
            .increment_each_async({"score": 3, "rank": 2})
            == 1
        )
        assert (
            await _query("values_table")
            .where("id", 2)
            .decrement_each_async({"score": 2, "rank": 1})
            == 1
        )
        assert await _query("values_table").select("score", "rank").where(
            "id", 2
        ).first_async() == {"score": 17, "rank": 1}
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
        with pytest.raises(DatabaseQueryError, match="at least one"):
            query.increment_each({})
        with pytest.raises(ValueError, match="non-negative integers"):
            query.increment_each({"score": True})

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
    assert (
        query.where("id", 3).increment_each(
            {"score": 2, "rank": 3},
        )
        == 1
    )
    assert (
        query.where("id", 3).decrement_each(
            {"score": 1, "rank": 1},
        )
        == 1
    )
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
