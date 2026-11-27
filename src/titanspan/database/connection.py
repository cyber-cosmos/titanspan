"""Provide one named logical connection over SQLAlchemy-owned engines.

The handle does not own a physical DBAPI connection. Each operation obtains
the current Unit of Work or opens a short-lived session through its manager.
"""

from __future__ import annotations

from copy import copy
from typing import TYPE_CHECKING, cast

from titanspan.contracts.database import (
    DatabaseConnectionService,
    DatabaseResult,
)
from titanspan.database.query_builder import QueryBuilder

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Mapping
    from contextlib import AbstractAsyncContextManager, AbstractContextManager

    from sqlalchemy.engine import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlalchemy.sql import Executable
    from sqlalchemy.sql.elements import ClauseElement

    from titanspan.database.manager import DatabaseManager


class Connection(DatabaseConnectionService):
    """Select sync and async operations for one configured connection.
    """  # fmt: skip

    def __init__(self, manager: DatabaseManager, name: str) -> None:
        """Retain the application manager and selected connection name.

        Args:
            manager: Application-owned manager that owns all engines.
            name: Validated connection key from application configuration.
        """
        self._manager = manager
        self._name = name

    @property
    def name(self) -> str:
        """Return the selected application connection name.

        Returns:
            The configured name used for this logical connection.
        """
        return self._name

    @property
    def transaction_level(self) -> int:
        """Return this named connection's depth in the current execution.

        Returns:
            Zero outside a transaction or the active savepoint depth.
        """
        return self._manager.connection_transaction_level(self._name)

    @property
    def dialect_name(self) -> str:
        """Return the configured SQLAlchemy dialect without opening an engine.

        Returns:
            A normalized backend name such as ``sqlite`` or ``postgresql``.
        """
        return self._manager.dialect_name(self._name)

    @property
    def target_identity(self) -> str:
        """Return the redacted configured database target.

        Returns:
            A database URL without usernames, passwords, or query options.
        """
        return self._manager.target_identity(self._name)

    @property
    def engine(self) -> Engine:
        """Expose the native SQLAlchemy sync engine for interoperability.

        Returns:
            The lazily constructed engine owned by the application manager.
        """
        return self._manager.engine(self._name)

    @property
    def async_engine(self) -> AsyncEngine:
        """Expose the native SQLAlchemy async engine for interoperability.

        Returns:
            The lazily constructed async engine owned by the manager.
        """
        return self._manager.async_engine(self._name)

    def execute_statement(
        self,
        statement: Executable,
        parameters: Mapping[str, object] | None = None,
    ) -> DatabaseResult:
        """Run a SQLAlchemy statement through this sync session policy.

        This method is the explicit interoperability boundary for advanced
        SQLAlchemy expressions. Native queries use ``table`` and the fluent
        builder.

        Args:
            statement: Supported SQLAlchemy Core or ORM statement.
            parameters: Additional named execution parameters.

        Returns:
            Detached result rows and affected-row metadata.
        """
        return self._manager.execute_statement_sync(
            self._name,
            statement,
            parameters,
        )

    def compile_statement(
        self,
        statement: ClauseElement,
        *,
        named_parameters: bool = False,
    ) -> tuple[str, Mapping[str, object]]:
        """Compile a statement without opening a database connection.

        Args:
            statement: SQLAlchemy Core or ORM statement.
            named_parameters: Use named placeholders for safe SQL wrappers.

        Returns:
            SQL placeholders and a separate copy of bound values.
        """
        dialect = self._manager.engine(self._name).dialect
        if named_parameters:
            dialect = copy(dialect)
            dialect.paramstyle = "named"
            dialect.positional = False
        compiled = statement.compile(
            dialect=dialect,
            compile_kwargs={"render_postcompile": True},
        )
        # SQLAlchemy's compiler overload types bind names as bytes here, while
        # runtime named parameter mappings use string keys.
        bindings = cast("Mapping[str, object]", compiled.params)
        return str(compiled), dict(bindings)

    async def execute_statement_async(
        self,
        statement: Executable,
        parameters: Mapping[str, object] | None = None,
    ) -> DatabaseResult:
        """Run a SQLAlchemy statement through this async session policy.

        Args:
            statement: Supported SQLAlchemy Core or ORM statement.
            parameters: Additional named execution parameters.

        Returns:
            Detached result rows and affected-row metadata.
        """
        return await self._manager.execute_statement_async(
            self._name,
            statement,
            parameters,
        )

    def stream_statement(
        self,
        statement: Executable,
        *,
        batch_size: int = 1000,
    ) -> AbstractContextManager[Iterator[Mapping[str, object]]]:
        """Stream mapping rows using this connection's sync session policy.

        Args:
            statement: SQLAlchemy Core statement to execute.
            batch_size: Maximum result batch buffered by SQLAlchemy.

        Returns:
            A context manager that owns the result until it exits.
        """
        return self._manager.stream_statement_sync(
            self._name,
            statement,
            batch_size=batch_size,
        )

    def stream_statement_async(
        self,
        statement: Executable,
        *,
        batch_size: int = 1000,
    ) -> AbstractAsyncContextManager[AsyncIterator[Mapping[str, object]]]:
        """Stream mapping rows using this connection's async session policy.

        Args:
            statement: SQLAlchemy Core statement to execute.
            batch_size: Maximum result batch buffered by SQLAlchemy.

        Returns:
            An async context manager that owns the result until it exits.
        """
        return self._manager.stream_statement_async(
            self._name,
            statement,
            batch_size=batch_size,
        )

    def table(self, name: str) -> QueryBuilder:
        """Start a fluent SQLAlchemy Core query for one table.

        Args:
            name: Safe table identifier, optionally with a schema.

        Returns:
            A fresh mutable builder tied to this logical connection.
        """
        return QueryBuilder(self, name)

    def execute(
        self,
        sql: str,
        parameters: Mapping[str, object] | None = None,
    ) -> DatabaseResult:
        """Run trusted SQL with driver-bound named values.

        Args:
            sql: Explicit SQL text supplied by trusted application code.
            parameters: Named values bound by SQLAlchemy and the driver.

        Returns:
            Detached rows and driver-reported affected-row metadata.
        """
        return self._manager.execute_sync(
            self._name,
            sql,
            parameters,
        )

    async def execute_async(
        self,
        sql: str,
        parameters: Mapping[str, object] | None = None,
    ) -> DatabaseResult:
        """Run trusted SQL asynchronously with bound values.

        Args:
            sql: Explicit SQL text supplied by trusted application code.
            parameters: Named values bound by SQLAlchemy and the driver.

        Returns:
            Detached rows and driver-reported affected-row metadata.
        """
        return await self._manager.execute_async(
            self._name,
            sql,
            parameters,
        )

    def select(
        self,
        sql: str,
        parameters: Mapping[str, object] | None = None,
    ) -> list[Mapping[str, object]]:
        """Run a read statement and return detached mapping rows.

        Args:
            sql: Explicit read statement supplied by trusted application code.
            parameters: Named values bound by SQLAlchemy and the driver.

        Returns:
            A list of copied result mappings.
        """
        return list(self.execute(sql, parameters).rows)

    async def select_async(
        self,
        sql: str,
        parameters: Mapping[str, object] | None = None,
    ) -> list[Mapping[str, object]]:
        """Run a read statement asynchronously and detach its rows.

        Args:
            sql: Explicit read statement supplied by trusted application code.
            parameters: Named values bound by SQLAlchemy and the driver.

        Returns:
            A list of copied result mappings.
        """
        result = await self.execute_async(sql, parameters)
        return list(result.rows)

    def statement(
        self,
        sql: str,
        parameters: Mapping[str, object] | None = None,
    ) -> bool:
        """Execute a statement and report successful completion.

        Args:
            sql: Explicit SQL statement supplied by trusted application code.
            parameters: Named values bound by SQLAlchemy and the driver.

        Returns:
            ``True`` after the statement completes without a database error.
        """
        self.execute(sql, parameters)
        return True

    async def statement_async(
        self,
        sql: str,
        parameters: Mapping[str, object] | None = None,
    ) -> bool:
        """Execute a statement asynchronously and report success.

        Args:
            sql: Explicit SQL statement supplied by trusted application code.
            parameters: Named values bound by SQLAlchemy and the driver.

        Returns:
            ``True`` after the statement completes without a database error.
        """
        await self.execute_async(sql, parameters)
        return True


__all__ = ["Connection"]
