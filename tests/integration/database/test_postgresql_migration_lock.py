"""Verify migration advisory locking through a real PostgreSQL connection.
"""  # fmt: skip

from __future__ import annotations

from collections.abc import Callable
from operator import attrgetter
from typing import TYPE_CHECKING, cast

import pytest
from alembic.config import Config
from sqlalchemy.engine import Connection, make_url
from tests.integration.database.postgresql_support import (
    configured_postgres_url,
)

from titanspan.database import (
    DatabaseManager,
    DatabaseServiceProvider,
    MigrationManager,
)
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_DATABASE_PREFIX = "titanspan_codex_test_"

type _MigrationCallback = Callable[[Config], object]
type _Coordinator = Callable[
    [Connection, _MigrationCallback, bool],
    object,
]


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an app for a disposable PostgreSQL integration database.

    Args:
        tmp_path: Temporary application root used for migration paths.

    Returns:
        An unopened application that owns a PostgreSQL service.
    """
    url = configured_postgres_url()
    database_name = make_url(url).database or ""
    if not database_name.startswith(_DATABASE_PREFIX):
        pytest.fail(
            "PostgreSQL integration requires a disposable test database.",
        )
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "postgres",
                "connections": {
                    "postgres": {
                        "url": url,
                        "async_url": url,
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_postgresql_migration_coordinator_takes_transaction_lock(
    application: Application,
) -> None:
    """Acquire Alembic's advisory lock on the active transaction connection.

    Args:
        application: Disposable PostgreSQL application fixture.
    """
    async with application:
        database = await application.container.make_async(DatabaseManager)
        migrations = await application.container.make_async(MigrationManager)
        coordinator = cast(
            "_Coordinator",
            attrgetter("_run_coordinated")(migrations),
        )
        observed_connections: list[Connection] = []

        async with database.session_async("postgres") as session:
            async_connection = await session.connection()

            def apply(sync_connection: Connection) -> object:
                """Build the native Alembic config while the lock is held.

                Args:
                    sync_connection: SQLAlchemy sync connection on the active
                        async session transaction.

                Returns:
                    A deterministic value proving the callback ran.
                """

                def migration(config: Config) -> str:
                    """Record the connection passed into Alembic.

                    Args:
                        config: Alembic configuration bound to this connection.

                    Returns:
                        A marker returned through the lock coordinator.
                    """
                    observed_connections.append(
                        cast(
                            "Connection",
                            config.attributes["connection"],
                        ),
                    )
                    return "locked"

                return coordinator(sync_connection, migration, True)

            result = await async_connection.run_sync(apply)

        assert result == "locked"
        assert len(observed_connections) == 1
        assert observed_connections[0].dialect.name == "postgresql"
