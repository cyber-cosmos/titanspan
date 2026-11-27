"""Verify rollback callbacks preserve confirmed transaction outcomes.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest

from titanspan.contracts.database import TransactionOutcome, TransactionReceipt
from titanspan.database import (
    DatabaseServiceProvider,
    DatabaseTransactionCallbackError,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with one disposable SQLite database.

    Args:
        tmp_path: Temporary application root used for the SQLite database.

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
                        "database": "database/transaction_failures.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def _create_table() -> None:
    """Create the table used to prove database rollback behavior.
    """  # fmt: skip
    await DB.statement_async(
        "CREATE TABLE transaction_failure_rows "
        "(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
    )


def _sync_rollback_callback_failure() -> tuple[
    TransactionReceipt, DatabaseTransactionCallbackError
]:
    """Run a sync rollback whose callback raises after rollback succeeds.

    Returns:
        The transaction receipt and its callback failure.
    """
    receipt: TransactionReceipt | None = None

    def fail_callback() -> None:
        """Fail the rollback callback after SQLAlchemy rolls back.
        """  # fmt: skip
        message = "sync rollback callback failed"
        raise RuntimeError(message)

    try:
        with DB.transaction() as active_receipt:
            receipt = active_receipt
            DB.after_rollback(fail_callback)
            DB.statement(
                "INSERT INTO transaction_failure_rows (id, value) "
                "VALUES (1, 'sync root')"
            )
            message = "sync body failed"
            raise ValueError(message)
    except DatabaseTransactionCallbackError as error:
        assert receipt is not None
        return receipt, error
    pytest.fail("The rollback callback failure was not raised.")


def _sync_nested_rollback_callback_failure() -> tuple[
    TransactionReceipt,
    TransactionReceipt,
    DatabaseTransactionCallbackError,
]:
    """Roll back a sync savepoint and then commit its owning transaction.

    Returns:
        The root and savepoint receipts plus the callback failure.
    """
    root_receipt: TransactionReceipt | None = None
    nested_receipt: TransactionReceipt | None = None

    def fail_callback() -> None:
        """Fail the savepoint rollback callback after the savepoint closes.
        """  # fmt: skip
        message = "sync savepoint callback failed"
        raise RuntimeError(message)

    with DB.transaction() as active_root:
        root_receipt = active_root
        DB.statement(
            "INSERT INTO transaction_failure_rows (id, value) "
            "VALUES (1, 'sync outer')"
        )
        try:
            with DB.transaction() as active_nested:
                nested_receipt = active_nested
                DB.after_rollback(fail_callback)
                DB.statement(
                    "INSERT INTO transaction_failure_rows (id, value) "
                    "VALUES (2, 'sync nested')"
                )
                message = "sync savepoint body failed"
                raise ValueError(message)
        except DatabaseTransactionCallbackError as error:
            nested_error = error
        else:
            pytest.fail("The savepoint callback failure was not raised.")
        DB.statement(
            "INSERT INTO transaction_failure_rows (id, value) "
            "VALUES (3, 'sync after savepoint')"
        )

    assert root_receipt is not None
    assert nested_receipt is not None
    return root_receipt, nested_receipt, nested_error


@pytest.mark.regression
async def test_async_rollback_callback_failure_reports_rolled_back_state(
    application: Application,
) -> None:
    """Distinguish rollback callback failure from failed persistence.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()
        receipt: TransactionReceipt | None = None

        def fail_callback() -> None:
            """Fail after SQLAlchemy confirms transaction rollback.
            """  # fmt: skip
            message = "async rollback callback failed"
            raise RuntimeError(message)

        async def run_transaction() -> None:
            """Insert a row and raise after registering a rollback callback.
            """  # fmt: skip
            nonlocal receipt
            async with DB.transaction_async() as active_receipt:
                receipt = active_receipt
                DB.after_rollback(fail_callback)
                await DB.statement_async(
                    "INSERT INTO transaction_failure_rows (id, value) "
                    "VALUES (1, 'async root')"
                )
                message = "async body failed"
                raise ValueError(message)

        with pytest.raises(DatabaseTransactionCallbackError) as captured:
            await run_transaction()

        error = captured.value
        assert receipt is not None
        assert error.outcome is TransactionOutcome.ROLLED_BACK
        assert error.rolled_back
        assert not error.committed
        assert error.callback_errors[0].args == (
            "async rollback callback failed",
        )
        assert receipt.outcome is error.outcome
        assert receipt.error is error
        assert await DB.table("transaction_failure_rows").count_async() == 0


@pytest.mark.regression
async def test_sync_rollback_callback_failure_reports_rolled_back_state(
    application: Application,
) -> None:
    """Keep a synchronous callback failure separate from rollback outcome.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()
        receipt, error = await anyio.to_thread.run_sync(
            _sync_rollback_callback_failure
        )

        assert error.outcome is TransactionOutcome.ROLLED_BACK
        assert error.rolled_back
        assert not error.committed
        assert receipt.outcome is error.outcome
        assert receipt.error is error
        assert await DB.table("transaction_failure_rows").count_async() == 0


@pytest.mark.regression
async def test_async_savepoint_callback_failure_preserves_root_transaction(
    application: Application,
) -> None:
    """Rollback one async savepoint while its root transaction commits.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()
        root_receipt: TransactionReceipt | None = None
        nested_receipt: TransactionReceipt | None = None

        def fail_callback() -> None:
            """Fail after SQLAlchemy confirms savepoint rollback.
            """  # fmt: skip
            message = "async savepoint callback failed"
            raise RuntimeError(message)

        async with DB.transaction_async() as active_root:
            root_receipt = active_root
            await DB.statement_async(
                "INSERT INTO transaction_failure_rows (id, value) "
                "VALUES (1, 'async outer')"
            )
            try:
                async with DB.transaction_async() as active_nested:
                    nested_receipt = active_nested
                    DB.after_rollback(fail_callback)
                    await DB.statement_async(
                        "INSERT INTO transaction_failure_rows (id, value) "
                        "VALUES (2, 'async nested')"
                    )
                    message = "async savepoint body failed"
                    raise ValueError(message)
            except DatabaseTransactionCallbackError as error:
                nested_error = error
            else:
                pytest.fail("The savepoint callback failure was not raised.")
            await DB.statement_async(
                "INSERT INTO transaction_failure_rows (id, value) "
                "VALUES (3, 'async after savepoint')"
            )

        assert root_receipt is not None
        assert nested_receipt is not None
        assert root_receipt.outcome is TransactionOutcome.COMMITTED
        assert nested_receipt.outcome is (
            TransactionOutcome.SAVEPOINT_ROLLED_BACK
        )
        assert nested_error.outcome is (
            TransactionOutcome.SAVEPOINT_ROLLED_BACK
        )
        assert nested_error.rolled_back
        assert not nested_error.committed
        assert nested_receipt.error is nested_error
        assert await DB.table("transaction_failure_rows").pluck_async("id") == [
            1,
            3,
        ]


@pytest.mark.regression
async def test_sync_savepoint_callback_failure_preserves_root_transaction(
    application: Application,
) -> None:
    """Rollback one sync savepoint while its root transaction commits.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _create_table()
        root_receipt, nested_receipt, error = await anyio.to_thread.run_sync(
            _sync_nested_rollback_callback_failure
        )

        assert root_receipt.outcome is TransactionOutcome.COMMITTED
        assert nested_receipt.outcome is (
            TransactionOutcome.SAVEPOINT_ROLLED_BACK
        )
        assert error.outcome is TransactionOutcome.SAVEPOINT_ROLLED_BACK
        assert error.rolled_back
        assert not error.committed
        assert nested_receipt.error is error
        assert await DB.table("transaction_failure_rows").pluck_async("id") == [
            1,
            3,
        ]


__all__ = []
