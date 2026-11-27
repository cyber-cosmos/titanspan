"""Verify native Query Builder behavior against real SQLite.

These integration tests use SQLAlchemy Core through the application-owned
Database manager and inspect actual rows and mutations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest

from titanspan.database import (
    DatabaseQueryError,
    DatabaseServiceProvider,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_EXPECTED_VIEW_SUM = 12
_EXPECTED_REMAINING_POST_COUNT = 2
_EXPECTED_FILTERED_SCORE = 10
_PAGE_SIZE = 2
_SECOND_PAGE = 2
_THIRD_PAGE = 3
_EXPECTED_PAGE_TOTAL = 5
_EXPECTED_INSERT_USING_ROWS = 2
_EXPECTED_SECOND_PAGE_IDS = (3, 4)
_EXPECTED_LAST_PAGE_IDS = (5,)


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with an isolated SQLite database.

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
                        "database": "database/query.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_fluent_selection_conditions_order_and_pagination(
    application: Application,
) -> None:
    """Bind values and preserve explicit condition-group semantics.

    Args:
        application: Application configured by this test.
    """
    async with application:
        connection = DB.connection()
        await connection.statement_async(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT, role TEXT NOT NULL, active BOOLEAN NOT NULL, "
            "score INTEGER NOT NULL)"
        )
        await DB.table("users").insert_many_async(
            [
                {
                    "id": 1,
                    "name": "Ada",
                    "email": "ada@example.test",
                    "role": "admin",
                    "active": True,
                    "score": 10,
                },
                {
                    "id": 2,
                    "name": "Grace",
                    "email": None,
                    "role": "editor",
                    "active": True,
                    "score": 20,
                },
                {
                    "id": 3,
                    "name": "Linus",
                    "email": "linus@example.test",
                    "role": "reader",
                    "active": False,
                    "score": 30,
                },
            ]
        )

        page = await (
            DB.table("users")
            .select("id", "name", "email")
            .where(
                lambda group: group.where("role", "admin").or_where(
                    "role",
                    "editor",
                )
            )
            .where("active", True)
            .where_not_null("email")
            .order_by("name")
            .limit(1)
            .offset(0)
            .get_async()
        )

        assert page == [
            {
                "id": 1,
                "name": "Ada",
                "email": "ada@example.test",
            },
        ]


async def test_raw_expressions_bind_values_explicitly(
    application: Application,
) -> None:
    """Allow explicit SQL expressions while keeping values parameterized.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, "
            "active BOOL)"
        )
        await DB.table("users").insert_async(
            {"id": 1, "name": "Ada", "active": True},
        )

        rows = await (
            DB.table("users")
            .select_raw("name || :suffix AS label", {"suffix": "!"})
            .where_raw("active = :enabled", {"enabled": True})
            .get_async()
        )

        assert rows == [{"label": "Ada!"}]


async def test_insert_using_copies_a_query_projection(
    application: Application,
) -> None:
    """Insert selected source rows into a target table with Core expressions.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE source_rows ("
            "id INTEGER PRIMARY KEY, label TEXT NOT NULL, active BOOLEAN)"
        )
        await DB.statement_async(
            "CREATE TABLE target_rows ("
            "id INTEGER PRIMARY KEY, label TEXT NOT NULL)"
        )
        await DB.table("source_rows").insert_many_async(
            [
                {"id": 1, "label": "keep", "active": True},
                {"id": 2, "label": "skip", "active": False},
                {"id": 3, "label": "also keep", "active": True},
            ],
        )

        inserted = await DB.table("target_rows").insert_using_async(
            ("id", "label"),
            DB.table("source_rows").select("id", "label").where("active", True),
        )

        assert inserted == _EXPECTED_INSERT_USING_ROWS
        assert await DB.table("target_rows").order_by("id").get_async() == [
            {"id": 1, "label": "keep"},
            {"id": 3, "label": "also keep"},
        ]

        await DB.table("source_rows").insert_async(
            {"id": 4, "label": "sync", "active": True},
        )
        sync_inserted = await anyio.to_thread.run_sync(_insert_one_sync)
        assert sync_inserted == 1
        assert (
            await DB.table("target_rows")
            .where("id", 4)
            .value_async(
                "label",
            )
            == "sync"
        )


def _insert_one_sync() -> int:
    """Insert one filtered source row through the synchronous builder.

    Returns:
        Driver-reported affected row count.
    """
    return DB.table("target_rows").insert_using(
        ("id", "label"),
        DB.table("source_rows").select("id", "label").where("id", 4),
    )


async def test_mutations_can_return_changed_rows(
    application: Application,
) -> None:
    """Return database-produced values from SQLite insert/update/delete.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE returning_rows ("
            "id INTEGER PRIMARY KEY, label TEXT NOT NULL)"
        )

        inserted = await DB.table("returning_rows").insert_returning_async(
            {"label": "before"},
            "id",
            "label",
        )
        assert inserted == [{"id": 1, "label": "before"}]

        updated = (
            await DB.table("returning_rows")
            .where(
                "id",
                1,
            )
            .update_returning_async({"label": "after"}, "id", "label")
        )
        assert updated == [{"id": 1, "label": "after"}]

        deleted = (
            await DB.table("returning_rows")
            .where(
                "id",
                1,
            )
            .delete_returning_async("id", "label")
        )
        assert deleted == [{"id": 1, "label": "after"}]


async def test_where_exists_and_not_exists_accept_trusted_sqlalchemy_text(
    application: Application,
) -> None:
    """Filter using database-side correlated existence expressions.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await DB.statement_async(
            "CREATE TABLE posts (id INTEGER PRIMARY KEY, "
            "user_id INTEGER NOT NULL)"
        )
        await DB.table("users").insert_many_async(
            ({"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}),
        )
        await DB.table("posts").insert_async({"user_id": 1})

        authors = (
            await DB.table("users")
            .where_exists(
                "SELECT 1 FROM posts WHERE posts.user_id = users.id",
            )
            .get_async()
        )
        non_authors = (
            await DB.table("users")
            .where_not_exists(
                "SELECT 1 FROM posts WHERE posts.user_id = users.id",
            )
            .get_async()
        )

        assert [row["name"] for row in authors] == ["Ada"]
        assert [row["name"] for row in non_authors] == ["Grace"]


async def test_query_builder_join_aggregates_and_mutations(
    application: Application,
) -> None:
    """Delegate joins, aggregates, and mutations through SQLAlchemy Core.

    Args:
        application: Application configured by this test.
    """
    async with application:
        connection = DB.connection()
        await connection.statement_async(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await connection.statement_async(
            "CREATE TABLE posts ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "views INTEGER NOT NULL, title TEXT NOT NULL)"
        )
        await DB.table("users").insert_many_async(
            [
                {"id": 1, "name": "Ada"},
                {"id": 2, "name": "Grace"},
            ]
        )
        await DB.table("posts").insert_many_async(
            [
                {"id": 1, "user_id": 1, "views": 5, "title": "Core"},
                {"id": 2, "user_id": 1, "views": 7, "title": "Async"},
                {"id": 3, "user_id": 2, "views": 2, "title": "Types"},
            ]
        )

        joined = await (
            DB.table("users")
            .join("posts", "users.id", "posts.user_id")
            .select("users.name as author", "posts.title as title")
            .order_by("posts.id")
            .get_async()
        )
        views = await (
            DB.table("posts").where_between("views", 5, 10).sum_async("views")
        )
        exists = await DB.table("posts").where_in("user_id", [2]).exists_async()
        changed = (
            await DB.table("posts")
            .where("id", 3)
            .increment_async(
                "views",
                4,
            )
        )
        deleted = await DB.table("posts").where("id", 2).delete_async()
        count = await DB.table("posts").count_async()

        assert joined == [
            {"author": "Ada", "title": "Core"},
            {"author": "Ada", "title": "Async"},
            {"author": "Grace", "title": "Types"},
        ]
        assert views == _EXPECTED_VIEW_SUM
        assert exists is True
        assert changed == 1
        assert deleted == 1
        assert count == _EXPECTED_REMAINING_POST_COUNT


async def test_empty_projection_and_condition_are_no_op(
    application: Application,
) -> None:
    """Treat empty optional builder inputs as no additional clauses.

    Args:
        application: Application configured by this test.
    """
    async with application:
        connection = DB.connection()
        await connection.statement_async(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await DB.table("users").insert_async({"id": 1, "name": "Ada"})

        rows = await (
            DB.table("users").select().add_select().where({}).get_async()
        )

        assert rows == [{"id": 1, "name": "Ada"}]


async def test_sqlite_upsert_and_insert_or_ignore_are_atomic(
    application: Application,
) -> None:
    """Use SQLite conflict clauses for native bulk mutations.

    Args:
        application: Application configured with an isolated SQLite file.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE contacts ("
            "id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
            "name TEXT NOT NULL, score INTEGER NOT NULL)"
        )
        query = DB.table("contacts")

        inserted = await query.upsert_async(
            [{"email": "ada@example.test", "name": "Ada", "score": 1}],
            unique_by=("email",),
        )
        updated = await query.upsert_async(
            [
                {
                    "email": "ada@example.test",
                    "name": "Ada Lovelace",
                    "score": 2,
                },
            ],
            unique_by=("email",),
        )
        ignored_update = await query.upsert_async(
            [
                {
                    "email": "ada@example.test",
                    "name": "Ignored",
                    "score": 99,
                },
            ],
            unique_by=("email",),
            update=(),
        )
        ignored = await query.insert_or_ignore_async(
            [
                {
                    "email": "ada@example.test",
                    "name": "Ignored",
                    "score": 99,
                },
                {
                    "email": "grace@example.test",
                    "name": "Grace",
                    "score": 3,
                },
            ],
        )
        synchronous_counts = await anyio.to_thread.run_sync(
            _sync_conflict_mutations,
        )

        rows = await query.order_by("email").get_async()

        assert inserted == 1
        assert updated == 1
        assert ignored_update == 0
        assert ignored == 1
        assert synchronous_counts == (1, 0)
        assert rows == [
            {
                "id": 1,
                "email": "ada@example.test",
                "name": "Ada Lovelace",
                "score": 3,
            },
            {
                "id": 2,
                "email": "grace@example.test",
                "name": "Grace",
                "score": 3,
            },
        ]


def _sync_conflict_mutations() -> tuple[int, int]:
    """Exercise sync mutation methods on their owning worker thread.

    Returns:
        Affected-row counts for a native upsert and ignored duplicate.
    """
    query = DB.table("contacts")
    updated = query.upsert(
        [{"email": "ada@example.test", "name": "Unused", "score": 3}],
        unique_by=("email",),
        update=("score",),
    )
    ignored = query.insert_or_ignore(
        [{"email": "ada@example.test", "name": "Ignored", "score": 99}],
    )
    return updated, ignored


async def test_length_aware_and_simple_pagination(
    application: Application,
) -> None:
    """Return exact totals or use a bounded lookahead without a count query.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE page_rows ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await DB.table("page_rows").insert_many_async(
            [
                {"id": item, "name": f"row-{item}"}
                for item in range(1, _EXPECTED_PAGE_TOTAL + 1)
            ],
        )
        query = DB.table("page_rows").order_by("id")

        length_aware = await query.paginate_async(
            _PAGE_SIZE,
            page=_SECOND_PAGE,
        )
        last_page = await query.simple_paginate_async(
            _PAGE_SIZE,
            page=_THIRD_PAGE,
        )

        assert tuple(row["id"] for row in length_aware.items) == (
            _EXPECTED_SECOND_PAGE_IDS
        )
        assert length_aware.total == _EXPECTED_PAGE_TOTAL
        assert length_aware.last_page == _THIRD_PAGE
        assert length_aware.previous_page == 1
        assert length_aware.next_page == _THIRD_PAGE
        assert tuple(row["id"] for row in last_page.items) == (
            _EXPECTED_LAST_PAGE_IDS
        )
        assert last_page.has_more_pages is False
        assert last_page.next_page is None
        assert await query.limit(1).count_async() == _EXPECTED_PAGE_TOTAL


async def test_query_builder_binds_values_and_rejects_identifiers(
    application: Application,
) -> None:
    """Treat ordinary values as parameters and reject unsafe SQL names.

    Args:
        application: Application configured by this test.
    """
    async with application:
        connection = DB.connection()
        await connection.statement_async(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await DB.table("users").insert_async({"id": 1, "name": "Ada"})
        malicious_value = "Ada' OR 1 = 1 --"

        rows = await (
            DB.table("users").where("name", malicious_value).get_async()
        )

        assert rows == []
        assert await DB.table("users").count_async() == 1
        with pytest.raises(DatabaseQueryError):
            DB.table("users").where("name; DROP TABLE users", "Ada")
        with pytest.raises(DatabaseQueryError):
            DB.table("users").where("name", "= OR 1=1", "Ada")


async def test_query_builder_clones_branch_filters_without_mutating_parent(
    application: Application,
) -> None:
    """Keep a cloned query independent from its source builder.

    Args:
        application: Application configured by this test.
    """
    async with application:
        connection = DB.connection()
        await connection.statement_async(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, active BOOLEAN)"
        )
        await DB.table("users").insert_many_async(
            [
                {"id": 1, "active": True},
                {"id": 2, "active": False},
            ]
        )
        active = DB.table("users").where("active", True)
        inactive = active.clone().where("active", False)

        assert await active.count_async() == 1
        assert await inactive.count_async() == 0


async def test_query_builder_filters_and_aggregates_composed_results(
    application: Application,
) -> None:
    """Compose negative filters, grouped aggregates, and scalar retrieval.

    Args:
        application: Application configured by this test.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, score INTEGER, "
            "active BOOLEAN NOT NULL)"
        )
        await DB.table("users").insert_many_async(
            [
                {"id": 1, "name": "Ada", "score": 10, "active": True},
                {"id": 2, "name": "Grace", "score": 20, "active": True},
                {"id": 3, "name": "Linus", "score": 30, "active": False},
                {"id": 4, "name": "No score", "score": None, "active": True},
            ]
        )

        query = (
            DB.table("users")
            .where("active", True)
            .where_not_between("score", 15, 25)
            .where_not_like("name", "No%")
            .where_not_null("score")
        )

        assert await query.clone().count_async() == 1
        assert (
            await query.clone().avg_async("score") == _EXPECTED_FILTERED_SCORE
        )
        assert (
            await query.clone().min_async("score") == _EXPECTED_FILTERED_SCORE
        )
        assert (
            await query.clone().max_async("score") == _EXPECTED_FILTERED_SCORE
        )
        assert await query.clone().doesnt_exist_async() is False
        assert await query.clone().value_async("name") == "Ada"
        assert await query.clone().pluck_async("name") == ["Ada"]

        grouped = (
            DB.table("users")
            .select("active")
            .group_by("active")
            .having("active", True)
            .order_by("active")
        )
        assert await grouped.get_async() == [{"active": True}]


async def test_subquery_join_preserves_fluent_alias_columns(
    application: Application,
) -> None:
    """Join a composed subquery through validated alias-qualified columns.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await DB.statement_async(
            "CREATE TABLE posts (id INTEGER PRIMARY KEY, user_id INTEGER, "
            "title TEXT NOT NULL, views INTEGER NOT NULL)"
        )
        await DB.table("users").insert_many_async(
            ({"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}),
        )
        await DB.table("posts").insert_many_async(
            (
                {
                    "id": 1,
                    "user_id": 1,
                    "title": "Popular",
                    "views": 100,
                },
                {
                    "id": 2,
                    "user_id": 2,
                    "title": "Quiet",
                    "views": 10,
                },
            ),
        )
        popular_posts = (
            DB.table("posts")
            .select("user_id", "title")
            .where("views", ">=", 50)
        )

        rows = await (
            DB.table("users")
            .join_sub(
                popular_posts,
                "popular",
                "users.id",
                "=",
                "popular.user_id",
            )
            .select("users.name", "popular.title")
            .get_async()
        )

        assert rows == [{"name": "Ada", "title": "Popular"}]

        all_users = await (
            DB.table("users")
            .left_join_sub(
                popular_posts,
                "popular",
                "users.id",
                "=",
                "popular.user_id",
            )
            .select("users.name", "popular.title")
            .order_by("users.id")
            .get_async()
        )
        assert all_users == [
            {"name": "Ada", "title": "Popular"},
            {"name": "Grace", "title": None},
        ]


async def test_generated_ids_and_atomic_update_or_insert(
    application: Application,
) -> None:
    """Retrieve generated IDs and delegate insert-or-update atomically.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE settings (id INTEGER PRIMARY KEY, "
            "name TEXT NOT NULL UNIQUE, value TEXT NOT NULL)"
        )

        identifier = await DB.table("settings").insert_get_id_async(
            {"name": "mode", "value": "old"},
        )
        assert identifier == 1

        await DB.table("settings").update_or_insert_async(
            {"name": "mode"},
            {"value": "new"},
        )
        await DB.table("settings").update_or_insert_async(
            {"name": "region"},
            {"value": "west"},
        )

        rows = await DB.table("settings").order_by("id").get_async()
        assert rows == [
            {"id": 1, "name": "mode", "value": "new"},
            {"id": 2, "name": "region", "value": "west"},
        ]
        conditional = await (
            DB.table("settings")
            .when(
                False,
                lambda builder: builder.where("name", "missing"),
                lambda builder: builder.where("name", "mode"),
            )
            .unless(
                False,
                lambda builder: builder.where("value", "new"),
            )
            .sole_async()
        )
        assert conditional["id"] == 1

        with pytest.raises(DatabaseQueryError, match="cannot change"):
            await DB.table("settings").update_or_insert_async(
                {"name": "mode"},
                {"name": "changed"},
            )


async def test_ctes_unions_and_outer_union_filters(
    application: Application,
) -> None:
    """Compose CTE, UNION, UNION ALL, and post-union conditions.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE entries (id INTEGER PRIMARY KEY, "
            "category TEXT NOT NULL)"
        )
        await DB.table("entries").insert_many_async(
            (
                {"id": 1, "category": "alpha"},
                {"id": 2, "category": "alpha"},
                {"id": 3, "category": "beta"},
            ),
        )
        counts = (
            DB.table("entries")
            .select("category")
            .select_raw("COUNT(*) AS total")
            .group_by("category")
        )
        cte_rows = await (
            DB.table("entry_counts")
            .with_cte("entry_counts", counts)
            .select("category", "total")
            .order_by("category")
            .get_async()
        )
        assert cte_rows == [
            {"category": "alpha", "total": 2},
            {"category": "beta", "total": 1},
        ]

        scalar_row = await (
            DB.table("entries")
            .add_select_sub(
                DB.table("entries").select("id").where("id", 1),
                "first_entry_id",
            )
            .first_async()
        )
        assert scalar_row == {"first_entry_id": 1}

        duplicate_cte = DB.table("entry_counts").with_cte(
            "entry_counts",
            counts,
        )
        with pytest.raises(DatabaseQueryError, match="unique safe name"):
            duplicate_cte.with_cte("entry_counts", counts)

        first = DB.table("entries").select("id").where("id", "<=", 2)
        second = DB.table("entries").select("id").where("id", ">=", 2)
        unique_rows = await (
            first.union(second).where("id", ">", 1).order_by("id").get_async()
        )
        repeated_rows = await (
            DB.table("entries")
            .select("id")
            .where("id", 2)
            .union_all(
                DB.table("entries").select("id").where("id", 2),
            )
            .get_async()
        )

        assert unique_rows == [{"id": 2}, {"id": 3}]
        assert repeated_rows == [{"id": 2}, {"id": 2}]
