"""Define the dependency-independent database connection operations.

SQLAlchemy engines and sessions remain behind implementation-owned native
interop properties rather than appearing in this contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.sql import Executable

    from titanspan.contracts.database.query import DatabaseQueryBuilder
    from titanspan.contracts.database.result import DatabaseResult


@runtime_checkable
class DatabaseConnectionService(Protocol):
    """Describe sync and async execution on one named logical connection.
    """  # fmt: skip

    @property
    def name(self) -> str:
        """Return the selected application connection name.

        Returns:
            The configured name used for this logical connection.
        """
        ...

    @property
    def dialect_name(self) -> str:
        """Return SQLAlchemy's normalized dialect name for this connection.

        Returns:
            A backend identifier such as ``sqlite`` or ``postgresql``.
        """
        ...

    def table(self, name: str) -> DatabaseQueryBuilder:
        """Start a fluent query against one safe table identifier.

        Args:
            name: Table name, optionally qualified by one schema.

        Returns:
            A native builder that delegates execution to this connection.
        """
        ...

    def execute(
        self,
        sql: str,
        parameters: Mapping[str, object] | None = None,
    ) -> DatabaseResult:
        """Run one explicit SQL statement with bound values.

        Args:
            sql: SQL text supplied by trusted application code.
            parameters: Named values bound by the database driver.

        Returns:
            A detached result with copied rows and affected-row metadata.
        """
        ...

    async def execute_async(
        self,
        sql: str,
        parameters: Mapping[str, object] | None = None,
    ) -> DatabaseResult:
        """Asynchronously run SQL without blocking the current task.

        Args:
            sql: SQL text supplied by trusted application code.
            parameters: Named values bound by the database driver.

        Returns:
            A detached result with copied rows and affected-row metadata.
        """
        ...

    def execute_statement(
        self,
        statement: Executable,
        parameters: Mapping[str, object] | None = None,
    ) -> DatabaseResult:
        """Run a SQLAlchemy statement through the native Unit of Work.

        Args:
            statement: Supported SQLAlchemy Core or ORM statement.
            parameters: Additional named execution values.

        Returns:
            Detached result rows and affected-row metadata.
        """
        ...

    async def execute_statement_async(
        self,
        statement: Executable,
        parameters: Mapping[str, object] | None = None,
    ) -> DatabaseResult:
        """Run a SQLAlchemy statement asynchronously.

        Args:
            statement: Supported SQLAlchemy Core or ORM statement.
            parameters: Additional named execution values.

        Returns:
            Detached result rows and affected-row metadata.
        """
        ...

    def select(
        self,
        sql: str,
        parameters: Mapping[str, object] | None = None,
    ) -> list[Mapping[str, object]]:
        """Run a read statement and return detached mapping rows.

        Args:
            sql: Read-only SQL text supplied by trusted application code.
            parameters: Named values bound by the database driver.

        Returns:
            Rows copied out of the short-lived result and session.
        """
        ...

    async def select_async(
        self,
        sql: str,
        parameters: Mapping[str, object] | None = None,
    ) -> list[Mapping[str, object]]:
        """Asynchronously run a read statement and detach its rows.

        Args:
            sql: Read-only SQL text supplied by trusted application code.
            parameters: Named values bound by the database driver.

        Returns:
            Rows copied out of the short-lived result and session.
        """
        ...

    def statement(
        self,
        sql: str,
        parameters: Mapping[str, object] | None = None,
    ) -> bool:
        """Execute one statement and report successful completion.

        Args:
            sql: SQL statement supplied by trusted application code.
            parameters: Named values bound by the database driver.

        Returns:
            ``True`` after the statement completes without an error.
        """
        ...

    async def statement_async(
        self,
        sql: str,
        parameters: Mapping[str, object] | None = None,
    ) -> bool:
        """Execute one statement asynchronously and report success.

        Args:
            sql: SQL statement supplied by trusted application code.
            parameters: Named values bound by the database driver.

        Returns:
            ``True`` after the statement completes without an error.
        """
        ...


__all__ = ["DatabaseConnectionService"]
