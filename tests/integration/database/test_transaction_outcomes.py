"""Verify explicit outcomes for application-owned transactions.

The tests exercise SQLAlchemy's real SQLite transactions through the native
Database manager and facade.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy import event

from titanspan.database import (
    DatabaseCommitOutcomeUnknownError,
    DatabaseServiceProvider,
    DatabaseTransactionCallbackError,
    TransactionOutcome,
    TransactionReceipt,
)
from titanspan.database.manager import DatabaseManager
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from sqlalchemy.engine import Connection

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with an isolated SQLite database.

    Args:
        tmp_path: Temporary root used for the database file.

    Returns:
        An application that owns one lazily initialized SQLite engine.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/transactions.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def _create_table() -> None:
    """Create the table used by transaction outcome tests.
    """  # fmt: skip
    await DB.statement_async(
        "CREATE TABLE outcomes (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
    )


async def _cause_rollback(
    receipts: list[TransactionReceipt],
) -> None:
    """Raise inside a transaction after recording its receipt.

    Args:
        receipts: Collection receiving the transaction receipt.
    """
    message = "rollback marker"
    async with DB.transaction_async() as receipt:
        receipts.append(receipt)
        await DB.statement_async(
            "INSERT INTO outcomes (id, value) VALUES (2, 'rolled back')"
        )
        raise ValueError(message)


async def _fail_savepoint(
    receipts: list[TransactionReceipt],
    callback: Callable[[], Awaitable[None]],
    rollback_callback: Callable[[], None],
) -> None:
    """Raise inside a savepoint after registering its callbacks.

    Args:
        receipts: Collection receiving the savepoint receipt.
        callback: Commit callback expected to be discarded on rollback.
        rollback_callback: Callback expected to run after savepoint rollback.
    """
    message = "savepoint marker"
    async with DB.transaction_async() as receipt:
        receipts.append(receipt)
        await DB.after_commit_async(callback)
        DB.after_rollback(rollback_callback)
        raise ValueError(message)


@pytest.mark.regression
async def test_async_transaction_reports_commit_and_confirmed_rollback(
    application: Application,
) -> None:
    """Expose committed and rolled-back outcomes on each transaction receipt.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()
        async with DB.transaction_async() as committed:
            await DB.statement_async(
                "INSERT INTO outcomes (id, value) VALUES (1, 'committed')"
            )

        assert committed.outcome is TransactionOutcome.COMMITTED

        receipts: list[TransactionReceipt] = []
        with pytest.raises(ValueError, match="rollback marker"):
            await _cause_rollback(receipts)

        assert receipts[0].outcome is TransactionOutcome.ROLLED_BACK
        assert await DB.table("outcomes").count_async() == 1


@pytest.mark.regression
async def test_savepoint_outcome_and_callback_order_follow_root_outcome(
    application: Application,
) -> None:
    """Report savepoint rollback and preserve ordered outer commit callbacks.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    observed: list[str] = []

    async def root_callback() -> None:
        """Append the root async callback marker.
        """  # fmt: skip
        observed.append("root-async")

    async def nested_callback() -> None:
        """Append the successful savepoint callback marker.
        """  # fmt: skip
        observed.append("nested-async")

    async def discarded_callback() -> None:
        """Mark callbacks incorrectly retained from rolled-back savepoints.
        """  # fmt: skip
        observed.append("discarded")

    def rollback_callback() -> None:
        """Append the rolled-back savepoint callback marker.
        """  # fmt: skip
        observed.append("nested-rollback")

    async with application:
        await _create_table()
        async with DB.transaction_async() as outer:
            DB.after_commit(lambda: observed.append("root-sync"))
            await DB.after_commit_async(root_callback)

            failed_receipts: list[TransactionReceipt] = []
            with pytest.raises(ValueError, match="savepoint marker"):
                await _fail_savepoint(
                    failed_receipts,
                    discarded_callback,
                    rollback_callback,
                )

            assert (
                failed_receipts[0].outcome
                is TransactionOutcome.SAVEPOINT_ROLLED_BACK
            )
            assert observed == ["nested-rollback"]

            async with DB.transaction_async() as released:
                await DB.after_commit_async(nested_callback)

            assert released.outcome is TransactionOutcome.SAVEPOINT_RELEASED
            assert observed == ["nested-rollback"]

        assert outer.outcome is TransactionOutcome.COMMITTED
        assert observed == [
            "nested-rollback",
            "root-sync",
            "root-async",
            "nested-async",
        ]


@pytest.mark.regression
async def test_async_post_commit_callback_failure_reports_committed_write(
    application: Application,
) -> None:
    """Distinguish callback failure from a failed database commit.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    callback_order: list[str] = []
    receipts: list[TransactionReceipt] = []

    async def failing_callback() -> None:
        """Raise after recording the callback position.
        """  # fmt: skip
        callback_order.append("failed")
        message = "observer failed"
        raise ValueError(message)

    async def later_callback() -> None:
        """Prove later callbacks still run after an ordinary failure.
        """  # fmt: skip
        callback_order.append("later")

    async def run_transaction() -> None:
        """Commit a row before invoking an ordered callback sequence.
        """  # fmt: skip
        async with DB.transaction_async() as receipt:
            receipts.append(receipt)
            await DB.statement_async(
                "INSERT INTO outcomes (id, value) VALUES (1, 'durable')"
            )
            await DB.after_commit_async(failing_callback)
            await DB.after_commit_async(later_callback)

    async with application:
        await _create_table()
        with pytest.raises(DatabaseTransactionCallbackError) as captured:
            await run_transaction()

        error = captured.value
        assert (
            error.outcome is TransactionOutcome.COMMITTED_WITH_CALLBACK_ERRORS
        )
        assert error.committed
        assert error.callback_errors[0].args == ("observer failed",)
        assert receipts[0].outcome is error.outcome
        assert receipts[0].error is error
        assert callback_order == ["failed", "later"]
        assert await DB.table("outcomes").value_async("value") == "durable"


@pytest.mark.regression
async def test_callback_cancellation_preserves_cancellation_after_commit(
    application: Application,
) -> None:
    """Propagate callback cancellation while exposing the committed outcome.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    receipts: list[TransactionReceipt] = []

    async def cancel_callback() -> None:
        """Raise cancellation after the database commit has completed.
        """  # fmt: skip
        raise asyncio.CancelledError

    async def run_transaction() -> None:
        """Commit a row before propagating callback cancellation.
        """  # fmt: skip
        async with DB.transaction_async() as receipt:
            receipts.append(receipt)
            await DB.statement_async(
                "INSERT INTO outcomes (id, value) VALUES (1, 'durable')"
            )
            await DB.after_commit_async(cancel_callback)

    async with application:
        await _create_table()
        with pytest.raises(asyncio.CancelledError) as captured:
            await run_transaction()

        assert (
            receipts[0].outcome
            is TransactionOutcome.COMMITTED_WITH_CALLBACK_ERRORS
        )
        assert receipts[0].error is captured.value
        assert await DB.table("outcomes").value_async("value") == "durable"


@pytest.mark.regression
async def test_failed_commit_reports_unknown_outcome_and_releases_resources(
    application: Application,
) -> None:
    """Report uncertain commit failures and permit a later transaction.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()
        manager = await application.container.make_async(DatabaseManager)
        engine = manager.async_engine("sqlite").sync_engine
        receipts: list[TransactionReceipt] = []

        def fail_commit(connection: Connection) -> None:
            """Inject a failure at SQLAlchemy's connection commit boundary.

            Args:
                connection: Connection whose commit event is being tested.
            """
            _ = connection
            message = "injected commit failure"
            raise RuntimeError(message)

        async def run_transaction() -> None:
            """Attempt a commit while the connection hook rejects it.
            """  # fmt: skip
            async with DB.transaction_async() as receipt:
                receipts.append(receipt)
                await DB.statement_async(
                    "INSERT INTO outcomes (id, value) VALUES (1, 'uncertain')"
                )

        event.listen(engine, "commit", fail_commit)
        try:
            with pytest.raises(
                DatabaseCommitOutcomeUnknownError,
            ) as captured:
                await run_transaction()
        finally:
            event.remove(engine, "commit", fail_commit)

        assert receipts[0].outcome is TransactionOutcome.COMMIT_OUTCOME_UNKNOWN
        assert receipts[0].error is captured.value
        assert isinstance(captured.value.__cause__, RuntimeError)

        async with DB.transaction_async() as later:
            assert await DB.table("outcomes").count_async() in (0, 1)
        assert later.outcome is TransactionOutcome.COMMITTED


@pytest.mark.regression
async def test_sync_transaction_reports_receipt_after_callback_failure(
    application: Application,
) -> None:
    """Expose confirmed synchronous commit despite callback errors.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()

        def execute_sync_transaction() -> TransactionOutcome:
            """Run a synchronous transaction on its owning worker thread.

            Returns:
                The committed outcome recorded before callback dispatch fails.
            """
            receipt: TransactionReceipt | None = None

            def fail_callback() -> None:
                """Raise after the synchronous transaction commits.
                """  # fmt: skip
                message = "sync callback failed"
                raise ValueError(message)

            def run_transaction() -> None:
                """Commit a row before dispatching a failing callback.
                """  # fmt: skip
                nonlocal receipt
                with DB.transaction() as active_receipt:
                    receipt = active_receipt
                    DB.statement(
                        "INSERT INTO outcomes (id, value) VALUES (1, 'durable')"
                    )
                    DB.after_commit(fail_callback)

            with pytest.raises(DatabaseTransactionCallbackError):
                run_transaction()

            assert receipt is not None
            assert DB.table("outcomes").value("value") == "durable"
            return receipt.outcome

        outcome = await anyio.to_thread.run_sync(execute_sync_transaction)
        assert outcome is TransactionOutcome.COMMITTED_WITH_CALLBACK_ERRORS
