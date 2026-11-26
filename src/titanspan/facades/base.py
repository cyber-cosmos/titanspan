"""Resolve facade services through the active application container.

Component facades share application-context lookup while retaining typed
resolution for the specific native contract each facade exposes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from titanspan._application_context import (
    ApplicationContextError,
    active_application_context,
)

if TYPE_CHECKING:
    from titanspan.contracts.container import ServiceContainer, ServiceOverride


class Facade[ServiceT]:
    """Provide one typed service-resolution path for component facades.

    Subclasses declare a native service contract and retain explicit methods
    for IDE discoverability. The base class performs no dynamic forwarding.
    """

    service_contract: type[object]

    @classmethod
    def resolve_service(cls) -> ServiceT:
        """Resolve this facade's declared contract from the active app.

        Returns:
            The service instance registered under ``service_contract``.

        Raises:
            ApplicationContextError: If no application is active.
        """
        return cls.resolve_from_container(cls.active_container())

    @classmethod
    def resolve_from_container(cls, container: ServiceContainer) -> ServiceT:
        """Resolve the declared contract from the supplied container.

        Args:
            container: Active application registry selected through the
                shared context infrastructure.

        Returns:
            The service registered under this facade's contract.
        """
        # Protocol classes are valid service keys, but ``type[ServiceT]``
        # excludes protocol definitions because it denotes implementations.
        return cast("ServiceT", container.make(cls.service_contract))

    @classmethod
    def use(cls, service: ServiceT) -> ServiceOverride:
        """Replace this service inside the active application context.

        The replacement uses the Container's temporary override lifecycle.
        It remains isolated to the current execution context and inherits the
        Container's restrictions for active scopes and shared dependencies.

        Args:
            service: Replacement instance satisfying the facade contract.

        Returns:
            A sync and async context manager that restores the prior graph.

        Raises:
            ApplicationContextError: If no application context is active.
        """
        container = cls.active_container()
        bindings: dict[type[object], object] = {
            cls.service_contract: service,
        }
        return container.override(bindings)

    @classmethod
    def active_container(cls) -> ServiceContainer:
        """Return the container in the active application context.

        Returns:
            The canonical registry for the current application or scope.

        Raises:
            ApplicationContextError: If no active app context is bound.
        """
        active = active_application_context()
        if active is None:
            message = "Bind an application context before using this facade."
            raise ApplicationContextError(message)
        return active.container


__all__ = ["Facade"]
