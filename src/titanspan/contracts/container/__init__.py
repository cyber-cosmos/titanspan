"""Define dependency-container contracts independent of implementations.

The sync-first protocol keeps ordinary construction synchronous while making
asynchronous dependency acquisition an explicit operation.
"""

from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class InstanceRegistration(Protocol):
    """Describe an externally constructed value contributed by a provider.

    Framework components can provide application-owned instances without
    importing a concrete service container or dependency engine.
    """

    @property
    def service(self) -> type[object]:
        """Return the contract key used for dependency resolution.

        Returns:
            The native service type registered by this provider.
        """
        ...

    @property
    def value(self) -> object:
        """Return the already constructed application-owned value.

        Returns:
            The instance supplied to the active application container.
        """
        ...


@runtime_checkable
class ServiceRegistry(Protocol):
    """Describe application registration operations used by providers.

    Providers depend on this narrow surface and do not construct or configure
    a dependency-engine backend directly.
    """

    def instance[ServiceT](
        self,
        service: type[ServiceT],
        value: ServiceT,
    ) -> None:
        """Register an already constructed application service.

        Args:
            service: Canonical contract or service type.
            value: The shared object returned for this key.
        """
        ...

    def bind[ServiceT](
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | Callable[..., ServiceT] | None = None,
    ) -> None:
        """Register a transient class or synchronous factory.

        Args:
            service: Canonical service contract.
            implementation: Type or factory used to construct the service.
        """
        ...

    def singleton[ServiceT](
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | Callable[..., ServiceT] | None = None,
    ) -> None:
        """Register one application-owned service instance.

        Args:
            service: Canonical service contract.
            implementation: Type or synchronous factory for the service.
        """
        ...


@runtime_checkable
class ServiceContainer(ServiceRegistry, Protocol):
    """Describe synchronous and explicit asynchronous service resolution.

    Implementations resolve synchronous graphs without an event-loop bridge,
    expose async-only graphs through ``get_async``, and own async shutdown.
    Runtime protocol checks confirm member presence only, not lifecycle or
    behavioral correctness.
    """

    def make[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Synchronously resolve a sync-safe dependency graph.

        Args:
            service: Class used as the dependency key.

        Returns:
            An instance compatible with the requested service type.
        """
        ...

    async def make_async[ServiceT](
        self,
        service: type[ServiceT],
    ) -> ServiceT:
        """Resolve a graph that may initialize asynchronous resources.

        Args:
            service: Class used as the dependency key.

        Returns:
            An instance compatible with the requested service type.
        """
        ...

    def get[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve a graph that is safe to construct synchronously.

        Args:
            service: Class used as the dependency key.

        Returns:
            An instance compatible with the requested service type.
        """
        ...

    async def get_async[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve a graph that may include asynchronous resources.

        Args:
            service: Class used as the dependency key.

        Returns:
            An instance compatible with the requested service type.
        """
        ...

    async def close(self) -> None:
        """Finalize container-owned asynchronous resources.

        Implementations propagate cleanup failures and do not claim to clean
        up after the method returns if active scopes remain open.
        """
        ...


@runtime_checkable
class AsyncServiceContainer(Protocol):
    """Describe asynchronous resolution for async-only consumers.

    This narrow protocol is useful to operations that inherently await a
    service. It does not imply that synchronous object construction must be
    asynchronous.
    """

    async def get_async[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve one service through an asynchronous execution boundary.

        Args:
            service: Class used as the dependency key.

        Returns:
            An instance compatible with the requested service type.
        """
        ...

    async def close(self) -> None:
        """Finalize resources owned by this container instance.

        Implementations propagate cleanup failures and preserve cancellation.
        """
        ...


__all__ = [
    "AsyncServiceContainer",
    "InstanceRegistration",
    "ServiceContainer",
    "ServiceRegistry",
]
