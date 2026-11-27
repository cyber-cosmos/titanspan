"""Compose trusted data seeders through the native application services.

Seeder classes are constructed by Foundation's Container. SQLAlchemy-backed
Database transactions own writes and nested savepoints.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, ClassVar

from titanspan.contracts.database import DatabaseService
from titanspan.foundation import app

if TYPE_CHECKING:
    from titanspan.foundation.application import Application

_ACTIVE_CONNECTION: ContextVar[str | None] = ContextVar(
    "titanspan_database_seeder_connection",
    default=None,
)
_SYNC_METHOD_MESSAGE = "Implement run() on this seeder."
_ASYNC_METHOD_MESSAGE = "Implement run_async() on this seeder."


class Seeder:
    """Run repeatable application data setup with explicit transactions.

    Subclasses implement either ``run`` or ``run_async``. A new seeder is
    resolved from the active application Container for every nested call.
    """

    connection: ClassVar[str | None] = None
    transactional: ClassVar[bool] = True

    def run(self) -> None:
        """Run the synchronous seeder body.

        Raises:
            NotImplementedError: If a synchronous body is not implemented.
        """
        raise NotImplementedError(_SYNC_METHOD_MESSAGE)

    async def run_async(self) -> None:
        """Run the asynchronous seeder body.

        Raises:
            NotImplementedError: If an asynchronous body is not implemented.
        """
        raise NotImplementedError(_ASYNC_METHOD_MESSAGE)

    def execute(self, connection: str | None = None) -> None:
        """Run this seeder with one thread-owned transaction when enabled.

        Args:
            connection: Optional connection override for this seeder tree.

        Notes:
            The selected connection is inherited by nested seeders unless
            they declare their own connection.
        """
        application = _application()
        service = application.container.make(DatabaseService)
        selected = self._connection(connection)
        token = _ACTIVE_CONNECTION.set(selected)
        try:
            if self.transactional:
                with service.transaction(selected):
                    self.run()
            else:
                self.run()
        finally:
            _ACTIVE_CONNECTION.reset(token)

    async def execute_async(self, connection: str | None = None) -> None:
        """Run this seeder with one task-owned transaction when enabled.

        Args:
            connection: Optional connection override for this seeder tree.

        Notes:
            Cancellation propagates after Database transaction cleanup.
        """
        application = _application()
        service = await application.container.make_async(DatabaseService)
        selected = self._connection(connection)
        token = _ACTIVE_CONNECTION.set(selected)
        try:
            if self.transactional:
                async with service.transaction_async(selected):
                    await self.run_async()
            else:
                await self.run_async()
        finally:
            _ACTIVE_CONNECTION.reset(token)

    def call(self, *seeder_types: type[Seeder]) -> None:
        """Resolve and run nested seeders inside this seeder's transaction.

        Args:
            *seeder_types: Trusted Seeder subclasses resolved by Container.
        """
        application = _application()
        for seeder_type in seeder_types:
            seeder = application.container.make(seeder_type)
            seeder.execute(
                seeder.connection or _ACTIVE_CONNECTION.get(),
            )

    async def call_async(self, *seeder_types: type[Seeder]) -> None:
        """Resolve and run nested seeders in the current task.

        Args:
            *seeder_types: Trusted Seeder subclasses resolved by Container.
        """
        application = _application()
        for seeder_type in seeder_types:
            seeder = await application.container.make_async(seeder_type)
            await seeder.execute_async(
                seeder.connection or _ACTIVE_CONNECTION.get(),
            )

    def _connection(self, requested: str | None) -> str | None:
        """Select an explicit, inherited, or class-declared connection.

        Args:
            requested: Explicit top-level or inherited connection name.

        Returns:
            The most specific configured connection name, if supplied.
        """
        return requested or self.connection or _ACTIVE_CONNECTION.get()


def _application() -> Application:
    """Return Foundation's active Application without creating a registry.

    Returns:
        The Application bound to the current command or test context.
    """
    return app()


__all__ = ["Seeder"]
