"""Provide one named logical connection over SQLAlchemy-owned engines.

The handle does not own a physical DBAPI connection. Each operation obtains
the current Unit of Work or opens a short-lived session through its manager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.contracts.database import (
    DatabaseConnectionService,
    DatabaseResult,
)
from titanspan.database.query_builder import QueryBuilder

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.engine import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlalchemy.sql import Executable

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
    def dialect_name(self) -> str:
        """Return the configured SQLAlchemy dialect without opening an engine.

        Returns:
            A normalized backend name such as ``sqlite`` or ``postgresql``.
        """
        return self._manager.dialect_name(self._name)

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
