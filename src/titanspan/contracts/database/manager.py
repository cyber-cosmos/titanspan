"""Define the canonical application database service contract.

The contract leaves engine construction, pooling, sessions, and execution to
the selected persistence backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from contextlib import AbstractAsyncContextManager, AbstractContextManager

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session

    from titanspan.contracts.database.connection import (
        DatabaseConnectionService,
    )


@runtime_checkable
class DatabaseService(Protocol):
    """Describe application connection selection and transaction ownership.
    """  # fmt: skip

    def connection(
        self,
        name: str | None = None,
    ) -> DatabaseConnectionService:
        """Select one configured logical connection.

        Args:
            name: Configured name or the selected default connection.

        Returns:
            A handle that reuses the application's engine and session policy.
        """
        ...

    def session(
        self,
        name: str | None = None,
    ) -> AbstractContextManager[Session]:
        """Open the current sync Unit of Work for explicit ORM interop.

        Ordinary application code should use Models and Query Builders.

        Args:
            name: Configured connection name or its default.

        Returns:
            A session participating in the active transaction, or one
            short-lived transaction when called outside an explicit scope.
        """
        ...

    def session_async(
        self,
        name: str | None = None,
    ) -> AbstractAsyncContextManager[AsyncSession]:
        """Open the current async Unit of Work for ORM interop.

        Args:
            name: Configured connection name or its default.

        Returns:
            A task-owned session participating in the active transaction, or
            one short-lived transaction outside an explicit scope.
        """
        ...

    @property
    def transaction_level(self) -> int:
        """Report the active transaction and savepoint depth.

        Returns:
            Zero outside a transaction or the current nested depth.
        """
        ...

    def transaction(
        self,
        name: str | None = None,
    ) -> AbstractContextManager[None]:
        """Open a synchronous transaction owned by the current thread.

        Args:
            name: Configured connection name or its default.

        Returns:
            A context manager that commits or rolls back the Unit of Work.
        """
        ...

    def transaction_async(
        self,
        name: str | None = None,
    ) -> AbstractAsyncContextManager[None]:
        """Open an async transaction owned by the current task.

        Args:
            name: Configured connection name or its default.

        Returns:
            An async context manager that commits or rolls back the Unit of
            Work.
        """
        ...

    def after_commit(
        self,
        callback: Callable[[], None],
        name: str | None = None,
    ) -> None:
        """Run a callback after the selected transaction commits.

        The callback runs immediately when no transaction is active.

        Args:
            callback: Application-owned callback with no database result.
            name: Connection whose active transaction owns the callback.
        """
        ...

    async def after_commit_async(
        self,
        callback: Callable[[], Awaitable[None]],
        name: str | None = None,
    ) -> None:
        """Await a callback after the selected async transaction commits.

        The callback runs immediately when no transaction is active. It may
        be registered only by the task that owns an async transaction.

        Args:
            callback: Asynchronous application callback with no database
                result.
            name: Connection whose active transaction owns the callback.
        """
        ...

    def after_rollback(
        self,
        callback: Callable[[], None],
        name: str | None = None,
    ) -> None:
        """Run a callback after the selected transaction rolls back.

        Args:
            callback: Application-owned callback with no database result.
            name: Connection whose active transaction owns the callback.
        """
        ...


__all__ = ["DatabaseService"]
