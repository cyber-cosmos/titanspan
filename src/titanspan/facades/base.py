"""Resolve facade services through the active application container.

Component facades share application-context lookup while retaining typed
resolution for the specific native contract each facade exposes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from titanspan._application_context import (
    ApplicationContextError,
    active_application_context,
)

if TYPE_CHECKING:
    from titanspan.contracts.container import ServiceContainer


class Facade[ServiceT](ABC):
    """Provide one typed service-resolution path for component facades.

    Subclasses declare a native service contract and retain explicit methods
    for IDE discoverability. The base class performs no dynamic forwarding.
    """

    service_contract: object

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
    @abstractmethod
    def resolve_from_container(cls, container: ServiceContainer) -> ServiceT:
        """Resolve this facade's contract from its active container.

        Args:
            container: Active application registry selected through the
                shared context infrastructure.

        Returns:
            The service associated with this facade's contract.
        """
        ...

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
