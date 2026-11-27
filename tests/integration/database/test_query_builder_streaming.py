"""Verify bounded query streams release their database resources.
"""  # fmt: skip

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol, cast

import anyio
import pytest

from titanspan.database import (
    DatabaseManager,
    DatabaseServiceProvider,
    ModelNotFoundError,
    MultipleModelsFoundError,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_ROW_COUNT = 7
_STREAM_BATCH_SIZE = 2
_CHUNK_SIZE = 3


class _PoolCheckoutCounter(Protocol):
    """Describe checkout inspection supported by the SQLite test pools.
    """  # fmt: skip

    def checkedout(self) -> int:
        """Return the number of checked-out pool connections.

        Returns:
            The number of checked-out connections.
        """
        ...


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with one disposable SQLite database.

    Args:
        tmp_path: Temporary application root managed by Pytest.

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
                        "database": "database/streaming.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_async_cursor_closes_early_results_and_sessions(
    application: Application,
) -> None:
    """Close the streaming result when its async context exits early.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _prepare_rows()
        manager = await application.container.make_async(DatabaseManager)
        pool = manager.async_engine("sqlite").sync_engine.pool
        query = DB.table("stream_rows").order_by("id")

        async with query.cursor_async(batch_size=_STREAM_BATCH_SIZE) as rows:
            assert _checked_out(pool) == 1
            first = await anext(rows)
            assert first["id"] == 1

        assert _checked_out(pool) == 0
        assert await DB.table("stream_rows").count_async() == _ROW_COUNT


async def test_async_stream_cancellation_releases_cursor_and_session(
    application: Application,
) -> None:
    """Release a live async result when consumer work is cancelled.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _prepare_rows()
        manager = await application.container.make_async(DatabaseManager)
        pool = manager.async_engine("sqlite").sync_engine.pool

        async def cancel_stream() -> None:
            """Cancel after receiving a row from the live cursor.
            """  # fmt: skip
            async with DB.table("stream_rows").cursor_async() as rows:
                assert _checked_out(pool) == 1
                await anext(rows)
                raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await cancel_stream()

        assert _checked_out(pool) == 0
        assert await DB.table("stream_rows").count_async() == _ROW_COUNT


async def test_sync_cursor_and_chunked_iteration_are_bounded(
    application: Application,
) -> None:
    """Close sync cursors early and yield chunks no larger than requested.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _prepare_rows()
        manager = await application.container.make_async(DatabaseManager)

        def consume() -> tuple[int, list[int], int]:
            """Consume one row and all bounded chunks in a worker thread.

            Returns:
                Pool size before and after chunking and row identifiers.
            """
            pool = manager.engine("sqlite").pool
            query = DB.table("stream_rows").order_by("id")
            with query.cursor(batch_size=_STREAM_BATCH_SIZE) as rows:
                assert _checked_out(pool) == 1
                first = next(rows)

            checked_in_after_close = _checked_out(pool)
            observed: list[int] = []
            with query.chunks(_CHUNK_SIZE) as chunks:
                for chunk in chunks:
                    assert len(chunk) <= _CHUNK_SIZE
                    observed.extend(_row_id(row) for row in chunk)

            return _row_id(first), observed, checked_in_after_close

        first, identifiers, checked_out = await anyio.to_thread.run_sync(
            consume,
        )

        assert first == 1
        assert identifiers == list(range(1, _ROW_COUNT + 1))
        assert checked_out == 0
        assert await DB.table("stream_rows").count_async() == _ROW_COUNT


async def test_async_chunks_are_bounded_and_close_on_early_exit(
    application: Application,
) -> None:
    """Close async chunk streams early without retaining a pool connection.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _prepare_rows()
        manager = await application.container.make_async(DatabaseManager)
        pool = manager.async_engine("sqlite").sync_engine.pool

        async with DB.table("stream_rows").chunks_async(_CHUNK_SIZE) as chunks:
            assert _checked_out(pool) == 1
            first = await anext(chunks)
            assert [_row_id(row) for row in first] == [1, 2, 3]

        assert _checked_out(pool) == 0
        assert await DB.table("stream_rows").count_async() == _ROW_COUNT


@pytest.mark.parametrize("batch_size", [0, -1, True])
async def test_stream_batch_size_must_be_positive(
    application: Application,
    batch_size: int,
) -> None:
    """Reject invalid stream sizes before acquiring a connection.

    Args:
        application: Application configured with an isolated SQLite database.
        batch_size: Invalid size rejected before connection acquisition.
    """
    async with application:
        await _prepare_rows()
        with pytest.raises(ValueError, match="positive"):
            DB.table("stream_rows").cursor(batch_size=batch_size)


async def test_key_and_exact_one_retrieval_methods(
    application: Application,
) -> None:
    """Retrieve matching rows with explicit missing and duplicate failures.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _prepare_rows()
        query = DB.table("stream_rows")
        found = await query.find_async(2, key_column="id")
        assert found is not None
        assert found["value"] == "row-2"
        assert [
            row["id"]
            for row in await query.find_many_async(
                (2, 4),
                key_column="id",
            )
        ] == [2, 4]
        assert (
            await DB.table("stream_rows")
            .where("id", 1)
            .sole_value_async("value")
        ) == "row-1"

        with pytest.raises(ModelNotFoundError):
            await DB.table("stream_rows").where("id", -1).sole_async()
        with pytest.raises(MultipleModelsFoundError):
            await DB.table("stream_rows").sole_async()


async def test_keyset_chunks_preserve_filters_and_hide_cursor_column(
    application: Application,
) -> None:
    """Use keyset pages with projected results and grouped conditions.

    Args:
        application: Application configured with an isolated SQLite database.
    """
    async with application:
        await _prepare_rows()
        query = (
            DB.table("stream_rows")
            .select("value")
            .where(
                lambda group: group.where("id", "<=", 3).or_where(
                    "id",
                    ">=",
                    6,
                )
            )
        )
        chunks = [
            chunk
            async for chunk in query.chunks_by_id_async(
                2,
                key_column="id",
            )
        ]

        assert [len(chunk) for chunk in chunks] == [2, 2, 1]
        assert [row["value"] for chunk in chunks for row in chunk] == [
            "row-1",
            "row-2",
            "row-3",
            "row-6",
            "row-7",
        ]
        assert all("id" not in row for chunk in chunks for row in chunk)


async def _prepare_rows() -> None:
    """Create and populate the SQLite table consumed by stream tests.
    """  # fmt: skip
    await DB.statement_async(
        "CREATE TABLE stream_rows (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
    )
    await DB.table("stream_rows").insert_many_async(
        [
            {"id": identifier, "value": f"row-{identifier}"}
            for identifier in range(1, _ROW_COUNT + 1)
        ],
    )


def _checked_out(pool: object) -> int:
    """Read checkout state through SQLAlchemy's public pool capability.

    Args:
        pool: SQLAlchemy pool implementation used by the SQLite engine.

    Returns:
        The number of checked-out connections.
    """
    counter = cast("_PoolCheckoutCounter", pool)
    return counter.checkedout()


def _row_id(row: Mapping[str, object]) -> int:
    """Read an integer fixture key from a detached query row.

    Args:
        row: One mapping returned by the test query.

    Returns:
        The integer row identifier.
    """
    value = row["id"]
    assert isinstance(value, int)
    return value
