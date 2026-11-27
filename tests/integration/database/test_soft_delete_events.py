"""Verify soft-delete events respect cancellation and transaction commits.

The tests exercise native model writes, events, and SQLite persistence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy.orm import Mapped  # noqa: TC002  # SQLAlchemy resolves types.

from titanspan.database import (
    DatabaseServiceProvider,
    Model,
    ModelDeleted,
    ModelDeleting,
    ModelForceDeleted,
    ModelForceDeleting,
    ModelRestored,
    ModelRestoring,
    ModelSoftDeleted,
    ModelSoftDeleting,
    SoftDeletes,
)
from titanspan.facades.database import DB
from titanspan.facades.event import Event
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_EVENT_ORDER = (
    "soft-deleting",
    "soft-deleted",
    "restoring",
    "restored",
)
_FORCE_DELETE_ORDER = (
    "force-deleting",
    "deleting",
    "deleted",
    "force-deleted",
)


class SoftDeleteEventRecord(SoftDeletes, Model):
    """Represent a row with cancellable soft-delete lifecycle events.

    The model uses the shared soft-delete behavior from Database.
    """

    table = "soft_delete_event_records"
    fillable = ("name",)
    name: Mapped[str]


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with an isolated SQLite database.

    Args:
        tmp_path: Pytest-owned directory for the database file.

    Returns:
        An application with its native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/soft_delete_events.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_soft_delete_and_restore_events_wait_for_commit(
    application: Application,
) -> None:
    """Dispatch soft-delete lifecycle events around durable state changes.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_table()
        record = await SoftDeleteEventRecord.create_async({"name": "draft"})
        observed: list[str] = []

        def soft_deleting(
            event: ModelSoftDeleting[SoftDeleteEventRecord],
        ) -> None:
            """Record the pending soft-delete event.

            Args:
                event: Soft-delete operation not yet flushed.
            """
            assert event.model is record
            observed.append("soft-deleting")

        def soft_deleted(
            event: ModelSoftDeleted[SoftDeleteEventRecord],
        ) -> None:
            """Record a soft-delete after its transaction commits.

            Args:
                event: Soft-deleted record after commit.
            """
            assert event.model is record
            observed.append("soft-deleted")

        def restoring(event: ModelRestoring[SoftDeleteEventRecord]) -> None:
            """Record the pending restoration event.

            Args:
                event: Restore operation not yet flushed.
            """
            assert event.model is record
            observed.append("restoring")

        def restored(event: ModelRestored[SoftDeleteEventRecord]) -> None:
            """Record a restoration after its transaction commits.

            Args:
                event: Restored record after commit.
            """
            assert event.model is record
            observed.append("restored")

        with (
            Event.listen(ModelSoftDeleting, soft_deleting),
            Event.listen(ModelSoftDeleted, soft_deleted),
            Event.listen(ModelRestoring, restoring),
            Event.listen(ModelRestored, restored),
        ):
            async with DB.transaction_async():
                assert await record.delete_async()
                assert observed == ["soft-deleting"]
            assert observed == list(_EVENT_ORDER[:2])

            async with DB.transaction_async():
                assert await record.restore_async()
                assert observed == [
                    "soft-deleting",
                    "soft-deleted",
                    "restoring",
                ]
            assert observed == list(_EVENT_ORDER)


async def test_cancelled_soft_delete_does_not_change_the_record(
    application: Application,
) -> None:
    """Reject a soft delete before changing mapped state or database rows.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_table()
        record = await SoftDeleteEventRecord.create_async({"name": "draft"})

        def cancel(event: ModelSoftDeleting[SoftDeleteEventRecord]) -> None:
            """Cancel the pending soft-delete operation.

            Args:
                event: Soft-delete event that may reject the write.
            """
            event.cancel()

        with Event.listen(ModelSoftDeleting, cancel):
            assert not await record.delete_async()

        assert not record.trashed()
        assert await SoftDeleteEventRecord.query().count_async() == 1


async def test_force_delete_events_wrap_the_delete_lifecycle(
    application: Application,
) -> None:
    """Dispatch force-delete events around standard deletion events.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_table()
        record = await SoftDeleteEventRecord.create_async({"name": "draft"})
        observed: list[str] = []

        def force_deleting(
            event: ModelForceDeleting[SoftDeleteEventRecord],
        ) -> None:
            """Record a pending force-delete operation.

            Args:
                event: Force-delete lifecycle event.
            """
            assert event.model is record
            observed.append("force-deleting")

        def deleting(event: ModelDeleting[SoftDeleteEventRecord]) -> None:
            """Record the standard delete lifecycle event.

            Args:
                event: Delete lifecycle event.
            """
            assert event.model is record
            observed.append("deleting")

        def deleted(event: ModelDeleted[SoftDeleteEventRecord]) -> None:
            """Record a committed delete lifecycle event.

            Args:
                event: Delete event after commit.
            """
            assert event.model is record
            observed.append("deleted")

        def force_deleted(
            event: ModelForceDeleted[SoftDeleteEventRecord],
        ) -> None:
            """Record a committed force-delete operation.

            Args:
                event: Force-delete event after commit.
            """
            assert event.model is record
            observed.append("force-deleted")

        with (
            Event.listen(ModelForceDeleting, force_deleting),
            Event.listen(ModelDeleting, deleting),
            Event.listen(ModelDeleted, deleted),
            Event.listen(ModelForceDeleted, force_deleted),
        ):
            assert await record.force_delete_async()

        assert observed == list(_FORCE_DELETE_ORDER)


async def test_sync_soft_delete_events_run_on_the_owner_thread(
    application: Application,
) -> None:
    """Run synchronous soft-delete lifecycle operations in a worker thread.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_table()
        record = await SoftDeleteEventRecord.create_async({"name": "draft"})
        observed: list[str] = []

        def soft_deleted(
            event: ModelSoftDeleted[SoftDeleteEventRecord],
        ) -> None:
            """Record a sync soft-delete after its commit.

            Args:
                event: Soft-deleted record after commit.
            """
            assert event.model is record
            observed.append("deleted")

        def restored(event: ModelRestored[SoftDeleteEventRecord]) -> None:
            """Record a sync restore after its commit.

            Args:
                event: Restored record after commit.
            """
            assert event.model is record
            observed.append("restored")

        with (
            Event.listen(ModelSoftDeleted, soft_deleted),
            Event.listen(ModelRestored, restored),
        ):
            deleted, restored_model = await anyio.to_thread.run_sync(
                _sync_soft_delete_and_restore,
                record,
            )

        assert deleted
        assert restored_model
        assert observed == ["deleted", "restored"]


async def _create_table() -> None:
    """Create the mapped soft-delete fixture table.

    The table includes every field declared by the mapped model.
    """
    await DB.statement_async(
        "CREATE TABLE soft_delete_event_records ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "deleted_at TIMESTAMP, created_at TIMESTAMP, updated_at TIMESTAMP)"
    )


def _sync_soft_delete_and_restore(
    record: SoftDeleteEventRecord,
) -> tuple[bool, bool]:
    """Delete and restore one model through sync APIs on its worker thread.

    Args:
        record: Application-owned model prepared by the async test.

    Returns:
        Whether both state transitions committed.
    """
    return record.delete(), record.restore()
