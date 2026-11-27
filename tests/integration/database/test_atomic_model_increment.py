"""Verify model instance increments remain atomic under task concurrency.

The integration tests use the real SQLAlchemy Unit of Work and SQLite engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import DatabaseServiceProvider, Model
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [
    pytest.mark.integration,
    pytest.mark.concurrency,
    pytest.mark.anyio,
]
_CONCURRENT_TASKS = 2
_EXPECTED_COUNTER_VALUE = 2


class AtomicCounter(Model):
    """Represent one counter row updated by competing application tasks."""

    table = "atomic_counters"
    fillable = ("value",)
    timestamps = False

    value: Mapped[int] = mapped_column(default=0)


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with an isolated SQLite database.

    Args:
        tmp_path: Pytest-managed root for the application database.

    Returns:
        An unopened application with the native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/atomic-increment.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_concurrent_instance_increments_are_atomic(
    application: Application,
) -> None:
    """Apply both increments to the row value present at SQL execution.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await DB.statement_async(
            "CREATE TABLE atomic_counters ("
            "id INTEGER PRIMARY KEY, value INTEGER NOT NULL, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        counter = await AtomicCounter.create_async({"value": 0})
        first = await AtomicCounter.find_async(counter.id)
        second = await AtomicCounter.find_async(counter.id)
        assert first is not None
        assert second is not None
        assert first.value == 0
        assert second.value == 0

        ready = anyio.Event()
        ready_lock = anyio.Lock()
        ready_count = 0
        observed_values: list[int] = []

        async def increment(model: AtomicCounter) -> None:
            """Increment a detached model after both tasks reach the barrier.

            Args:
                model: Independent model instance with the same database key.
            """
            nonlocal ready_count
            async with ready_lock:
                ready_count += 1
                if ready_count == _CONCURRENT_TASKS:
                    ready.set()
            await ready.wait()
            assert await model.increment_async("value")
            observed_values.append(model.value)

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(increment, first)
            tasks.start_soon(increment, second)

        assert sorted(observed_values) == [1, 2]
        assert (
            await AtomicCounter.query().value_async("value")
            == _EXPECTED_COUNTER_VALUE
        )
