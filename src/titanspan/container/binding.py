"""Describe native service bindings and their cache lifetimes.

These immutable definitions are shared by registration and graph discovery.
"""

from dataclasses import dataclass
from enum import Enum

from titanspan.contracts.container.factory import ServiceFactory
from titanspan.contracts.container.scope import Scope


class Lifetime(Enum):
    """Select whether a binding is cached and where its cache belongs.

    Transient bindings create a new value for each resolution. Singleton
    bindings are owned by the application container. Scoped bindings are
    cached in the selected active execution scope.
    """

    TRANSIENT = "transient"
    SINGLETON = "singleton"
    SCOPED = "scoped"


@dataclass(frozen=True, slots=True)
class BindingDeclaration:
    """Declare a class-level cache policy for active container discovery.

    Attributes:
        lifetime: Cache behavior applied when the class is auto-discovered.
        scope: Lifecycle scope that owns a cached instance.
    """

    lifetime: Lifetime
    scope: Scope


@dataclass(frozen=True, slots=True)
class Binding[ServiceT]:
    """Record a service key, factory, cache policy, and lifecycle scope.

    Attributes:
        service: Type used to request this service.
        implementation: Class or typed factory, if the binding is constructed.
        lifetime: Cache behavior selected for the binding.
        scope: Native lifecycle scope owning a scoped cache.
        instance: Externally supplied instance, if this is an instance binding.
    """

    service: type[ServiceT]
    implementation: type[ServiceT] | ServiceFactory[ServiceT] | None
    lifetime: Lifetime
    scope: Scope
    instance: ServiceT | None = None
    instance_binding: bool = False

    @property
    def is_instance(self) -> bool:
        """Return whether registration uses an externally supplied instance.

        Returns:
            The explicit registration-kind flag.
        """
        return self.instance_binding


__all__ = [
    "Binding",
    "BindingDeclaration",
    "Lifetime",
    "ServiceFactory",
]
