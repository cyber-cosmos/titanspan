"""Register one configuration-driven filesystem manager per application.

The provider resolves its settings from the already registered canonical
Config repository and binds concrete and contract keys to one manager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.contracts.config import ConfigRepository  # noqa: TC001
from titanspan.contracts.filesystem import StorageManager
from titanspan.contracts.foundation import ApplicationPaths  # noqa: TC001
from titanspan.filesystem.manager import (
    FilesystemDriverFactory,
    FilesystemManager,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from titanspan.contracts.container import ServiceContainer, ServiceRegistry


class FilesystemServiceProvider:
    """Register Filesystem services through Foundation's provider extension.

    Applications pass this provider through ``Application.service_providers``.
    It creates no process-global manager and owns no independent registry.
    """

    def __init__(
        self,
        *,
        drivers: Mapping[str, FilesystemDriverFactory] | None = None,
    ) -> None:
        """Retain custom fsspec drivers for each application manager.

        Args:
            drivers: Optional factories selected by configured driver names.
        """
        self._drivers = dict(drivers or {})

    def register(self, container: ServiceRegistry) -> None:
        """Register a concrete manager and its canonical storage contract.

        Args:
            container: Application-owned service registry.
        """

        def make_manager(
            repository: ConfigRepository,
            paths: ApplicationPaths,
        ) -> FilesystemManager:
            """Construct a manager from the final application settings.

            Args:
                repository: Canonical Config repository registered by
                    Foundation.
                paths: Effective root selected by the composition root.

            Returns:
                One application-owned manager instance.
            """
            return FilesystemManager.from_repository(
                repository,
                drivers=self._drivers,
                base_path=paths.base_path,
            )

        def provide_storage_manager(
            manager: FilesystemManager,
        ) -> StorageManager:
            """Expose the same concrete manager through its public contract.

            Args:
                manager: Concrete application-owned Filesystem manager.

            Returns:
                The exact manager registered under its contract.
            """
            return manager

        container.singleton(FilesystemManager, make_manager)
        container.bind(StorageManager, provide_storage_manager)

    async def shutdown(self, container: ServiceContainer) -> None:
        """Close an existing manager without initializing unused disks.

        Args:
            container: Stopped application registry available for inspection.
        """
        found, manager = container.find_resolved(FilesystemManager)
        if found and manager is not None:
            await manager.aclose()

    _drivers: dict[str, FilesystemDriverFactory]


__all__ = ["FilesystemServiceProvider"]
