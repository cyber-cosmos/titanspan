"""Verify cancellation and cleanup failures at sync transaction boundaries.

The tests use native transaction contexts and SQLAlchemy's public SQLite
events to observe durable outcomes and cleanup failures.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

import anyio
import pytest
from sqlalchemy import event

from titanspan.database import (
    DatabaseCommitOutcomeUnknownError,
    DatabaseManager,
    DatabaseServiceProvider,
    TransactionOutcome,
    TransactionReceipt,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.engine import Connection
    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with a disposable SQLite database.

    Args:
        tmp_path: Temporary root used for the database file.

    Returns:
        An unopened application that owns the native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/transaction_interruptions.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def _create_table() -> None:
    """Create a table used to verify transaction durability.
    """  # fmt: skip
    await DB.statement_async(
        "CREATE TABLE transaction_interruptions "
        "(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
    )


@pytest.mark.regression
async def test_sync_after_commit_cancellation_preserves_committed_write(
    application: Application,
) -> None:
    """Preserve cancellation while reporting a committed callback outcome.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()

        def commit_then_cancel() -> tuple[
            TransactionReceipt,
            asyncio.CancelledError,
        ]:
            """Commit a row before a callback raises cancellation.
            """  # fmt: skip
            receipts: list[TransactionReceipt] = []

            def cancel_callback() -> None:
                """Interrupt synchronous callback dispatch after commit.
                """  # fmt: skip
                message = "observer cancellation"
                raise asyncio.CancelledError(message)

            def write_row() -> None:
                """Commit a row and register the interrupting callback.
                """  # fmt: skip
                with DB.transaction() as receipt:
                    receipts.append(receipt)
                    DB.statement(
                        "INSERT INTO transaction_interruptions "
                        "(id, value) VALUES (1, 'committed')"
                    )
                    DB.after_commit(cancel_callback)

            with pytest.raises(asyncio.CancelledError) as captured:
                write_row()

            assert len(receipts) == 1
            return receipts[0], captured.value

        receipt, cancellation = await anyio.to_thread.run_sync(
            commit_then_cancel,
        )

        assert (
            receipt.outcome is TransactionOutcome.COMMITTED_WITH_CALLBACK_ERRORS
        )
        assert receipt.error is cancellation
        assert (
            await DB.scalar_async(
                "SELECT value FROM transaction_interruptions WHERE id = :id",
                {"id": 1},
            )
            == "committed"
        )


@pytest.mark.regression
async def test_sync_rollback_callback_failure_preserves_cancellation(
    application: Application,
) -> None:
    """Report rollback while preserving body and callback failures.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()

        def cancel_with_rollback_failure() -> tuple[
            TransactionReceipt,
            asyncio.CancelledError,
            list[str],
        ]:
            """Roll back work and preserve a failing rollback observer.
            """  # fmt: skip
            receipts: list[TransactionReceipt] = []
            callback_order: list[str] = []

            def fail_rollback_callback() -> None:
                """Record invocation before the callback reports its failure.
                """  # fmt: skip
                callback_order.append("rollback")
                message = "rollback observer failed"
                raise RuntimeError(message)

            def cancel_transaction() -> None:
                """Raise cancellation from an active synchronous transaction.
                """  # fmt: skip
                with DB.transaction() as receipt:
                    receipts.append(receipt)
                    DB.after_rollback(fail_rollback_callback)
                    DB.statement(
                        "INSERT INTO transaction_interruptions "
                        "(id, value) VALUES (2, 'rolled back')"
                    )
                    message = "request cancelled"
                    raise asyncio.CancelledError(message)

            with pytest.raises(asyncio.CancelledError) as captured:
                cancel_transaction()

            assert len(receipts) == 1
            return receipts[0], captured.value, callback_order

        receipt, cancellation, callback_order = await anyio.to_thread.run_sync(
            cancel_with_rollback_failure,
        )

        cause = cancellation.__cause__
        assert isinstance(cause, BaseExceptionGroup)
        group = cast("BaseExceptionGroup[BaseException]", cause)
        assert group.exceptions[0] is cancellation
        assert isinstance(group.exceptions[1], RuntimeError)
        assert receipt.outcome is TransactionOutcome.ROLLED_BACK
        assert receipt.error is cancellation
        assert callback_order == ["rollback"]
        assert (
            await DB.scalar_async(
                "SELECT COUNT(*) FROM transaction_interruptions",
            )
            == 0
        )


@pytest.mark.regression
async def test_sync_unknown_commit_preserves_invalidation_failure(
    application: Application,
) -> None:
    """Preserve commit and cleanup causes when SQLite invalidation fails.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()
        manager = await application.container.make_async(DatabaseManager)
        engine = manager.engine("sqlite")

        def fail_commit(connection: Connection) -> None:
            """Reject the driver commit through SQLAlchemy's event API.
            """  # fmt: skip
            _ = connection
            message = "commit rejected"
            raise RuntimeError(message)

        def fail_invalidation(
            dbapi_connection: DBAPIConnection,
            connection_record: ConnectionPoolEntry,
            exception: BaseException | None,
        ) -> None:
            """Inject a failure while the manager invalidates that connection.

            Args:
                dbapi_connection: SQLite connection being invalidated.
                connection_record: SQLAlchemy pool record for the connection.
                exception: Failure that prompted invalidation, if provided.
            """
            _ = dbapi_connection, connection_record, exception
            message = "connection invalidation failed"
            raise LookupError(message)

        def commit_with_failed_cleanup() -> tuple[
            TransactionReceipt,
            DatabaseCommitOutcomeUnknownError,
        ]:
            """Observe the native unknown-outcome error and its receipt.
            """  # fmt: skip
            receipts: list[TransactionReceipt] = []

            def write_row() -> None:
                """Attempt a write while the event rejects commit.
                """  # fmt: skip
                with DB.transaction() as receipt:
                    receipts.append(receipt)
                    DB.statement(
                        "INSERT INTO transaction_interruptions "
                        "(id, value) VALUES (3, 'unknown')"
                    )

            with pytest.raises(
                DatabaseCommitOutcomeUnknownError,
            ) as captured:
                write_row()

            assert len(receipts) == 1
            return receipts[0], captured.value

        event.listen(engine, "commit", fail_commit)
        event.listen(engine.pool, "invalidate", fail_invalidation)
        try:
            receipt, error = await anyio.to_thread.run_sync(
                commit_with_failed_cleanup,
            )
        finally:
            event.remove(engine, "commit", fail_commit)
            event.remove(engine.pool, "invalidate", fail_invalidation)

        assert receipt.outcome is TransactionOutcome.COMMIT_OUTCOME_UNKNOWN
        assert isinstance(error.commit_error, RuntimeError)
        assert isinstance(error.cleanup_error, LookupError)
        cause = error.__cause__
        assert isinstance(cause, BaseExceptionGroup)
        group = cast("BaseExceptionGroup[BaseException]", cause)
        assert group.exceptions == (
            error.commit_error,
            error.cleanup_error,
        )


@pytest.mark.regression
async def test_sync_commit_cancellation_records_invalidation_failure(
    application: Application,
) -> None:
    """Preserve commit cancellation and note failed connection cleanup.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()
        manager = await application.container.make_async(DatabaseManager)
        engine = manager.engine("sqlite")

        def cancel_commit(connection: Connection) -> None:
            """Interrupt commit through SQLAlchemy's connection event.
            """  # fmt: skip
            _ = connection
            message = "commit cancelled"
            raise asyncio.CancelledError(message)

        def fail_invalidation(
            dbapi_connection: DBAPIConnection,
            connection_record: ConnectionPoolEntry,
            exception: BaseException | None,
        ) -> None:
            """Fail cleanup after the commit interruption.

            Args:
                dbapi_connection: SQLite connection being invalidated.
                connection_record: SQLAlchemy pool record for the connection.
                exception: Failure that prompted invalidation, if provided.
            """
            _ = dbapi_connection, connection_record, exception
            message = "connection invalidation failed"
            raise LookupError(message)

        def run_interrupted_transaction() -> tuple[
            TransactionReceipt,
            asyncio.CancelledError,
        ]:
            """Return the receipt after synchronous commit cancellation.
            """  # fmt: skip
            receipts: list[TransactionReceipt] = []

            def write_row() -> None:
                """Attempt a write whose commit event raises cancellation.
                """  # fmt: skip
                with DB.transaction() as receipt:
                    receipts.append(receipt)
                    DB.statement(
                        "INSERT INTO transaction_interruptions "
                        "(id, value) VALUES (4, 'uncertain')"
                    )

            with pytest.raises(asyncio.CancelledError) as captured:
                write_row()

            assert len(receipts) == 1
            return receipts[0], captured.value

        event.listen(engine, "commit", cancel_commit)
        event.listen(engine.pool, "invalidate", fail_invalidation)
        try:
            receipt, cancellation = await anyio.to_thread.run_sync(
                run_interrupted_transaction,
            )
        finally:
            event.remove(engine, "commit", cancel_commit)
            event.remove(engine.pool, "invalidate", fail_invalidation)

        assert receipt.outcome is TransactionOutcome.COMMIT_OUTCOME_UNKNOWN
        assert receipt.error is cancellation
        notes = getattr(cancellation, "__notes__", [])
        assert any("commit was interrupted" in note for note in notes)
        assert any("LookupError" in note for note in notes)
