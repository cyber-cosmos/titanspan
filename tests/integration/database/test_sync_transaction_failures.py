"""Verify synchronous transaction failure outcomes with real SQLite.

The tests inject failures at SQLAlchemy's flush, commit, and callback
boundaries while exercising the native Database manager and facade.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import (
    DatabaseCommitOutcomeUnknownError,
    DatabaseManager,
    DatabaseServiceProvider,
    DatabaseTransactionCallbackError,
    DatabaseTransactionError,
    Model,
    TransactionOutcome,
    TransactionReceipt,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.engine import Connection

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


class SyncTransactionRecord(Model):
    """Represent rows used to verify synchronous transaction outcomes.

    A unique value forces SQLAlchemy's Unit of Work flush to fail.
    """

    table = "sync_transaction_records"
    fillable = ("value",)

    value: Mapped[str] = mapped_column(unique=True)


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with one disposable SQLite database.

    Args:
        tmp_path: Temporary root used for this test's database file.

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
                        "database": "database/sync_transactions.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def _create_table() -> None:
    """Create the table used by the synchronous transaction tests.
    """  # fmt: skip
    await DB.statement_async(
        "CREATE TABLE sync_transaction_records "
        "(id INTEGER PRIMARY KEY, value TEXT NOT NULL UNIQUE, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )


@pytest.mark.regression
async def test_sync_flush_failure_rolls_back_the_root_transaction(
    application: Application,
) -> None:
    """Report a confirmed rollback when the root Unit of Work cannot flush.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()
        manager = await application.container.make_async(DatabaseManager)
        receipts: list[TransactionReceipt] = []

        def insert_duplicate_models() -> None:
            """Add conflicting models so root commit flush raises.
            """  # fmt: skip
            with manager.transaction() as receipt:
                receipts.append(receipt)
                with manager.session() as session:
                    first = SyncTransactionRecord()
                    first.value = "duplicate"
                    second = SyncTransactionRecord()
                    second.value = "duplicate"
                    session.add_all((first, second))

        with pytest.raises(DatabaseTransactionError) as captured:
            await anyio.to_thread.run_sync(insert_duplicate_models)

        assert len(receipts) == 1
        receipt = receipts[0]
        assert isinstance(captured.value.__cause__, IntegrityError)
        assert receipt.outcome is TransactionOutcome.ROLLED_BACK
        assert await DB.table("sync_transaction_records").count_async() == 0


@pytest.mark.regression
async def test_sync_commit_failure_reports_unknown_outcome_and_recovers(
    application: Application,
) -> None:
    """Mark failed commits uncertain and allow a later transaction to commit.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()
        manager = await application.container.make_async(DatabaseManager)
        engine = manager.engine("sqlite")

        def fail_commit(connection: Connection) -> None:
            """Inject a failure at SQLAlchemy's commit event boundary.

            Args:
                connection: SQLAlchemy connection attempting to commit.
            """
            _ = connection
            message = "injected synchronous commit failure"
            raise RuntimeError(message)

        def run_failed_transaction() -> TransactionReceipt:
            """Capture the outcome reported for an interrupted commit.
            """  # fmt: skip
            receipts: list[TransactionReceipt] = []

            def commit_uncertain_row() -> None:
                """Attempt to commit a row while the hook rejects commit.
                """  # fmt: skip
                with DB.transaction() as receipt:
                    receipts.append(receipt)
                    DB.statement(
                        "INSERT INTO sync_transaction_records "
                        "(id, value) VALUES (1, 'uncertain')"
                    )

            with pytest.raises(
                DatabaseCommitOutcomeUnknownError,
            ) as captured:
                commit_uncertain_row()

            assert len(receipts) == 1
            receipt = receipts[0]
            assert isinstance(captured.value.__cause__, RuntimeError)
            assert receipt.outcome is TransactionOutcome.COMMIT_OUTCOME_UNKNOWN
            return receipt

        event.listen(engine, "commit", fail_commit)
        try:
            receipt = await anyio.to_thread.run_sync(
                run_failed_transaction,
            )
        finally:
            event.remove(engine, "commit", fail_commit)

        assert receipt.outcome is TransactionOutcome.COMMIT_OUTCOME_UNKNOWN

        def run_recovery_transaction() -> TransactionReceipt:
            """Prove the invalidated connection is replaced on later work.
            """  # fmt: skip
            with DB.transaction() as active_receipt:
                DB.statement(
                    "INSERT INTO sync_transaction_records "
                    "(id, value) VALUES (2, 'recovered')"
                )
            return active_receipt

        recovered = await anyio.to_thread.run_sync(
            run_recovery_transaction,
        )
        assert recovered.outcome is TransactionOutcome.COMMITTED
        assert (
            await DB.table("sync_transaction_records")
            .where("id", 2)
            .value_async("value")
            == "recovered"
        )


@pytest.mark.regression
async def test_sync_callback_failure_preserves_commit_and_callback_order(
    application: Application,
) -> None:
    """Report committed persistence and continue ordered callback dispatch.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()

        def commit_with_failing_callback() -> tuple[
            TransactionReceipt,
            DatabaseTransactionCallbackError,
            list[str],
        ]:
            """Commit a row and verify callback order after one failure.
            """  # fmt: skip
            receipts: list[TransactionReceipt] = []
            callback_order: list[str] = []

            def fail_callback() -> None:
                """Raise after the database has committed its row.
                """  # fmt: skip
                message = "synchronous callback failed"
                raise ValueError(message)

            def later_callback() -> None:
                """Record that later callbacks still run after a failure.
                """  # fmt: skip
                callback_order.append("later")

            def commit_row() -> None:
                """Commit the row and register both callbacks.
                """  # fmt: skip
                with DB.transaction() as receipt:
                    receipts.append(receipt)
                    DB.statement(
                        "INSERT INTO sync_transaction_records "
                        "(id, value) VALUES (3, 'committed')"
                    )
                    DB.after_commit(fail_callback)
                    DB.after_commit(later_callback)

            with pytest.raises(
                DatabaseTransactionCallbackError,
            ) as captured:
                commit_row()

            assert len(receipts) == 1
            receipt = receipts[0]
            return receipt, captured.value, callback_order

        receipt, error, callback_order = await anyio.to_thread.run_sync(
            commit_with_failing_callback,
        )

        assert (
            error.outcome is TransactionOutcome.COMMITTED_WITH_CALLBACK_ERRORS
        )
        assert error.committed
        assert error.callback_errors[0].args == ("synchronous callback failed",)
        assert receipt.outcome is error.outcome
        assert receipt.error is error
        assert callback_order == ["later"]
        assert (
            await DB.table("sync_transaction_records")
            .where("id", 3)
            .value_async("value")
            == "committed"
        )
