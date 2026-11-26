"""Define dependency-safe routing value types.

These aliases describe application handlers without exposing an ASGI backend.
"""

from collections.abc import Awaitable, Callable

type RouteEndpoint = Callable[..., object] | Callable[..., Awaitable[object]]
type ControllerAction = tuple[type[object], str]
type RouteAction = RouteEndpoint | type[object] | ControllerAction

__all__ = ["ControllerAction", "RouteAction", "RouteEndpoint"]
