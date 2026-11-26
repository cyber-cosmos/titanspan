"""Register one configuration-driven Hashing manager per application.

The provider uses the canonical Config repository and Container registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.contracts.config import ConfigRepository  # noqa: TC001
from titanspan.contracts.hashing import Hasher
from titanspan.hashing.manager import HasherFactory, HashingManager

if TYPE_CHECKING:
    from collections.abc import Mapping

    from titanspan.contracts.container import ServiceRegistry


class HashingServiceProvider:
    """Register an application-owned hasher and manager.

    Applications include this provider in ``Application.service_providers``.
    It creates no global service registry and retains no passwords.
    """

    def __init__(
        self,
        *,
        drivers: Mapping[str, HasherFactory] | None = None,
    ) -> None:
        """Retain custom driver factories for the application manager.

        Args:
            drivers: Optional native ``Hasher`` factories selected by config.
        """
        self._drivers = dict(drivers or {})

    def register(self, container: ServiceRegistry) -> None:
        """Bind the manager and selected hasher to the shared service graph.

        Args:
            container: Application-owned service registry.
        """

        def create_manager(repository: ConfigRepository) -> HashingManager:
            """Build settings from the active application's Config service.

            Args:
                repository: Canonical Config repository.

            Returns:
                One manager isolated to this application's container.
            """
            return HashingManager.from_repository(
                repository,
                drivers=self._drivers,
            )

        def provide_hasher(manager: HashingManager) -> Hasher:
            """Expose the selected driver through its canonical contract.

            Args:
                manager: Application-owned Hashing manager.

            Returns:
                The exact hasher owned by the manager.
            """
            return manager.hasher()

        container.singleton(HashingManager, create_manager)
        container.bind(Hasher, provide_hasher)

    _drivers: dict[str, HasherFactory]


__all__ = ["HashingServiceProvider"]
