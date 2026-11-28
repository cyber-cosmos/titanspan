"""Verify Queue dispatch follows the canonical Database transaction outcome.

The local sync Queue driver exercises dispatch timing without external
broker infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

import anyio
import pytest

from titanspan.database import (
    DatabaseServiceProvider,
    DatabaseTransactionCallbackError,
    Schema,
)
from titanspan.facades import Bus, Queue
from titanspan.facades.database import DB
from titanspan.foundation import Application
from titanspan.queue import Job, QueueManager, QueueServiceProvider

if TYPE_CHECKING:
    from pathlib import Path

    from titanspan.contracts.container import ServiceRegistry

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

_DISPATCHED_VALUES: list[str] = []
_COMMITTED_JOB = "committed"
_ROLLED_BACK_JOB = "rolled-back"
_NESTED_JOB = "nested-savepoint"
_ROLLBACK_MESSAGE = "rollback transaction"
_JOB_FAILURE_MESSAGE = "job failed after commit"
_ROLLBACK_MARKER = 2


@dataclass
class _AfterCommitRecordJob(Job):
    """Record one local job execution for transaction assertions.

    The local connection lets tests inspect dispatch timing directly.
    """

    value: str

    def handle(self) -> None:
        """Record the value only when Queue actually executes this job.

        Queue invokes this method after the registered callback fires.
        """
        _DISPATCHED_VALUES.append(self.value)


@dataclass
class _AfterCommitFailureJob(Job):
    """Raise during local execution to verify committed failure reporting.

    The Queue callback error must preserve the already committed outcome.
    """

    def handle(self) -> None:
        """Fail after the Database transaction has already committed.

        Raises:
            ValueError: Always, to exercise post-commit publication failure.
        """
        raise ValueError(_JOB_FAILURE_MESSAGE)


class _DatabaseVisibility:
    """Collect values observed by jobs after their Database transaction.

    The Redis worker reads actual SQLite rows through the Database facade.
    """

    def __init__(self) -> None:
        """Create isolated observations and completion signals.

        One event coordinates the test with its real Redis worker.
        """
        self.rows: list[int] = []
        self.completed = anyio.Event()


@dataclass
class _VerifyCommittedRowJob(Job):
    """Read one row through a real Redis worker after transaction commit.

    This job proves the callback publishes only after the row is visible.
    """

    marker: int

    async def handle(self, visibility: _DatabaseVisibility) -> None:
        """Record whether the selected marker was visible to the worker.

        Args:
            visibility: Application-owned observation dependency.
        """
        exists = (
            await DB.table("after_commit_rows")
            .where(
                "marker",
                self.marker,
            )
            .exists_async()
        )
        if exists:
            visibility.rows.append(self.marker)
        visibility.completed.set()


class _DatabaseVisibilityProvider:
    """Register one application-owned observer for the Redis job.

    The same object records each observed row for its owning test.
    """

    def __init__(self, visibility: _DatabaseVisibility) -> None:
        """Retain the test's isolated job observation.

        Args:
            visibility: Observation object owned by this test application.
        """
        self._visibility = visibility

    def register(self, container: ServiceRegistry) -> None:
        """Expose the same observation to each job scope.

        Args:
            container: Canonical application dependency registry.
        """
        container.instance(_DatabaseVisibility, self._visibility)


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an app with native Database and local Queue services.

    Args:
        tmp_path: Isolated application directory provided by pytest.

    Returns:
        An unopened application with disposable SQLite persistence.
    """
    return Application(
        base_path=tmp_path,
        config={
            "app": {"name": "database-after-commit", "env": "testing"},
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/after-commit.sqlite",
                    },
                },
            },
        },
        service_providers=(
            DatabaseServiceProvider(),
            QueueServiceProvider(
                jobs=(_AfterCommitRecordJob, _AfterCommitFailureJob),
            ),
        ),
    )


async def test_bus_and_queue_dispatch_only_after_outer_commit(
    application: Application,
) -> None:
    """Defer nested dispatch until commit and discard it after rollback.

    Args:
        application: Application configured by the test fixture.
    """
    _DISPATCHED_VALUES.clear()
    async with application:
        async with DB.transaction_async("sqlite"):
            async with DB.transaction_async("sqlite"):
                await Bus.dispatch_after_commit_async(
                    _AfterCommitRecordJob(_COMMITTED_JOB),
                    database="sqlite",
                )
            assert _DISPATCHED_VALUES == []
        assert _DISPATCHED_VALUES == [_COMMITTED_JOB]

        async def rollback_transaction() -> None:
            """Schedule a job and abort the transaction before commit.

            The callback must be discarded when this scope rolls back.
            """
            async with DB.transaction_async("sqlite"):
                await Queue.dispatch_after_commit_async(
                    _AfterCommitRecordJob(_ROLLED_BACK_JOB),
                    database="sqlite",
                )
                raise RuntimeError(_ROLLBACK_MESSAGE)

        with pytest.raises(RuntimeError, match=_ROLLBACK_MESSAGE):
            await rollback_transaction()

        assert _DISPATCHED_VALUES == [_COMMITTED_JOB]


async def test_dispatch_after_commit_runs_immediately_without_transaction(
    application: Application,
) -> None:
    """Preserve Database's immediate callback behavior outside transactions.

    Args:
        application: Application configured by the test fixture.
    """
    _DISPATCHED_VALUES.clear()
    async with application:
        await Bus.dispatch_after_commit_async(
            _AfterCommitRecordJob(_NESTED_JOB),
            database="sqlite",
        )

    assert _DISPATCHED_VALUES == [_NESTED_JOB]


async def test_publication_failure_reports_the_confirmed_commit(
    application: Application,
) -> None:
    """Surface dispatch errors without implying the database rolled back.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        with pytest.raises(DatabaseTransactionCallbackError) as captured:
            async with DB.transaction_async("sqlite"):
                await Bus.dispatch_after_commit_async(
                    _AfterCommitFailureJob(),
                    database="sqlite",
                )

        assert captured.value.committed
        assert "committed" in str(captured.value).casefold()


async def test_real_redis_dispatch_reads_only_committed_database_rows(
    tmp_path: Path,
    queue_redis_port: int,
) -> None:
    """Verify commit and rollback behavior with SQLite and Redis services.

    Args:
        tmp_path: Isolated SQLite application path.
        queue_redis_port: Disposable Redis port supplied by the fixture.
    """
    visibility = _DatabaseVisibility()
    application = Application(
        base_path=tmp_path,
        config={
            "app": {
                "name": f"database-after-commit-{uuid4().hex}",
                "env": "testing",
            },
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/redis-after-commit.sqlite",
                    },
                },
            },
            "queue": {
                "default_connection": "redis",
                "default_queue": "after-commit",
                "connections": {
                    "redis": {
                        "driver": "redis_stream",
                        "options": {
                            "url": (f"redis://127.0.0.1:{queue_redis_port}/15"),
                        },
                    },
                },
            },
        },
        service_providers=(
            DatabaseServiceProvider(),
            _DatabaseVisibilityProvider(visibility),
            QueueServiceProvider(jobs=(_VerifyCommittedRowJob,)),
        ),
    )

    async with application:
        async with Schema.create("after_commit_rows") as table:
            table.id()
            table.integer("marker").unique()

        manager = application.container.make(QueueManager)

        async def run_worker() -> None:
            """Consume only the queue dedicated to this integration test.

            Concurrency and prefetch are bounded to one job.
            """
            await manager.work_async(
                connection="redis",
                queue="after-commit",
                concurrency=1,
                prefetch=1,
            )

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_worker)
            async with DB.transaction_async("sqlite"):
                await DB.table("after_commit_rows").insert_async(
                    {"marker": 1},
                )
                await Bus.dispatch_after_commit_async(
                    _VerifyCommittedRowJob(1),
                    database="sqlite",
                    connection="redis",
                    queue="after-commit",
                )
                assert visibility.rows == []
            with anyio.fail_after(15):
                await visibility.completed.wait()
            assert visibility.rows == [1]

            visibility.completed = anyio.Event()

            async def rollback_redis_dispatch() -> None:
                """Insert and schedule a job before forcing transaction abort.

                Raises:
                    RuntimeError: Always, to verify rollback discards dispatch.
                """
                async with DB.transaction_async("sqlite"):
                    await DB.table("after_commit_rows").insert_async(
                        {"marker": _ROLLBACK_MARKER},
                    )
                    await Queue.dispatch_after_commit_async(
                        _VerifyCommittedRowJob(_ROLLBACK_MARKER),
                        database="sqlite",
                        connection="redis",
                        queue="after-commit",
                    )
                    raise RuntimeError(_ROLLBACK_MESSAGE)

            with pytest.raises(RuntimeError, match=_ROLLBACK_MESSAGE):
                await rollback_redis_dispatch()

            with anyio.move_on_after(0.5):
                await visibility.completed.wait()
            assert visibility.rows == [1]
            assert (
                not await DB.table("after_commit_rows")
                .where(
                    "marker",
                    _ROLLBACK_MARKER,
                )
                .exists_async()
            )
            task_group.cancel_scope.cancel()
