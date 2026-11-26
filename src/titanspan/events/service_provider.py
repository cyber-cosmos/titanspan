"""Register and boot one application-owned event dispatcher.

The provider registers one dispatcher for the application lifetime.
"""

from collections.abc import Awaitable, Callable

from titanspan.container import Container
from titanspan.contracts.config import ConfigRepository
from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.events import EventDispatcher
from titanspan.contracts.foundation import BootableServiceProvider
from titanspan.events.configuration import EventsConfiguration
from titanspan.events.discovery import discover_events
from titanspan.events.dispatcher import NativeEventDispatcher

_DISPATCHER_NOT_REGISTERED_ERROR = "The event dispatcher was not registered."


class EventServiceProvider(BootableServiceProvider):
    """Register event services and discover trusted listeners at startup.

    Startup discovery and dispatch share the canonical instance.
    """

    def __init__(
        self,
        container: Container,
        repository: ConfigRepository,
    ) -> None:
        """Retain the application registry and validated event settings.

        Args:
            container: Native application container used for listener injection.
            repository: Canonical configuration repository.
        """
        self._container = container
        self._configuration = EventsConfiguration.from_repository(repository)
        self._dispatcher: NativeEventDispatcher | None = None

    def register(self, container: ServiceRegistry) -> None:
        """Register one dispatcher under concrete and contract service keys.

        Args:
            container: Shared application-owned service registry.
        """
        dispatcher = NativeEventDispatcher(
            self._container,
            deferred_buffer_limit=self._configuration.deferred_buffer_limit,
            max_dispatch_depth=self._configuration.max_dispatch_depth,
        )
        container.instance(EventDispatcher, dispatcher)
        container.instance(NativeEventDispatcher, dispatcher)
        self._dispatcher = dispatcher

    @property
    def boot(self) -> Callable[..., Awaitable[object] | None]:
        """Return startup discovery for explicitly configured modules.

        Returns:
            A coroutine that registers discovered listeners and subscribers.
        """
        return self._boot

    async def _boot(self) -> None:
        """Import only configured modules and register their declarations.

        Raises:
            RuntimeError: If registration did not create the dispatcher.
            EventDiscoveryError: If discovery or a manifest is invalid.
        """
        dispatcher = self._dispatcher
        if dispatcher is None:
            raise RuntimeError(_DISPATCHER_NOT_REGISTERED_ERROR)
        await discover_events(
            dispatcher,
            self._configuration.discovery_modules,
            manifest_path=self._configuration.manifest_path,
        )

    _container: Container
    _configuration: EventsConfiguration
    _dispatcher: NativeEventDispatcher | None


__all__ = ["EventServiceProvider"]
