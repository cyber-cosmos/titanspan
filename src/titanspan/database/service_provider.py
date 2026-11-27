"""Register one Database manager with the application service Container.

The provider owns lazy engine construction through the canonical
ApplicationPaths and ConfigRepository contracts.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable  # noqa: TC003
from typing import TYPE_CHECKING

from titanspan.contracts.config import ConfigRepository  # noqa: TC001
from titanspan.contracts.database import DatabaseService
from titanspan.contracts.foundation import (
    ApplicationPaths,
    BootableServiceProvider,
)
from titanspan.database.manager import DatabaseManager
from titanspan.database.migration_manager import MigrationManager

if TYPE_CHECKING:
    from titanspan.contracts.container import ServiceRegistry


class DatabaseServiceProvider(BootableServiceProvider):
    """Bind one lazy manager and its canonical service interface per app.
    """  # fmt: skip

    def register(self, container: ServiceRegistry) -> None:
        """Register the manager as a Container-owned async resource.

        Args:
            container: Canonical application registry used by all providers.
        """

        async def provide_manager(
            repository: ConfigRepository,
            paths: ApplicationPaths,
        ) -> AsyncIterator[DatabaseManager]:
            """Construct and finalize the manager with its application.

            Args:
                repository: Canonical configuration service.
                paths: Canonical application root and path resolver.

            Yields:
                One manager with no opened remote or local connection.
            """
            manager = DatabaseManager.from_repository(repository, paths)
            try:
                yield manager
            finally:
                await manager.aclose()

        def provide_service(manager: DatabaseManager) -> DatabaseService:
            """Expose the same manager through its shared service contract.

            Args:
                manager: Container-owned application manager.

            Returns:
                The exact manager shared by direct injection and DB facade.
            """
            return manager

        def provide_migrations(
            service: DatabaseService,
            paths: ApplicationPaths,
        ) -> MigrationManager:
            """Bind revision files to the app root and Database service.

            Args:
                service: The canonical app-owned Database service.
                paths: The application root and path resolver.

            Returns:
                A lazy migration manager for this application.
            """
            return MigrationManager(service, paths.base_path)

        container.singleton(DatabaseManager, provide_manager)
        container.singleton(DatabaseService, provide_service)
        container.singleton(MigrationManager, provide_migrations)

    @property
    def boot(self) -> Callable[..., Awaitable[object] | None]:
        """Expose a startup check that resolves the lazy manager once.
        """  # fmt: skip
        return self._boot

    async def _boot(self, manager: DatabaseManager) -> None:
        """Construct application configuration without opening a connection.

        Args:
            manager: Database service owned until Foundation shutdown.
        """
        _ = manager


__all__ = ["DatabaseServiceProvider"]
