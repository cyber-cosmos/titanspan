"""Exercise DatabaseManager lifecycle and error boundaries with SQLite.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import anyio
import pytest

from titanspan.contracts.database import TransactionOutcome, TransactionReceipt
from titanspan.database import (
    AsyncOperationRequiredError,
    DatabaseConfiguration,
    DatabaseConnectionError,
    DatabaseManager,
    DatabaseQueryError,
    DatabaseTransactionCallbackError,
    DatabaseTransactionError,
)
from titanspan.foundation import Application

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator
    from pathlib import Path

    from titanspan.database.connection import Connection

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


def _manager(
    tmp_path: Path,
    *,
    url: str | None = None,
) -> DatabaseManager:
    """Create an independent manager with two local named connections.

    Args:
        tmp_path: Temporary application path used by SQLite.
        url: Optional explicit URL for driver-boundary tests.

    Returns:
        A manager that owns only resources created by the current test.
    """
    sqlite: dict[str, object] = {
        "driver": "sqlite",
        "database": "database/manager.sqlite",
    }
    if url is not None:
        sqlite = {"url": url}
    configuration = DatabaseConfiguration.from_mapping(
        {
            "default": "sqlite",
            "connections": {
                "sqlite": sqlite,
                "analytics": {
                    "driver": "sqlite",
                    "database": "database/analytics.sqlite",
                },
            },
        },
        Application(base_path=tmp_path),
    )
    return DatabaseManager(configuration)


@pytest.fixture
def sync_manager(tmp_path: Path) -> Iterator[DatabaseManager]:
    """Own one synchronous manager for each test case.

    Args:
        tmp_path: Temporary application root for SQLite files.

    Yields:
        A manager isolated from other test applications.
    """
    manager = _manager(tmp_path)
    yield manager
    manager.close()


@pytest.fixture
async def async_manager(tmp_path: Path) -> AsyncIterator[DatabaseManager]:
    """Own and asynchronously dispose one manager per async test.

    Args:
        tmp_path: Temporary application root for SQLite files.

    Yields:
        A manager isolated from other test applications.
    """
    manager = _manager(tmp_path)
    yield manager
    await manager.aclose()


def test_callback_registration_and_depth_outside_transactions(
    sync_manager: DatabaseManager,
) -> None:
    """Run commit callbacks immediately and reject unowned rollback hooks.

    Args:
        sync_manager: Test-owned manager with named SQLite connections.
    """
    manager = sync_manager
    callbacks: list[str] = []

    assert manager.transaction_level == 0
    assert manager.connection_transaction_level("analytics") == 0
    manager.after_commit(lambda: callbacks.append("committed"))

    assert callbacks == ["committed"]
    with pytest.raises(DatabaseTransactionError, match="requires an active"):
        manager.after_rollback(lambda: callbacks.append("rolled back"))


async def test_async_commit_callback_runs_immediately_without_transaction(
    async_manager: DatabaseManager,
) -> None:
    """Await an async callback immediately when it has no transaction owner.

    Args:
        async_manager: Test-owned manager with named SQLite connections.
    """
    manager = async_manager
    callbacks: list[str] = []

    async def callback() -> None:
        """Record callback delivery after registration completes.

        The callback has no database side effects and remains deterministic.
        """
        callbacks.append("committed")

    await manager.after_commit_async(callback)

    assert callbacks == ["committed"]


def test_sync_commit_rejects_async_callback_after_persisting(
    sync_manager: DatabaseManager,
) -> None:
    """Report a callback API mismatch without reversing a committed write.

    Args:
        sync_manager: Test-owned manager with a local SQLite database.
    """
    manager = sync_manager
    connection = manager.connection()
    connection.statement(
        "CREATE TABLE callback_rows (id INTEGER PRIMARY KEY, name TEXT)"
    )
    receipts: list[TransactionReceipt] = []

    with pytest.raises(DatabaseTransactionCallbackError) as captured:
        _write_with_async_callback(manager, connection, receipts)

    assert captured.value.committed
    receipt = receipts[0]
    assert receipt.outcome is TransactionOutcome.COMMITTED_WITH_CALLBACK_ERRORS
    assert connection.select("SELECT name FROM callback_rows") == [
        {"name": "committed"},
    ]


def test_sync_database_errors_keep_a_safe_native_cause(
    sync_manager: DatabaseManager,
) -> None:
    """Translate a real SQLite statement failure without exposing SQL text.

    Args:
        sync_manager: Test-owned manager with a local SQLite database.
    """
    manager = sync_manager

    with pytest.raises(DatabaseTransactionError) as automatic:
        manager.connection().select("SELECT * FROM missing_sync_table")
    assert "missing_sync_table" not in str(automatic.value)
    assert automatic.value.__cause__ is not None

    with pytest.raises(DatabaseQueryError) as captured, manager.transaction():
        manager.connection().select("SELECT * FROM missing_sync_table")

    assert "missing_sync_table" not in str(captured.value)
    assert captured.value.__cause__ is not None


async def test_async_database_errors_keep_a_safe_native_cause(
    async_manager: DatabaseManager,
) -> None:
    """Translate an async SQLite statement failure at the query boundary.

    Args:
        async_manager: Test-owned manager with a local SQLite database.
    """
    manager = async_manager

    with pytest.raises(DatabaseTransactionError) as automatic:
        await manager.connection().select_async(
            "SELECT * FROM missing_async_table",
        )
    assert "missing_async_table" not in str(automatic.value)
    assert automatic.value.__cause__ is not None

    with pytest.raises(DatabaseQueryError) as captured:
        await _select_missing_inside_transaction(manager)

    assert "missing_async_table" not in str(captured.value)
    assert captured.value.__cause__ is not None


async def test_worker_thread_cannot_use_an_async_session(
    async_manager: DatabaseManager,
) -> None:
    """Reject inherited session access from a thread distinct from its owner.

    Args:
        async_manager: Test-owned manager with a local SQLite database.
    """
    manager = async_manager
    connection = manager.connection()
    await connection.statement_async(
        "CREATE TABLE thread_rows (id INTEGER PRIMARY KEY)"
    )

    async with manager.transaction_async():
        with pytest.raises(
            DatabaseTransactionError,
            match="another thread",
        ):
            await anyio.to_thread.run_sync(
                connection.select,
                "SELECT id FROM thread_rows",
            )


async def test_sync_io_is_rejected_inside_an_async_operation(
    async_manager: DatabaseManager,
) -> None:
    """Require explicit async execution while an event loop is running.

    Args:
        async_manager: Test-owned manager with named SQLite connections.
    """
    manager = async_manager

    with pytest.raises(AsyncOperationRequiredError, match="explicit async"):
        manager.connection().select("SELECT 1")


def test_sync_manager_closure_rejects_later_engine_access(
    tmp_path: Path,
) -> None:
    """Prevent engine construction after permanent manager shutdown.

    Args:
        tmp_path: Temporary application root for the Database configuration.
    """
    manager = _manager(tmp_path)
    manager.close()

    with pytest.raises(DatabaseConnectionError, match="manager is closed"):
        manager.engine("sqlite")


async def test_unavailable_sync_and_async_drivers_are_translated(
    tmp_path: Path,
) -> None:
    """Preserve driver construction failures behind Database exceptions.

    Args:
        tmp_path: Temporary application root for the Database configuration.
    """
    manager = _manager(
        tmp_path,
        url="sqlite+titanspan_missing_driver:///:memory:",
    )

    with pytest.raises(DatabaseConnectionError, match="sync database driver"):
        manager.engine("sqlite")
    with pytest.raises(
        DatabaseConnectionError,
        match="async database driver",
    ):
        manager.async_engine("sqlite")

    await manager.aclose()


async def _select_missing_inside_transaction(
    manager: DatabaseManager,
) -> None:
    """Run a failing read inside an explicitly owned async transaction.

    Args:
        manager: Manager whose async connection owns the transaction.
    """
    async with manager.transaction_async():
        await manager.connection().select_async(
            "SELECT * FROM missing_async_table",
        )


def _write_with_async_callback(
    manager: DatabaseManager,
    connection: Connection,
    receipts: list[TransactionReceipt],
) -> None:
    """Commit one row and deliberately register an awaitable sync callback.

    Args:
        manager: Manager whose transaction commits the row.
        connection: Logical SQLite connection used for the test insert.
        receipts: Caller-owned list used to inspect the durable outcome.
    """

    async def callback() -> None:
        """Represent a callback that requires explicit async execution.

        This coroutine must be rejected by synchronous transaction delivery.
        """

    with manager.transaction() as receipt:
        receipts.append(receipt)
        connection.statement(
            "INSERT INTO callback_rows (name) VALUES (:name)",
            {"name": "committed"},
        )
        manager.after_commit(cast("Callable[[], None]", callback))
