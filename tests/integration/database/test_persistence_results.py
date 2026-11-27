"""Verify high-level persistence APIs report unsuccessful model writes.

The tests use SQLAlchemy's real Unit of Work and isolated SQLite databases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import (
    DatabaseError,
    DatabaseServiceProvider,
    Model,
    ModelCreating,
    ModelPersistenceCancelledError,
    ModelUpdating,
    Schema,
)
from titanspan.facades.database import DB
from titanspan.facades.event import Event
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_FIRST_EMAIL = "first@example.test"
_SECOND_EMAIL = "second@example.test"
_REJECTED_NAME = "Rejected"


class PersistenceResultUser(Model):
    """Represent users persisted by the result-contract regressions.

    Unique email values make failed writes observable through real constraints.
    """

    table = "persistence_result_users"
    fillable = ("name", "email")

    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with a temporary SQLite database.

    Args:
        tmp_path: Pytest-owned temporary application directory.

    Returns:
        An unopened application configured with Database services.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/persistence_results.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def _create_schema() -> None:
    """Create the table used by persistence-result tests.

    The test table includes the model's generated timestamps and a unique key.
    """
    async with Schema.create("persistence_result_users") as table:
        table.id()
        table.string("name", length=120)
        table.string("email", length=320).unique()
        table.timestamps()


def _values(name: str, email: str) -> dict[str, str]:
    """Return fillable values for one result-test user.

    Args:
        name: User display name.
        email: Unique test email.

    Returns:
        A fresh mass-assignment mapping.
    """
    return {"name": name, "email": email}


def _cancel_creation(event: ModelCreating[PersistenceResultUser]) -> None:
    """Cancel every insert requested by the active test.

    Args:
        event: Model creation event dispatched before flush.
    """
    event.cancel()


def _cancel_named_creation(
    event: ModelCreating[PersistenceResultUser],
) -> None:
    """Cancel the selected insert after an earlier batch item was flushed.

    Args:
        event: Model creation event dispatched before flush.
    """
    if event.model.name == _REJECTED_NAME:
        event.cancel()


def _cancel_update(event: ModelUpdating[PersistenceResultUser]) -> None:
    """Cancel updates requested by the active test.

    Args:
        event: Model update event dispatched before flush.
    """
    event.cancel()


async def test_async_create_helpers_raise_on_cancelled_inserts(
    application: Application,
) -> None:
    """Reject async APIs that promise persisted models when save is cancelled.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_schema()
        with Event.listen(ModelCreating, _cancel_creation):
            rejected = PersistenceResultUser(
                name="Save or fail",
                email=_SECOND_EMAIL,
            )
            with pytest.raises(ModelPersistenceCancelledError):
                await rejected.save_or_fail_async()
            with pytest.raises(ModelPersistenceCancelledError):
                await PersistenceResultUser.create_async(
                    _values("Create", _FIRST_EMAIL),
                )
            with pytest.raises(ModelPersistenceCancelledError):
                await PersistenceResultUser.force_create_async(
                    _values("Force", _FIRST_EMAIL),
                )
            with pytest.raises(ModelPersistenceCancelledError):
                await PersistenceResultUser.create_or_first_async(
                    {"email": _FIRST_EMAIL},
                    {"name": "Create or first"},
                )
            with pytest.raises(ModelPersistenceCancelledError):
                await PersistenceResultUser.first_or_create_async(
                    {"email": _FIRST_EMAIL},
                    {"name": "First or create"},
                )
            with pytest.raises(ModelPersistenceCancelledError):
                await PersistenceResultUser.update_or_create_async(
                    {"email": _FIRST_EMAIL},
                    {"name": "Update or create"},
                )

        assert await DB.table("persistence_result_users").count_async() == 0


async def test_async_create_many_rolls_back_when_an_item_is_cancelled(
    application: Application,
) -> None:
    """Raise and roll back earlier inserts when a batch item is rejected.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_schema()
        with (
            Event.listen(ModelCreating, _cancel_named_creation),
            pytest.raises(ModelPersistenceCancelledError),
        ):
            await PersistenceResultUser.create_many_async(
                [
                    _values("Accepted", _FIRST_EMAIL),
                    _values(_REJECTED_NAME, _SECOND_EMAIL),
                ],
            )

        assert await DB.table("persistence_result_users").count_async() == 0


async def test_async_update_or_create_raises_on_cancelled_update(
    application: Application,
) -> None:
    """Do not return a model as updated when its save was rejected.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_schema()
        original = await PersistenceResultUser.create_async(
            _values("Original", _FIRST_EMAIL),
        )

        with (
            Event.listen(ModelUpdating, _cancel_update),
            pytest.raises(ModelPersistenceCancelledError),
        ):
            await PersistenceResultUser.update_or_create_async(
                {"email": _FIRST_EMAIL},
                {"name": "Rejected update"},
            )

        persisted_name = await (
            DB.table("persistence_result_users")
            .where("id", original.id)
            .value_async("name")
        )
        assert persisted_name == "Original"


async def test_sync_update_or_create_raises_on_cancelled_update(
    application: Application,
) -> None:
    """Preserve the previous value when synchronous update is rejected.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_schema()
        original = await PersistenceResultUser.create_async(
            _values("Original", _FIRST_EMAIL),
        )

        def reject_sync_update() -> None:
            """Run one cancelled update on the synchronous owner thread.

            The native high-level API must not report a rejected save as done.
            """
            with (
                Event.listen(ModelUpdating, _cancel_update),
                pytest.raises(ModelPersistenceCancelledError),
            ):
                PersistenceResultUser.update_or_create(
                    {"email": _FIRST_EMAIL},
                    {"name": "Rejected update"},
                )

        await anyio.to_thread.run_sync(reject_sync_update)
        persisted_name = await (
            DB.table("persistence_result_users")
            .where("id", original.id)
            .value_async("name")
        )
        assert persisted_name == "Original"


async def test_async_factory_does_not_run_after_create_on_cancellation(
    application: Application,
) -> None:
    """Require a successful insert before scheduling factory callbacks.

    Args:
        application: Application configured by the test fixture.
    """
    callbacks: list[PersistenceResultUser] = []

    async with application:
        await _create_schema()
        factory = (
            PersistenceResultUser.factory()
            .sequence(
                _values("Accepted", _FIRST_EMAIL),
                _values(_REJECTED_NAME, _SECOND_EMAIL),
            )
            .after_creating(callbacks.append)
            .count(2)
        )
        with (
            Event.listen(ModelCreating, _cancel_named_creation),
            pytest.raises(ModelPersistenceCancelledError),
        ):
            await factory.create_async()

        assert callbacks == []
        assert await DB.table("persistence_result_users").count_async() == 0


async def test_sync_creation_and_factory_apis_report_cancellation(
    application: Application,
) -> None:
    """Preserve the async cancellation contract in synchronous operations.

    Args:
        application: Application configured by the test fixture.
    """
    callbacks: list[PersistenceResultUser] = []

    async with application:
        await _create_schema()

        def attempt_sync_writes() -> None:
            """Run synchronous Database operations on their owner thread.

            Event cancellation must not be reported as persisted creation.
            """
            with Event.listen(ModelCreating, _cancel_creation):
                rejected = PersistenceResultUser(
                    name="Save or fail",
                    email=_SECOND_EMAIL,
                )
                with pytest.raises(ModelPersistenceCancelledError):
                    rejected.save_or_fail()
                with pytest.raises(ModelPersistenceCancelledError):
                    PersistenceResultUser.create(
                        _values("Create", _FIRST_EMAIL),
                    )
                with pytest.raises(ModelPersistenceCancelledError):
                    PersistenceResultUser.force_create(
                        _values("Force", _FIRST_EMAIL),
                    )
                with pytest.raises(ModelPersistenceCancelledError):
                    PersistenceResultUser.create_or_first(
                        {"email": _FIRST_EMAIL},
                        {"name": "Create or first"},
                    )
                with pytest.raises(ModelPersistenceCancelledError):
                    PersistenceResultUser.first_or_create(
                        {"email": _FIRST_EMAIL},
                        {"name": "First or create"},
                    )
                with pytest.raises(ModelPersistenceCancelledError):
                    PersistenceResultUser.update_or_create(
                        {"email": _FIRST_EMAIL},
                        {"name": "Update or create"},
                    )
                with pytest.raises(ModelPersistenceCancelledError):
                    PersistenceResultUser.create_many(
                        [_values("Batch", _FIRST_EMAIL)],
                    )
                factory = PersistenceResultUser.factory().after_creating(
                    callbacks.append,
                )
                with pytest.raises(ModelPersistenceCancelledError):
                    factory.create(_values("Factory", _FIRST_EMAIL))

        await anyio.to_thread.run_sync(attempt_sync_writes)

        assert callbacks == []
        assert await DB.table("persistence_result_users").count_async() == 0


async def test_sync_create_many_rolls_back_when_later_item_is_cancelled(
    application: Application,
) -> None:
    """Roll back earlier synchronous batch writes after later cancellation.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_schema()

        def create_sync_batch() -> None:
            """Run a real synchronous batch on its owner thread.

            The caller must roll back a prior write after later cancellation.
            """
            with (
                Event.listen(ModelCreating, _cancel_named_creation),
                pytest.raises(ModelPersistenceCancelledError),
            ):
                PersistenceResultUser.create_many(
                    [
                        _values("Accepted", _FIRST_EMAIL),
                        _values(_REJECTED_NAME, _SECOND_EMAIL),
                    ],
                )

        await anyio.to_thread.run_sync(create_sync_batch)
        assert await DB.table("persistence_result_users").count_async() == 0


async def test_factory_does_not_dispatch_after_create_after_database_failure(
    application: Application,
) -> None:
    """Do not report factory success when a real unique constraint fails.

    Args:
        application: Application configured by the test fixture.
    """
    callbacks: list[PersistenceResultUser] = []

    async with application:
        await _create_schema()
        await PersistenceResultUser.create_async(
            _values("Existing", _FIRST_EMAIL),
        )
        factory = PersistenceResultUser.factory().after_creating(
            callbacks.append,
        )

        with pytest.raises(DatabaseError):
            await factory.create_async(
                _values("Duplicate", _FIRST_EMAIL),
            )

        assert callbacks == []
        assert await DB.table("persistence_result_users").count_async() == 1
