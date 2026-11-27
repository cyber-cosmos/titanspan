"""Verify Database application ownership with real SQLite operations.

These tests exercise the native provider, facade, async engine, and
transaction lifecycle through a real Foundation application.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

import anyio
import pytest

from titanspan.database import (
    AsyncOperationRequiredError,
    DatabaseConfiguration,
    DatabaseConnectionError,
    DatabaseManager,
    DatabaseServiceProvider,
    DatabaseTransactionError,
    DatabaseTransactionOwnershipError,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine

    from titanspan.contracts.database import DatabaseConnectionService

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_ROLLBACK_MARKER = "rollback marker"
_EXPECTED_SAVEPOINT_LEVEL = 2


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with one relative SQLite connection.

    Args:
        tmp_path: Temporary application root provided by Pytest.

    Returns:
        An application that owns an unopened SQLite database.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/database.sqlite",
                        "options": {
                            "connect_args": {"timeout": 20.0},
                        },
                    },
                    "analytics": {
                        "driver": "sqlite",
                        "database": "database/analytics.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_provider_shares_manager_and_initializes_sqlite_lazily(
    application: Application,
    tmp_path: Path,
) -> None:
    """Resolve one app-owned manager and create SQLite on first I/O.

    Args:
        application: Application configured by the test fixture.
        tmp_path: Temporary application root used for path resolution.
    """
    database_path = (tmp_path / "database" / "database.sqlite").resolve()

    async with application:
        manager = await application.container.make_async(DatabaseManager)
        connection = manager.connection()

        assert DB.resolve_service() is manager
        assert connection.engine.url.database == str(database_path)
        assert not database_path.exists()

        await connection.statement_async(
            "CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT)"
        )
        await connection.statement_async(
            "INSERT INTO entries (name) VALUES (:name)",
            {"name": "native"},
        )
        rows = await connection.select_async(
            "SELECT name FROM entries WHERE id = :id",
            {"id": 1},
        )

        assert database_path.exists()
        assert rows == [{"name": "native"}]


async def test_async_transaction_rolls_back_through_the_facade(
    application: Application,
) -> None:
    """Roll back async statements when an explicit transaction fails.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        connection = DB.connection()
        await connection.statement_async(
            "CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT)"
        )

        with pytest.raises(RuntimeError, match=_ROLLBACK_MARKER):
            await _insert_then_raise(connection)

        rows = await connection.select_async("SELECT id FROM entries")

        assert rows == []


async def test_child_task_cannot_reuse_parent_async_session(
    application: Application,
) -> None:
    """Reject inherited context authority before child SQL execution.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        connection = DB.connection()
        await connection.statement_async(
            "CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT)"
        )
        rejected = anyio.Event()

        async with DB.transaction_async():
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(
                    _assert_child_session_rejected,
                    connection,
                    rejected,
                )
                await rejected.wait()
            await connection.statement_async(
                "INSERT INTO entries (name) VALUES (:name)",
                {"name": "parent"},
            )

        rows = await connection.select_async(
            "SELECT name FROM entries ORDER BY id"
        )

        assert rows == [{"name": "parent"}]


async def test_nested_transaction_uses_savepoint_and_restores_depth(
    application: Application,
) -> None:
    """Rollback a failed nested transaction without losing its parent.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        connection = DB.connection()
        await connection.statement_async(
            "CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT)"
        )

        async with DB.transaction_async():
            assert DB.transaction_level() == 1
            await connection.statement_async(
                "INSERT INTO entries (name) VALUES (:name)",
                {"name": "kept"},
            )
            with pytest.raises(RuntimeError, match=_ROLLBACK_MARKER):
                await _insert_then_raise_nested(connection)
            assert DB.transaction_level() == 1
            await connection.statement_async(
                "INSERT INTO entries (name) VALUES (:name)",
                {"name": "also kept"},
            )

        assert DB.transaction_level() == 0
        rows = await connection.select_async(
            "SELECT name FROM entries ORDER BY id"
        )

        assert rows == [
            {"name": "kept"},
            {"name": "also kept"},
        ]


async def test_transaction_callbacks_follow_commit_and_savepoint_outcomes(
    application: Application,
) -> None:
    """Dispatch commit and rollback callbacks at their owning boundaries.

    Callbacks from a rolled-back savepoint must not leak into the outer
    transaction's eventual commit.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        committed: list[str] = []
        rolled_back: list[str] = []

        async with DB.transaction_async():
            DB.after_commit(lambda: committed.append("root"))
            DB.after_rollback(lambda: rolled_back.append("root"))
            with pytest.raises(RuntimeError, match=_ROLLBACK_MARKER):
                await _rollback_callback_savepoint(
                    committed,
                    rolled_back,
                )
            assert rolled_back == ["savepoint"]
            assert committed == []

        assert committed == ["root"]
        assert rolled_back == ["savepoint"]


async def test_root_rollback_dispatches_only_rollback_callbacks(
    application: Application,
) -> None:
    """Run rollback callbacks after a root transaction is rolled back.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        outcomes: list[str] = []
        with pytest.raises(RuntimeError, match=_ROLLBACK_MARKER):
            await _rollback_callback_root(outcomes)

        assert outcomes == ["rollback"]


async def test_sync_transaction_callbacks_follow_commit_and_rollback(
    application: Application,
) -> None:
    """Exercise callback boundaries through the explicit sync API.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        outcomes = await anyio.to_thread.run_sync(
            _sync_transaction_callback_roundtrip,
        )

        assert outcomes == ["nested rollback", "root commit", "root rollback"]


async def test_active_transaction_does_not_capture_other_named_connection(
    application: Application,
) -> None:
    """Keep independent named connections on their own Units of Work.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        primary = DB.connection()
        analytics = DB.connection("analytics")
        await primary.statement_async(
            "CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT)"
        )
        await analytics.statement_async(
            "CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT)"
        )

        async with DB.transaction_async():
            await primary.statement_async(
                "INSERT INTO entries (name) VALUES (:name)",
                {"name": "primary"},
            )
            await analytics.statement_async(
                "INSERT INTO entries (name) VALUES (:name)",
                {"name": "analytics"},
            )

        assert await primary.select_async("SELECT name FROM entries") == [
            {"name": "primary"},
        ]
        assert await analytics.select_async("SELECT name FROM entries") == [
            {"name": "analytics"},
        ]


async def test_sync_operations_run_on_a_worker_thread(
    application: Application,
) -> None:
    """Use SQLAlchemy's sync engine without blocking the app event loop.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        rows = await anyio.to_thread.run_sync(_sync_roundtrip)

    assert rows == [{"name": "sync"}]


async def test_manager_pool_lifecycle_and_active_transaction_guard(
    application: Application,
) -> None:
    """Dispose and recreate async pools without breaking active work.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        manager = await application.container.make_async(DatabaseManager)
        sync_engine = manager.engine("sqlite")
        engine = manager.async_engine("sqlite")
        assert manager.connection_names == ("sqlite", "analytics")

        with pytest.raises(AsyncOperationRequiredError):
            manager.disconnect("sqlite")
        with pytest.raises(AsyncOperationRequiredError):
            manager.purge("sqlite")
        async with DB.transaction_async():
            with pytest.raises(DatabaseTransactionError):
                manager.close()
            with pytest.raises(DatabaseTransactionError):
                await manager.aclose()
            with pytest.raises(DatabaseTransactionError):
                await manager.purge_async("sqlite")
        with pytest.raises(AsyncOperationRequiredError):
            manager.close()

        await manager.disconnect_async("sqlite")
        assert manager.engine("sqlite") is sync_engine
        assert manager.async_engine("sqlite") is engine
        await manager.purge_async("sqlite")
        assert manager.engine("sqlite") is not sync_engine
        assert manager.async_engine("sqlite") is not engine


def test_sync_manager_savepoints_and_engine_lifecycle(
    tmp_path: Path,
) -> None:
    """Rollback nested sync work and exercise pool disposal policies.

    Args:
        tmp_path: Temporary root for an application-local SQLite database.
    """
    application = Application(base_path=tmp_path)
    configuration = DatabaseConfiguration.from_mapping(
        {
            "default": "sqlite",
            "connections": {
                "sqlite": {
                    "driver": "sqlite",
                    "database": "database/sync_manager.sqlite",
                },
            },
        },
        application,
    )
    manager = DatabaseManager(configuration)
    connection = manager.connection()
    connection.statement(
        "CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
    )

    with manager.transaction():
        assert manager.transaction_level == 1
        assert manager.connection_transaction_level() == 1
        connection.statement(
            "INSERT INTO entries (name) VALUES (:name)",
            {"name": "kept"},
        )
        with pytest.raises(RuntimeError, match=_ROLLBACK_MARKER):
            _sync_insert_then_raise(manager, connection)
        assert manager.transaction_level == 1
        with pytest.raises(DatabaseTransactionError):
            manager.disconnect()

    assert manager.transaction_level == 0
    assert connection.select("SELECT name FROM entries") == [
        {"name": "kept"},
    ]
    engine = manager.engine("sqlite")
    manager.disconnect()
    assert manager.engine("sqlite") is engine
    manager.purge()
    assert manager.engine("sqlite") is not engine
    manager.close()


async def test_async_disconnect_rejects_work_during_pool_disposal(
    application: Application,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject new work until async pool disposal has completed.

    Args:
        application: Application configured by the test fixture.
        monkeypatch: Fixture that pauses SQLAlchemy's real disposal call.
    """
    async with application:
        manager = await application.container.make_async(DatabaseManager)
        connection = manager.connection()
        engine = manager.async_engine("sqlite")
        disposal_started = anyio.Event()
        allow_disposal = anyio.Event()
        original_dispose = engine.dispose

        async def pause_disposal(active_engine: AsyncEngine) -> None:
            """Hold the real disposal call at a deterministic boundary.

            No database operation is mocked; the test only controls timing.
            """
            assert active_engine is engine
            disposal_started.set()
            await allow_disposal.wait()
            await original_dispose()

        monkeypatch.setattr(type(engine), "dispose", pause_disposal)
        rejected = False
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(manager.disconnect_async, "sqlite")
            await disposal_started.wait()
            try:
                try:
                    await connection.select_async("SELECT 1")
                except DatabaseTransactionError:
                    rejected = True
            finally:
                allow_disposal.set()

        assert rejected


async def test_async_transaction_cancellation_rolls_back_and_releases_session(
    application: Application,
) -> None:
    """Roll back cancelled work and allow the task owner to query again.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        connection = DB.connection()
        await connection.statement_async(
            "CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT)"
        )
        entered = anyio.Event()
        cancel_scopes: list[anyio.CancelScope] = []

        async def hold_transaction() -> None:
            """Insert one row and wait for parent-directed cancellation.
            """  # fmt: skip
            with anyio.CancelScope() as cancel_scope:
                cancel_scopes.append(cancel_scope)
                async with DB.transaction_async():
                    await connection.statement_async(
                        "INSERT INTO entries (name) VALUES (:name)",
                        {"name": "cancelled"},
                    )
                    entered.set()
                    await anyio.sleep_forever()

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(hold_transaction)
            await entered.wait()
            cancel_scopes[0].cancel()

        rows = await connection.select_async("SELECT id FROM entries")

        assert rows == []


async def test_raw_facade_operations_use_bound_values(
    application: Application,
) -> None:
    """Exercise sync and async facade operations through one service.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        with pytest.raises(AsyncOperationRequiredError):
            DB.connection().select("SELECT 1")
        await DB.statement_async(
            "CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT)"
        )
        await DB.execute_async(
            "INSERT INTO entries (id, name) VALUES (:id, :name)",
            {"id": 1, "name": "native"},
        )

        rows = await DB.select_async(
            "SELECT name FROM entries WHERE id = :id",
            {"id": 1},
        )
        row = await DB.select_one_async(
            "SELECT name FROM entries WHERE id = :id",
            {"id": 1},
        )
        scalar = await DB.scalar_async(
            "SELECT name FROM entries WHERE id = :id",
            {"id": 1},
        )
        result = await DB.execute_async(
            "SELECT name FROM entries WHERE id = :id",
            {"id": 1},
        )

        assert rows == [{"name": "native"}]
        assert row == {"name": "native"}
        assert scalar == "native"
        assert result.rows == ({"name": "native"},)


def test_sync_manager_close_is_terminal(tmp_path: Path) -> None:
    """Close an initialized manager and reject later engine access.

    Args:
        tmp_path: Temporary application root used for SQLite files.
    """
    paths = Application(base_path=tmp_path)
    configuration = DatabaseConfiguration.from_mapping(
        {
            "default": "sqlite",
            "connections": {
                "sqlite": {
                    "driver": "sqlite",
                    "database": "database/closed.sqlite",
                },
            },
        },
        paths,
    )
    manager = DatabaseManager(configuration)
    manager.connection().statement(
        "CREATE TABLE entries (id INTEGER PRIMARY KEY)"
    )

    manager.close()

    with pytest.raises(DatabaseConnectionError):
        manager.engine("sqlite")


def test_sync_engine_discards_partial_initialization(
    tmp_path: Path,
) -> None:
    """Dispose an unopened engine when its SQLite path cannot be prepared.

    Args:
        tmp_path: Temporary root containing a blocking file path.
    """
    blocking_file = tmp_path / "database"
    blocking_file.write_text("block directory creation", encoding="utf-8")
    application = Application(base_path=tmp_path)
    configuration = DatabaseConfiguration.from_mapping(
        {
            "default": "sqlite",
            "connections": {
                "sqlite": {
                    "driver": "sqlite",
                    "database": "database/unavailable.sqlite",
                },
            },
        },
        application,
    )
    manager = DatabaseManager(configuration)

    with pytest.raises(DatabaseConnectionError):
        manager.engine("sqlite")


async def test_async_engine_discards_partial_initialization(
    tmp_path: Path,
) -> None:
    """Dispose an async engine when SQLite path setup fails before use.

    Args:
        tmp_path: Temporary root containing a blocking file path.
    """
    blocking_file = tmp_path / "database"
    blocking_file.write_text("block directory creation", encoding="utf-8")
    application = Application(base_path=tmp_path)
    configuration = DatabaseConfiguration.from_mapping(
        {
            "default": "sqlite",
            "connections": {
                "sqlite": {
                    "driver": "sqlite",
                    "database": "database/unavailable.sqlite",
                },
            },
        },
        application,
    )
    manager = DatabaseManager(configuration)

    with pytest.raises(DatabaseConnectionError):
        manager.async_engine("sqlite")

    await manager.aclose()


async def _insert_then_raise(
    connection: DatabaseConnectionService,
) -> None:
    """Insert within an explicit transaction and trigger its rollback.

    Args:
        connection: Application-owned logical connection used by the test.
    """
    async with DB.transaction_async():
        await connection.statement_async(
            "INSERT INTO entries (name) VALUES (:name)",
            {"name": "rolled back"},
        )
        raise RuntimeError(_ROLLBACK_MARKER)


async def _insert_then_raise_nested(
    connection: DatabaseConnectionService,
) -> None:
    """Insert inside a nested savepoint and trigger its rollback.

    Args:
        connection: Application-owned logical connection used by the test.
    """
    async with DB.transaction_async():
        await connection.statement_async(
            "INSERT INTO entries (name) VALUES (:name)",
            {"name": "rolled back"},
        )
        raise RuntimeError(_ROLLBACK_MARKER)


async def _rollback_callback_savepoint(
    committed: list[str],
    rolled_back: list[str],
) -> None:
    """Register callbacks inside a savepoint and raise to roll it back.

    Args:
        committed: Capture callbacks that must wait for root commit.
        rolled_back: Capture callbacks owned by the savepoint rollback.
    """
    async with DB.transaction_async():
        DB.after_commit(lambda: committed.append("savepoint"))
        DB.after_rollback(lambda: rolled_back.append("savepoint"))
        raise RuntimeError(_ROLLBACK_MARKER)


async def _rollback_callback_root(outcomes: list[str]) -> None:
    """Register root callbacks and raise to roll back the transaction.

    Args:
        outcomes: Capture the callback selected by root rollback.
    """
    async with DB.transaction_async():
        DB.after_commit(lambda: outcomes.append("commit"))
        DB.after_rollback(lambda: outcomes.append("rollback"))
        raise RuntimeError(_ROLLBACK_MARKER)


async def _assert_child_session_rejected(
    connection: DatabaseConnectionService,
    rejected: anyio.Event,
) -> None:
    """Attempt child task I/O and signal successful ownership rejection.

    Args:
        connection: Parent task's logical connection handle.
        rejected: Event signaled after the manager rejects child reuse.
    """
    with pytest.raises(DatabaseTransactionOwnershipError):
        await connection.select_async("SELECT 1")
    rejected.set()


def _sync_roundtrip() -> list[Mapping[str, object]]:
    """Create, write, and read through the sync database facade.

    Returns:
        Rows returned by a synchronous SQLite query.
    """
    connection = DB.connection()
    connection.statement(
        "CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT)"
    )
    with DB.transaction():
        connection.statement(
            "INSERT INTO entries (name) VALUES (:name)",
            {"name": "sync"},
        )
    return connection.select("SELECT name FROM entries ORDER BY id")


def _sync_transaction_callback_roundtrip() -> list[str]:
    """Verify sync nested callbacks and a later root rollback.

    Returns:
        Callback labels in their transaction completion order.
    """
    outcomes: list[str] = []
    with DB.transaction():
        DB.after_commit(lambda: outcomes.append("root commit"))
        DB.after_rollback(lambda: outcomes.append("root rollback"))
        with suppress(RuntimeError):
            _sync_rollback_callback_savepoint(outcomes)
    with suppress(RuntimeError):
        _sync_rollback_callback_root(outcomes)
    return outcomes


def _sync_rollback_callback_savepoint(outcomes: list[str]) -> None:
    """Register one savepoint rollback callback and trigger its rollback.

    Args:
        outcomes: Capture committed or rolled-back callback labels.
    """
    with DB.transaction():
        DB.after_commit(lambda: outcomes.append("nested commit"))
        DB.after_rollback(lambda: outcomes.append("nested rollback"))
        raise RuntimeError(_ROLLBACK_MARKER)


def _sync_rollback_callback_root(outcomes: list[str]) -> None:
    """Register a root rollback callback and trigger the rollback.

    Args:
        outcomes: Capture committed or rolled-back callback labels.
    """
    with DB.transaction():
        DB.after_commit(lambda: outcomes.append("second root commit"))
        DB.after_rollback(lambda: outcomes.append("root rollback"))
        raise RuntimeError(_ROLLBACK_MARKER)


def _sync_insert_then_raise(
    manager: DatabaseManager,
    connection: DatabaseConnectionService,
) -> None:
    """Insert through a nested savepoint and trigger a rollback.

    Args:
        manager: Database manager whose sync transaction is already active.
        connection: Logical connection used for the insert.
    """
    with manager.transaction():
        assert (
            manager.connection_transaction_level()
            == _EXPECTED_SAVEPOINT_LEVEL
        )
        connection.statement(
            "INSERT INTO entries (name) VALUES (:name)",
            {"name": "rolled back"},
        )
        raise RuntimeError(_ROLLBACK_MARKER)
