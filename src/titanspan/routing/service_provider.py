"""Register application-owned routing services in the native container.

The provider shares route definitions with URL generation and route discovery.
"""

from collections.abc import Awaitable, Callable

from titanspan.contracts.config import ConfigRepository
from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.foundation import BootableServiceProvider
from titanspan.contracts.routing import RouteCatalog, UriUrlGenerator
from titanspan.routing.discovery import RouteDiscovery
from titanspan.routing.router import Router
from titanspan.routing.url_generator import UrlGenerator
_INVALID_ORIGIN_TYPE_ERROR = "routing.origin must be text when configured."


class RoutingServiceProvider(BootableServiceProvider):
    """Register one Router and URL generator for an application.

    Route metadata is created once and shared by endpoint dispatch, helpers,
    facades, inspection, and OpenAPI compilation.
    """

    def __init__(self, configuration: ConfigRepository) -> None:
        """Create routing services from trusted application configuration.

        Args:
            configuration: Canonical configuration repository for this app.

        Raises:
            TypeError: If a configured origin is not text or None.
        """
        origin = configuration.get(
            "routing.origin",
            configuration.get("app.url"),
        )
        if origin is not None and not isinstance(origin, str):
            raise TypeError(_INVALID_ORIGIN_TYPE_ERROR)
        self._router = Router()
        self._discovery = RouteDiscovery.from_configuration(configuration)
        self._url_generator = UrlGenerator(
            self._router.routes,
            origin=origin,
        )

    @property
    def router(self) -> Router:
        """Return the application-owned route registrar.

        Returns:
            The exact Router instance registered into the service container.
        """
        return self._router

    @property
    def url_generator(self) -> UrlGenerator:
        """Return the URL generator sharing this Router's route catalog.

        Returns:
            The application-owned native URL generator.
        """
        return self._url_generator

    def register(self, container: ServiceRegistry) -> None:
        """Contribute routing services to the canonical application registry.

        Args:
            container: Service registry shared by all application providers.
        """
        container.instance(Router, self._router)
        container.instance(RouteCatalog, self._router.routes)
        container.instance(UrlGenerator, self._url_generator)
        container.instance(UriUrlGenerator, self._url_generator)

    @property
    def boot(self) -> Callable[..., Awaitable[object] | None]:
        """Return route discovery for the application startup phase.

        Returns:
            An asynchronous callback that registers configured route modules.
        """
        return self._boot

    async def _boot(self) -> None:
        """Discover routes before Foundation freezes the canonical catalog.

        Raises:
            RouteDiscoveryError: If a trusted module cannot register routes.
            DuplicateRouteError: If discovered routes conflict.
        """
        await self._discovery.register(self._router)

    _router: Router
    _url_generator: UrlGenerator
    _discovery: RouteDiscovery


__all__ = ["RoutingServiceProvider"]
