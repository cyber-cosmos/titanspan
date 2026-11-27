"""Verify Active Record behavior with the application Database service.

These tests use SQLAlchemy's real mapper and an isolated SQLite database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy import ForeignKey, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titanspan.database import (
    DatabaseManager,
    DatabaseQueryError,
    DatabaseServiceProvider,
    DatabaseTransactionOwnershipError,
    Model,
    ModelCollection,
    ModelNotFoundError,
    MultipleModelsFoundError,
    SoftDeletes,
    has_many,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_EXPECTED_USER_NAME = "Ada"
_EXPECTED_USER_TOTAL = 2
_EXPECTED_COLLECTION_SIZE = 2
_EXPECTED_EAGER_QUERY_COUNT = 2
_EXPECTED_EAGER_POST_COUNT = 2
_STATEMENT_EVENT_ARGUMENT_INDEX = 2
_MINIMUM_STATEMENT_EVENT_ARGUMENTS = 3
_PAGE_SIZE = 1
_SECOND_PAGE = 2
_EXPECTED_POST_COUNT = 2
_EXPECTED_BULK_MODEL_COUNT = 2
_EXPECTED_DESTROYED_MODEL_COUNT = 1
_EXPECTED_LOGIN_COUNT_AFTER_INCREMENT = 2
_EXPECTED_LOGIN_COUNT_AFTER_DECREMENT = 1
_EXPECTED_LOGIN_COUNT_AFTER_BULK_INCREMENT = 3
_EXPECTED_LOGIN_COUNT_AFTER_SYNC_INCREMENT = 5
_SYNC_LOGIN_INCREMENT = 2
_EXPECTED_AFFECTED_ROW_COUNT = 1
_MISSING_USER_ID = 999
_UNASSIGNED_ADMIN_VALUE: bool | None = None
_ROLLBACK_MARKER = "rollback marker"


class Post(Model):
    """Represent one user-authored post for relationship integration tests.

    The model provides the child side of the mapped user relationship.
    """

    table = "posts"
    fillable = ("user_id", "title")

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str]
    user: Mapped[User] = relationship(back_populates="posts")


class User(Model):
    """Represent one application user for persistence integration tests.

    The mapping exercises the default integer key and a one-to-many relation.
    """

    table = "users"
    fillable = ("name", "email")
    hidden = ("email",)

    name: Mapped[str]
    email: Mapped[str]
    is_admin: Mapped[bool] = mapped_column(default=False)
    login_count: Mapped[int] = mapped_column(default=0)
    posts: Mapped[list[Post]] = has_many(Post, back_populates="user")


class SoftEntry(SoftDeletes, Model):
    """Represent a model with application-wide soft-delete query policy.

    The mapped deletion timestamp is supplied by the composable mixin.
    """

    table = "soft_entries"
    fillable = ("name",)
    name: Mapped[str]


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application that owns an isolated SQLite database.

    Args:
        tmp_path: Temporary path used as the application base directory.

    Returns:
        An unopened app with the native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/active_record.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_model_create_query_and_update_use_application_sessions(
    application: Application,
) -> None:
    """Create and update typed models through sync and async APIs.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT 0, "
            "login_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        await DB.statement_async(
            "CREATE TABLE posts ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "title TEXT NOT NULL, created_at TIMESTAMP, "
            "updated_at TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id))"
        )

        user = User()
        user.fill(
            {
                "name": _EXPECTED_USER_NAME,
                "email": "ada@example.test",
                "is_admin": True,
            }
        )
        assert user.is_admin is _UNASSIGNED_ADMIN_VALUE
        await user.save_async()

        results = await (
            User.query()
            .where("email", "ada@example.test")
            .where("is_admin", False)
            .get_async()
        )
        found = await User.find_async(user.id)

        assert len(results) == 1
        assert isinstance(results[0], User)
        assert results[0].name == _EXPECTED_USER_NAME
        assert found is not None
        found.name = "Augusta"
        await found.save_async()
        assert await found.increment_async(
            "login_count",
            _EXPECTED_LOGIN_COUNT_AFTER_INCREMENT,
        )
        assert found.login_count == _EXPECTED_LOGIN_COUNT_AFTER_INCREMENT
        assert await found.decrement_async("login_count")
        assert found.login_count == _EXPECTED_LOGIN_COUNT_AFTER_DECREMENT
        with pytest.raises(DatabaseQueryError):
            await found.increment_async("is_admin")

        matching = (
            User.query()
            .where_not("name", "Missing")
            .where_between("login_count", 0, 3)
            .where_column("id", "=", "id")
        )
        assert await matching.count_async() == _EXPECTED_AFFECTED_ROW_COUNT
        assert await matching.pluck_async("name", "id") == {
            user.id: "Augusta",
        }
        assert (
            await matching.sum_async("login_count")
            == _EXPECTED_LOGIN_COUNT_AFTER_DECREMENT
        )
        changed = await (
            User.query().where("id", user.id).increment_async("login_count", 2)
        )
        assert changed == _EXPECTED_AFFECTED_ROW_COUNT
        assert (
            await User.query().value_async("login_count")
            == _EXPECTED_LOGIN_COUNT_AFTER_BULK_INCREMENT
        )
        assert await User.query().value_async("name") == "Augusta"

        await Post.create_async({"user_id": user.id, "title": "First"})
        await Post.create_async({"user_id": user.id, "title": "Second"})
        loaded = await (
            User.query()
            .where("id", user.id)
            .with_("posts")
            .prevent_lazy_loading()
            .get_async()
        )
        assert len(loaded[0].posts) == _EXPECTED_POST_COUNT
        serialized_posts = loaded[0].to_dict()["posts"]
        assert isinstance(serialized_posts, list)
        assert serialized_posts

        await anyio.to_thread.run_sync(_sync_update_user)
        assert await DB.table("users").count_async() == 1


async def test_soft_deletes_filter_restore_and_force_delete(
    application: Application,
) -> None:
    """Keep deleted rows hidden until restore or explicit force deletion.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE soft_entries ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "deleted_at TIMESTAMP, created_at TIMESTAMP, "
            "updated_at TIMESTAMP)"
        )
        entry = await SoftEntry.create_async({"name": "archived"})

        assert await entry.delete_async()
        assert entry.trashed()
        assert await SoftEntry.query().count_async() == 0
        assert await SoftEntry.query().with_trashed().count_async() == 1
        archived = await SoftEntry.query().only_trashed().first_async()
        assert archived is not None
        assert archived.id == entry.id

        assert await entry.restore_async()
        assert not entry.trashed()
        assert await SoftEntry.query().count_async() == 1
        assert await entry.delete_async()
        assert await entry.force_delete_async()
        assert await SoftEntry.query().with_trashed().count_async() == 0


async def test_relationship_existence_queries_use_correlated_sql(
    application: Application,
) -> None:
    """Filter models through related rows and constrained relation queries.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, "
            "is_admin BOOLEAN NOT NULL DEFAULT 0, "
            "login_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        await DB.statement_async(
            "CREATE TABLE posts ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "title TEXT NOT NULL, created_at TIMESTAMP, updated_at TIMESTAMP, "
            "FOREIGN KEY (user_id) REFERENCES users(id))"
        )
        ada = await User.create_async(
            {"name": "Ada", "email": "ada@example.test"},
        )
        grace = await User.create_async(
            {"name": "Grace", "email": "grace@example.test"},
        )
        await Post.create_async({"user_id": ada.id, "title": "First"})
        await Post.create_async({"user_id": ada.id, "title": "Second"})

        authors = await User.query().has("posts").get_async()
        editors = (
            await User.query()
            .where_has(
                "posts",
                lambda query: query.where("title", "Second"),
            )
            .get_async()
        )
        non_authors = await User.query().doesnt_have("posts").get_async()
        related_by_value = (
            await User.query()
            .where_relation(
                "posts",
                "title",
                "First",
            )
            .get_async()
        )
        combined = await (
            User.query()
            .where("name", "Grace")
            .or_where_has("posts")
            .get_async()
        )

        assert [model.id for model in authors] == [ada.id]
        assert [model.id for model in editors] == [ada.id]
        assert [model.id for model in non_authors] == [grace.id]
        assert [model.id for model in related_by_value] == [ada.id]
        assert {model.id for model in combined} == {ada.id, grace.id}


async def test_eager_relationship_loading_avoids_n_plus_one_queries(
    application: Application,
) -> None:
    """Load related models with a bounded query count and safe serialization.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT 0, "
            "login_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        await DB.statement_async(
            "CREATE TABLE posts ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "title TEXT NOT NULL, created_at TIMESTAMP, updated_at TIMESTAMP, "
            "FOREIGN KEY (user_id) REFERENCES users(id))"
        )
        ada = await User.create_async(
            {"name": "Ada", "email": "ada@example.test"},
        )
        grace = await User.create_async(
            {"name": "Grace", "email": "grace@example.test"},
        )
        await Post.create_async({"user_id": ada.id, "title": "First"})
        await Post.create_async({"user_id": ada.id, "title": "Second"})

        manager = await application.container.make_async(DatabaseManager)
        engine = manager.async_engine("sqlite").sync_engine
        statements: list[str] = []

        def record_query(*arguments: object) -> None:
            """Capture statement text without retaining parameter values.

            SQLAlchemy invokes this listener with connection, cursor,
            statement, parameters, execution context, and executemany flag.
            """
            if len(arguments) >= _MINIMUM_STATEMENT_EVENT_ARGUMENTS:
                statement = arguments[_STATEMENT_EVENT_ARGUMENT_INDEX]
                if isinstance(
                    statement, str
                ) and statement.lstrip().upper().startswith("SELECT"):
                    statements.append(statement)

        event.listen(engine, "before_cursor_execute", record_query)
        try:
            users = await (
                User.query()
                .with_("posts")
                .prevent_lazy_loading()
                .order_by("id")
                .get_async()
            )
            serialized = users[0].to_dict()
            post_count = len(users[0].posts)
        finally:
            event.remove(engine, "before_cursor_execute", record_query)

        assert [user.id for user in users] == [ada.id, grace.id]
        assert post_count == _EXPECTED_EAGER_POST_COUNT
        assert "posts" in serialized
        assert "email" not in serialized
        assert len(statements) == _EXPECTED_EAGER_QUERY_COUNT


async def test_model_queries_return_collection_with_database_identity(
    application: Application,
) -> None:
    """Use native Collection behavior with model-key-aware operations.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT 0, "
            "login_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        ada = await User.create_async(
            {"name": "Ada", "email": "ada@example.test"},
        )
        grace = await User.create_async(
            {"name": "Grace", "email": "grace@example.test"},
        )
        ada_copy = await User.find_async(ada.id)
        assert ada_copy is not None

        users = await User.query().order_by("id").get_async()
        remaining = users.difference(ModelCollection((ada_copy,)))
        intersection = users.intersection(ModelCollection((ada_copy,)))
        merged = intersection.merge(ModelCollection((grace,)))

        assert isinstance(users, ModelCollection)
        assert users.model_keys() == (ada.id, grace.id)
        assert users.find(ada.id) is users[0]
        assert ada_copy in users
        assert remaining.model_keys() == (grace.id,)
        assert intersection.model_keys() == (ada.id,)
        assert merged.model_keys() == (ada.id, grace.id)
        assert len(users.unique()) == _EXPECTED_COLLECTION_SIZE
        assert users.to_collection().all() == [*users]
        assert users.to_dicts()[0]["name"] == _EXPECTED_USER_NAME
        assert "email" not in users.to_dicts()[0]
        fresh = await users.fresh_async()
        assert fresh.model_keys() == users.model_keys()


async def test_model_collection_loads_missing_relationships_in_batches(
    application: Application,
) -> None:
    """Load collection relationships with a bounded follow-up query count.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT 0, "
            "login_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        await DB.statement_async(
            "CREATE TABLE posts ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "title TEXT NOT NULL, created_at TIMESTAMP, updated_at TIMESTAMP, "
            "FOREIGN KEY (user_id) REFERENCES users(id))"
        )
        ada = await User.create_async(
            {"name": "Ada", "email": "ada@example.test"},
        )
        grace = await User.create_async(
            {"name": "Grace", "email": "grace@example.test"},
        )
        await Post.create_async({"user_id": ada.id, "title": "First"})
        await Post.create_async({"user_id": ada.id, "title": "Second"})

        users = await User.query().order_by("id").get_async()
        returned = await users.load_missing_async("posts")

        assert returned is users
        assert [user.id for user in users] == [ada.id, grace.id]
        assert [len(user.posts) for user in users] == [
            _EXPECTED_EAGER_POST_COUNT,
            0,
        ]


async def test_model_first_sole_and_find_many_contracts(
    application: Application,
) -> None:
    """Return typed models and distinguish missing from duplicate matches.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT 0, "
            "login_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        await User.create_async(
            {"name": "Ada", "email": "ada@example.test"},
        )
        await User.create_async(
            {"name": "Grace", "email": "grace@example.test"},
        )

        found = await User.find_many_async([1, 2, 99])
        first = await User.query().first_or_fail_async()
        one = await User.query().where("id", 1).sole_async()
        page = (
            await User.query()
            .order_by("id")
            .paginate_async(
                _PAGE_SIZE,
                page=_SECOND_PAGE,
            )
        )

        assert [model.id for model in found] == [1, 2]
        assert first is not None
        assert first.id == 1
        assert one.name == "Ada"
        assert page.total == _EXPECTED_USER_TOTAL
        assert len(page.items) == _PAGE_SIZE
        assert page.items[0].name == "Grace"

        with pytest.raises(MultipleModelsFoundError):
            await User.query().sole_async()
        with pytest.raises(ModelNotFoundError):
            await User.query().where("id", 99).first_or_fail_async()


async def test_model_state_refresh_replication_and_delete(
    application: Application,
) -> None:
    """Expose SQLAlchemy persistence state through native model helpers.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT 0, "
            "login_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        await DB.statement_async(
            "CREATE TABLE posts ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "title TEXT NOT NULL, created_at TIMESTAMP, "
            "updated_at TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id))"
        )
        user = await User.create_async(
            {"name": "Ada", "email": "ada@example.test"},
        )

        assert user.exists
        assert user.was_recently_created
        assert user.changes["name"] == "Ada"
        assert not user.dirty

        user.name = "Augusta"
        assert user.dirty["name"] == "Augusta"
        await user.refresh_async()
        assert user.name == "Ada"
        assert not user.dirty
        user.name = "Augusta"
        fresh = await user.fresh_async()
        assert fresh is not None
        assert fresh is not user
        assert fresh.name == "Ada"

        await user.save_async()
        assert not user.was_recently_created
        assert user.was_changed("name")
        assert user.changes["name"] == "Augusta"

        replica = user.replicate()
        assert not replica.exists
        assert replica.id is None
        assert replica.name == "Augusta"

        assert await user.delete_async()
        assert not user.exists
        assert await user.fresh_async() is None


async def test_cross_application_save_rejects_before_mutating_timestamps(
    application: Application,
    tmp_path: Path,
) -> None:
    """Reject cross-app model use before changing its mapped state.

    Args:
        application: First application that creates and owns the model.
        tmp_path: Temporary directory used to isolate the second application.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT 0, "
            "login_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        user = await User.create_async(
            {"name": "Ada", "email": "ada@example.test"},
        )
    original_updated_at = user.updated_at
    user.name = "Other application"

    second_base_path = tmp_path / "second_application"
    (second_base_path / "routes").mkdir(parents=True)
    second_application = Application(
        base_path=second_base_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/other.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )
    async with second_application:
        with pytest.raises(DatabaseTransactionOwnershipError):
            await user.save_async()

    assert user.updated_at == original_updated_at


async def test_model_first_create_and_update_or_create_contracts(
    application: Application,
) -> None:
    """Create matching models and update records through Active Record.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT NOT NULL UNIQUE, "
            "is_admin BOOLEAN NOT NULL DEFAULT 0, "
            "login_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        await DB.statement_async(
            "CREATE TABLE posts ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "title TEXT NOT NULL, created_at TIMESTAMP, "
            "updated_at TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id))"
        )
        pending = await User.first_or_new_async(
            {"email": "ada@example.test"},
            {"name": "Ada"},
        )
        assert not pending.exists
        assert pending.name == "Ada"

        await pending.save_async()
        fallback = await User.find_or_async(
            _MISSING_USER_ID,
            lambda: User(
                name="Fallback",
                email="fallback@example.test",
            ),
        )
        selected = await User.first_or_create_async(
            {"email": "ada@example.test"},
            {"name": "Ignored"},
        )
        assert selected.id == pending.id
        assert selected.name == "Ada"
        assert not fallback.exists

        created = await User.create_or_first_async(
            {"email": "grace@example.test"},
            {"name": "Grace"},
        )
        duplicate = await User.create_or_first_async(
            {"email": "grace@example.test"},
            {"name": "Ignored"},
        )
        assert duplicate.id == created.id
        assert duplicate.name == "Grace"

        updated = await User.update_or_create_async(
            {"email": "grace@example.test"},
            {"name": "Grace Hopper"},
        )
        inserted = await User.update_or_create_async(
            {"email": "katherine@example.test"},
            {"name": "Katherine"},
        )
        assert updated.id == created.id
        assert updated.name == "Grace Hopper"
        assert inserted.was_recently_created

        bulk_models = await User.create_many_async(
            [
                {"name": "Dorothy", "email": "dorothy@example.test"},
                {"name": "Annie", "email": "annie@example.test"},
            ],
        )
        destroyed = await User.destroy_async(
            [bulk_models[0].id, _MISSING_USER_ID],
        )
        assert len(bulk_models) == _EXPECTED_BULK_MODEL_COUNT
        assert destroyed == _EXPECTED_DESTROYED_MODEL_COUNT


def _sync_update_user() -> None:
    """Update the same row through the explicit synchronous model API.

    This helper runs on an AnyIO worker thread to avoid blocking async code.
    """
    user = User.find(1)
    assert user is not None
    user.name = "Ada Lovelace"
    user.save()
    assert user.increment(
        "login_count",
        _SYNC_LOGIN_INCREMENT,
    )
    assert user.login_count == _EXPECTED_LOGIN_COUNT_AFTER_SYNC_INCREMENT


async def test_model_save_markers_change_only_after_outer_commit(
    application: Application,
) -> None:
    """Keep Active Record persistence markers consistent with rollback.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT 0, "
            "login_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        rolled_back_user = User(
            name="Grace",
            email="grace@example.test",
        )

        with pytest.raises(RuntimeError, match=_ROLLBACK_MARKER):
            await _save_new_user_then_raise(rolled_back_user)

        assert rolled_back_user.exists is False
        assert rolled_back_user.was_recently_created is False
        assert await User.query().count_async() == 0

        user = await User.create_async(
            {"name": "Grace", "email": "grace@example.test"},
        )

        assert user.exists is True
        assert user.was_recently_created is True
        assert user.changes.get("name") == "Grace"

        user.name = "Grace Hopper"
        with pytest.raises(RuntimeError, match=_ROLLBACK_MARKER):
            await _save_user_update_then_raise(user)

        assert user.was_recently_created is True
        assert user.changes.get("name") == "Grace"


async def _save_new_user_then_raise(user: User) -> None:
    """Flush a new model and raise to roll back its insertion.

    Args:
        user: Transient model whose insert belongs to the transaction.
    """
    async with DB.transaction_async():
        await user.save_async()
        assert user.was_recently_created is False
        raise RuntimeError(_ROLLBACK_MARKER)


async def _save_user_update_then_raise(user: User) -> None:
    """Flush an update and raise to preserve earlier committed markers.

    Args:
        user: Persisted model whose update belongs to the transaction.
    """
    async with DB.transaction_async():
        await user.save_async()
        assert user.changes.get("name") != "Grace Hopper"
        raise RuntimeError(_ROLLBACK_MARKER)
