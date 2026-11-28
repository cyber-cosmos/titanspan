"""Verify PostgreSQL behavior when an isolated test URL is configured.

The required CI flag turns a missing URL into a test failure.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING, ClassVar

import anyio
import pytest
from sqlalchemy import ForeignKey
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Mapped, mapped_column
from tests.integration.database.postgresql_support import (
    configured_postgres_url,
)

from titanspan.database import (
    DatabaseServiceProvider,
    DatabaseTransactionError,
    MigrationManager,
    Model,
    MorphTo,
    Schema,
    latest_of_many,
    morph_to,
    oldest_of_many,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_DATABASE_PREFIX = "titanspan_codex_test_"
_CONCURRENT_TASK_COUNT = 2
_EXPECTED_UPSERTED_SCORE = 2
_EXPECTED_INCREMENT_VALUES = [1, 2]
_UNKNOWN_ROWCOUNT = -1
_ROLLBACK_MARKER = "rollback marker"
_MIGRATION_UP = '''    def up(self) -> None:
        """Apply this revision's schema changes."""
        with Schema.create("postgres_migration_rows") as table:
            table.id()
            table.string("name")
'''
_MIGRATION_DOWN = '''    def down(self) -> None:
        """Reverse this revision's schema changes."""
        with Schema.drop_if_exists("postgres_migration_rows"):
            pass
'''


class PostgreSQLAtomicCounter(Model):
    """Represent a counter row updated by independent PostgreSQL sessions.
    """  # fmt: skip

    table = "postgres_atomic_counters"
    fillable = ("value",)
    timestamps = False

    value: Mapped[int] = mapped_column(default=0)


class PostgreSQLUpsertRecord(Model):
    """Represent a mapped row written through native model upsert.

    A Python attribute maps to a differently named SQL column to verify
    mapper-based identifier translation on PostgreSQL.
    """

    table = "postgres_model_upserts"
    fillable = ("email", "name")

    email: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column("display_name")
    is_admin: Mapped[bool] = mapped_column(default=False)


class PostgreSQLOneOfManyChild(Model):
    """Represent a PostgreSQL child row selected by parent and primary key.

    The relationship loader must apply its row-number predicate on PostgreSQL.
    """

    table = "postgres_one_of_many_children"
    timestamps = False
    fillable = ("parent_id", "label")

    parent_id: Mapped[int] = mapped_column(
        ForeignKey("postgres_one_of_many_parents.id"),
    )
    label: Mapped[str]


class PostgreSQLOneOfManyParent(Model):
    """Represent a PostgreSQL parent with latest and oldest child views.

    The row-limited relations are read-only SQLAlchemy mappings.
    """

    table = "postgres_one_of_many_parents"
    timestamps = False
    fillable = ("label",)

    label: Mapped[str]
    latest_child: Mapped[PostgreSQLOneOfManyChild | None] = latest_of_many(
        PostgreSQLOneOfManyChild,
        "parent_id",
    )
    oldest_child: Mapped[PostgreSQLOneOfManyChild | None] = oldest_of_many(
        PostgreSQLOneOfManyChild,
        "parent_id",
    )


class PostgreSQLMorphTarget(Model):
    """Represent one explicitly mapped PostgreSQL polymorphic target.

    The class is selected by an application-owned discriminator alias.
    """

    table = "postgres_morph_targets"
    timestamps = False
    fillable = ("label",)

    label: Mapped[str]


class PostgreSQLMorphSource(Model):
    """Represent one PostgreSQL row with a polymorphic target reference.

    The target class is resolved through the app-scoped trusted morph map.
    """

    table = "postgres_morph_sources"
    timestamps = False
    fillable = ("label", "subject_type", "subject_id")

    label: Mapped[str]
    subject_type: Mapped[str | None]
    subject_id: Mapped[int | None]
    subject: ClassVar[MorphTo[PostgreSQLMorphTarget]] = morph_to(
        PostgreSQLMorphTarget,
        type_column="subject_type",
        foreign_key="subject_id",
    )


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create a Postgres test application after validating its DB identity.

    Args:
        tmp_path: Temporary application root provided by Pytest.

    Returns:
        An app configured only for a named, disposable test database.
    """
    url = configured_postgres_url()
    if not (make_url(url).database or "").startswith(_DATABASE_PREFIX):
        pytest.fail("Postgres integration requires a disposable test database.")
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "postgres",
                "connections": {
                    "postgres": {
                        "url": url,
                        "async_url": url,
                    },
                },
                "morph_map": {
                    "postgres_target": PostgreSQLMorphTarget,
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_postgresql_transactions_and_concurrent_sessions(
    application: Application,
) -> None:
    """Verify real DDL, rollback, and isolated concurrent async sessions.

    Args:
        application: Isolated Postgres integration application.
    """
    async with application:
        async with Schema.create("database_test_rows") as table:
            table.id()
            table.string("name", length=100).unique()

        with pytest.raises(RuntimeError, match=_ROLLBACK_MARKER):
            await _insert_then_raise()

        assert await DB.table("database_test_rows").count_async() == 0

        ready = anyio.Event()
        release = anyio.Event()
        rendezvous_lock = anyio.Lock()
        ready_count = 0

        async def insert_row(name: str) -> None:
            """Insert one independent row in a synchronized transaction.

            Args:
                name: Unique row value for this concurrent task.
            """
            nonlocal ready_count
            async with DB.transaction_async():
                await DB.table("database_test_rows").insert_async(
                    {"name": name},
                )
                async with rendezvous_lock:
                    ready_count += 1
                    if ready_count == _CONCURRENT_TASK_COUNT:
                        ready.set()
                await release.wait()

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(insert_row, "first")
            tasks.start_soon(insert_row, "second")
            await ready.wait()
            release.set()

        assert (
            await DB.table("database_test_rows").count_async()
            == _CONCURRENT_TASK_COUNT
        )
        await Schema.drop_if_exists("database_test_rows").apply_async()

        migrations = await application.container.make_async(MigrationManager)
        path = migrations.create_revision("postgres migration round trip")
        source = path.read_text(encoding="utf-8")
        source = source.replace(
            "from titanspan.database import Migration, run_migration",
            "from titanspan.database import Migration, Schema, run_migration",
        )
        source = source.replace(
            "    def up(self) -> None:\n"
            '        """Apply this revision\'s schema changes."""\n'
            "        pass\n",
            _MIGRATION_UP,
        )
        source = source.replace(
            "    def down(self) -> None:\n"
            '        """Reverse this revision\'s schema changes."""\n'
            "        pass\n",
            _MIGRATION_DOWN,
        )
        path.write_text(source, encoding="utf-8")
        await migrations.upgrade_async(isolated=True)

        assert await Schema.has_table_async("postgres_migration_rows")

        await migrations.rollback_async()

        assert not await Schema.has_table_async("postgres_migration_rows")


async def test_postgresql_one_of_many_relationships_use_ranked_rows(
    application: Application,
) -> None:
    """Load deterministic latest and oldest rows from real PostgreSQL.

    Args:
        application: Isolated Postgres integration application.
    """
    async with application:
        await DB.statement_async(
            "DROP TABLE IF EXISTS postgres_one_of_many_children",
        )
        await DB.statement_async(
            "DROP TABLE IF EXISTS postgres_one_of_many_parents",
        )
        try:
            await DB.statement_async(
                "CREATE TABLE postgres_one_of_many_parents ("
                "id SERIAL PRIMARY KEY, label TEXT NOT NULL, "
                "created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)"
            )
            await DB.statement_async(
                "CREATE TABLE postgres_one_of_many_children ("
                "id SERIAL PRIMARY KEY, parent_id INTEGER NOT NULL, "
                "label TEXT NOT NULL, created_at TIMESTAMPTZ, "
                "updated_at TIMESTAMPTZ, "
                "FOREIGN KEY(parent_id) "
                "REFERENCES postgres_one_of_many_parents(id))"
            )
            parent = await PostgreSQLOneOfManyParent.create_async(
                {"label": "parent"},
            )
            first = await PostgreSQLOneOfManyChild.create_async(
                {"parent_id": parent.id, "label": "first"},
            )
            latest = await PostgreSQLOneOfManyChild.create_async(
                {"parent_id": parent.id, "label": "latest"},
            )

            loaded = await (
                PostgreSQLOneOfManyParent.query()
                .with_("latest_child", "oldest_child")
                .where("id", parent.id)
                .first_or_fail_async()
            )

            assert loaded.latest_child is not None
            assert loaded.latest_child.id == latest.id
            assert loaded.oldest_child is not None
            assert loaded.oldest_child.id == first.id
        finally:
            await DB.statement_async(
                "DROP TABLE IF EXISTS postgres_one_of_many_children",
            )
            await DB.statement_async(
                "DROP TABLE IF EXISTS postgres_one_of_many_parents",
            )


async def test_postgresql_morph_to_resolves_trusted_target(
    application: Application,
) -> None:
    """Resolve and persist a polymorphic association on real PostgreSQL.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async(
            "DROP TABLE IF EXISTS postgres_morph_sources",
        )
        await DB.statement_async(
            "DROP TABLE IF EXISTS postgres_morph_targets",
        )
        try:
            await DB.statement_async(
                "CREATE TABLE postgres_morph_targets ("
                "id SERIAL PRIMARY KEY, label TEXT NOT NULL, "
                "created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)"
            )
            await DB.statement_async(
                "CREATE TABLE postgres_morph_sources ("
                "id SERIAL PRIMARY KEY, label TEXT NOT NULL, "
                "subject_type TEXT, subject_id INTEGER, "
                "created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)"
            )
            target = await PostgreSQLMorphTarget.create_async(
                {"label": "target"},
            )
            source = await PostgreSQLMorphSource.create_async(
                {
                    "label": "source",
                    "subject_type": "postgres_target",
                    "subject_id": target.id,
                },
            )

            resolved = await source.subject.resolve_async()

            assert isinstance(resolved, PostgreSQLMorphTarget)
            assert resolved.id == target.id
            source.subject.dissociate()
            assert source.subject_type is None
            assert source.subject_id is None
        finally:
            await DB.statement_async(
                "DROP TABLE IF EXISTS postgres_morph_sources",
            )
            await DB.statement_async(
                "DROP TABLE IF EXISTS postgres_morph_targets",
            )


async def test_postgresql_model_increments_are_atomic(
    application: Application,
) -> None:
    """Preserve both increments through competing real database sessions.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async(
            "DROP TABLE IF EXISTS postgres_atomic_counters",
        )
        await DB.statement_async(
            "CREATE TABLE postgres_atomic_counters ("
            "id BIGSERIAL PRIMARY KEY, value BIGINT NOT NULL, "
            "created_at TIMESTAMPTZ NULL, updated_at TIMESTAMPTZ NULL)"
        )
        counter = await PostgreSQLAtomicCounter.create_async({"value": 0})
        first = await PostgreSQLAtomicCounter.find_async(counter.id)
        second = await PostgreSQLAtomicCounter.find_async(counter.id)
        assert first is not None
        assert second is not None

        ready = anyio.Event()
        rendezvous_lock = anyio.Lock()
        ready_count = 0
        observed_values: list[int] = []

        async def increment(model: PostgreSQLAtomicCounter) -> None:
            """Run one instance increment after both models are ready.

            Args:
                model: Detached model loaded in an independent operation.
            """
            nonlocal ready_count
            async with rendezvous_lock:
                ready_count += 1
                if ready_count == _CONCURRENT_TASK_COUNT:
                    ready.set()
            await ready.wait()
            assert await model.increment_async("value")
            observed_values.append(model.value)

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(increment, first)
            tasks.start_soon(increment, second)

        assert sorted(observed_values) == _EXPECTED_INCREMENT_VALUES
        assert (
            await PostgreSQLAtomicCounter.query().value_async("value")
            == _CONCURRENT_TASK_COUNT
        )
        await DB.statement_async(
            "DROP TABLE postgres_atomic_counters",
        )


async def test_postgresql_upsert_and_insert_or_ignore_are_atomic(
    application: Application,
) -> None:
    """Use PostgreSQL ON CONFLICT for native insert-or-update operations.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async("DROP TABLE IF EXISTS postgres_upsert_rows")
        await DB.statement_async(
            "CREATE TABLE postgres_upsert_rows ("
            "id BIGSERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL, "
            "name TEXT NOT NULL, score INTEGER NOT NULL)"
        )
        query = DB.table("postgres_upsert_rows")

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
        ignored = await query.insert_or_ignore_async(
            [
                {
                    "email": "ada@example.test",
                    "name": "Ignored",
                    "score": 99,
                },
            ],
        )
        row = await query.where("email", "ada@example.test").first_async()

        assert inserted in (1, _UNKNOWN_ROWCOUNT)
        assert updated in (1, _UNKNOWN_ROWCOUNT)
        assert ignored in (0, _UNKNOWN_ROWCOUNT)
        assert row is not None
        assert row["name"] == "Ada Lovelace"
        assert row["score"] == _EXPECTED_UPSERTED_SCORE
        assert await query.count_async() == 1
        await DB.statement_async("DROP TABLE postgres_upsert_rows")


async def test_postgresql_model_upsert_uses_mapper_and_assignment_policy(
    application: Application,
) -> None:
    """Upsert model values atomically with timestamps and guarded fields.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async("DROP TABLE IF EXISTS postgres_model_upserts")
        await DB.statement_async(
            "CREATE TABLE postgres_model_upserts ("
            "id BIGSERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL, "
            "display_name TEXT NOT NULL, "
            "is_admin BOOLEAN NOT NULL DEFAULT FALSE, "
            "created_at TIMESTAMPTZ NULL, updated_at TIMESTAMPTZ NULL)"
        )
        inserted = await PostgreSQLUpsertRecord.upsert_async(
            [
                {
                    "email": "ada@example.test",
                    "name": "Ada",
                    "is_admin": True,
                },
            ],
            unique_by=("email",),
        )
        original = await PostgreSQLUpsertRecord.query().first_async()
        assert original is not None

        updated = await PostgreSQLUpsertRecord.upsert_async(
            [
                {
                    "email": "ada@example.test",
                    "name": "Augusta",
                    "is_admin": True,
                },
            ],
            unique_by=("email",),
        )
        current = await PostgreSQLUpsertRecord.query().first_async()

        assert inserted in (1, _UNKNOWN_ROWCOUNT)
        assert updated in (1, _UNKNOWN_ROWCOUNT)
        assert current is not None
        assert current.name == "Augusta"
        assert current.is_admin is False
        assert current.created_at == original.created_at
        assert current.updated_at is not None
        await DB.statement_async("DROP TABLE postgres_model_upserts")


async def test_postgresql_row_locks_require_and_use_transactions(
    application: Application,
) -> None:
    """Execute row-lock SQL only inside the owning PostgreSQL transaction.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async("DROP TABLE IF EXISTS postgres_lock_rows")
        await DB.statement_async(
            "CREATE TABLE postgres_lock_rows ("
            "id BIGSERIAL PRIMARY KEY, value TEXT NOT NULL)"
        )
        await DB.table("postgres_lock_rows").insert_async(
            {"value": "available"},
        )

        with pytest.raises(
            DatabaseTransactionError,
            match="active transaction",
        ):
            DB.table("postgres_lock_rows").lock_for_update()

        async with DB.transaction_async():
            locked = (
                DB.table("postgres_lock_rows")
                .where("value", "available")
                .lock_for_update(skip_locked=True)
            )
            row = await locked.first_async()
            assert row is not None
            assert row["value"] == "available"

        with pytest.raises(
            DatabaseTransactionError,
            match="active transaction",
        ):
            await locked.get_async()

        async with DB.transaction_async():
            stale_cursor = (
                DB.table("postgres_lock_rows").lock_for_update().cursor_async()
            )

        with pytest.raises(
            DatabaseTransactionError,
            match="active transaction",
        ):
            async with stale_cursor:
                pass

        await DB.statement_async("DROP TABLE postgres_lock_rows")


async def test_postgresql_temporal_query_predicates(
    application: Application,
) -> None:
    """Compare temporal predicates against real timestamptz data.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async(
            "DROP TABLE IF EXISTS postgres_temporal_rows",
        )
        await DB.statement_async(
            "CREATE TABLE postgres_temporal_rows ("
            "id BIGSERIAL PRIMARY KEY, occurred_at TIMESTAMPTZ NOT NULL)"
        )
        await DB.table("postgres_temporal_rows").insert_many_async(
            [
                {
                    "occurred_at": datetime(
                        2026,
                        11,
                        27,
                        8,
                        30,
                        tzinfo=UTC,
                    ),
                },
                {
                    "occurred_at": datetime(
                        2026,
                        11,
                        27,
                        14,
                        45,
                        tzinfo=UTC,
                    ),
                },
                {
                    "occurred_at": datetime(
                        2026,
                        11,
                        28,
                        8,
                        30,
                        tzinfo=UTC,
                    ),
                },
            ],
        )

        date_rows = (
            await DB.table("postgres_temporal_rows")
            .where_date(
                "occurred_at",
                date(2026, 11, 27),
            )
            .order_by("id")
            .get_async()
        )
        assert [row["id"] for row in date_rows] == [1, 2]

        time_rows = (
            await DB.table("postgres_temporal_rows")
            .where_time(
                "occurred_at",
                ">=",
                time(12),
            )
            .get_async()
        )
        assert [row["id"] for row in time_rows] == [2]

        component_rows = (
            await DB.table(
                "postgres_temporal_rows",
            )
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
        await DB.statement_async("DROP TABLE postgres_temporal_rows")


async def test_postgresql_json_path_predicates(
    application: Application,
) -> None:
    """Compare typed scalars extracted from a real PostgreSQL JSONB value.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async("DROP TABLE IF EXISTS postgres_json_rows")
        await DB.statement_async(
            "CREATE TABLE postgres_json_rows ("
            "id BIGSERIAL PRIMARY KEY, payload JSONB NOT NULL)"
        )
        await DB.statement_async(
            "INSERT INTO postgres_json_rows (payload) "
            "VALUES (CAST(:payload AS JSONB))",
            {"payload": '{"profile":{"active":true,"score":12}}'},
        )

        active = (
            await DB.table("postgres_json_rows")
            .where_json_value(
                "payload",
                "profile.active",
                True,
            )
            .first_async()
        )
        high_score = (
            await DB.table("postgres_json_rows")
            .where_json_value(
                "payload",
                "profile.score",
                ">=",
                10,
            )
            .first_async()
        )
        assert active is not None
        assert high_score is not None
        assert active["id"] == high_score["id"]
        await DB.statement_async("DROP TABLE postgres_json_rows")


async def test_postgresql_json_containment_key_and_array_length(
    application: Application,
) -> None:
    """Query JSONB containment, nested keys, and array lengths.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE postgres_json_advanced_rows ("
            "id INTEGER PRIMARY KEY, payload JSONB NOT NULL)"
        )
        await DB.statement_async(
            "INSERT INTO postgres_json_advanced_rows (id, payload) VALUES "
            "(1, CAST(:first AS JSONB)), (2, CAST(:second AS JSONB)), "
            "(3, CAST(:third AS JSONB))",
            {
                "first": (
                    '{"labels":["agents","python"],'
                    '"metadata":{"reviewed":true,"nullable":null}}'
                ),
                "second": '{"labels":["python"],"metadata":{}}',
                "third": '{"labels":[],"metadata":{}}',
            },
        )

        contained = await (
            DB.table("postgres_json_advanced_rows")
            .select("id")
            .where_json_contains("payload", "labels", ["python"])
            .order_by("id")
            .get_async()
        )
        with_nullable_key = await (
            DB.table("postgres_json_advanced_rows")
            .where_json_contains_key("payload", "metadata.nullable")
            .first_async()
        )
        without_contained_value = await (
            DB.table("postgres_json_advanced_rows")
            .select("id")
            .where_json_doesnt_contain(
                "payload",
                "labels",
                ["agents"],
            )
            .order_by("id")
            .get_async()
        )
        without_key = await (
            DB.table("postgres_json_advanced_rows")
            .select("id")
            .where_json_doesnt_contain_key("payload", "metadata.nullable")
            .order_by("id")
            .get_async()
        )
        long_arrays = await (
            DB.table("postgres_json_advanced_rows")
            .where_json_length("payload", "labels", ">", 1)
            .get_async()
        )
        or_long_arrays = await (
            DB.table("postgres_json_advanced_rows")
            .select("id")
            .where("id", 3)
            .or_where_json_length("payload", "labels", ">", 1)
            .order_by("id")
            .get_async()
        )

        assert contained == [{"id": 1}, {"id": 2}]
        assert with_nullable_key is not None
        assert with_nullable_key["id"] == 1
        assert without_contained_value == [{"id": 2}, {"id": 3}]
        assert without_key == [{"id": 2}, {"id": 3}]
        assert [row["id"] for row in long_arrays] == [1]
        assert or_long_arrays == [{"id": 1}, {"id": 3}]
        assert (
            await DB.table("postgres_json_advanced_rows")
            .where("id", 1)
            .update_json_async("payload", "metadata.reviewed", False)
        ) == 1
        updated = await (
            DB.table("postgres_json_advanced_rows")
            .where_json_value("payload", "metadata.reviewed", False)
            .first_async()
        )
        assert updated is not None
        assert updated["id"] == 1
        await DB.statement_async("DROP TABLE postgres_json_advanced_rows")


async def test_postgresql_mutations_return_rows(
    application: Application,
) -> None:
    """Use native PostgreSQL RETURNING for insert, update, and delete.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async(
            "DROP TABLE IF EXISTS postgres_returning_rows",
        )
        await DB.statement_async(
            "CREATE TABLE postgres_returning_rows ("
            "id BIGSERIAL PRIMARY KEY, label TEXT NOT NULL)"
        )
        inserted = await DB.table(
            "postgres_returning_rows",
        ).insert_returning_async(
            {"label": "before"},
            "id",
            "label",
        )
        assert inserted == [{"id": 1, "label": "before"}]

        updated = (
            await DB.table("postgres_returning_rows")
            .where(
                "id",
                1,
            )
            .update_returning_async({"label": "after"}, "id", "label")
        )
        assert updated == [{"id": 1, "label": "after"}]

        deleted = (
            await DB.table("postgres_returning_rows")
            .where(
                "id",
                1,
            )
            .delete_returning_async("id", "label")
        )
        assert deleted == [{"id": 1, "label": "after"}]
        await DB.statement_async("DROP TABLE postgres_returning_rows")


async def test_postgresql_right_and_full_outer_joins(
    application: Application,
) -> None:
    """Preserve unmatched rows through native right and full outer joins.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async(
            "DROP TABLE IF EXISTS postgres_join_posts",
        )
        await DB.statement_async(
            "DROP TABLE IF EXISTS postgres_join_users",
        )
        await DB.statement_async(
            "CREATE TABLE postgres_join_users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await DB.statement_async(
            "CREATE TABLE postgres_join_posts ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "title TEXT NOT NULL)"
        )
        await DB.table("postgres_join_users").insert_many_async(
            [
                {"id": 1, "name": "Ada"},
                {"id": 2, "name": "Grace"},
            ],
        )
        await DB.table("postgres_join_posts").insert_many_async(
            [
                {"id": 1, "user_id": 1, "title": "matched"},
                {"id": 2, "user_id": 3, "title": "orphan"},
            ],
        )

        right_rows = await (
            DB.table("postgres_join_users")
            .right_join(
                "postgres_join_posts",
                "postgres_join_users.id",
                "postgres_join_posts.user_id",
            )
            .select("postgres_join_users.name", "postgres_join_posts.title")
            .get_async()
        )
        full_rows = await (
            DB.table("postgres_join_users")
            .full_outer_join(
                "postgres_join_posts",
                "postgres_join_users.id",
                "postgres_join_posts.user_id",
            )
            .select("postgres_join_users.name", "postgres_join_posts.title")
            .order_by("postgres_join_users.id")
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
        await DB.statement_async("DROP TABLE postgres_join_posts")
        await DB.statement_async("DROP TABLE postgres_join_users")


async def test_postgresql_row_value_comparisons(
    application: Application,
) -> None:
    """Execute a bound row-value comparison against PostgreSQL.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE postgres_tuple_rows ("
            "id INTEGER PRIMARY KEY, first_value INTEGER, "
            "second_value INTEGER)"
        )
        await DB.table("postgres_tuple_rows").insert_many_async(
            [
                {"id": 1, "first_value": 1, "second_value": 2},
                {"id": 2, "first_value": 1, "second_value": 3},
                {"id": 3, "first_value": 2, "second_value": 0},
            ],
        )

        rows = await (
            DB.table("postgres_tuple_rows")
            .where_row_values(
                ("first_value", "second_value"),
                ">",
                (1, 2),
            )
            .order_by("id")
            .pluck_async("id")
        )

        assert rows == [2, 3]
        await DB.statement_async("DROP TABLE postgres_tuple_rows")


async def test_postgresql_lateral_subquery_joins(
    application: Application,
) -> None:
    """Join correlated per-parent selections through PostgreSQL LATERAL.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE postgres_lateral_users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        await DB.statement_async(
            "CREATE TABLE postgres_lateral_posts ("
            "id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT NOT NULL)"
        )
        await DB.table("postgres_lateral_users").insert_many_async(
            [
                {"id": 1, "name": "Ada"},
                {"id": 2, "name": "Grace"},
            ],
        )
        await DB.table("postgres_lateral_posts").insert_many_async(
            [
                {"id": 1, "user_id": 1, "title": "older"},
                {"id": 2, "user_id": 1, "title": "newer"},
            ],
        )

        users = DB.table("postgres_lateral_users")
        latest_post = (
            users.subquery("postgres_lateral_posts")
            .select("title")
            .where_column(
                "postgres_lateral_posts.user_id",
                "=",
                "postgres_lateral_users.id",
            )
            .order_by("postgres_lateral_posts.id", descending=True)
            .limit(1)
        )
        inner_rows = await (
            users.clone()
            .join_lateral(latest_post, "latest_post")
            .select("postgres_lateral_users.name", "latest_post.title")
            .order_by("postgres_lateral_users.id")
            .get_async()
        )
        left_rows = await (
            users.clone()
            .left_join_lateral(latest_post, "latest_post")
            .select("postgres_lateral_users.name", "latest_post.title")
            .order_by("postgres_lateral_users.id")
            .get_async()
        )

        assert inner_rows == [{"name": "Ada", "title": "newer"}]
        assert left_rows == [
            {"name": "Ada", "title": "newer"},
            {"name": "Grace", "title": None},
        ]
        await DB.statement_async("DROP TABLE postgres_lateral_posts")
        await DB.statement_async("DROP TABLE postgres_lateral_users")


async def test_postgresql_full_text_queries(
    application: Application,
) -> None:
    """Search one or more columns through PostgreSQL text-search expressions.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE postgres_full_text_docs ("
            "id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL)"
        )
        await DB.table("postgres_full_text_docs").insert_many_async(
            [
                {
                    "id": 1,
                    "title": "Titanspan guide",
                    "body": "Async intelligent systems",
                },
                {
                    "id": 2,
                    "title": "SQL patterns",
                    "body": "Relational database design",
                },
                {
                    "id": 3,
                    "title": "Other guide",
                    "body": "Search examples",
                },
            ],
        )

        rows = await (
            DB.table("postgres_full_text_docs")
            .select("id")
            .where_full_text(("title", "body"), "titanspan async")
            .or_where_full_text("body", "relational")
            .order_by("id")
            .get_async()
        )
        assert rows == [{"id": 1}, {"id": 2}]
        await DB.statement_async("DROP TABLE postgres_full_text_docs")


async def test_postgresql_explain_returns_a_bound_query_plan(
    application: Application,
) -> None:
    """Inspect a PostgreSQL plan while keeping query values parameterized.

    Args:
        application: Isolated PostgreSQL integration application.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE postgres_explain_rows ("
            "id INTEGER PRIMARY KEY, label TEXT NOT NULL)"
        )
        await DB.table("postgres_explain_rows").insert_many_async(
            [
                {"id": 1, "label": "private-one"},
                {"id": 2, "label": "private-two"},
            ],
        )

        plan = await (
            DB.table("postgres_explain_rows")
            .select("id")
            .where_in("id", [1, 2])
            .explain_async()
        )

        assert plan
        assert "private-one" not in str(plan)
        await DB.statement_async("DROP TABLE postgres_explain_rows")


async def _insert_then_raise() -> None:
    """Roll a PostgreSQL insert back through the application transaction.

    Raises:
        RuntimeError: The deliberate failure used to verify rollback.
    """
    async with DB.transaction_async():
        await DB.table("database_test_rows").insert_async(
            {"name": "rolled back"},
        )
        raise RuntimeError(_ROLLBACK_MARKER)
