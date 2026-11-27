"""Describe read-only route information shared by routing services.

The contract deliberately omits matcher and ASGI implementation details.
"""

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from titanspan.contracts.http import MiddlewareItem
from titanspan.contracts.routing.types import RouteAction


@runtime_checkable
class RouteInfo(Protocol):
    """Expose route metadata without granting registration mutation.

    Route inspection and URL generation use this structural boundary.
    """

    @property
    def path(self) -> str:
        """Return the path template used for route matching.

        This value is shared by dispatch and URL generation.
        """
        ...

    @property
    def methods(self) -> tuple[str, ...]:
        """Return the ordered HTTP methods accepted by this route.

        The tuple is stable after route registration is frozen.
        """
        ...

    @property
    def protocol(self) -> str:
        """Return whether this entry handles HTTP or WebSocket traffic.

        The native route catalog stores both protocols in declaration order.
        """
        ...

    @property
    def route_name(self) -> str | None:
        """Return the unique route name when one was assigned.

        Unnamed routes remain available through route enumeration.
        """
        ...

    @property
    def default_values(self) -> Mapping[str, object]:
        """Return registration-time default parameter values.

        The mapping is read-only to catalog consumers.
        """
        ...

    @property
    def constraints(self) -> Mapping[str, str]:
        """Return parameter patterns that constrain matched path values.

        URL generation uses these patterns to reject invalid substitutions.
        """
        ...

    @property
    def middleware_types(self) -> tuple[MiddlewareItem, ...]:
        """Return route middleware declarations in registration order.

        Alias names remain unresolved until the Router compiles the route.
        """
        ...

    @property
    def domain_name(self) -> str | None:
        """Return the exact host constraint, when the route declares one.

        Absolute URL generation must verify its configured origin against this
        host. Relative URL generation does not require an origin.
        """
        ...

    @property
    def action(self) -> RouteAction | None:
        """Return the registered callable identity without invoking it.

        URL generation may compare controller actions without constructing a
        controller or resolving any application services.
        """
        ...


@runtime_checkable
class RouteCatalog(Protocol):
    """Expose stable route lookup for generation and inspection services.

    Implementations return snapshots and reject reads of missing names with
    a native routing exception.
    """

    def all(self) -> tuple[RouteInfo, ...]:
        """Return a read-only snapshot in deterministic registration order.

        Callers cannot mutate the Router through this view.
        """
        ...

    def named(self, name: str) -> RouteInfo:
        """Return a route by its unique name.

        Missing names use the native route lookup error.
        """
        ...

    def has(self, name: str) -> bool:
        """Report whether a named route has been registered.

        This inspection does not construct an endpoint or service.
        """
        ...


__all__ = ["RouteCatalog", "RouteInfo"]
