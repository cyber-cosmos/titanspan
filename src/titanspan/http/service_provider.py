"""Register HTTP clients and response services in the native container.

The provider owns HTTP registration and shutdown.
"""

from collections.abc import AsyncIterator, Awaitable, Callable

from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.foundation import BootableServiceProvider
from titanspan.contracts.http import HttpClient, ResponseFactory
from titanspan.http._backends.client import HttpxClientAdapter
from titanspan.http.configuration import HttpConfiguration
from titanspan.http.response_factory import NativeResponseFactory


class HttpServiceProvider(BootableServiceProvider):
    """Register a shared client pool and a stateless response factory.

    Application startup eagerly resolves the HTTP client so synchronous
    facades can access its sync pool safely after startup. The container owns
    asynchronous pool finalization at application shutdown.
    """

    def __init__(self, configuration: HttpConfiguration) -> None:
        """Retain HTTP configuration validated by application bootstrap.

        Args:
            configuration: Immutable settings shared by request handling and
                outgoing client construction.
        """
        self._configuration = configuration

    def register(self, container: ServiceRegistry) -> None:
        """Register HTTP services against the canonical application graph.

        Args:
            container: Shared Titanspan service registry.
        """

        async def create_client(
            configuration: HttpConfiguration,
        ) -> AsyncIterator[HttpClient]:
            """Create and yield the application-owned pooled client service.

            Args:
                configuration: Validated application HTTP configuration.

            Yields:
                A client with isolated sync and async connection pools.

            Side Effects:
                Opens transport resources that are closed at container
                shutdown, including startup rollback paths.
            """
            client = HttpxClientAdapter(configuration.client)
            try:
                yield client
            finally:
                await client.aclose()

        container.instance(HttpConfiguration, self._configuration)
        container.singleton(HttpClient, create_client)
        container.singleton(ResponseFactory, NativeResponseFactory)

    @property
    def boot(self) -> Callable[..., Awaitable[object] | None]:
        """Expose a startup callback resolved by the application container.

        Returns:
            The asynchronous pool initialization callback.
        """
        return self._boot

    async def _boot(self, client: HttpClient) -> None:
        """Initialize the pooled service before application work begins.

        Args:
            client: Resolved service whose async factory and resource graph
                must be ready before synchronous facade calls are allowed.
        """
        _ = client

    _configuration: HttpConfiguration


__all__ = ["HttpServiceProvider"]
