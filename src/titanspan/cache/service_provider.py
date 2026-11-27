"""Register application-owned Cache services with the native Container.
"""  # fmt: skip

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable  # noqa: TC003
from typing import TYPE_CHECKING

from titanspan.cache.manager import CacheManager
from titanspan.contracts.cache import CacheRepository
from titanspan.contracts.config import ConfigRepository  # noqa: TC001
from titanspan.contracts.events import EventDispatcher  # noqa: TC001
from titanspan.contracts.foundation import BootableServiceProvider
from titanspan.contracts.logging import LogWriter  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Mapping

    from titanspan.cache.manager import CacheDriverFactory
    from titanspan.contracts.container import ServiceRegistry


class CacheServiceProvider(BootableServiceProvider):
    """Register one lazily initialized Cache manager per application.
    """  # fmt: skip

    def __init__(
        self,
        *,
        drivers: Mapping[str, CacheDriverFactory] | None = None,
    ) -> None:
        """Retain trusted custom backend factories for the application.

        Args:
            drivers: Custom cache drivers selected by configured store names.
        """
        self._drivers = dict(drivers or {})

    def register(self, container: ServiceRegistry) -> None:
        """Bind CacheManager and CacheRepository through the shared graph.

        Args:
            container: Native registry used by the application and providers.
        """

        async def provide_manager(
            repository: ConfigRepository,
            dispatcher: EventDispatcher,
            logger: LogWriter,
        ) -> AsyncIterator[CacheManager]:
            """Own manager shutdown through the Container resource stack.

            Args:
                repository: Canonical application configuration contract.
                dispatcher: Canonical application event dispatcher.
                logger: Canonical application logger for diagnostics.

            Yields:
                One application-specific manager with unopened backends.
            """
            manager = CacheManager.from_repository(
                repository,
                drivers=self._drivers,
                events=dispatcher,
                logger=logger,
            )
            try:
                yield manager
            finally:
                await manager.aclose()

        def provide_repository(manager: CacheManager) -> CacheRepository:
            """Expose the manager's default repository under its contract.

            Args:
                manager: Application-owned concrete manager.

            Returns:
                Stable repository proxy shared by DI and facade consumers.
            """
            return manager.store()

        container.singleton(CacheManager, provide_manager)
        container.singleton(CacheRepository, provide_repository)

    @property
    def boot(self) -> Callable[..., Awaitable[object] | None]:
        """Expose startup preparation for synchronous facade operations.
        """  # fmt: skip
        return self._boot

    async def _boot(self, manager: CacheManager) -> None:
        """Resolve the application manager without opening its lazy stores.

        Args:
            manager: Resource owned by the Container until application close.
        """
        _ = manager

    _drivers: dict[str, CacheDriverFactory]


__all__ = ["CacheServiceProvider"]
