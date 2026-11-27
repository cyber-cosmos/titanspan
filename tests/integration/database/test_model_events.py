"""Verify model lifecycle events use native Events and commit boundaries.

The tests exercise ORM persistence, the application dispatcher, and real
SQLite transactions together.
"""

from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING, ClassVar

import anyio
import pytest
from sqlalchemy.orm import Mapped  # noqa: TC002

from titanspan.database import DatabaseServiceProvider, Model
from titanspan.database.events import (
    ModelCreated,
    ModelCreating,
    ModelDeleted,
    ModelDeleting,
    ModelSaved,
    ModelSaving,
    ModelUpdated,
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
