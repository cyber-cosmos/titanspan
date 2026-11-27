"""Verify dialect-aware migration lock orchestration boundaries.

The fake connection isolates the lock policy without claiming MySQL server
compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from operator import attrgetter
from typing import TYPE_CHECKING, cast

import pytest
from alembic.config import Config

from titanspan.database import (
    DatabaseConfiguration,
    DatabaseManager,
    DatabaseMigrationError,
    MigrationManager,
)
from titanspan.foundation import Application

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from pathlib import Path

    from sqlalchemy.engine import Connection
    from sqlalchemy.sql import Executable

pytestmark = pytest.mark.unit

type _MigrationCallback = Callable[[Config], object]
type _Coordinator = Callable[
    [Connection, _MigrationCallback, bool],
    object,
]


@dataclass(frozen=True, slots=True)
class _FakeURL:
    """Provide the configured database identity required by lock naming.

    Attributes:
        database: Database name configured on the simulated server.
    """

    database: str | None


@dataclass(frozen=True, slots=True)
class _FakeEngine:
    """Provide SQLAlchemy's engine URL boundary for the lock policy.

    Attributes:
        url: URL-like value containing the database name.
    """

    url: _FakeURL


@dataclass(frozen=True, slots=True)
class _FakeDialect:
    """Select the dialect path used by migration coordination.

    Attributes:
        name: SQLAlchemy dialect name presented to the coordinator.
    """

    name: str


def _new_statement_list() -> list[str]:
    """Create an independently owned SQL statement list.

    Returns:
        An empty list for one fake connection's statement log.
    """
    return []


def _new_parameter_list() -> list[dict[str, object]]:
    """Create an independently owned bound-parameter list.

    Returns:
        An empty list for one fake connection's parameter log.
    """
    return []


@dataclass(slots=True)
class _FakeConnection:
    """Record migration lock statements without emulating a database.

    Attributes:
        database: Database name used to derive the lock identifier.
        scalar_results: Ordered results or failures for lock statements.
        dialect_name: Dialect selected by the migration coordinator.
        invalidation_error: Optional failure raised during invalidation.
    """

    database: str | None
    scalar_results: list[int | None | BaseException]
    dialect_name: str = "mysql"
    invalidation_error: BaseException | None = None
    statements: list[str] = field(default_factory=_new_statement_list)
    parameters: list[dict[str, object]] = field(
        default_factory=_new_parameter_list,
    )
    invalidated: bool = False

    @property
    def dialect(self) -> _FakeDialect:
        """Return the selected dialect marker.

        Returns:
            A dialect marker suitable for the migration branch selection.
        """
        return _FakeDialect(self.dialect_name)

    @property
    def engine(self) -> _FakeEngine:
        """Return an engine marker containing the database name.

        Returns:
            A fake engine boundary used only for lock identifier derivation.
        """
        return _FakeEngine(_FakeURL(self.database))

    def scalar(
        self,
        statement: Executable,
        parameters: Mapping[str, object] | None = None,
    ) -> int | None:
        """Return the next lock result while recording bound SQL inputs.

        Args:
            statement: SQLAlchemy expression submitted by the lock adapter.
            parameters: Bound values submitted with that expression.

        Returns:
            The configured scalar result for this statement.

        Raises:
            BaseException: The configured failure for this statement.
        """
        self.statements.append(str(statement))
        self.parameters.append(dict(parameters or {}))
        result = self.scalar_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def invalidate(self) -> None:
        """Record invalidation after a lock release cannot be confirmed.

        Raises:
            BaseException: A configured invalidation failure.
        """
        if self.invalidation_error is not None:
            raise self.invalidation_error
        self.invalidated = True


@pytest.fixture
def migrations(tmp_path: Path) -> Iterator[MigrationManager]:
    """Create a migration adapter without opening a physical connection.

    Args:
        tmp_path: Temporary application root used by migration discovery.

    Yields:
        A migration manager with a real application-owned DatabaseManager.
    """
    application = Application(base_path=tmp_path)
    configuration = DatabaseConfiguration.from_mapping(
        {
            "default": "sqlite",
            "connections": {
                "sqlite": {
                    "driver": "sqlite",
                    "database": "database/migrations.sqlite",
                },
            },
        },
        application,
    )
    service = DatabaseManager(configuration)
    yield MigrationManager(service, tmp_path)
    service.close()


def _coordinate(
    manager: MigrationManager,
    connection: _FakeConnection,
    callback: _MigrationCallback,
    *,
    isolated: bool = True,
) -> object:
    """Invoke the private dialect adapter through a narrow typed boundary.

    Args:
        manager: Application-owned migration manager under test.
        connection: Simulated SQLAlchemy connection at the lock boundary.
        callback: Alembic callback invoked while the named lock is held.
        isolated: Whether the test requires cross-process coordination.

    Returns:
        The migration callback result.
    """
    # This test targets the lock adapter, not driver or server behavior.
    coordinator = cast(
        "_Coordinator",
        attrgetter("_run_coordinated")(manager),
    )
    sql_connection = cast("Connection", connection)
    return coordinator(sql_connection, callback, isolated)


def test_mysql_lock_uses_one_redacted_name_for_apply_and_release(
    migrations: MigrationManager,
) -> None:
    """Run the callback between acquisition and release on one connection.

    Args:
        migrations: Application-owned migration manager fixture.
    """
    connection = _FakeConnection("private_database", [1, 1])
    observed_connections: list[object] = []

    def apply(config: Config) -> str:
        """Record which connection Alembic receives while locked.

        Args:
            config: Fresh Alembic configuration for this migration operation.

        Returns:
            A deterministic operation result.
        """
        observed_connections.append(config.attributes["connection"])
        return "applied"

    result = _coordinate(migrations, connection, apply, isolated=False)

    assert result == "applied"
    assert observed_connections == [connection]
    assert connection.statements == [
        "SELECT GET_LOCK(:lock_name, :timeout)",
        "SELECT RELEASE_LOCK(:lock_name)",
    ]
    acquire_name = connection.parameters[0]["lock_name"]
    release_name = connection.parameters[1]["lock_name"]
    assert acquire_name == release_name
    assert isinstance(acquire_name, str)
    assert acquire_name.startswith("titanspan:migrations:")
    assert "private_database" not in acquire_name
    assert connection.invalidated is False


def test_mysql_lock_acquisition_failure_skips_migration_callback(
    migrations: MigrationManager,
) -> None:
    """Reject a failed named-lock acquisition before invoking Alembic.

    Args:
        migrations: Application-owned migration manager fixture.
    """
    connection = _FakeConnection("application", [0])
    callback_called = False

    def apply(_: Config) -> object:
        """Mark an operation that must not run without the lock.
        """  # fmt: skip
        nonlocal callback_called
        callback_called = True
        return None

    with pytest.raises(DatabaseMigrationError, match="Could not acquire"):
        _coordinate(migrations, connection, apply)

    assert callback_called is False
    assert len(connection.statements) == 1
    assert connection.invalidated is False


def test_mysql_operation_failure_releases_lock_and_preserves_cause(
    migrations: MigrationManager,
) -> None:
    """Release an acquired lock while preserving the migration failure.

    Args:
        migrations: Application-owned migration manager fixture.
    """
    connection = _FakeConnection("application", [1, 1])
    operation_error = RuntimeError("migration callback failed")

    def fail(_: Config) -> object:
        """Raise the operation error after lock acquisition.

        Raises:
            RuntimeError: The expected migration failure.
        """
        raise operation_error

    with pytest.raises(RuntimeError, match="migration callback failed") as err:
        _coordinate(migrations, connection, fail)

    assert err.value is operation_error
    assert connection.statements[-1] == "SELECT RELEASE_LOCK(:lock_name)"
    assert connection.invalidated is False


def test_mysql_release_failure_invalidates_lock_owning_connection(
    migrations: MigrationManager,
) -> None:
    """Discard a physical connection when the server denies lock release.

    Args:
        migrations: Application-owned migration manager fixture.
    """
    connection = _FakeConnection("application", [1, 0])

    with pytest.raises(DatabaseMigrationError, match="was not released"):
        _coordinate(migrations, connection, lambda _: "applied")

    assert connection.invalidated


def test_mysql_release_query_error_invalidates_lock_owner(
    migrations: MigrationManager,
) -> None:
    """Discard a connection when releasing its server lock raises.

    Args:
        migrations: Application-owned migration manager fixture.
    """
    release_error = RuntimeError("release query failed")
    connection = _FakeConnection("application", [1, release_error])

    with pytest.raises(RuntimeError, match="release query failed"):
        _coordinate(migrations, connection, lambda _: "applied")

    assert connection.invalidated


def test_mysql_callback_and_release_failure_preserve_operation_error(
    migrations: MigrationManager,
) -> None:
    """Preserve callback failure while recording lock-release failure.

    Args:
        migrations: Application-owned migration manager fixture.
    """
    release_error = RuntimeError("release query failed")
    connection = _FakeConnection("application", [1, release_error])
    operation_error = ValueError("migration callback failed")

    def fail(_: Config) -> object:
        """Raise the callback error while the simulated lock is held.

        Raises:
            ValueError: The expected migration callback failure.
        """
        raise operation_error

    with pytest.raises(ValueError, match="migration callback failed") as err:
        _coordinate(migrations, connection, fail)

    assert err.value is operation_error
    assert any(
        "lock could not be released" in note for note in err.value.__notes__
    )
    assert connection.invalidated


def test_mysql_invalidation_failure_is_recorded_on_release_error(
    migrations: MigrationManager,
) -> None:
    """Retain invalidation failure context without masking lock failure.

    Args:
        migrations: Application-owned migration manager fixture.
    """
    invalidation_error = OSError("connection disposal failed")
    connection = _FakeConnection(
        "application",
        [1, 0],
        invalidation_error=invalidation_error,
    )

    with pytest.raises(DatabaseMigrationError, match="was not released") as err:
        _coordinate(migrations, connection, lambda _: "applied")

    assert any(
        "could not be invalidated" in note for note in err.value.__notes__
    )
    assert connection.invalidated is False
