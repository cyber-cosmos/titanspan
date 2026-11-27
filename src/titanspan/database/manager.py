"""Own lazy SQLAlchemy engines and execution-scoped Units of Work.

Each manager belongs to one Application. Its context-local session state is
checked against the current thread or asyncio task before reuse.
"""

from __future__ import annotations

import asyncio
import threading
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
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from titanspan.contracts.database import DatabaseResult
from titanspan.database.configuration import DatabaseConfiguration
from titanspan.database.connection import Connection
from titanspan.database.exceptions import (
    AsyncOperationRequiredError,
    DatabaseConfigurationError,
    DatabaseConnectionError,
    DatabaseQueryError,
    DatabaseTransactionError,
    DatabaseTransactionOwnershipError,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator, Mapping
    from contextvars import Token

    from sqlalchemy.engine import URL, CursorResult, Engine
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSessionTransaction
    from sqlalchemy.orm import SessionTransaction
    from sqlalchemy.sql import Executable

    from titanspan.contracts.config import ConfigRepository
    from titanspan.contracts.foundation import ApplicationPaths
    from titanspan.database.configuration import ConnectionConfiguration


type _ExecutionMode = Literal["sync", "async"]
type _Session = Session | AsyncSession


class _TransactionCallback(Protocol):
    """Describe a synchronous callback owned by a transaction boundary.
    """  # fmt: skip

    def __call__(self) -> None:
        """Perform one application callback without returning a value.
        """  # fmt: skip
        ...


def _new_callback_list() -> list[_TransactionCallback]:
    """Create a fresh typed list for one transaction callback phase.
    """  # fmt: skip
    return []


@dataclass(slots=True)
class _TransactionCallbacks:
    """Keep post-commit and post-rollback callbacks at one savepoint level.

    Successful savepoints merge their callbacks into the parent transaction.
    A rolled-back savepoint discards commit callbacks and runs its rollback
    callbacks immediately.
    """

    after_commit: list[_TransactionCallback] = field(
        default_factory=_new_callback_list,
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
    ) -> Generator[None, None, None]:
        """Own a synchronous Unit of Work for the current thread.

        Nested calls use SQLAlchemy savepoints. Database work inherited by a
        different task or thread is rejected before accessing the session.

        Args:
            name: Configured connection name or its default.

        Yields:
            Control while statements participate in the active transaction.

        Raises:
            AsyncOperationRequiredError: If sync I/O would block an event loop.
            DatabaseTransactionError: If the requested savepoint fails.
        """
        self._ensure_sync_allowed()
        connection_name = self._connection_name(name)
        active = self._active_state("sync", connection_name)
        if active is not None:
            with self._nested_sync(active):
                yield
            return

        callbacks: tuple[_TransactionCallback, ...] = ()
        operation_error: BaseException | None = None
        try:
            with self._root_sync_scope(connection_name) as (
                session,
                state,
            ):
                transaction = session.begin()
                transaction.__enter__()
                try:
                    yield
                except BaseException as error:
                    operation_error, callbacks = _rollback_sync(
                        transaction,
                        state,
                        error,
                    )
                else:
                    operation_error, callbacks = _commit_sync(
                        transaction,
                        state,
                    )
        except BaseException as error:
            operation_error = _combine_failures(
                operation_error,
                error,
                "The database transaction cleanup failed.",
            )
        _finish_transaction(operation_error, callbacks)

    @asynccontextmanager
    async def transaction_async(
        self,
        name: str | None = None,
    ) -> AsyncGenerator[None, None]:
        """Own an async Unit of Work for the current asyncio task.

        A ContextVar copied into a child task does not grant that task access
        to its parent's mutable SQLAlchemy AsyncSession.

        Args:
            name: Configured connection name or its default.

        Yields:
            Control while statements participate in the active transaction.

        Raises:
            AsyncOperationRequiredError: If no asyncio task is active.
            DatabaseTransactionError: If the transaction or savepoint fails.
        """
        task = self._current_async_task()
        connection_name = self._connection_name(name)
        active = self._active_state("async", connection_name)
        if active is not None:
            async with self._nested_async(active):
                yield
            return

        callbacks: tuple[_TransactionCallback, ...] = ()
        operation_error: BaseException | None = None
        try:
            async with self._root_async_scope(
                connection_name,
                task,
            ) as (session, state):
                transaction = session.begin()
                await transaction.__aenter__()
                try:
                    yield
                except BaseException as error:
                    operation_error, callbacks = await _rollback_async(
                        transaction,
                        state,
                        error,
                    )
                else:
                    operation_error, callbacks = await _commit_async(
                        transaction,
                        state,
                    )
        except BaseException as error:
            operation_error = _combine_failures(
                operation_error,
                error,
                "The database transaction cleanup failed.",
            )
        _finish_transaction(operation_error, callbacks)

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
                    ),
                )
            except (ImportError, SQLAlchemyError) as error:
                msg = "The configured async database driver is unavailable."
                raise DatabaseConnectionError(msg) from error
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
                    "CursorResult[object]",
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
                    "CursorResult[object]",
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
                    "CursorResult[object]",
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
                    "CursorResult[object]",
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
    ) -> Generator[None, None, None]:
        """Open a SQLAlchemy savepoint inside an owned sync transaction.

        Args:
            state: Current owner-validated transaction state.

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
            _raise_savepoint_error(error, frame, rollback_confirmed)
        else:
            _merge_savepoint(state, frame)

    @asynccontextmanager
    async def _nested_async(
        self,
        state: _ExecutionState,
    ) -> AsyncGenerator[None, None]:
        """Open a SQLAlchemy savepoint inside an owned async transaction.

        Args:
            state: Current owner-validated transaction state.

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
            _raise_savepoint_error(error, frame, rollback_confirmed)
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
) -> NoReturn:
    """Dispatch confirmed savepoint rollback callbacks and raise its failure.

    Args:
        error: Body, savepoint, or savepoint cleanup failure.
        frame: Callback frame discarded when the savepoint ends.
        rollback_confirmed: Whether rollback completed successfully.
    """
    callback_errors = (
        _run_callbacks(tuple(frame.after_rollback))
        if rollback_confirmed
        else []
    )
    if callback_errors:
        message = "The savepoint and its rollback callbacks failed."
        raise BaseExceptionGroup(message, [error, *callback_errors]) from error
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
) -> tuple[BaseException, tuple[_TransactionCallback, ...]]:
    """Roll back a sync transaction and select confirmed rollback callbacks.

    Args:
        transaction: SQLAlchemy root transaction being rolled back.
        state: Owning callback state for that transaction.
        original: Failure raised by the transaction body.

    Returns:
        The original or combined failure, plus safe rollback callbacks.
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
        )
    callbacks = tuple(state.callback_frames[0].after_rollback)
    return original, callbacks


def _commit_sync(
    transaction: SessionTransaction,
    state: _ExecutionState,
) -> tuple[BaseException | None, tuple[_TransactionCallback, ...]]:
    """Commit a sync transaction and select post-commit callbacks.

    Args:
        transaction: SQLAlchemy root transaction to commit.
        state: Owning callback state for that transaction.

    Returns:
        A commit failure and cleanup details, or its callbacks after commit.
    """
    try:
        transaction.__exit__(None, None, None)
    except BaseException as error:
        if transaction.is_active:
            try:
                transaction.rollback()
            except BaseException as rollback_error:
                message = "The transaction commit and cleanup failed."
                error = _combine_failures(error, rollback_error, message)
        return error, ()
    return None, tuple(state.callback_frames[0].after_commit)


async def _rollback_async(
    transaction: AsyncSessionTransaction,
    state: _ExecutionState,
    original: BaseException,
) -> tuple[BaseException, tuple[_TransactionCallback, ...]]:
    """Shield async rollback and select callbacks only after it succeeds.

    Args:
        transaction: SQLAlchemy root transaction being rolled back.
        state: Owning callback state for that transaction.
        original: Failure or cancellation raised by the transaction body.

    Returns:
        The original or combined failure, plus safe rollback callbacks.
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
        )
    callbacks = tuple(state.callback_frames[0].after_rollback)
    return original, callbacks


async def _commit_async(
    transaction: AsyncSessionTransaction,
    state: _ExecutionState,
) -> tuple[BaseException | None, tuple[_TransactionCallback, ...]]:
    """Commit an async transaction and select post-commit callbacks.

    A failed commit has an uncertain outcome, so rollback callbacks are not
    dispatched even if SQLAlchemy permits a later cleanup rollback.

    Args:
        transaction: SQLAlchemy root transaction to commit.
        state: Owning callback state for that transaction.

    Returns:
        A commit failure and cleanup details, or its callbacks after commit.
    """
    try:
        await transaction.__aexit__(None, None, None)
    except BaseException as error:
        if transaction.is_active:
            try:
                with anyio.CancelScope(shield=True):
                    await transaction.rollback()
            except BaseException as rollback_error:
                message = "The transaction commit and cleanup failed."
                error = _combine_failures(error, rollback_error, message)
        return error, ()
    return None, tuple(state.callback_frames[0].after_commit)


def _finish_transaction(
    operation_error: BaseException | None,
    callbacks: tuple[_TransactionCallback, ...],
) -> None:
    """Run callbacks after cleanup and re-raise transaction failures.

    Args:
        operation_error: Body, commit, or cleanup failure if one occurred.
        callbacks: Callbacks selected by a confirmed transaction outcome.
    """
    callback_errors = _run_callbacks(callbacks)
    if operation_error is not None:
        if callback_errors:
            operation_error = BaseExceptionGroup(
                "The database transaction and its callbacks failed.",
                [operation_error, *callback_errors],
            )
        if isinstance(operation_error, SQLAlchemyError):
            message = "The database transaction failed."
            raise DatabaseTransactionError(message) from operation_error
        raise operation_error
    if callback_errors:
        message = "One or more database transaction callbacks failed."
        raise ExceptionGroup(message, callback_errors)


def _run_callbacks(
    callbacks: tuple[_TransactionCallback, ...],
) -> list[Exception]:
    """Run every synchronous transaction callback and collect failures.

    Args:
        callbacks: Callbacks selected by a committed or rolled-back scope.

    Returns:
        Exceptions raised by callbacks, in registration order.
    """
    failures: list[Exception] = []
    for callback in callbacks:
        try:
            callback()
        except Exception as error:
            failures.append(error)
    return failures


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


def _detach_result(result: CursorResult[object]) -> DatabaseResult:
    """Copy result rows and metadata before the session scope closes.

    Args:
        result: Buffered SQLAlchemy result from one completed statement.

    Returns:
        A backend-independent value with no live cursor references.
    """
    try:
        rows = (
            tuple(
                MappingProxyType(dict(row)) for row in result.mappings().all()
            )
            if result.returns_rows
            else ()
        )
        return DatabaseResult(rows=rows, rowcount=result.rowcount)
    finally:
        result.close()


def _engine_options_for_factory(
    options: Mapping[str, object],
    url: URL,
) -> dict[str, object]:
    """Copy immutable options into the mutable DBAPI input shape.

    Args:
        options: Validated connection options.
        url: SQLAlchemy URL for the selected connection and execution mode.

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
        # SQLite's legacy mode allows a released SAVEPOINT to outlive its
        # enclosing transaction when no earlier statement emitted BEGIN.
        detached_args["autocommit"] = False
    if connect_args is not None or url.get_backend_name() == "sqlite":
        copied["connect_args"] = detached_args
    return copied


__all__ = ["DatabaseManager"]
