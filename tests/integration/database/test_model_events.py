"""Verify model lifecycle events use native Events and commit boundaries.

The tests exercise ORM persistence, the application dispatcher, and real
SQLite transactions together.
"""

from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING, ClassVar

import anyio
import pytest
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titanspan.database import DatabaseServiceProvider, Model
from titanspan.database.events import (
    ModelCreated,
    ModelCreating,
    ModelDeleted,
    ModelDeleting,
    ModelSaved,
    ModelSaving,
    ModelUpdated,
    ModelUpdating,
)
from titanspan.facades.database import DB
from titanspan.facades.event import Event
from titanspan.foundation import Application

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_ROLLBACK_MARKER = "rollback lifecycle events"
_OBSERVER_HOOK_COUNT = 3


class EventRecord(Model):
    """Represent one row for lifecycle event integration tests.

    The model uses actual SQLite persistence through the application service.
    """

    table = "event_records"
    fillable = ("name",)

    name: Mapped[str]


class EventParent(Model):
    """Represent a parent used to verify cancelled relationship mutations.

    The relationship provides a pending child to the same Unit of Work.
    """

    table = "event_parents"
    fillable = ("name",)

    name: Mapped[str]
    children: Mapped[list[EventChild]] = relationship(
        back_populates="parent",
    )


class EventChild(Model):
    """Represent a child cascaded from a rejected parent update.

    The foreign key proves that no child insert escaped cancellation.
    """

    table = "event_children"
    fillable = ("parent_id", "name")

    parent_id: Mapped[int] = mapped_column(
        ForeignKey("event_parents.id"),
    )
    name: Mapped[str]
    parent: Mapped[EventParent] = relationship(back_populates="children")


class ObserverDependency:
    """Supply a transient dependency to observer instances.

    The unique token proves each observer hook uses Container resolution.
    """

    def __init__(self) -> None:
        """Create a token that identifies this resolved dependency.

        Each observer invocation receives a separately constructed value.
        """
        self.token = object()


class EventRecordObserver:
    """Observe event-record creation and reject its deletion.

    The test uses shared events only within one isolated test application.
    """

    events: ClassVar[list[str]] = []
    dependency_tokens: ClassVar[list[object]] = []

    def __init__(self, dependency: ObserverDependency) -> None:
        """Retain a dependency constructed by the active Container.

        Args:
            dependency: Transient value resolved for this hook invocation.
        """
        self._dependency = dependency

    def creating(self, model: EventRecord) -> bool:
        """Record the pending insert and allow it to continue.

        Args:
            model: Record being inserted by the application.

        Returns:
            ``True`` to allow the insert to continue.
        """
        self.dependency_tokens.append(self._dependency.token)
        self.events.append(f"creating:{model.name}")
        return True

    async def created(self, model: EventRecord) -> None:
        """Record the insert after the owning transaction commits.

        Args:
            model: Record whose insert has committed.
        """
        self.dependency_tokens.append(self._dependency.token)
        self.events.append(f"created:{model.name}")

    def deleting(self, model: EventRecord) -> bool:
        """Reject deletion through the observer's typed model hook.

        Args:
            model: Record whose delete has not yet been flushed.

        Returns:
            ``False`` to cancel the deletion.
        """
        self.dependency_tokens.append(self._dependency.token)
        self.events.append(f"deleting:{model.name}")
        return False


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with an isolated SQLite database.

    Args:
        tmp_path: Pytest-owned temporary directory.

    Returns:
        An application configured with the native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/model_events.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_model_events_dispatch_and_allow_cancellation(
    application: Application,
) -> None:
    """Dispatch pre-save events and honor explicit cancellation.

    Args:
        application: Application configured by the test fixture.
    """
    observed: list[str] = []

    async def cancel(event: ModelCreating[EventRecord]) -> None:
        """Cancel creation at the documented model event boundary.

        The test verifies that no insert reaches SQLite.
        """
        event.cancel()

    def saving(event: ModelSaving[EventRecord]) -> None:
        """Record the first pre-save event in lifecycle order.

        The payload also verifies its concrete model type.
        """
        observed.append(f"saving:{event.model.name}")

    def saved(event: ModelSaved[EventRecord]) -> None:
        """Record a save event after the database commit.

        Cancellation must keep this listener from running.
        """
        observed.append(event.model.name)

    async with application:
        await DB.statement_async(
            "CREATE TABLE event_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        with (
            Event.listen(ModelSaving, saving),
            Event.listen(ModelCreating, cancel),
            Event.listen(
                ModelSaved,
                saved,
            ),
        ):
            record = EventRecord(name="cancelled")
            assert await record.save_async() is False
            assert (
                await DB.scalar_async("SELECT COUNT(*) FROM event_records") == 0
            )
            assert observed == ["saving:cancelled"]


async def test_cancelled_update_discards_changes_before_autoflush(
    application: Application,
) -> None:
    """Discard a rejected persistent update without reverting other models.

    Args:
        application: Application configured by the test fixture.
    """

    async def cancel(event: ModelUpdating[EventRecord]) -> None:
        """Reject this model update before SQLAlchemy flushes it.

        Args:
            event: Update event for the model whose save was rejected.
        """
        event.cancel()

    async with application:
        await DB.statement_async(
            "CREATE TABLE event_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        await EventRecord.create_many_async(
            [{"name": "original"}, {"name": "independent"}],
        )

        async with DB.transaction_async():
            rejected = await EventRecord.find_async(1)
            retained = await EventRecord.find_async(2)
            assert rejected is not None
            assert retained is not None
            retained.name = "legitimate"

            async with DB.transaction_async():
                rejected.name = "rejected"
                with Event.listen(ModelUpdating, cancel):
                    assert not await rejected.save_async()

                persisted_name = await (
                    EventRecord.query()
                    .where("id", rejected.id)
                    .value_async("name")
                )
                assert persisted_name == "original"

        assert await (
            EventRecord.query().where("id", rejected.id).value_async("name")
        ) == "original"
        assert await (
            EventRecord.query().where("id", retained.id).value_async("name")
        ) == "legitimate"


async def test_cancelled_pending_model_cannot_autoflush(
    application: Application,
) -> None:
    """Remove a cancelled pending model from its owning Unit of Work.

    Args:
        application: Application configured by the test fixture.
    """

    def cancel(event: ModelCreating[EventRecord]) -> None:
        """Reject the pending insert before its first flush.

        Args:
            event: Create event for the pending model.
        """
        event.cancel()

    async with application:
        await DB.statement_async(
            "CREATE TABLE event_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        async with DB.transaction_async():
            record = EventRecord(name="pending")
            service = DB.resolve_service()
            async with service.session_async() as session:
                session.add(record)

            with Event.listen(ModelCreating, cancel):
                assert not await record.save_async()

            assert await EventRecord.query().count_async() == 0

        assert await EventRecord.query().count_async() == 0


async def test_cancelled_detached_update_discards_dirty_value(
    application: Application,
) -> None:
    """Keep a cancelled detached update from persisting on a later save.

    Args:
        application: Application configured by the test fixture.
    """

    def cancel(event: ModelUpdating[EventRecord]) -> None:
        """Reject the detached model update.

        Args:
            event: Update event for the model whose save was rejected.
        """
        event.cancel()

    async with application:
        await DB.statement_async(
            "CREATE TABLE event_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        created = await EventRecord.create_async({"name": "original"})
        detached = await EventRecord.find_async(created.id)
        assert detached is not None
        detached.name = "rejected"

        with Event.listen(ModelUpdating, cancel):
            assert not await detached.save_async()

        assert detached.name == "original"
        assert await detached.save_async()
        assert await (
            EventRecord.query()
            .where("id", detached.id)
            .value_async("name")
        ) == "original"


async def test_sync_cancelled_update_does_not_autoflush(
    application: Application,
) -> None:
    """Discard a rejected sync update and preserve unrelated model changes.

    Args:
        application: Application configured by the test fixture.
    """

    def cancel(event: ModelUpdating[EventRecord]) -> None:
        """Reject an attached synchronous model update.

        Args:
            event: Update event for the model whose save was rejected.
        """
        event.cancel()

    async with application:
        await DB.statement_async(
            "CREATE TABLE event_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        await EventRecord.create_many_async(
            [{"name": "original"}, {"name": "independent"}],
        )

        def update_records() -> tuple[str | None, str | None]:
            """Run sync ORM operations on their owning worker thread.

            Returns:
                Values observed after the rejected model's autoflush check.
            """
            with DB.transaction():
                rejected = EventRecord.find(1)
                retained = EventRecord.find(2)
                assert rejected is not None
                assert retained is not None
                rejected.name = "rejected"
                retained.name = "legitimate"

                with Event.listen(ModelUpdating, cancel):
                    assert not rejected.save()

                rejected_name = (
                    EventRecord.query()
                    .where("id", rejected.id)
                    .value("name")
                )
                retained_name = (
                    EventRecord.query()
                    .where("id", retained.id)
                    .value("name")
                )
                assert rejected_name is None or isinstance(rejected_name, str)
                assert retained_name is None or isinstance(retained_name, str)
                return rejected_name, retained_name

        observed = await anyio.to_thread.run_sync(update_records)
        assert observed == ("original", "legitimate")


async def test_sync_cancellation_covers_transient_pending_and_detached_models(
    application: Application,
) -> None:
    """Keep rejected sync writes out of later queries and transaction commits.

    Args:
        application: Application configured by the test fixture.
    """

    def cancel_create(event: ModelCreating[EventRecord]) -> None:
        """Reject a transient or pending insert.

        Args:
            event: Create event for the model whose insert was rejected.
        """
        event.cancel()

    def cancel_update(event: ModelUpdating[EventRecord]) -> None:
        """Reject an update to a detached model.

        Args:
            event: Update event for the model whose write was rejected.
        """
        event.cancel()

    async with application:
        await DB.statement_async(
            "CREATE TABLE event_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        created = await EventRecord.create_async({"name": "original"})

        def reject_sync_models() -> tuple[str | None, int]:
            """Exercise all non-persistent sync model states on one thread.

            Returns:
                The detached value after cancellation and committed row count.
            """
            detached = EventRecord.find(created.id)
            assert detached is not None
            detached.name = "rejected detached"
            with Event.listen(ModelUpdating, cancel_update):
                assert not detached.save()

            with DB.transaction():
                transient = EventRecord(name="transient")
                with Event.listen(ModelCreating, cancel_create):
                    assert not transient.save()

                pending = EventRecord(name="pending")
                service = DB.resolve_service()
                with service.session() as session:
                    session.add(pending)
                with Event.listen(ModelCreating, cancel_create):
                    assert not pending.save()

                count = EventRecord.query().count()

            return detached.name, count

        detached_name, count = await anyio.to_thread.run_sync(
            reject_sync_models,
        )
        assert detached_name == "original"
        assert count == 1
        assert await EventRecord.query().value_async("name") == "original"


async def test_cancelled_relationship_mutation_cannot_insert_child(
    application: Application,
) -> None:
    """Discard a new child cascaded by a cancelled parent update.

    Args:
        application: Application configured by the test fixture.
    """

    def cancel(event: ModelUpdating[EventParent]) -> None:
        """Reject the parent update that introduced the child.

        Args:
            event: Update event for the parent whose save was rejected.
        """
        event.cancel()

    async with application:
        await DB.statement_async(
            "CREATE TABLE event_parents ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        await DB.statement_async(
            "CREATE TABLE event_children ("
            "id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, "
            "name TEXT NOT NULL, created_at TIMESTAMP, "
            "updated_at TIMESTAMP, FOREIGN KEY (parent_id) "
            "REFERENCES event_parents(id))"
        )
        created = await EventParent.create_async({"name": "parent"})

        async with DB.transaction_async():
            parent = await (
                EventParent.query()
                .with_("children")
                .where("id", created.id)
                .first_async()
            )
            assert parent is not None
            parent.children.append(EventChild(name="rejected child"))

            with Event.listen(ModelUpdating, cancel):
                assert not await parent.save_async()

            assert parent.children == []
            assert await EventChild.query().count_async() == 0

        assert await EventChild.query().count_async() == 0


async def test_model_observers_use_container_and_events_lifecycle(
    application: Application,
) -> None:
    """Resolve an observer and deliver typed hooks through Events.

    Args:
        application: Application configured by the test fixture.
    """
    EventRecordObserver.events.clear()
    EventRecordObserver.dependency_tokens.clear()
    async with application:
        await DB.statement_async(
            "CREATE TABLE event_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        registrations = EventRecord.observe(EventRecordObserver)
        with ExitStack() as stack:
            for registration in registrations:
                stack.enter_context(registration)

            record = await EventRecord.create_async({"name": "observed"})
            assert not await record.delete_async()

        assert EventRecordObserver.events == [
            "creating:observed",
            "created:observed",
            "deleting:observed",
        ]
        assert (
            len(EventRecordObserver.dependency_tokens) == _OBSERVER_HOOK_COUNT
        )
        assert len(set(EventRecordObserver.dependency_tokens)) == (
            _OBSERVER_HOOK_COUNT
        )
        assert await DB.scalar_async("SELECT COUNT(*) FROM event_records") == 1


def test_model_observers_reject_missing_or_invalid_hooks() -> None:
    """Reject observer classes that cannot handle a model lifecycle event.

    No application context is needed because validation happens before
    registrations are created.
    """

    class EmptyObserver:
        """Represent an observer without lifecycle hooks.

        Registration must reject this empty declaration.
        """

    class InvalidObserver:
        """Represent an observer with a non-callable lifecycle hook.

        Registration must reject this invalid declaration.
        """

        creating = object()

    with pytest.raises(ValueError, match="lifecycle method"):
        EventRecord.observe(EmptyObserver)
    with pytest.raises(TypeError, match="hooks must be callable"):
        EventRecord.observe(InvalidObserver)


async def test_created_events_wait_for_the_outer_transaction_commit(
    application: Application,
) -> None:
    """Await async observers only after the owning transaction commits.

    Args:
        application: Application configured by the test fixture.
    """
    observed: list[str] = []

    async def created(event: ModelCreated[EventRecord]) -> None:
        """Record a created event through the async dispatcher.

        The test checks that rollback suppresses this notification.
        """
        observed.append(event.model.name)

    async def callback() -> None:
        """Record explicit async after-commit registration order.

        This callback is registered before model persistence.
        """
        observed.append("callback")

    async def nested_callback() -> None:
        """Record a committed savepoint callback in registration order.

        The callback must remain after the outer callback.
        """
        observed.append("nested")

    async with application:
        await DB.statement_async(
            "CREATE TABLE event_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        with Event.listen(ModelCreated, created):
            async with DB.transaction_async():
                record = EventRecord(name="committed")
                await DB.after_commit_async(callback)
                async with DB.transaction_async():
                    await DB.after_commit_async(nested_callback)
                await record.save_async()
                assert observed == []
            assert observed == ["callback", "nested", "committed"]

            with pytest.raises(RuntimeError, match=_ROLLBACK_MARKER):
                await _rollback_record(callback)

            assert observed == ["callback", "nested", "committed"]
            assert (
                await DB.scalar_async("SELECT COUNT(*) FROM event_records") == 1
            )


async def test_delete_events_are_dispatched_after_deletion(
    application: Application,
) -> None:
    """Dispatch deleting before SQL and deleted after committed removal.

    Args:
        application: Application configured by the test fixture.
    """
    observed: list[str] = []

    def deleting(event: ModelDeleting[EventRecord]) -> None:
        """Observe the model while its row still exists.

        The later query verifies committed deletion.
        """
        observed.append(f"deleting:{event.model.name}")

    async def deleted(event: ModelDeleted[EventRecord]) -> None:
        """Observe the committed removal through async listeners.

        This event follows the transaction's successful commit.
        """
        observed.append(f"deleted:{event.model.name}")

    async with application:
        await DB.statement_async(
            "CREATE TABLE event_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        record = await EventRecord.create_async({"name": "remove me"})
        with (
            Event.listen(ModelDeleting, deleting),
            Event.listen(
                ModelDeleted,
                deleted,
            ),
        ):
            assert await record.delete_async()

        assert observed == ["deleting:remove me", "deleted:remove me"]
        assert await DB.scalar_async("SELECT COUNT(*) FROM event_records") == 0


async def test_listener_failure_does_not_reverse_a_committed_write(
    application: Application,
) -> None:
    """Surface post-commit listener failure without claiming rollback.

    Args:
        application: Application configured by the test fixture.
    """

    async def fail(event: ModelCreated[EventRecord]) -> None:
        """Raise after the database has committed the insert.

        The test distinguishes event failure from database rollback.
        """
        raise RuntimeError(event.model.name)

    async with application:
        await DB.statement_async(
            "CREATE TABLE event_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        with (
            Event.listen(ModelCreated, fail),
            pytest.raises(ExceptionGroup, match="callbacks failed"),
        ):
            await EventRecord.create_async({"name": "committed first"})

        assert await DB.scalar_async("SELECT COUNT(*) FROM event_records") == 1


async def _rollback_record(callback: Callable[[], Awaitable[None]]) -> None:
    """Persist a model and deliberately roll back its transaction.

    Raises:
        RuntimeError: The expected marker used by the caller's assertion.
    """
    async with DB.transaction_async():
        await DB.after_commit_async(callback)
        rolled_back = EventRecord(name="rolled back")
        await rolled_back.save_async()
        raise RuntimeError(_ROLLBACK_MARKER)


def _sync_create(name: str) -> EventRecord:
    """Create one record through the synchronous Active Record API.

    Args:
        name: Persisted display name.

    Returns:
        The created model detached from its operation session.
    """
    return EventRecord.create({"name": name})


def _sync_update(identifier: int) -> None:
    """Update one record through the sync API from its worker thread.

    Args:
        identifier: Primary key returned by the create operation.
    """
    record = EventRecord.find_or_fail(identifier)
    record.name = "updated record"
    record.save()


async def test_sync_events_use_the_same_application_dispatcher(
    application: Application,
) -> None:
    """Dispatch synchronous lifecycle events from the owning worker thread.

    Args:
        application: Application configured by the test fixture.
    """
    observed: list[str] = []

    def created(event: ModelCreated[EventRecord]) -> None:
        """Record the synchronous post-commit callback.

        The test invokes this listener from an AnyIO worker thread.
        """
        observed.append(event.model.name)

    def updated(event: ModelUpdated[EventRecord]) -> None:
        """Record a synchronous update event after commit.

        The observed value comes from the persisted model instance.
        """
        observed.append(event.model.name)

    async with application:
        await DB.statement_async(
            "CREATE TABLE event_records ("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        with (
            Event.listen(ModelCreated, created),
            Event.listen(ModelUpdated, updated),
        ):
            record = await anyio.to_thread.run_sync(
                _sync_create,
                "sync record",
            )
            await anyio.to_thread.run_sync(_sync_update, record.id)

        assert observed == ["sync record", "updated record"]
