"""Define native registration and startup hooks for application components.

Providers contribute bindings and may opt into injected startup hooks after
the complete application service registry has been assembled.
"""

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from titanspan.contracts.container import ServiceContainer, ServiceRegistry


@runtime_checkable
class ServiceProvider(Protocol):
    """Register component services with an application-owned registry.

    Providers declare services during composition. They must not construct a
    competing registry or mutate bindings after the application graph starts
    resolving services.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Contribute native service bindings to the application.

        Args:
            container: Shared application registry used by all providers.

        Raises:
            Exception: A native registration error that prevents startup.
        """
        ...


@runtime_checkable
class BootableServiceProvider(ServiceProvider, Protocol):
    """Describe the optional application-startup phase for a provider.

    Providers declare bindings synchronously through ``ServiceProvider``.
    The application invokes the callable after all registrations, injects its
    annotated dependencies, and awaits asynchronous startup methods. Runtime
    protocol checks confirm member presence but do not validate the signature.
    """

    @property
    def boot(self) -> Callable[..., Awaitable[object] | None]:
        """Return the provider's optional startup callback.

        Returns:
            A callback that may be synchronous or awaitable and whose
            annotated dependencies are resolved by the application.
        """
        ...


@runtime_checkable
class ShutdownableServiceProvider(ServiceProvider, Protocol):
    """Describe a provider that finalizes its owned services.

    Application calls this hook before closing the service Container.
    Providers inspect already-resolved services and must not resolve new ones.
    """

    def shutdown(
        self,
        container: ServiceContainer,
    ) -> object | Awaitable[object]:
        """Return or perform cleanup using the application-owned Container.

        Args:
            container: Active registry whose owned services are closing.

        Returns:
            None or an awaitable completed before Container shutdown.
        """
        ...


__all__ = [
    "BootableServiceProvider",
    "ServiceProvider",
    "ShutdownableServiceProvider",
]
