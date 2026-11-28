"""Own lazy SQLAlchemy engines and execution-scoped Units of Work.

Each manager belongs to one Application. Its context-local session state is
checked against the current thread or asyncio task before reuse.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Awaitable, Callable
from contextlib import (
    AsyncExitStack,
    ExitStack,
    asynccontextmanager,
    contextmanager,
)
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, NoReturn, Protocol, cast

import anyio
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import CursorResult, Result
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from titanspan.contracts.database import (
    DatabaseResult,
    TransactionOutcome,
    TransactionReceipt,
)
from titanspan.database.configuration import DatabaseConfiguration
from titanspan.database.connection import Connection
from titanspan.database.exceptions import (
    AsyncOperationRequiredError,
    DatabaseCommitOutcomeUnknownError,
    DatabaseConfigurationError,
    DatabaseConnectionError,
    DatabaseQueryError,
    DatabaseTransactionCallbackError,
    DatabaseTransactionError,
    DatabaseTransactionOwnershipError,
)

if TYPE_CHECKING:
    from collections.abc import (
        AsyncGenerator,
        AsyncIterator,
        Generator,
        Iterator,
        Mapping,
    )
    from contextvars import Token

    from sqlalchemy.engine import URL, Engine
    from sqlalchemy.engine import (
        Connection as SQLAlchemyConnection,
    )
    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSessionTransaction
    from sqlalchemy.orm import SessionTransaction
    from sqlalchemy.pool import ConnectionPoolEntry
    from sqlalchemy.sql import Executable

    from titanspan.contracts.config import ConfigRepository
    from titanspan.contracts.foundation import ApplicationPaths
    from titanspan.database.configuration import ConnectionConfiguration


type _ExecutionMode = Literal["sync", "async"]
type _Session = Session | AsyncSession


type _TransactionCallback = Callable[[], None]
type _AsyncTransactionCallback = Callable[[], Awaitable[None]]


type _CommitCallback = _TransactionCallback | _AsyncTransactionCallback
type _TransactionFinalization = tuple[
    BaseException | None,
    tuple[_CommitCallback, ...],
    TransactionOutcome,
]


@dataclass(slots=True)
class _MutableTransactionReceipt:
    """Store the final status for one caller-owned transaction scope.
    """  # fmt: skip

    _outcome: TransactionOutcome | None = None
    _error: BaseException | None = None

    @property
    def outcome(self) -> TransactionOutcome | None:
        """Return the confirmed outcome after the scope exits.

        Returns:
            The transaction outcome, or ``None`` while it remains active.
        """
        return self._outcome

    @property
    def error(self) -> BaseException | None:
        """Return the operation or callback failure associated with the scope.

        Returns:
            The failure raised while finalizing the scope, if any.
        """
        return self._error

    def finish(
        self,
        outcome: TransactionOutcome,
        error: BaseException | None = None,
    ) -> None:
        """Record a final outcome and its associated error.

        Args:
            outcome: Confirmed state selected by transaction finalization.
            error: Optional operation, cleanup, or callback error.
        """
        self._outcome = outcome
        self._error = error

    def record_error(self, error: BaseException) -> None:
        """Retain the final exception while preserving an earlier outcome.

        Args:
            error: Exception raised while cleaning up or dispatching callbacks.
        """
        self._error = error


class _SQLiteDBAPICursor(Protocol):
    """Expose the cursor operations used by SQLite connection setup.
    """  # fmt: skip

    def execute(self, statement: str) -> object:
        """Execute the trusted connection initialization statement.
        """  # fmt: skip
        ...

    def close(self) -> None:
        """Release the short-lived initialization cursor.
        """  # fmt: skip
        ...


class _SQLiteDBAPIConnection(Protocol):
    """Expose SQLite cursor access through SQLAlchemy's driver adapter.
    """  # fmt: skip

    def cursor(self) -> _SQLiteDBAPICursor:
        """Create a cursor through SQLAlchemy's sync driver adapter.
        """  # fmt: skip
        ...


class _SQLiteSyncDBAPIConnection(_SQLiteDBAPIConnection, Protocol):
    """Expose sync SQLite autocommit control for connection setup.
    """  # fmt: skip

    autocommit: bool


class _SQLiteAsyncDBAPIConnection(_SQLiteDBAPIConnection, Protocol):
    """Expose aiosqlite transaction-control configuration.
    """  # fmt: skip

    isolation_level: str | None


def _new_callback_list() -> list[_TransactionCallback]:
    """Create a fresh typed list for one transaction callback phase.
    """  # fmt: skip
    return []


def _new_commit_callback_list() -> list[_CommitCallback]:
    """Create ordered sync and async post-commit callback storage.
    """  # fmt: skip
    return []


@dataclass(slots=True)
class _TransactionCallbacks:
    """Keep post-commit and post-rollback callbacks at one savepoint level.

    Successful savepoints merge their callbacks into the parent transaction.
    A rolled-back savepoint discards commit callbacks and runs its rollback
    callbacks immediately.
    """

    after_commit: list[_CommitCallback] = field(
        default_factory=_new_commit_callback_list,
    )
    after_rollback: list[_TransactionCallback] = field(
        default_factory=_new_callback_list,
    )


@dataclass(slots=True)
class _ExecutionState:
    """Track one mutable session and the execution that owns it.

    Attributes:
        connection_name: Connection whose transaction owns this session.
        mode: Explicit sync or async database API used to create the session.
        thread_id: Thread that owns synchronous use and cleanup.
        task: asyncio task that owns asynchronous use and cleanup.
        session: SQLAlchemy Unit of Work used by nested operations.
        depth: Root transaction plus active savepoint nesting depth.
        callback_frames: Callbacks grouped by transaction and savepoint.
    """

    connection_name: str
    mode: _ExecutionMode
    thread_id: int
    task: object | None
    session: _Session
    depth: int = 1
    callback_frames: list[_TransactionCallbacks] = field(
        default_factory=lambda: [_TransactionCallbacks()],
    )


class DatabaseManager:
    """Own one application's database configuration, engines, and sessions.
    """  # fmt: skip

    def __init__(self, configuration: DatabaseConfiguration) -> None:
        """Create an unopened manager for one validated configuration.

        Args:
            configuration: Immutable settings with application-relative
                SQLite paths already resolved.
        """
        self._configuration = configuration
        self._sync_engines: dict[str, Engine] = {}
        self._async_engines: dict[str, AsyncEngine] = {}
        self._scope: ContextVar[Mapping[str, _ExecutionState]] = ContextVar(
            f"titanspan_database_scope_{id(self)}",
            default=MappingProxyType({}),
        )
        self._lock = threading.RLock()
        self._active_connections: dict[str, int] = {}
        self._disposing_connections: set[str] = set()
        self._closed = False

    @classmethod
    def from_repository(
        cls,
        repository: ConfigRepository,
        paths: ApplicationPaths,
    ) -> DatabaseManager:
        """Construct a manager from canonical application contracts.

        Args:
            repository: Application-owned configuration repository.
            paths: Application-owned path resolution contract.

        Returns:
            A manager that has parsed settings but opened no engines.
        """
        configuration = DatabaseConfiguration.from_repository(
            repository,
            paths,
        )
        return cls(configuration)

    @property
    def connection_names(self) -> tuple[str, ...]:
        """Return configured connection names in declaration order.

        Returns:
            The immutable order from the application configuration.
        """
        return tuple(self._configuration.connections)

    def morph_model_for(self, alias: str) -> type[object] | None:
        """Resolve a persisted alias through this app's trusted map.

        Args:
            alias: Stored discriminator value read from a database row.

        Returns:
            The configured mapped model class, or ``None`` if unknown.
        """
        return self._configuration.morph_map.model_for(alias)

    def morph_alias_for(self, model_type: type[object]) -> str | None:
        """Return the configured alias for one exact mapped class.

        Args:
            model_type: Mapped class whose alias will be stored.

        Returns:
            The trusted alias, or ``None`` if the class is not configured.
        """
        return self._configuration.morph_map.alias_for(model_type)

    def dialect_name(self, name: str | None = None) -> str:
        """Return a connection's normalized dialect without engine creation.

        Args:
            name: Configured connection name or its default.

        Returns:
            SQLAlchemy's backend name, independent of the selected driver.
        """
        connection_name = self._connection_name(name)
        with self._lock:
            self._ensure_open()
            definition = self._configuration.connections[connection_name]
            return definition.sync_url.get_backend_name()

    def target_identity(self, name: str | None = None) -> str:
        """Return the selected database target with credentials redacted.

        Args:
            name: Configured connection name or its default.

        Returns:
            A URL identifying the database without usernames or options.
        """
        connection_name = self._connection_name(name)
        with self._lock:
            self._ensure_open()
            definition = self._configuration.connections[connection_name]
            return definition.target_identity

    @property
    def transaction_level(self) -> int:
        """Return the current execution's root and savepoint depth.

        Returns:
            Zero outside a transaction or the active nested depth.

        Raises:
            DatabaseTransactionOwnershipError: If an inherited context belongs
                to another thread or task.
        """
        state = self._scope.get().get(self._configuration.default or "")
        if state is None:
            return 0
        self._validate_owner(state)
        return state.depth

    def connection_transaction_level(self, name: str | None = None) -> int:
        """Return the active transaction depth for one named connection.

        Args:
            name: Connection name or the application default.

        Returns:
            Zero when that connection has no transaction in this execution.

        Raises:
            DatabaseTransactionOwnershipError: If an inherited transaction
                belongs to another execution.
        """
        connection_name = self._connection_name(name)
        state = self._scope.get().get(connection_name)
        if state is None:
            return 0
        self._validate_owner(state)
        return state.depth

    def after_commit(
        self,
        callback: _TransactionCallback,
        name: str | None = None,
    ) -> None:
        """Run a callback after the owning transaction commits.

        Args:
            callback: Synchronous application callback with no return value.
            name: Connection whose transaction owns the callback.
        """
        connection_name = self._connection_name(name)
        state = self._scope.get().get(connection_name)
        if state is None:
            callback()
            return
        self._validate_owner(state)
        state.callback_frames[-1].after_commit.append(callback)

    async def after_commit_async(
        self,
        callback: _AsyncTransactionCallback,
        name: str | None = None,
    ) -> None:
        """Await a callback after the current task's transaction commits.

        Args:
            callback: Awaitable callback delivered after confirmed commit.
            name: Connection whose async transaction owns this callback.

        Raises:
            DatabaseTransactionOwnershipError: If the active transaction is
                synchronous or belongs to another task.
        """
        connection_name = self._connection_name(name)
        state = self._scope.get().get(connection_name)
        if state is None:
            await callback()
            return
        self._validate_owner(state)
        if state.mode != "async":
            msg = "Async commit callbacks require an async transaction."
            raise DatabaseTransactionOwnershipError(msg)
        state.callback_frames[-1].after_commit.append(callback)

    def after_rollback(
        self,
        callback: _TransactionCallback,
        name: str | None = None,
    ) -> None:
        """Run a callback after its transaction or savepoint rolls back.

        Args:
            callback: Synchronous application callback with no return value.
            name: Connection whose transaction owns the callback.

        Raises:
            DatabaseTransactionError: If no transaction owns the callback.
        """
        connection_name = self._connection_name(name)
        state = self._scope.get().get(connection_name)
        if state is None:
            msg = "A rollback callback requires an active transaction."
            raise DatabaseTransactionError(msg)
        self._validate_owner(state)
        state.callback_frames[-1].after_rollback.append(callback)

    def connection(self, name: str | None = None) -> Connection:
        """Select a configured logical connection without opening an engine.

        Args:
            name: Configured name or the selected default connection.

        Returns:
            A lightweight handle that delegates ownership to this manager.

        Raises:
            DatabaseConfigurationError: If the connection is missing.
        """
        selected = self._connection_name(name)
        return Connection(self, selected)

    @contextmanager
    def session(
        self,
        name: str | None = None,
    ) -> Generator[Session, None, None]:
        """Expose the owned sync Session for advanced ORM interoperability.

        Ordinary application code should use Models and Query Builders. This
        context joins the current Unit of Work or owns one operation
        transaction.

        Args:
            name: Configured connection name or its default.

        Yields:
            The current sync SQLAlchemy Session.
        """
        connection_name = self._connection_name(name)
        with self._session_sync(connection_name) as session:
            yield session

    @asynccontextmanager
    async def session_async(
        self,
        name: str | None = None,
    ) -> AsyncGenerator[AsyncSession, None]:
        """Expose the task-owned async Session for ORM interoperability.

        Ordinary application code should use Models and Query Builders. This
        context joins the current Unit of Work or owns one operation
        transaction.

        Args:
            name: Configured connection name or its default.

        Yields:
            The current task's async SQLAlchemy Session.
        """
        connection_name = self._connection_name(name)
        async with self._session_async(connection_name) as session:
            yield session

    @contextmanager
    def transaction(
        self,
        name: str | None = None,
    ) -> Generator[TransactionReceipt, None, None]:
        """Own a synchronous Unit of Work for the current thread.

        Nested calls use SQLAlchemy savepoints. Database work inherited by a
        different task or thread is rejected before accessing the session.

        Args:
            name: Configured connection name or its default.

        Yields:
            A receipt whose outcome becomes available after the scope exits.

        Raises:
            AsyncOperationRequiredError: If sync I/O would block an event loop.
            DatabaseTransactionError: If the requested savepoint fails.
        """
        self._ensure_sync_allowed()
        connection_name = self._connection_name(name)
        active = self._active_state("sync", connection_name)
        receipt = _MutableTransactionReceipt()
        if active is not None:
            try:
                with self._nested_sync(active, receipt):
                    yield receipt
            except BaseException as error:
                if receipt.outcome is None:
                    receipt.finish(TransactionOutcome.FAILED, error)
                else:
                    receipt.record_error(error)
                raise
            else:
                receipt.finish(TransactionOutcome.SAVEPOINT_RELEASED)
            return

        callbacks: tuple[_CommitCallback, ...] = ()
        operation_error: BaseException | None = None
        outcome = TransactionOutcome.FAILED
        try:
            with self._root_sync_scope(connection_name) as (
                session,
                state,
            ):
                transaction = session.begin()
                transaction.__enter__()
                try:
                    yield receipt
                except BaseException as error:
                    (
                        operation_error,
                        callbacks,
                        outcome,
                    ) = _rollback_sync(
                        transaction,
                        state,
                        error,
                    )
                else:
                    (
                        operation_error,
                        callbacks,
                        outcome,
                    ) = _commit_sync(
                        transaction,
                        state,
                    )
                receipt.finish(outcome, operation_error)
        except BaseException as error:
            operation_error = _combine_failures(
                operation_error,
                error,
                "The database transaction cleanup failed.",
            )
            if receipt.outcome is None:
                receipt.finish(TransactionOutcome.FAILED, operation_error)
            else:
                receipt.record_error(operation_error)
        try:
            _finish_transaction(operation_error, callbacks, receipt)
        except BaseException as error:
            receipt.record_error(error)
            raise

    @asynccontextmanager
    async def transaction_async(
        self,
        name: str | None = None,
    ) -> AsyncGenerator[TransactionReceipt, None]:
        """Own an async Unit of Work for the current asyncio task.

        A ContextVar copied into a child task does not grant that task access
        to its parent's mutable SQLAlchemy AsyncSession.

        Args:
            name: Configured connection name or its default.

        Yields:
            A receipt whose outcome becomes available after the scope exits.

        Raises:
            AsyncOperationRequiredError: If no asyncio task is active.
            DatabaseTransactionError: If the transaction or savepoint fails.
        """
        task = self._current_async_task()
        connection_name = self._connection_name(name)
        active = self._active_state("async", connection_name)
        receipt = _MutableTransactionReceipt()
        if active is not None:
            try:
                async with self._nested_async(active, receipt):
                    yield receipt
            except BaseException as error:
                if receipt.outcome is None:
                    receipt.finish(TransactionOutcome.FAILED, error)
                else:
                    receipt.record_error(error)
                raise
            else:
                receipt.finish(TransactionOutcome.SAVEPOINT_RELEASED)
            return

        callbacks: tuple[_CommitCallback, ...] = ()
        operation_error: BaseException | None = None
        outcome = TransactionOutcome.FAILED
        try:
            async with self._root_async_scope(
                connection_name,
                task,
            ) as (session, state):
                transaction = session.begin()
                await transaction.__aenter__()
                try:
                    yield receipt
                except BaseException as error:
                    (
                        operation_error,
                        callbacks,
                        outcome,
                    ) = await _rollback_async(
                        transaction,
                        state,
                        error,
                    )
                else:
                    (
                        operation_error,
                        callbacks,
                        outcome,
                    ) = await _commit_async(
                        transaction,
                        state,
                    )
                receipt.finish(outcome, operation_error)
        except BaseException as error:
            operation_error = _combine_failures(
                operation_error,
                error,
                "The database transaction cleanup failed.",
            )
            if receipt.outcome is None:
                receipt.finish(TransactionOutcome.FAILED, operation_error)
            else:
                receipt.record_error(operation_error)
        try:
            await _finish_transaction_async(
                operation_error,
                callbacks,
                receipt,
            )
        except BaseException as error:
            receipt.record_error(error)
            raise

    @contextmanager
    def _root_sync_scope(
        self,
        name: str,
    ) -> Generator[tuple[Session, _ExecutionState], None, None]:
        """Own a sync session and restore its execution-local state.

        Args:
            name: Selected connection owned by the root transaction.

        Yields:
            Its SQLAlchemy session and application ownership state.
        """
        activity_started = False
        session: Session | None = None
        token: Token[Mapping[str, _ExecutionState]] | None = None
        try:
            self._begin_activity(name)
            activity_started = True
            session = sessionmaker(
                bind=self.engine(name),
                expire_on_commit=False,
            )()
            state = _ExecutionState(
                connection_name=name,
                mode="sync",
                thread_id=threading.get_ident(),
                task=None,
                session=session,
            )
            token = self._push_state(name, state)
            yield session, state
        finally:
            if token is not None:
                self._scope.reset(token)
            try:
                if session is not None:
                    session.close()
            finally:
                if activity_started:
                    self._end_activity(name)

    @asynccontextmanager
    async def _root_async_scope(
        self,
        name: str,
        task: object,
    ) -> AsyncGenerator[tuple[AsyncSession, _ExecutionState], None]:
        """Own an async session and restore its task-local state.

        Args:
            name: Selected connection owned by the root transaction.
            task: Current asyncio task validated before opening the session.

        Yields:
            Its task-owned SQLAlchemy session and manager state.
        """
        activity_started = False
        session: AsyncSession | None = None
        token: Token[Mapping[str, _ExecutionState]] | None = None
        try:
            self._begin_activity(name)
            activity_started = True
            factory = async_sessionmaker(
                bind=self.async_engine(name),
                expire_on_commit=False,
            )
            session = factory()
            state = _ExecutionState(
                connection_name=name,
                mode="async",
                thread_id=threading.get_ident(),
                task=task,
                session=session,
            )
            token = self._push_state(name, state)
            yield session, state
        finally:
            if token is not None:
                self._scope.reset(token)
            try:
                if session is not None:
                    with anyio.CancelScope(shield=True):
                        await session.close()
            finally:
                if activity_started:
                    self._end_activity(name)

    def disconnect(self, name: str | None = None) -> None:
        """Dispose a sync pool while retaining its reusable engine object.

        Args:
            name: Configured connection name or its default.

        Raises:
            DatabaseTransactionError: If a transaction currently owns the
                connection.
            AsyncOperationRequiredError: If an async engine is initialized.
        """
        connection_name = self._connection_name(name)
        self._claim_disposal(connection_name)
        try:
            if connection_name in self._async_engines:
                msg = "Use disconnect_async for an async database engine."
                raise AsyncOperationRequiredError(msg)
            engine = self._sync_engines.get(connection_name)
            if engine is not None:
                engine.dispose()
        finally:
            self._release_disposal(connection_name)

    async def disconnect_async(self, name: str | None = None) -> None:
        """Dispose initialized sync and async pools without removing engines.

        Args:
            name: Configured connection name or its default.

        Raises:
            DatabaseTransactionError: If a transaction currently owns the
                connection.
        """
        connection_name = self._connection_name(name)
        self._claim_disposal(connection_name)
        try:
            with self._lock:
                sync_engine = self._sync_engines.get(connection_name)
                async_engine = self._async_engines.get(connection_name)
            with anyio.CancelScope(shield=True):
                async with AsyncExitStack() as stack:
                    if sync_engine is not None:
                        stack.callback(sync_engine.dispose)
                    if async_engine is not None:
                        stack.push_async_callback(async_engine.dispose)
        finally:
            self._release_disposal(connection_name)

    def purge(self, name: str | None = None) -> None:
        """Dispose and remove a sync engine so it is rebuilt on next use.

        Args:
            name: Configured connection name or its default.

        Raises:
            DatabaseTransactionError: If a transaction currently owns the
                connection.
            AsyncOperationRequiredError: If an async engine is initialized.
        """
        connection_name = self._connection_name(name)
        self._claim_disposal(connection_name)
        try:
            if connection_name in self._async_engines:
                msg = "Use purge_async for an async database engine."
                raise AsyncOperationRequiredError(msg)
            engine = self._sync_engines.pop(connection_name, None)
            if engine is not None:
                engine.dispose()
        finally:
            self._release_disposal(connection_name)

    async def purge_async(self, name: str | None = None) -> None:
        """Dispose and remove initialized engines for one connection.

        Args:
            name: Configured connection name or its default.

        Raises:
            DatabaseTransactionError: If a transaction currently owns the
                connection.
        """
        connection_name = self._connection_name(name)
        self._claim_disposal(connection_name)
        try:
            with self._lock:
                sync_engine = self._sync_engines.pop(connection_name, None)
                async_engine = self._async_engines.pop(connection_name, None)
            with anyio.CancelScope(shield=True):
                async with AsyncExitStack() as stack:
                    if sync_engine is not None:
                        stack.callback(sync_engine.dispose)
                    if async_engine is not None:
                        stack.push_async_callback(async_engine.dispose)
        finally:
            self._release_disposal(connection_name)

    def close(self) -> None:
        """Dispose all sync engines and close this manager permanently.

        Raises:
            DatabaseTransactionError: If any operation is active.
            AsyncOperationRequiredError: If an async engine needs disposal.
        """
        with self._lock:
            self._ensure_open()
            if self._active_connections or self._disposing_connections:
                msg = "Cannot close the database manager during active work."
                raise DatabaseTransactionError(msg)
            if self._async_engines:
                msg = "Use aclose to dispose async database engines."
                raise AsyncOperationRequiredError(msg)
            engines = tuple(self._sync_engines.values())
            self._closed = True
            self._sync_engines.clear()
        with ExitStack() as stack:
            for engine in engines:
                stack.callback(engine.dispose)

    async def aclose(self) -> None:
        """Dispose every engine and close this manager permanently.

        Raises:
            DatabaseTransactionError: If any operation is active.
        """
        with self._lock:
            self._ensure_open()
            if self._active_connections or self._disposing_connections:
                msg = "Cannot close the database manager during active work."
                raise DatabaseTransactionError(msg)
            sync_engines = tuple(self._sync_engines.values())
            async_engines = tuple(self._async_engines.values())
            self._sync_engines.clear()
            self._async_engines.clear()
            self._closed = True
        async with AsyncExitStack() as stack:
            for engine in sync_engines:
                stack.callback(engine.dispose)
            for engine in async_engines:
                stack.push_async_callback(engine.dispose)

    def engine(self, name: str) -> Engine:
        """Return one lazily constructed sync engine for a connection.

        Args:
            name: Validated configured connection name.

        Returns:
            The sync engine owned by this application manager.
        """
        with self._lock:
            self._ensure_open()
            self._ensure_not_disposing(name)
            engine = self._sync_engines.get(name)
            if engine is not None:
                return engine
            definition = self._definition(name)
            try:
                engine = create_engine(
                    definition.sync_url,
                    **_engine_options_for_factory(
                        definition.engine_options,
                        definition.sync_url,
                    ),
                )
            except (ImportError, SQLAlchemyError) as error:
                msg = "The configured sync database driver is unavailable."
                raise DatabaseConnectionError(msg) from error
            if definition.sync_url.get_backend_name() == "sqlite":
                event.listen(
                    engine,
                    "connect",
                    _enable_sync_sqlite_foreign_keys,
                )
            try:
                self._prepare_sqlite_path(definition.sync_url)
            except BaseException:
                engine.dispose()
                raise
            self._sync_engines[name] = engine
            return engine

    def async_engine(self, name: str) -> AsyncEngine:
        """Return one lazily constructed async engine for a connection.

        Args:
            name: Validated configured connection name.

        Returns:
            The async engine owned by this application manager.

        Raises:
            AsyncOperationRequiredError: If a driver cannot create an async
                engine through SQLAlchemy's supported asyncio API.
        """
        with self._lock:
            self._ensure_open()
            self._ensure_not_disposing(name)
            engine = self._async_engines.get(name)
            if engine is not None:
                return engine
            definition = self._definition(name)
            try:
                engine = create_async_engine(
                    definition.async_url,
                    **_engine_options_for_factory(
                        definition.engine_options,
                        definition.async_url,
                        async_mode=True,
                    ),
                )
            except (ImportError, SQLAlchemyError) as error:
                msg = "The configured async database driver is unavailable."
                raise DatabaseConnectionError(msg) from error
            if definition.async_url.get_backend_name() == "sqlite":
                event.listen(
                    engine.sync_engine,
                    "connect",
                    _enable_async_sqlite_foreign_keys,
                )
                event.listen(
                    engine.sync_engine,
                    "begin",
                    _begin_async_sqlite_transaction,
                )
            try:
                self._prepare_sqlite_path(definition.async_url)
            except BaseException:
                # This engine has no connections before path preparation.
                engine.sync_engine.dispose()
                raise
            self._async_engines[name] = engine
            return engine

    def execute_sync(
        self,
        name: str,
        sql: str,
        parameters: Mapping[str, object] | None,
    ) -> DatabaseResult:
        """Execute a bound SQL statement inside the current Unit of Work.

        Args:
            name: Validated configured connection name.
            sql: Explicit trusted SQL text.
            parameters: Named values bound by SQLAlchemy.

        Returns:
            Detached rows and the backend's affected-row count.
        """
        self._ensure_sync_allowed()
        try:
            with self._session_sync(name) as session:
                result = cast(
                    "Result[object]",
                    session.execute(text(sql), dict(parameters or {})),
                )
                return _detach_result(result)
        except SQLAlchemyError as error:
            msg = "The database statement failed."
            raise DatabaseQueryError(msg) from error

    async def execute_async(
        self,
        name: str,
        sql: str,
        parameters: Mapping[str, object] | None,
    ) -> DatabaseResult:
        """Asynchronously execute a bound SQL statement in its Unit of Work.

        Args:
            name: Validated configured connection name.
            sql: Explicit trusted SQL text.
            parameters: Named values bound by SQLAlchemy.

        Returns:
            Detached rows and the backend's affected-row count.
        """
        self._current_async_task()
        try:
            async with self._session_async(name) as session:
                result = cast(
                    "Result[object]",
                    await session.execute(
                        text(sql),
                        dict(parameters or {}),
                    ),
                )
                return _detach_result(result)
        except SQLAlchemyError as error:
            msg = "The database statement failed."
            raise DatabaseQueryError(msg) from error

    def execute_statement_sync(
        self,
        name: str,
        statement: Executable,
        parameters: Mapping[str, object] | None = None,
    ) -> DatabaseResult:
        """Execute a SQLAlchemy Core or ORM statement synchronously.

        Args:
            name: Validated configured connection name.
            statement: SQLAlchemy statement built through supported APIs.
            parameters: Additional values bound to the statement.

        Returns:
            Detached rows and driver-reported affected-row metadata.
        """
        self._ensure_sync_allowed()
        try:
            with self._session_sync(name) as session:
                result = cast(
                    "Result[object]",
                    session.execute(statement, dict(parameters or {})),
                )
                return _detach_result(result)
        except SQLAlchemyError as error:
            msg = "The database statement failed."
            raise DatabaseQueryError(msg) from error

    async def execute_statement_async(
        self,
        name: str,
        statement: Executable,
        parameters: Mapping[str, object] | None = None,
    ) -> DatabaseResult:
        """Execute a SQLAlchemy Core or ORM statement asynchronously.

        Args:
            name: Validated configured connection name.
            statement: SQLAlchemy statement built through supported APIs.
            parameters: Additional values bound to the statement.

        Returns:
            Detached rows and driver-reported affected-row metadata.
        """
        self._current_async_task()
        try:
            async with self._session_async(name) as session:
                result = cast(
                    "Result[object]",
                    await session.execute(
                        statement,
                        dict(parameters or {}),
                    ),
                )
                return _detach_result(result)
        except SQLAlchemyError as error:
            msg = "The database statement failed."
            raise DatabaseQueryError(msg) from error

    @contextmanager
    def stream_statement_sync(
        self,
        name: str,
        statement: Executable,
        *,
        batch_size: int = 1000,
    ) -> Generator[Iterator[Mapping[str, object]], None, None]:
        """Stream query mappings within an owned synchronous session.

        Args:
            name: Validated configured connection name.
            statement: SQLAlchemy statement built through supported APIs.
            batch_size: Maximum result batch buffered by SQLAlchemy.

        Yields:
            A live iterator that must not outlive this context manager.
        """
        if type(batch_size) is not int or batch_size < 1:
            msg = "The stream batch size must be a positive integer."
            raise ValueError(msg)
        self._ensure_sync_allowed()
        try:
            with self._session_sync(name) as session:
                result = session.execute(
                    statement.execution_options(yield_per=batch_size),
                )

                def rows() -> Iterator[Mapping[str, object]]:
                    """Yield copied mappings from the live sync result.

                    Yields:
                        A copied mapping for each selected row.
                    """
                    for row in result.mappings():
                        yield dict(row)

                try:
                    yield rows()
                finally:
                    result.close()
        except SQLAlchemyError as error:
            msg = "The database stream failed."
            raise DatabaseQueryError(msg) from error

    @asynccontextmanager
    async def stream_statement_async(
        self,
        name: str,
        statement: Executable,
        *,
        batch_size: int = 1000,
    ) -> AsyncGenerator[
        AsyncIterator[Mapping[str, object]],
        None,
    ]:
        """Stream query mappings within an owned asynchronous session.

        SQLAlchemy async results own a live cursor. Cleanup runs in a shielded
        scope so cancellation cannot strand a checked-out connection.

        Args:
            name: Validated configured connection name.
            statement: SQLAlchemy statement built through supported APIs.
            batch_size: Maximum result batch buffered by SQLAlchemy.

        Yields:
            An async iterator that must not outlive this context manager.
        """
        if type(batch_size) is not int or batch_size < 1:
            msg = "The stream batch size must be a positive integer."
            raise ValueError(msg)
        self._current_async_task()
        try:
            async with self._session_async(name) as session:
                result = await session.stream(
                    statement.execution_options(yield_per=batch_size),
                )

                async def rows() -> AsyncIterator[Mapping[str, object]]:
                    """Yield detached mappings from the live async result.

                    Yields:
                        A copied mapping for each selected row.
                    """
                    async for row in result.mappings():
                        yield dict(row)

                try:
                    yield rows()
                finally:
                    with anyio.CancelScope(shield=True):
                        await result.close()
        except SQLAlchemyError as error:
            msg = "The database stream failed."
            raise DatabaseQueryError(msg) from error

    @contextmanager
    def _session_sync(self, name: str) -> Generator[Session, None, None]:
        """Yield the owned sync session or create an operation transaction.

        Args:
            name: Validated configured connection name.

        Yields:
            The synchronous SQLAlchemy session owned by this execution.
        """
        active = self._active_state("sync", name)
        if active is not None:
            if not isinstance(active.session, Session):
                msg = "The active transaction does not own a sync session."
                raise DatabaseTransactionOwnershipError(msg)
            yield active.session
            return
        with self.transaction(name):
            state = self._active_state("sync", name)
            if state is None or not isinstance(state.session, Session):
                msg = "The sync transaction did not establish a session."
                raise DatabaseTransactionError(msg)
            yield state.session

    @asynccontextmanager
    async def _session_async(
        self,
        name: str,
    ) -> AsyncGenerator[AsyncSession, None]:
        """Yield the owned async session or create an operation transaction.

        Args:
            name: Validated configured connection name.

        Yields:
            The asynchronous SQLAlchemy session owned by this task.
        """
        active = self._active_state("async", name)
        if active is not None:
            if not isinstance(active.session, AsyncSession):
                msg = "The active transaction does not own an async session."
                raise DatabaseTransactionOwnershipError(msg)
            yield active.session
            return
        async with self.transaction_async(name):
            state = self._active_state("async", name)
            if state is None or not isinstance(state.session, AsyncSession):
                msg = "The async transaction did not establish a session."
                raise DatabaseTransactionError(msg)
            yield state.session

    @contextmanager
    def _nested_sync(
        self,
        state: _ExecutionState,
        receipt: _MutableTransactionReceipt,
    ) -> Generator[None, None, None]:
        """Open a SQLAlchemy savepoint inside an owned sync transaction.

        Args:
            state: Current owner-validated transaction state.
            receipt: Caller-owned result for this savepoint scope.

        Yields:
            Control while the savepoint is active.
        """
        if not isinstance(state.session, Session):
            msg = "The active transaction does not own a sync session."
            raise DatabaseTransactionOwnershipError(msg)
        nested = state.session.begin_nested()
        nested.__enter__()
        frame = _TransactionCallbacks()
        state.callback_frames.append(frame)
        state.depth += 1
        rollback_confirmed = False
        try:
            try:
                yield
            except BaseException as error:
                nested.__exit__(
                    type(error),
                    error,
                    error.__traceback__,
                )
                rollback_confirmed = True
                raise
            else:
                nested.__exit__(None, None, None)
        except BaseException as error:
            _pop_savepoint(state)
            outcome = (
                TransactionOutcome.SAVEPOINT_ROLLED_BACK
                if rollback_confirmed
                else TransactionOutcome.FAILED
            )
            receipt.finish(outcome, error)
            _raise_savepoint_error(
                error,
                frame,
                rollback_confirmed,
                receipt,
            )
        else:
            _merge_savepoint(state, frame)

    @asynccontextmanager
    async def _nested_async(
        self,
        state: _ExecutionState,
        receipt: _MutableTransactionReceipt,
    ) -> AsyncGenerator[None, None]:
        """Open a SQLAlchemy savepoint inside an owned async transaction.

        Args:
            state: Current owner-validated transaction state.
            receipt: Caller-owned result for this savepoint scope.

        Yields:
            Control while the savepoint is active.
        """
        if not isinstance(state.session, AsyncSession):
            msg = "The active transaction does not own an async session."
            raise DatabaseTransactionOwnershipError(msg)
        nested = state.session.begin_nested()
        frame = _TransactionCallbacks()
        state.callback_frames.append(frame)
        state.depth += 1
        rollback_confirmed = False
        try:
            try:
                await nested.__aenter__()
                try:
                    yield
                except BaseException as error:
                    with anyio.CancelScope(shield=True):
                        await nested.__aexit__(
                            type(error),
                            error,
                            error.__traceback__,
                        )
                    rollback_confirmed = True
                    raise
                else:
                    await nested.__aexit__(None, None, None)
            except BaseException as error:
                await _rollback_async_savepoint_if_active(nested, error)
                raise
        except BaseException as error:
            _pop_savepoint(state)
            outcome = (
                TransactionOutcome.SAVEPOINT_ROLLED_BACK
                if rollback_confirmed
                else TransactionOutcome.FAILED
            )
            receipt.finish(outcome, error)
            _raise_savepoint_error(
                error,
                frame,
                rollback_confirmed,
                receipt,
            )
        else:
            _merge_savepoint(state, frame)

    def _active_state(
        self,
        mode: _ExecutionMode,
        name: str,
    ) -> _ExecutionState | None:
        """Return current transaction state after checking its owner.

        Args:
            mode: API mode requested by the caller.
            name: Connection required by the caller.

        Returns:
            The matching active state, or ``None`` outside a transaction.

        Raises:
            DatabaseTransactionOwnershipError: If ownership, mode, or
                connection does not match.
        """
        state = self._scope.get().get(name)
        if state is None:
            return None
        self._validate_owner(state)
        if state.mode is not mode:
            msg = "Database work must use its owning transaction context."
            raise DatabaseTransactionOwnershipError(msg)
        return state

    def _push_state(
        self,
        name: str,
        state: _ExecutionState,
    ) -> Token[Mapping[str, _ExecutionState]]:
        """Add an independent connection scope without mutating its parent.

        Args:
            name: Logical connection owned by this Unit of Work.
            state: New session state with its current task or thread owner.

        Returns:
            Context token that restores all previous connection scopes.
        """
        scopes = dict(self._scope.get())
        scopes[name] = state
        return self._scope.set(MappingProxyType(scopes))

    def _validate_owner(self, state: _ExecutionState) -> None:
        """Ensure inherited ContextVar state belongs to this execution.

        Args:
            state: Context state whose mutable session may be reused.

        Raises:
            DatabaseTransactionOwnershipError: If another task or thread owns
                the Unit of Work.
        """
        if state.thread_id != threading.get_ident():
            msg = "The database session belongs to another thread."
            raise DatabaseTransactionOwnershipError(msg)
        task = self._current_task_or_none()
        if task is not state.task:
            msg = "The database session belongs to another task."
            raise DatabaseTransactionOwnershipError(msg)

    def _begin_activity(self, name: str) -> None:
        """Mark an operation active before it can acquire a pool connection.

        Args:
            name: Connection whose engine must remain stable.

        Raises:
            DatabaseConnectionError: If this manager has already closed.
        """
        with self._lock:
            self._ensure_open()
            self._ensure_not_disposing(name)
            self._active_connections[name] = (
                self._active_connections.get(name, 0) + 1
            )

    def _end_activity(self, name: str) -> None:
        """Release the manager's active-operation guard.

        Args:
            name: Connection whose operation has finalized.
        """
        with self._lock:
            active = self._active_connections.get(name, 0)
            if active <= 1:
                self._active_connections.pop(name, None)
            else:
                self._active_connections[name] = active - 1

    def _claim_disposal(self, name: str) -> None:
        """Atomically reserve an idle connection for engine disposal.

        Args:
            name: Connection selected for disposal or purge.

        Raises:
            DatabaseTransactionError: If work or disposal is already active.
        """
        with self._lock:
            self._ensure_open()
            if self._active_connections.get(name, 0):
                msg = "Cannot dispose a connection during active work."
                raise DatabaseTransactionError(msg)
            self._ensure_not_disposing(name)
            self._disposing_connections.add(name)

    def _release_disposal(self, name: str) -> None:
        """Allow new work after the selected engine operation completes.

        Args:
            name: Connection whose disposal or purge has completed.
        """
        with self._lock:
            self._disposing_connections.discard(name)

    def _ensure_not_disposing(self, name: str) -> None:
        """Reject access while an engine is being disposed or replaced.

        Args:
            name: Connection selected for use.

        Raises:
            DatabaseTransactionError: If disposal currently owns the
                connection lifecycle.
        """
        if name in self._disposing_connections:
            msg = "Cannot use a connection while its engine is disposing."
            raise DatabaseTransactionError(msg)

    def _connection_name(self, name: str | None) -> str:
        """Validate an explicit name or resolve the configured default.

        Args:
            name: Optional application connection key.

        Returns:
            A configured connection name.

        Raises:
            DatabaseConfigurationError: If no matching name is configured.
        """
        selected = name or self._configuration.default
        if selected is None or selected not in self._configuration.connections:
            msg = "The requested database connection is not configured."
            raise DatabaseConfigurationError(msg)
        return selected

    def _definition(self, name: str) -> ConnectionConfiguration:
        """Return the already validated definition for one connection.

        Args:
            name: Validated configured connection name.

        Returns:
            The immutable configuration for the selected connection.
        """
        try:
            return self._configuration.connections[name]
        except KeyError as error:
            msg = "The requested database connection is not configured."
            raise DatabaseConfigurationError(msg) from error

    def _prepare_sqlite_path(self, url: URL) -> None:
        """Create an application-local parent directory only on engine use.

        Args:
            url: SQLAlchemy URL selected for the engine.
        """
        if url.get_backend_name() != "sqlite":
            return
        database = url.database
        if database in (None, "", ":memory:"):
            return
        try:
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            msg = "The SQLite database directory could not be prepared."
            raise DatabaseConnectionError(msg) from error

    def _ensure_open(self) -> None:
        """Reject manager use after its application lifecycle has ended.
        """  # fmt: skip
        if self._closed:
            msg = "The application database manager is closed."
            raise DatabaseConnectionError(msg)

    @staticmethod
    def _ensure_sync_allowed() -> None:
        """Reject synchronous database I/O inside a running event loop.
        """  # fmt: skip
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        msg = "Use the explicit async database operation in this event loop."
        raise AsyncOperationRequiredError(msg)

    @staticmethod
    def _current_task_or_none() -> object | None:
        """Return the current asyncio task without creating an event loop.
        """  # fmt: skip
        try:
            return asyncio.current_task()
        except RuntimeError:
            return None

    @classmethod
    def _current_async_task(cls) -> object:
        """Require an active asyncio task for async database work.

        Returns:
            The current task used to enforce AsyncSession ownership.

        Raises:
            AsyncOperationRequiredError: If no asyncio task is running.
        """
        task = cls._current_task_or_none()
        if task is None:
            msg = "Async database operations require an asyncio task."
            raise AsyncOperationRequiredError(msg)
        return task


async def _rollback_async_savepoint_if_active(
    transaction: AsyncSessionTransaction,
    error: BaseException,
) -> None:
    """Shield cleanup rollback after an async savepoint failure.

    Args:
        transaction: Savepoint whose commit or body operation failed.
        error: Failure supplied to exit the SQLAlchemy context.
    """
    if transaction.is_active:
        with anyio.CancelScope(shield=True):
            await transaction.__aexit__(
                type(error),
                error,
                error.__traceback__,
            )


def _raise_savepoint_error(
    error: BaseException,
    frame: _TransactionCallbacks,
    rollback_confirmed: bool,
    receipt: _MutableTransactionReceipt,
) -> NoReturn:
    """Dispatch confirmed savepoint rollback callbacks and raise its failure.

    Args:
        error: Body, savepoint, or savepoint cleanup failure.
        frame: Callback frame discarded when the savepoint ends.
        rollback_confirmed: Whether rollback completed successfully.
        receipt: Caller-owned result updated before an error escapes.
    """
    callback_errors = (
        _run_callbacks(tuple(frame.after_rollback), receipt)
        if rollback_confirmed
        else []
    )
    if callback_errors:
        _raise_transaction_failure(error, callback_errors, receipt)
    if isinstance(error, SQLAlchemyError):
        message = "The nested database transaction failed."
        raise DatabaseTransactionError(message) from error
    raise error.with_traceback(error.__traceback__) from None


def _pop_savepoint(state: _ExecutionState) -> None:
    """Remove the callback frame for a completed savepoint.

    Args:
        state: Current transaction state owning the nested frame.
    """
    state.depth -= 1
    state.callback_frames.pop()


def _merge_savepoint(
    state: _ExecutionState,
    frame: _TransactionCallbacks,
) -> None:
    """Retain successful savepoint callbacks until root completion.

    Args:
        state: Current transaction state owning the nested frame.
        frame: Successfully committed savepoint callback frame.
    """
    _pop_savepoint(state)
    parent = state.callback_frames[-1]
    parent.after_commit.extend(frame.after_commit)
    parent.after_rollback.extend(frame.after_rollback)


def _rollback_sync(
    transaction: SessionTransaction,
    state: _ExecutionState,
    original: BaseException,
) -> tuple[
    BaseException,
    tuple[_CommitCallback, ...],
    TransactionOutcome,
]:
    """Roll back a sync transaction and select confirmed rollback callbacks.

    Args:
        transaction: SQLAlchemy root transaction being rolled back.
        state: Owning callback state for that transaction.
        original: Failure raised by the transaction body.

    Returns:
        Failure, eligible rollback callbacks, and the confirmed outcome.
    """
    try:
        transaction.__exit__(
            type(original),
            original,
            original.__traceback__,
        )
    except BaseException as rollback_error:
        message = "The transaction and its rollback both failed."
        return (
            _combine_failures(original, rollback_error, message),
            (),
            TransactionOutcome.FAILED,
        )
    callbacks = tuple(state.callback_frames[0].after_rollback)
    return original, callbacks, TransactionOutcome.ROLLED_BACK


def _commit_sync(
    transaction: SessionTransaction,
    state: _ExecutionState,
) -> _TransactionFinalization:
    """Commit a sync transaction and select post-commit callbacks.

    Args:
        transaction: SQLAlchemy root transaction to commit.
        state: Owning callback state for that transaction.

    Returns:
        Failure, callbacks selected after a confirmed outcome, and that
        transaction outcome.
    """
    if not isinstance(state.session, Session):
        message = "The active transaction does not own a sync session."
        return (
            DatabaseTransactionOwnershipError(message),
            (),
            TransactionOutcome.FAILED,
        )
    try:
        state.session.flush()
    except BaseException as error:
        return _rollback_sync(transaction, state, error)
    try:
        transaction.commit()
    except BaseException as error:
        cleanup_error: BaseException | None = None
        try:
            # A failed commit leaves the driver's transaction state uncertain.
            # Invalidate its physical connection instead of returning it to the
            # pool with a possibly open transaction.
            state.session.invalidate()
        except BaseException as invalidate_error:
            cleanup_error = invalidate_error
        if not isinstance(error, Exception):
            error.add_note(
                "The database commit outcome is unknown because "
                "commit was interrupted."
            )
            if cleanup_error is not None:
                error.add_note(
                    "Rollback cleanup also failed: "
                    f"{type(cleanup_error).__name__}."
                )
            return error, (), TransactionOutcome.COMMIT_OUTCOME_UNKNOWN
        unknown = DatabaseCommitOutcomeUnknownError(error, cleanup_error)
        return unknown, (), TransactionOutcome.COMMIT_OUTCOME_UNKNOWN
    return (
        None,
        tuple(state.callback_frames[0].after_commit),
        TransactionOutcome.COMMITTED,
    )


async def _rollback_async(
    transaction: AsyncSessionTransaction,
    state: _ExecutionState,
    original: BaseException,
) -> tuple[
    BaseException,
    tuple[_CommitCallback, ...],
    TransactionOutcome,
]:
    """Shield async rollback and select callbacks only after it succeeds.

    Args:
        transaction: SQLAlchemy root transaction being rolled back.
        state: Owning callback state for that transaction.
        original: Failure or cancellation raised by the transaction body.

    Returns:
        Failure, eligible rollback callbacks, and the confirmed outcome.
    """
    try:
        with anyio.CancelScope(shield=True):
            await transaction.__aexit__(
                type(original),
                original,
                original.__traceback__,
            )
    except BaseException as rollback_error:
        message = "The transaction and its rollback both failed."
        return (
            _combine_failures(original, rollback_error, message),
            (),
            TransactionOutcome.FAILED,
        )
    callbacks = tuple(state.callback_frames[0].after_rollback)
    return original, callbacks, TransactionOutcome.ROLLED_BACK


async def _commit_async(
    transaction: AsyncSessionTransaction,
    state: _ExecutionState,
) -> _TransactionFinalization:
    """Commit an async transaction and select post-commit callbacks.

    A failed commit has an uncertain outcome, so rollback callbacks are not
    dispatched even if SQLAlchemy permits a later cleanup rollback.

    Args:
        transaction: SQLAlchemy root transaction to commit.
        state: Owning callback state for that transaction.

    Returns:
        Failure, callbacks selected after a confirmed outcome, and that
        transaction outcome.
    """
    if not isinstance(state.session, AsyncSession):
        message = "The active transaction does not own an async session."
        return (
            DatabaseTransactionOwnershipError(message),
            (),
            TransactionOutcome.FAILED,
        )
    try:
        await state.session.flush()
    except BaseException as error:
        return await _rollback_async(transaction, state, error)
    try:
        await transaction.commit()
    except BaseException as error:
        cleanup_error: BaseException | None = None
        try:
            # Do not reuse a physical connection whose commit result is
            # uncertain. Shield invalidation so cancellation cannot skip it.
            with anyio.CancelScope(shield=True):
                await state.session.invalidate()
        except BaseException as invalidate_error:
            cleanup_error = invalidate_error
        if not isinstance(error, Exception):
            error.add_note(
                "The database commit outcome is unknown because "
                "commit was interrupted."
            )
            if cleanup_error is not None:
                error.add_note(
                    "Rollback cleanup also failed: "
                    f"{type(cleanup_error).__name__}."
                )
            return error, (), TransactionOutcome.COMMIT_OUTCOME_UNKNOWN
        unknown = DatabaseCommitOutcomeUnknownError(error, cleanup_error)
        return unknown, (), TransactionOutcome.COMMIT_OUTCOME_UNKNOWN
    return (
        None,
        tuple(state.callback_frames[0].after_commit),
        TransactionOutcome.COMMITTED,
    )


def _finish_transaction(
    operation_error: BaseException | None,
    callbacks: tuple[_CommitCallback, ...],
    receipt: _MutableTransactionReceipt,
) -> None:
    """Run callbacks after cleanup and re-raise transaction failures.

    Args:
        operation_error: Body, commit, or cleanup failure if one occurred.
        callbacks: Callbacks selected by a confirmed transaction outcome.
        receipt: Caller-owned result updated before raising any failure.
    """
    callback_errors = _run_callbacks(callbacks, receipt)
    _raise_transaction_failure(operation_error, callback_errors, receipt)


def _run_callbacks(
    callbacks: tuple[_CommitCallback, ...],
    receipt: _MutableTransactionReceipt,
) -> list[Exception]:
    """Run every synchronous transaction callback and collect failures.

    Args:
        callbacks: Callbacks selected by a committed or rolled-back scope.
        receipt: Caller-owned result updated before any interruption escapes.

    Returns:
        Exceptions raised by callbacks, in registration order.
    """
    failures: list[Exception] = []
    for callback in callbacks:
        try:
            result = callback()
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                msg = "An async commit callback requires an async transaction."
                failures.append(DatabaseTransactionOwnershipError(msg))
        except Exception as error:
            failures.append(error)
        except BaseException as error:
            _record_callback_interruption(receipt, error)
            raise
    return failures


async def _finish_transaction_async(
    operation_error: BaseException | None,
    callbacks: tuple[_CommitCallback, ...],
    receipt: _MutableTransactionReceipt,
) -> None:
    """Run sync and awaited callbacks after async transaction cleanup.

    Args:
        operation_error: Body, commit, or cleanup failure if one occurred.
        callbacks: Ordered callbacks selected by a confirmed outcome.
        receipt: Caller-owned result updated before raising any failure.
    """
    callback_errors: list[Exception] = []
    for callback in callbacks:
        try:
            result = callback()
            if inspect.isawaitable(result):
                await result
        except Exception as error:
            callback_errors.append(error)
        except BaseException as error:
            _record_callback_interruption(receipt, error)
            raise
    _raise_transaction_failure(operation_error, callback_errors, receipt)


def _record_callback_interruption(
    receipt: _MutableTransactionReceipt,
    error: BaseException,
) -> None:
    """Preserve cancellation while recording already completed persistence.

    Args:
        receipt: Outcome record for the transaction that selected callbacks.
        error: Non-Exception failure raised by a callback.
    """
    outcome = receipt.outcome
    if outcome is TransactionOutcome.COMMITTED:
        receipt.finish(
            TransactionOutcome.COMMITTED_WITH_CALLBACK_ERRORS,
            error,
        )
        error.add_note(
            "The database transaction committed before callback execution "
            "was interrupted."
        )
    elif outcome is None:
        receipt.finish(TransactionOutcome.FAILED, error)
    else:
        receipt.record_error(error)


def _raise_transaction_failure(
    operation_error: BaseException | None,
    callback_errors: list[Exception],
    receipt: _MutableTransactionReceipt,
) -> None:
    """Raise a typed failure without obscuring the durable transaction state.

    Args:
        operation_error: Body, commit, or cleanup failure if one occurred.
        callback_errors: Ordinary callback failures in registration order.
        receipt: Caller-owned result updated before any exception escapes.
    """
    if operation_error is None and not callback_errors:
        return

    if operation_error is not None and not isinstance(
        operation_error,
        Exception,
    ):
        _raise_interrupted_transaction(
            operation_error,
            callback_errors,
            receipt,
        )

    if callback_errors:
        _raise_callback_failure(
            operation_error,
            callback_errors,
            receipt,
        )

    if operation_error is None:
        return
    receipt.record_error(operation_error)
    if isinstance(operation_error, DatabaseCommitOutcomeUnknownError):
        _raise_unknown_commit(operation_error)
    if isinstance(operation_error, SQLAlchemyError):
        if receipt.outcome is TransactionOutcome.ROLLED_BACK:
            message = "The database transaction failed and was rolled back."
        elif receipt.outcome is TransactionOutcome.COMMITTED:
            message = "The database transaction committed, but cleanup failed."
        else:
            message = "The database transaction outcome could not be confirmed."
        raise DatabaseTransactionError(message) from operation_error
    raise operation_error


def _raise_callback_failure(
    operation_error: BaseException | None,
    callback_errors: list[Exception],
    receipt: _MutableTransactionReceipt,
) -> NoReturn:
    """Raise ordered callback failures with the recorded transaction outcome.

    Args:
        operation_error: Optional transaction error preceding callback errors.
        callback_errors: Callback errors in registration order.
        receipt: Caller-owned result updated before the error escapes.
    """
    outcome = receipt.outcome
    if outcome is TransactionOutcome.COMMITTED:
        outcome = TransactionOutcome.COMMITTED_WITH_CALLBACK_ERRORS
    elif outcome is None:
        outcome = TransactionOutcome.FAILED
    error = DatabaseTransactionCallbackError(outcome, callback_errors)
    receipt.finish(outcome, error)
    failures: list[BaseException] = list(callback_errors)
    if operation_error is not None:
        failures.insert(0, operation_error)
    group = BaseExceptionGroup(
        "The database transaction and its callbacks failed.",
        failures,
    )
    raise error from group


def _raise_interrupted_transaction(
    operation_error: BaseException,
    callback_errors: list[Exception],
    receipt: _MutableTransactionReceipt,
) -> NoReturn:
    """Preserve cancellation and other BaseException transaction failures.

    Args:
        operation_error: Cancellation or other non-Exception failure.
        callback_errors: Ordinary errors raised by any selected callbacks.
        receipt: Caller-owned result updated before the error escapes.
    """
    receipt.record_error(operation_error)
    if callback_errors:
        cause = BaseExceptionGroup(
            "The transaction and its callbacks failed.",
            [operation_error, *callback_errors],
        )
        operation_error.add_note(
            "One or more transaction callbacks also failed."
        )
        raise operation_error from cause
    if isinstance(operation_error, DatabaseCommitOutcomeUnknownError):
        _raise_unknown_commit(operation_error)
    raise operation_error


def _raise_unknown_commit(
    error: DatabaseCommitOutcomeUnknownError,
) -> NoReturn:
    """Raise uncertain commit status with every backend cause preserved.

    Args:
        error: Native error containing commit and optional cleanup failures.
    """
    if error.cleanup_error is None:
        raise error from error.commit_error
    group = BaseExceptionGroup(
        "The commit and connection cleanup both failed.",
        [error.commit_error, error.cleanup_error],
    )
    raise error from group


def _combine_failures(
    previous: BaseException | None,
    current: BaseException,
    message: str,
) -> BaseException:
    """Preserve both the transaction failure and a cleanup failure.

    Args:
        previous: Existing failure, if an earlier transaction step failed.
        current: Failure raised by the latest cleanup operation.
        message: Context for the resulting exception group.

    Returns:
        The current error or a group containing both failures.
    """
    if previous is None:
        return current
    return BaseExceptionGroup(message, [previous, current])


def _detach_result(result: Result[object]) -> DatabaseResult:
    """Copy result rows and metadata before the session scope closes.

    Args:
        result: Buffered SQLAlchemy result from one completed statement.

    Returns:
        A backend-independent value with no live cursor references.
    """
    try:
        # ORM execution returns ChunkedIteratorResult, which deliberately has
        # no cursor-specific rowcount or returns_rows attributes. Only the
        # CursorResult contract can authoritatively report those values.
        if isinstance(result, CursorResult):
            rows = (
                tuple(
                    MappingProxyType(dict(row))
                    for row in result.mappings().all()
                )
                if result.returns_rows
                else ()
            )
            rowcount = result.rowcount
        else:
            rows = tuple(
                MappingProxyType(dict(row)) for row in result.mappings().all()
            )
            rowcount = -1
        return DatabaseResult(rows=rows, rowcount=rowcount)
    finally:
        result.close()


def _engine_options_for_factory(
    options: Mapping[str, object],
    url: URL,
    *,
    async_mode: bool = False,
) -> dict[str, object]:
    """Copy immutable options into the mutable DBAPI input shape.

    Args:
        options: Validated connection options.
        url: SQLAlchemy URL for the selected connection and execution mode.
        async_mode: Whether the factory will create an AsyncEngine.

    Returns:
        A fresh engine keyword mapping with a detached ``connect_args`` map.

    Raises:
        DatabaseConfigurationError: If SQLite's legacy autocommit mode is
            explicitly requested, because it breaks nested rollback.
    """
    copied = dict(options)
    connect_args = copied.get("connect_args")
    detached_args = (
        {}
        if connect_args is None
        else dict(cast("Mapping[str, object]", connect_args))
    )
    if url.get_backend_name() == "sqlite":
        if detached_args.get("autocommit", False) is not False:
            msg = "SQLite requires PEP 249 transaction control."
            raise DatabaseConfigurationError(msg)
        if async_mode:
            # aiosqlite does not expose the DBAPI autocommit attribute needed
            # to apply the foreign-key pragma under PEP 249 mode. Its engine
            # instead uses SQLAlchemy begin events for equivalent boundaries.
            detached_args.pop("autocommit", None)
        else:
            # SQLite's legacy mode allows a released SAVEPOINT to outlive its
            # enclosing transaction when no earlier statement emitted BEGIN.
            detached_args["autocommit"] = False
    if connect_args is not None or url.get_backend_name() == "sqlite":
        copied["connect_args"] = detached_args
    return copied


def _enable_sync_sqlite_foreign_keys(
    dbapi_connection: DBAPIConnection,
    connection_record: ConnectionPoolEntry,
) -> None:
    """Enable referential checks on one synchronous SQLite connection.

    SQLite ignores declared foreign keys unless every physical connection
    enables the pragma. PEP 249 transaction control requires temporarily
    enabling autocommit while applying this connection-local setting.

    Args:
        dbapi_connection: Synchronous SQLite DBAPI connection.
        connection_record: SQLAlchemy pool record for the new connection.
    """
    del connection_record
    sqlite_connection = cast("_SQLiteSyncDBAPIConnection", dbapi_connection)
    previous_autocommit = sqlite_connection.autocommit
    sqlite_connection.autocommit = True
    try:
        cursor = sqlite_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
    finally:
        sqlite_connection.autocommit = previous_autocommit


def _enable_async_sqlite_foreign_keys(
    dbapi_connection: DBAPIConnection,
    connection_record: ConnectionPoolEntry,
) -> None:
    """Configure aiosqlite for explicit BEGIN and enforce foreign keys.

    SQLAlchemy's async SQLite adapter does not expose the DBAPI autocommit
    attribute. The supported isolation-level event strategy leaves the raw
    connection in autocommit while applying this pragma; a begin event then
    restores explicit SQLAlchemy transaction boundaries.

    Args:
        dbapi_connection: SQLAlchemy's aiosqlite DBAPI adapter.
        connection_record: SQLAlchemy pool record for the new connection.
    """
    del connection_record
    sqlite_connection = cast("_SQLiteAsyncDBAPIConnection", dbapi_connection)
    sqlite_connection.isolation_level = None
    cursor = sqlite_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _begin_async_sqlite_transaction(
    connection: SQLAlchemyConnection,
) -> None:
    """Start SQLite transactions through SQLAlchemy's begin event.

    The matching connect event disables driver-emitted ``BEGIN`` so SQLite's
    transaction state remains explicit and savepoints stay inside the root.

    Args:
        connection: SQLAlchemy connection beginning a transaction.
    """
    connection.exec_driver_sql("BEGIN")


__all__ = ["DatabaseManager"]
