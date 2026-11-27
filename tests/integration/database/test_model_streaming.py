"""Verify bounded ORM result streams and deterministic resource cleanup.

The tests use real SQLite sessions and exercise sync and async APIs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy.orm import Mapped  # noqa: TC002  # SQLAlchemy resolves types.

from titanspan.database import DatabaseServiceProvider, Model
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_RECORD_COUNT = 5
_BATCH_SIZE = 2
_CONSUMER_FAILURE = "consumer stopped"


class StreamRecord(Model):
    """Represent rows returned through bounded ORM streams.

    The model uses SQLAlchemy's native ORM result handling.
    """

    table = "stream_records"
    fillable = ("name",)
    name: Mapped[str]


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with an isolated SQLite database.

    Args:
        tmp_path: Pytest-owned directory for the database file.

    Returns:
        An application with the native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/model_streaming.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_async_model_stream_yields_bounded_ordered_results(
    application: Application,
) -> None:
    """Stream model instances in deterministic database order.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_table()
        await _insert_records()
        query = StreamRecord.query().order_by("id")

        async with query.stream_async(batch_size=_BATCH_SIZE) as records:
            identifiers = [record.id async for record in records]

        assert identifiers == list(range(1, _RECORD_COUNT + 1))
        assert await DB.table("stream_records").count_async() == _RECORD_COUNT

        with pytest.raises(ValueError, match="positive integer"):
            async with query.stream_async(batch_size=0):
                pass


async def test_sync_model_stream_closes_after_early_exit(
    application: Application,
) -> None:
    """Release a synchronous result when its consumer stops early.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_table()
        await _insert_records()
        first_identifier = await anyio.to_thread.run_sync(
            _take_first_sync_model,
        )

        assert first_identifier == 1
        assert await DB.table("stream_records").count_async() == _RECORD_COUNT


async def test_async_model_stream_closes_after_consumer_failure(
    application: Application,
) -> None:
    """Close the async result and session when a consumer fails.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_table()
        await _insert_records()

        with pytest.raises(RuntimeError, match=_CONSUMER_FAILURE):
            await _fail_stream_consumer()

        assert await DB.table("stream_records").count_async() == _RECORD_COUNT


async def test_async_model_stream_closes_when_consumer_is_cancelled(
    application: Application,
) -> None:
    """Shield result cleanup when stream consumption is cancelled.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_table()
        await _insert_records()

        with anyio.CancelScope() as scope:
            async with StreamRecord.query().stream_async() as records:
                await anext(records)
                scope.cancel()
                await anyio.lowlevel.checkpoint()

        assert scope.cancel_called
        assert await DB.table("stream_records").count_async() == _RECORD_COUNT


async def test_model_cursor_pages_preserve_order(
    application: Application,
) -> None:
    """Hydrate cursor pages as models in stable query order.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_table()
        await _insert_records()
        query = StreamRecord.query().order_by("name", descending=True)

        first = await query.cursor_paginate_async(per_page=2)
        assert [record.name for record in first.items] == [
            "record-5",
            "record-4",
        ]
        assert first.next_cursor is not None

        second = await query.cursor_paginate_async(
            per_page=2,
            cursor=first.next_cursor,
        )
        assert [record.name for record in second.items] == [
            "record-3",
            "record-2",
        ]


async def test_sync_model_cursor_page_hydrates_selected_models(
    application: Application,
) -> None:
    """Hydrate a synchronous cursor page from a partial projection.

    Args:
        application: Isolated Database application for this test.
    """
    async with application:
        await _create_table()
        await _insert_records()
        names, next_cursor = await anyio.to_thread.run_sync(
            _take_sync_cursor_page,
        )

        assert names == ["record-1", "record-2"]
        assert next_cursor is not None


def _take_first_sync_model() -> int:
    """Read one model and close the synchronous streaming scope.

    Returns:
        The first model primary key.
    """
    with StreamRecord.query().order_by("id").stream(batch_size=1) as records:
        return next(records).id


def _take_sync_cursor_page() -> tuple[list[str], str | None]:
    """Read a projected model page through the synchronous ORM API.

    Returns:
        Model names and an optional next-page cursor.
    """
    page = (
        StreamRecord.query()
        .select("name")
        .order_by("name")
        .cursor_paginate(per_page=2)
    )
    return [record.name for record in page.items], page.next_cursor


async def _create_table() -> None:
    """Create the mapped streaming fixture table.

    The table includes the model's mapped identifier and timestamps.
    """
    await DB.statement_async(
        "CREATE TABLE stream_records ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )


async def _fail_stream_consumer() -> None:
    """Raise after reading one item to exercise async stream cleanup.

    The helper runs inside the test's active application context.
    """
    async with StreamRecord.query().stream_async() as records:
        await anext(records)
        raise RuntimeError(_CONSUMER_FAILURE)


async def _insert_records() -> None:
    """Insert a finite input dataset for streaming checks.

    The bounded test data fits several ORM fetch batches.
    """
    await DB.table("stream_records").insert_many_async(
        [{"name": f"record-{index}"} for index in range(1, _RECORD_COUNT + 1)],
    )
