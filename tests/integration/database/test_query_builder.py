"""Verify native Query Builder behavior against real SQLite.

These integration tests use SQLAlchemy Core through the application-owned
Database manager and inspect actual rows and mutations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
