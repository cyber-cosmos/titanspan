"""Expose native database operations through the active application.

The facade resolves the canonical Database service and keeps one manager
identity shared with dependency injection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.contracts.database import (
    DatabaseConnectionService,
    DatabaseQueryBuilder,
    DatabaseService,
)
from titanspan.facades.base import Facade

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping
    from contextlib import AbstractAsyncContextManager, AbstractContextManager

    from titanspan.contracts.database import DatabaseResult, TransactionReceipt


class DB(Facade[DatabaseService]):
    """Resolve application database operations through one native facade.
    """  # fmt: skip

    service_contract = DatabaseService

    @classmethod
    def connection(
        cls,
        name: str | None = None,
    ) -> DatabaseConnectionService:
        """Select one named or default logical database connection.

        Args:
            name: Configured connection name or ``None`` for the default.

        Returns:
            A lightweight connection handle owned by the current application.
        """
        return cls.resolve_service().connection(name)

    @classmethod
    def table(
        cls,
        table_name: str,
        *,
        connection: str | None = None,
    ) -> DatabaseQueryBuilder:
        """Start a fluent query against a table on a selected connection.

        Args:
            table_name: Safe table name, optionally qualified by a schema.
            connection: Optional configured connection name.

        Returns:
            A fresh mutable query builder for the selected table.
        """
        return cls.connection(connection).table(table_name)

    @classmethod
    def query(
        cls,
        table_name: str,
        *,
        connection: str | None = None,
    ) -> DatabaseQueryBuilder:
        """Start a fluent query using the same API as ``table``.

        Args:
            table_name: Safe table name, optionally qualified by a schema.
            connection: Optional configured connection name.

        Returns:
            A fresh mutable query builder for the selected table.
        """
        return cls.table(table_name, connection=connection)

    @classmethod
    def transaction(
        cls,
        name: str | None = None,
    ) -> AbstractContextManager[TransactionReceipt]:
        """Open a sync transaction on the selected connection.

        Args:
            name: Configured connection name or ``None`` for the default.

        Returns:
            A context manager that records its transaction outcome.
        """
        return cls.resolve_service().transaction(name)

    @classmethod
    def transaction_async(
        cls,
        name: str | None = None,
    ) -> AbstractAsyncContextManager[TransactionReceipt]:
        """Open an async transaction owned by the current task.

        Args:
            name: Configured connection name or ``None`` for the default.

        Returns:
            An async context manager that records its transaction outcome.
        """
        return cls.resolve_service().transaction_async(name)

    @classmethod
    def after_commit(
        cls,
        callback: Callable[[], None],
        *,
        connection: str | None = None,
    ) -> None:
        """Run a callback after its connection transaction commits.

        Args:
            callback: Synchronous callback invoked after a successful commit.
            connection: Connection owning the transaction. Outside a
                transaction, the callback runs immediately.
        """
        cls.resolve_service().after_commit(callback, connection)

    @classmethod
    async def after_commit_async(
        cls,
        callback: Callable[[], Awaitable[None]],
        *,
        connection: str | None = None,
    ) -> None:
        """Await a callback after the owning async transaction commits.

        Args:
            callback: Asynchronous application callback with no result.
            connection: Connection owning the active async transaction.
        """
        await cls.resolve_service().after_commit_async(callback, connection)

    @classmethod
    def after_rollback(
        cls,
        callback: Callable[[], None],
        *,
        connection: str | None = None,
    ) -> None:
        """Run a callback after its connection transaction rolls back.

        Args:
            callback: Synchronous callback invoked after rollback.
            connection: Connection owning the active transaction.
        """
        cls.resolve_service().after_rollback(callback, connection)

    @classmethod
    def execute(
        cls,
        sql: str,
        parameters: Mapping[str, object] | None = None,
        *,
        connection: str | None = None,
    ) -> DatabaseResult:
        """Execute explicit SQL with values bound by the database driver.

        Args:
            sql: Trusted SQL statement.
            parameters: Named values bound by SQLAlchemy.
            connection: Optional configured connection name.

        Returns:
            Detached statement rows and affected-row metadata.
        """
        return cls.connection(connection).execute(sql, parameters)

    @classmethod
    async def execute_async(
        cls,
        sql: str,
        parameters: Mapping[str, object] | None = None,
        *,
        connection: str | None = None,
    ) -> DatabaseResult:
        """Asynchronously execute explicit SQL with bound values.

        Args:
            sql: Trusted SQL statement.
            parameters: Named values bound by SQLAlchemy.
            connection: Optional configured connection name.

        Returns:
            Detached statement rows and affected-row metadata.
        """
        return await cls.connection(connection).execute_async(sql, parameters)

    @classmethod
    def select(
        cls,
        sql: str,
        parameters: Mapping[str, object] | None = None,
        *,
        connection: str | None = None,
    ) -> list[Mapping[str, object]]:
        """Run a trusted SQL read and return detached mapping rows.

        Args:
            sql: Trusted read statement.
            parameters: Named values bound by SQLAlchemy.
            connection: Optional configured connection name.

        Returns:
            The selected rows as ordinary Python mappings.
        """
        return cls.connection(connection).select(sql, parameters)

    @classmethod
    async def select_async(
        cls,
        sql: str,
        parameters: Mapping[str, object] | None = None,
        *,
        connection: str | None = None,
    ) -> list[Mapping[str, object]]:
        """Asynchronously run a SQL read and detach its result rows.

        Args:
            sql: Trusted read statement.
            parameters: Named values bound by SQLAlchemy.
            connection: Optional configured connection name.

        Returns:
            The selected rows as ordinary Python mappings.
        """
        return await cls.connection(connection).select_async(sql, parameters)

    @classmethod
    def select_one(
        cls,
        sql: str,
        parameters: Mapping[str, object] | None = None,
        *,
        connection: str | None = None,
    ) -> Mapping[str, object] | None:
        """Return the first row from a SQL read, if one exists.

        Args:
            sql: Trusted read statement.
            parameters: Named values bound by SQLAlchemy.
            connection: Optional configured connection name.

        Returns:
            The first row or ``None``.
        """
        rows = cls.select(sql, parameters, connection=connection)
        return rows[0] if rows else None

    @classmethod
    async def select_one_async(
        cls,
        sql: str,
        parameters: Mapping[str, object] | None = None,
        *,
        connection: str | None = None,
    ) -> Mapping[str, object] | None:
        """Asynchronously return the first row, if one exists.

        Args:
            sql: Trusted read statement.
            parameters: Named values bound by SQLAlchemy.
            connection: Optional configured connection name.

        Returns:
            The first row or ``None``.
        """
        rows = await cls.select_async(sql, parameters, connection=connection)
        return rows[0] if rows else None

    @classmethod
    def scalar(
        cls,
        sql: str,
        parameters: Mapping[str, object] | None = None,
        *,
        connection: str | None = None,
    ) -> object | None:
        """Return the first column from the first SQL result row.

        Args:
            sql: Trusted read statement.
            parameters: Named values bound by SQLAlchemy.
            connection: Optional configured connection name.

        Returns:
            The first scalar value or ``None`` when no row exists.
        """
        row = cls.select_one(sql, parameters, connection=connection)
        return next(iter(row.values()), None) if row is not None else None

    @classmethod
    async def scalar_async(
        cls,
        sql: str,
        parameters: Mapping[str, object] | None = None,
        *,
        connection: str | None = None,
    ) -> object | None:
        """Asynchronously return the first column from the first row.

        Args:
            sql: Trusted read statement.
            parameters: Named values bound by SQLAlchemy.
            connection: Optional configured connection name.

        Returns:
            The first scalar value or ``None`` when no row exists.
        """
        row = await cls.select_one_async(
            sql,
            parameters,
            connection=connection,
        )
        return next(iter(row.values()), None) if row is not None else None

    @classmethod
    def statement(
        cls,
        sql: str,
        parameters: Mapping[str, object] | None = None,
        *,
        connection: str | None = None,
    ) -> bool:
        """Run explicit SQL and return true when the statement succeeds.

        Args:
            sql: Trusted SQL statement.
            parameters: Named values bound by SQLAlchemy.
            connection: Optional configured connection name.

        Returns:
            ``True`` after successful statement execution.
        """
        cls.connection(connection).execute(sql, parameters)
        return True

    @classmethod
    async def statement_async(
        cls,
        sql: str,
        parameters: Mapping[str, object] | None = None,
        *,
        connection: str | None = None,
    ) -> bool:
        """Asynchronously run SQL and return true when it succeeds.

        Args:
            sql: Trusted SQL statement.
            parameters: Named values bound by SQLAlchemy.
            connection: Optional configured connection name.

        Returns:
            ``True`` after successful statement execution.
        """
        await cls.connection(connection).execute_async(sql, parameters)
        return True

    @classmethod
    def transaction_level(cls) -> int:
        """Return the active transaction and savepoint nesting depth.

        Returns:
            Zero when no transaction is active in the current execution.
        """
        return cls.resolve_service().transaction_level


__all__ = ["DB"]
