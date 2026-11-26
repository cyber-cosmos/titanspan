"""Define dependency-container contracts independent of implementations.

The sync-first protocol keeps ordinary construction synchronous while making
asynchronous dependency acquisition an explicit operation.
"""

from collections.abc import Awaitable, Callable, Mapping
from types import TracebackType
from typing import Literal, Protocol, runtime_checkable

from titanspan.contracts.container.factory import (
    ServiceExtension,
    ServiceFactory,
)
from titanspan.contracts.container.scope import Scope


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
        implementation: type[ServiceT] | ServiceFactory[ServiceT] | None = None,
    ) -> None:
        """Register transient construction or a managed resource factory.

        Args:
            service: Canonical service contract.
            implementation: Type or sync/async factory for the service.
        """
        ...

    def singleton[ServiceT](
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | ServiceFactory[ServiceT] | None = None,
    ) -> None:
        """Register one application-owned service instance.

        Args:
            service: Canonical service contract.
            implementation: Type or sync/async factory for the service.
        """
        ...

    def scoped[ServiceT](
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | ServiceFactory[ServiceT] | None = None,
        *,
        scope: Scope = Scope.REQUEST,
    ) -> None:
        """Register a service cached for one selected execution lifecycle.

        Args:
            service: Canonical service contract or concrete service type.
            implementation: Class or sync/async resource factory.
            scope: Execution lifetime that owns the resulting instance.
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

    def call[ReturnT](
        self,
        callback: Callable[..., ReturnT],
        parameters: Mapping[str, object] | None = None,
    ) -> ReturnT:
        """Invoke a synchronous callable with container-resolved arguments.

        Args:
            callback: Synchronous endpoint, provider, or service method.
            parameters: Explicit values keyed by callable parameter name.

        Returns:
            The callback result.
        """
        ...

    async def call_async[ReturnT](
        self,
        callback: (Callable[..., ReturnT] | Callable[..., Awaitable[ReturnT]]),
        parameters: Mapping[str, object] | None = None,
    ) -> ReturnT:
        """Invoke sync or async callables through explicit async resolution.

        Args:
            callback: Callable whose annotated dependencies are resolved.
            parameters: Explicit values keyed by callable parameter name.

        Returns:
            The callback result, awaiting it when necessary.
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


class ServiceOverride(Protocol):
    """Describe a temporary sync or async service replacement context.

    Implementations restore the active container after either context form
    exits and finalize resources using the matching lifecycle mode.
    """

    def __enter__(self) -> ServiceContainer:
        """Activate a sync-safe replacement graph.

        Returns:
            The active temporary service registry.
        """
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        """Finalize sync resources and restore the previous graph.

        Args:
            exc_type: Exception type leaving the context, if any.
            exc_value: Exception instance leaving the context, if any.
            traceback: Traceback associated with the context exception.

        Returns:
            ``False`` so application exceptions propagate unchanged.
        """
        ...

    async def __aenter__(self) -> ServiceContainer:
        """Activate a graph that may initialize asynchronous resources.

        Returns:
            The active temporary service registry.
        """
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        """Await resource finalization and restore the prior graph.

        Args:
            exc_type: Exception type leaving the context, if any.
            exc_value: Exception instance leaving the context, if any.
            traceback: Traceback associated with the context exception.

        Returns:
            ``False`` so application exceptions propagate unchanged.
        """
        ...


__all__ = [
    "AsyncServiceContainer",
    "InstanceRegistration",
    "Scope",
    "ServiceContainer",
    "ServiceExtension",
    "ServiceFactory",
    "ServiceOverride",
    "ServiceRegistry",
]
