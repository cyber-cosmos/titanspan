"""Manage Alembic revisions through application-owned Database sessions.

The manager supplies a connection to a small generated Alembic environment.
Alembic remains authoritative for revision graphs and database revision state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import blake2s
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import Script, ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from titanspan.database.exceptions import DatabaseMigrationError
from titanspan.database.model import Model

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy.engine import Connection as SQLConnection

    from titanspan.contracts.database import DatabaseService

_ENVIRONMENT_NAME = "env.py"
_VERSIONS_DIRECTORY = "versions"
_TEMPLATE_NAME = "script.py.mako"
_MIGRATION_CLASS_NAME = "NativeMigration"
_INVALID_CLASS_CHARS = re.compile(r"[^A-Za-z0-9]+")
_MIGRATION_LOCK_NAMESPACE = 1_414_083_649
_MIGRATION_LOCK_OBJECT = 1_296_641_874
_MIGRATION_LOCK_TIMEOUT_SECONDS = 30
_Result = TypeVar("_Result")

_ENVIRONMENT = '''"""Run Alembic revisions on a Titanspan-owned connection."""

from alembic import context

config = context.config
connection = config.attributes.get("connection")
if connection is None:
    raise RuntimeError("A Titanspan Database connection is required.")

target_metadata = config.attributes.get("target_metadata")
context.configure(
    connection=connection,
    target_metadata=target_metadata,
    compare_type=True,
    render_as_batch=connection.dialect.name == "sqlite",
)

with context.begin_transaction():
    context.run_migrations()
'''

_TEMPLATE = '''${repr(message)}
# Revision ID: ${up_revision}
# Revises: ${down_revision | comma,n}
# Create Date: ${create_date}

from typing import Sequence

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Apply this revision."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Reverse this revision."""
    ${downgrades if downgrades else "pass"}
'''


@dataclass(frozen=True, slots=True)
class MigrationStatus:
    """Describe one Alembic revision relative to stored database heads.

    Attributes:
        revision: Alembic revision identifier.
        down_revision: Parent revision identifier or identifiers.
        applied: Whether the revision is an ancestor of a stored head.
        current_head: Whether the revision is a stored database head.
    """

    revision: str
    down_revision: str | Sequence[str] | None
    applied: bool
    current_head: bool


class MigrationManager:
    """Run migrations through Alembic and the active application service.

    The manager resolves the selected connection from the application.
    """

    def __init__(
        self,
        service: DatabaseService,
        base_path: Path,
        migration_path: Path | None = None,
    ) -> None:
        """Bind revisions to one app root and canonical Database service.

        Args:
            service: Application-owned Database contract.
            base_path: Application root used for path safety.
            migration_path: Optional app-relative migration directory.

        Raises:
            DatabaseMigrationError: If the path escapes the application root.
        """
        self._service = service
        self._base_path = base_path.resolve()
        selected = migration_path or Path("database/migrations")
        candidate = (
            selected if selected.is_absolute() else self._base_path / selected
        )
        self._migration_path = candidate.resolve()
        if not self._migration_path.is_relative_to(self._base_path):
            message = "Migration paths must remain inside the application."
            raise DatabaseMigrationError(message)
        if not self._migration_path.resolve().is_relative_to(self._base_path):
            message = "Migration paths must remain inside the application."
            raise DatabaseMigrationError(message)

    @property
    def migration_path(self) -> Path:
        """Return the absolute application-owned migration directory.

        Returns:
            The directory containing Alembic environment and revisions.
        """
        return self._migration_path

    def target_identity(self, connection: str | None = None) -> str:
        """Return the selected target identity without credentials.

        Args:
            connection: Optional configured connection name.

        Returns:
            A URL identifying the database target with credentials removed.
        """
        return self._service.connection(connection).target_identity

    def install(
        self,
        connection: str | None = None,
        *,
        isolated: bool = False,
    ) -> None:
        """Create Alembic's version table without applying revisions.

        Args:
            connection: Optional named application connection.
            isolated: Require database-supported cross-process coordination.
        """
        self._execute_sync(
            connection,
            lambda config: command.ensure_version(config),
            isolated=isolated,
        )

    async def install_async(
        self,
        connection: str | None = None,
        *,
        isolated: bool = False,
    ) -> None:
        """Asynchronously create Alembic's version table.

        Args:
            connection: Optional named application connection.
            isolated: Require database-supported cross-process coordination.
        """
        await self._execute_async(
            connection,
            lambda config: command.ensure_version(config),
            isolated=isolated,
        )

    def upgrade(
        self,
        revision: str = "heads",
        *,
        connection: str | None = None,
        isolated: bool = False,
    ) -> None:
        """Apply pending Alembic revisions up to a selected target.

        Args:
            revision: Alembic target such as ``heads`` or a revision ID.
            connection: Optional named application connection.
            isolated: Require database-supported cross-process coordination.
        """
        self._execute_sync(
            connection,
            lambda config: command.upgrade(config, revision),
            isolated=isolated,
        )

    async def upgrade_async(
        self,
        revision: str = "heads",
        *,
        connection: str | None = None,
        isolated: bool = False,
    ) -> None:
        """Asynchronously apply pending Alembic revisions.

        Args:
            revision: Alembic target such as ``heads`` or a revision ID.
            connection: Optional named application connection.
            isolated: Require database-supported cross-process coordination.
        """
        await self._execute_async(
            connection,
            lambda config: command.upgrade(config, revision),
            isolated=isolated,
        )

    def rollback(
        self,
        steps: int = 1,
        *,
        connection: str | None = None,
        isolated: bool = False,
    ) -> None:
        """Downgrade a number of Alembic revision steps.

        Args:
            steps: Positive number of revisions to reverse.
            connection: Optional named application connection.
            isolated: Require database-supported cross-process coordination.

        Raises:
            DatabaseMigrationError: If the step count is not positive.
        """
        if steps < 1:
            message = "Migration rollback steps must be positive."
            raise DatabaseMigrationError(message)
        target = f"-{steps}"
        self._execute_sync(
            connection,
            lambda config: command.downgrade(config, target),
            isolated=isolated,
        )

    async def rollback_async(
        self,
        steps: int = 1,
        *,
        connection: str | None = None,
        isolated: bool = False,
    ) -> None:
        """Asynchronously downgrade a number of revisions.

        Args:
            steps: Positive number of revisions to reverse.
            connection: Optional named application connection.
            isolated: Require database-supported cross-process coordination.

        Raises:
            DatabaseMigrationError: If the step count is not positive.
        """
        if steps < 1:
            message = "Migration rollback steps must be positive."
            raise DatabaseMigrationError(message)
        target = f"-{steps}"
        await self._execute_async(
            connection,
            lambda config: command.downgrade(config, target),
            isolated=isolated,
        )

    def reset(
        self,
        connection: str | None = None,
        *,
        isolated: bool = False,
    ) -> None:
        """Reverse every applied revision through Alembic.

        Args:
            connection: Optional named application connection.
            isolated: Require database-supported cross-process coordination.
        """
        self._execute_sync(
            connection,
            lambda config: command.downgrade(config, "base"),
            isolated=isolated,
        )

    async def reset_async(
        self,
        connection: str | None = None,
        *,
        isolated: bool = False,
    ) -> None:
        """Asynchronously reverse every applied revision.

        Args:
            connection: Optional named application connection.
            isolated: Require database-supported cross-process coordination.
        """
        await self._execute_async(
            connection,
            lambda config: command.downgrade(config, "base"),
            isolated=isolated,
        )

    def refresh(
        self,
        connection: str | None = None,
        *,
        isolated: bool = False,
    ) -> None:
        """Reverse all revisions, then apply the current Alembic heads.

        Args:
            connection: Optional named application connection.
            isolated: Require database-supported cross-process coordination.
        """

        def reset_and_upgrade(config: Config) -> None:
            """Run a full revision refresh on one owned connection.

            Args:
                config: Alembic config bound to the selected connection.
            """
            command.downgrade(config, "base")
            command.upgrade(config, "heads")

        self._execute_sync(
            connection,
            reset_and_upgrade,
            isolated=isolated,
        )

    async def refresh_async(
        self,
        connection: str | None = None,
        *,
        isolated: bool = False,
    ) -> None:
        """Asynchronously reverse and reapply all current Alembic heads.

        Args:
            connection: Optional named application connection.
            isolated: Require database-supported cross-process coordination.
        """

        def reset_and_upgrade(config: Config) -> None:
            """Run a full revision refresh on one owned connection.

            Args:
                config: Alembic config bound to the selected connection.
            """
            command.downgrade(config, "base")
            command.upgrade(config, "heads")

        await self._execute_async(
            connection,
            reset_and_upgrade,
            isolated=isolated,
        )

    def create_revision(
        self,
        message: str,
        *,
        autogenerate: bool = False,
        connection: str | None = None,
    ) -> Path:
        """Create a new Alembic revision with a native Migration body.

        Autogenerated revisions remain ordinary Alembic operations because
        Alembic owns schema comparison and reviewable migration output.

        Args:
            message: Short revision description.
            autogenerate: Compare mapped models against the selected schema.
            connection: Required named connection when autogenerating.

        Returns:
            The generated migration file path.

        Raises:
            DatabaseMigrationError: If Alembic does not return one revision.
        """
        if autogenerate:
            return self._execute_sync(
                connection,
                lambda config: self._create_revision(
                    config,
                    message,
                    autogenerate=True,
                ),
            )
        self._ensure_layout()
        return self._create_revision(self._config(None), message)

    async def create_revision_async(
        self,
        message: str,
        *,
        autogenerate: bool = False,
        connection: str | None = None,
    ) -> Path:
        """Create a revision, using async I/O for metadata autogeneration.

        Args:
            message: Short revision description.
            autogenerate: Compare mapped models against the selected schema.
            connection: Required named connection when autogenerating.

        Returns:
            The generated migration file path.
        """
        if not autogenerate:
            self._ensure_layout()
            return self._create_revision(self._config(None), message)
        return await self._execute_async(
            connection,
            lambda config: self._create_revision(
                config,
                message,
                autogenerate=True,
            ),
        )

    def status(
        self,
        connection: str | None = None,
    ) -> tuple[MigrationStatus, ...]:
        """Report the Alembic graph and the selected database's applied state.

        Args:
            connection: Optional named application connection.

        Returns:
            Revisions ordered newest first, with applied flags.
        """
        return self._execute_sync(connection, self._status)

    async def status_async(
        self,
        connection: str | None = None,
    ) -> tuple[MigrationStatus, ...]:
        """Asynchronously inspect Alembic revision state.

        Args:
            connection: Optional named application connection.

        Returns:
            Revisions ordered newest first, with applied flags.
        """
        return await self._execute_async(connection, self._status)

    def _status(self, config: Config) -> tuple[MigrationStatus, ...]:
        """Build status records from Alembic's version table and graph.

        Args:
            config: Alembic config bound to the selected database.

        Returns:
            Revisions ordered newest first.
        """
        connection = config.attributes["connection"]
        context = MigrationContext.configure(connection)
        heads = frozenset(context.get_current_heads())
        scripts = ScriptDirectory.from_config(config)
        applied = {
            revision.revision
            for head in heads
            for revision in scripts.get_revisions(head)
        }
        return tuple(
            MigrationStatus(
                revision=script.revision,
                down_revision=script.down_revision,
                applied=script.revision in applied,
                current_head=script.revision in heads,
            )
            for script in scripts.walk_revisions()
        )

    def _create_revision(
        self,
        config: Config,
        message: str,
        *,
        autogenerate: bool = False,
    ) -> Path:
        """Ask Alembic to create and validate a revision file.

        Args:
            config: Alembic config for the selected migration directory.
            message: Short revision description.
            autogenerate: Whether model metadata should be compared.

        Returns:
            The generated revision path.

        Raises:
            DatabaseMigrationError: If revision generation is ambiguous.
        """
        try:
            result = command.revision(
                config,
                message=message,
                autogenerate=autogenerate,
            )
        except CommandError as error:
            message = "Alembic could not create the requested revision."
            raise DatabaseMigrationError(message) from error
        if not isinstance(result, Script):
            error_message = "Alembic did not return one migration revision."
            raise DatabaseMigrationError(error_message)
        if not autogenerate:
            Path(result.path).write_text(
                _render_native_revision(result, message),
                encoding="utf-8",
            )
        return Path(result.path)

    def _execute_sync(
        self,
        connection: str | None,
        callback: Callable[[Config], _Result],
        *,
        isolated: bool = False,
    ) -> _Result:
        """Run one Alembic command in the app's sync transaction.

        Args:
            connection: Optional named application connection.
            callback: Alembic operation using a connection-bound config.
            isolated: Require database-supported cross-process coordination.

        Returns:
            The command's result.
        """
        self._ensure_layout()
        try:
            with self._service.session(connection) as session:
                selected = session.connection()
                return self._run_coordinated(
                    selected,
                    callback,
                    isolated,
                )
        except (CommandError, SQLAlchemyError) as error:
            message = "The database migration operation failed."
            raise DatabaseMigrationError(message) from error

    async def _execute_async(
        self,
        connection: str | None,
        callback: Callable[[Config], _Result],
        *,
        isolated: bool = False,
    ) -> _Result:
        """Run one Alembic command through SQLAlchemy's async bridge.

        Args:
            connection: Optional named application connection.
            callback: Alembic operation using a connection-bound config.
            isolated: Require database-supported cross-process coordination.

        Returns:
            The command's result.
        """
        self._ensure_layout()
        try:
            async with self._service.session_async(connection) as session:
                async_connection = await session.connection()
                return await async_connection.run_sync(
                    lambda sync_connection: self._run_coordinated(
                        sync_connection,
                        callback,
                        isolated,
                    ),
                )
        except (CommandError, SQLAlchemyError) as error:
            message = "The database migration operation failed."
            raise DatabaseMigrationError(message) from error

    def _run_coordinated(
        self,
        connection: SQLConnection,
        callback: Callable[[Config], _Result],
        isolated: bool,
    ) -> _Result:
        """Run Alembic with dialect-owned migration coordination.

        PostgreSQL uses a transaction advisory lock. MySQL uses a named
        connection lock released even when Alembic raises. Other dialects
        remain usable without a cross-process guarantee; explicit isolated
        mode fails closed on those dialects.

        Args:
            connection: Active SQLAlchemy connection owned by the session.
            callback: Alembic operation using the selected connection.
            isolated: Whether coordination is mandatory for this operation.

        Returns:
            The Alembic operation's result.

        Raises:
            DatabaseMigrationError: If required coordination is unavailable.
        """
        dialect = connection.dialect.name
        if dialect == "postgresql":
            connection.exec_driver_sql(
                "SELECT pg_advisory_xact_lock("
                f"{_MIGRATION_LOCK_NAMESPACE}, {_MIGRATION_LOCK_OBJECT})"
            ).close()
            return callback(self._config(connection))
        if dialect == "mysql":
            return self._run_with_mysql_lock(connection, callback)
        if isolated:
            message = (
                "Isolated migrations require PostgreSQL or MySQL database "
                "locks; this dialect does not provide the supported lock."
            )
            raise DatabaseMigrationError(message)
        return callback(self._config(connection))

    def _run_with_mysql_lock(
        self,
        connection: SQLConnection,
        callback: Callable[[Config], _Result],
    ) -> _Result:
        """Serialize MySQL migrations with a server-scoped named lock.

        Args:
            connection: Active connection retained for the lock lifetime.
            callback: Alembic operation using this same connection.

        Returns:
            The Alembic operation's result.

        Raises:
            DatabaseMigrationError: If lock acquisition or release fails.
        """
        database = connection.engine.url.database or "default"
        digest = blake2s(database.encode("utf-8"), digest_size=20).hexdigest()
        lock_name = f"titanspan:migrations:{digest}"
        acquired = connection.scalar(
            text("SELECT GET_LOCK(:lock_name, :timeout)"),
            {
                "lock_name": lock_name,
                "timeout": _MIGRATION_LOCK_TIMEOUT_SECONDS,
            },
        )
        if acquired != 1:
            message = "Could not acquire the MySQL database migration lock."
            raise DatabaseMigrationError(message)

        try:
            result = callback(self._config(connection))
        except BaseException as operation_error:
            try:
                self._release_mysql_lock(connection, lock_name)
            except BaseException as release_error:
                operation_error.add_note(
                    "The MySQL migration lock could not be released; "
                    "its connection was invalidated. Release failure type: "
                    f"{type(release_error).__name__}."
                )
                raise operation_error from operation_error.__cause__
            raise

        self._release_mysql_lock(connection, lock_name)
        return result

    @staticmethod
    def _release_mysql_lock(
        connection: SQLConnection,
        lock_name: str,
    ) -> None:
        """Release the MySQL named lock on its acquiring connection.

        Args:
            connection: Physical connection that owns the lock.
            lock_name: Stable, non-secret lock name for this database.

        Raises:
            DatabaseMigrationError: If the database does not confirm release.
            SQLAlchemyError: If lock release execution fails.
        """
        try:
            released = connection.scalar(
                text("SELECT RELEASE_LOCK(:lock_name)"),
                {"lock_name": lock_name},
            )
        except BaseException as release_error:
            _invalidate_failed_lock_connection(connection, release_error)
            raise
        if released != 1:
            message = "The MySQL database migration lock was not released."
            release_error = DatabaseMigrationError(message)
            _invalidate_failed_lock_connection(connection, release_error)
            raise release_error

    def _config(self, connection: SQLConnection | None) -> Config:
        """Build a fresh Alembic config without exposing connection URLs.

        Args:
            connection: Optional currently owned SQLAlchemy connection.

        Returns:
            Alembic configuration scoped to this application directory.
        """
        config = Config()
        location = str(self._migration_path).replace("%", "%%")
        config.set_main_option("script_location", location)
        config.attributes["connection"] = connection
        config.attributes["target_metadata"] = Model.metadata
        return config

    def _ensure_layout(self) -> None:
        """Create only missing Alembic application files and directories.

        Raises:
            DatabaseMigrationError: If the app path became unsafe.
        """
        if not self._migration_path.is_relative_to(self._base_path):
            message = "Migration paths must remain inside the application."
            raise DatabaseMigrationError(message)
        self._migration_path.mkdir(parents=True, exist_ok=True)
        (self._migration_path / _VERSIONS_DIRECTORY).mkdir(
            parents=True,
            exist_ok=True,
        )
        environment = self._migration_path / _ENVIRONMENT_NAME
        if not environment.exists():
            environment.write_text(_ENVIRONMENT, encoding="utf-8")
        template = self._migration_path / _TEMPLATE_NAME
        if not template.exists():
            template.write_text(_TEMPLATE, encoding="utf-8")


def _invalidate_failed_lock_connection(
    connection: SQLConnection,
    release_error: BaseException,
) -> None:
    """Discard a connection that may still own a MySQL named lock.

    Args:
        connection: Physical connection that attempted lock release.
        release_error: Failure that prevented confirmed lock release.
    """
    try:
        connection.invalidate()
    except BaseException as invalidation_error:
        release_error.add_note(
            "The lock-owning connection could not be invalidated. "
            f"Invalidation failure type: "
            f"{type(invalidation_error).__name__}."
        )


def _render_native_revision(script: Script, message: str) -> str:
    """Render a new Python migration with an explicit native migration class.

    Args:
        script: Alembic-generated revision identity and graph metadata.
        message: Human-readable revision description.

    Returns:
        A valid Alembic revision module using Titanspan's Migration adapter.
    """
    class_name = _class_name(message)
    return f'''{message!r}
# Revision ID: {script.revision}

from collections.abc import Sequence

from titanspan.database import Migration, run_migration

revision: str = {script.revision!r}
down_revision: str | Sequence[str] | None = {script.down_revision!r}
branch_labels: str | Sequence[str] | None = {script.branch_labels!r}
depends_on: str | Sequence[str] | None = {script.dependencies!r}


class {class_name}(Migration):
    """Define schema changes for this revision."""

    def up(self) -> None:
        """Apply this revision's schema changes."""
        pass

    def down(self) -> None:
        """Reverse this revision's schema changes."""
        pass


def upgrade() -> None:
    """Apply this revision through Alembic."""
    run_migration({class_name}(), "up")


def downgrade() -> None:
    """Reverse this revision through Alembic."""
    run_migration({class_name}(), "down")
'''


def _class_name(message: str) -> str:
    """Create a stable Python class name from an Alembic revision message.

    Args:
        message: Human-readable revision summary.

    Returns:
        A valid class name with a descriptive fallback.
    """
    parts = [part for part in _INVALID_CLASS_CHARS.split(message) if part]
    words = "".join(part[:1].upper() + part[1:] for part in parts)
    if not words:
        words = "Database"
    if words[0].isdigit():
        words = f"Revision{words}"
    return f"{words}Migration"


__all__ = ["MigrationManager", "MigrationStatus"]
