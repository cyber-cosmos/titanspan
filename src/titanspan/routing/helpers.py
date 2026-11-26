"""Resolve routing services through the active application context.

Helpers never create a process-global router or response service.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

from titanspan._application_context import (
    active_application_context,
)
from titanspan.container import BindingResolutionError
from titanspan.contracts.http import HttpResponse, ResponseFactory
from titanspan.contracts.routing import UriUrlGenerator
from titanspan.http.request import Request
from titanspan.routing.exceptions import RoutingContextError
from titanspan.routing.route import RouteDefinition

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

_ROUTE_ATTRIBUTE = "titanspan.route"
_ROUTE_CONTEXT_ERROR = (
    "Route inspection requires an active matched HTTP request."
)
_URL_CONTEXT_ERROR = "Route URL helpers require an active application."
_REDIRECT_CONTEXT_ERROR = (
    "Redirect helpers require an active application context."
)
_CURRENT_ROUTE: ContextVar[RouteDefinition | None] = ContextVar(
    "titanspan_current_route",
    default=None,
)


@contextmanager
def bind_current_route(
    route_definition: RouteDefinition,
) -> Generator[None, None, None]:
    """Bind route metadata for one handler and middleware call chain.

    Args:
        route_definition: Route selected by the native ASGI matcher.

    Yields:
        Control while current-route helpers can inspect the matched route.
    """
    token: Token[RouteDefinition | None] = _CURRENT_ROUTE.set(route_definition)
    try:
        yield
    finally:
        _CURRENT_ROUTE.reset(token)


class Redirector:
    """Build safe redirects using the application response and route services.

    External locations remain rejected by the native ResponseFactory.
    """

    def __init__(
        self,
        factory: ResponseFactory,
        generator: UriUrlGenerator,
    ) -> None:
        """Retain application-owned response and URL construction services.

        Args:
            factory: Canonical response factory for this application.
            generator: Route generator sharing the canonical route catalog.
        """
        self._factory = factory
        self._generator = generator

    def to(self, path: str, *, status: int = 303) -> HttpResponse:
        """Redirect to a validated local path.

        Args:
            path: Relative application location.
            status: Redirect status accepted by the response factory.

        Returns:
            Native response with a validated Location header.
        """
        return self._factory.redirect(path, status=status)

    def route(
        self,
        name: str,
        parameters: Mapping[str, object] | None = None,
        *,
        status: int = 303,
    ) -> HttpResponse:
        """Redirect to a named route in the active route catalog.

        Args:
            name: Registered route name.
            parameters: Path and query values for URL generation.
            status: Redirect status accepted by the response factory.

        Returns:
            Native response with a relative Location header.
        """
        location = self._generator.route(
            name,
            {} if parameters is None else parameters,
            False,
        )
        return self._factory.redirect(location, status=status)

    _factory: ResponseFactory
    _generator: UriUrlGenerator


def route(
    name: str,
    parameters: Mapping[str, object] | None = None,
    *,
    absolute: bool = False,
) -> str:
    """Generate a URL from the active application's named route.

    Args:
        name: Registered route name.
        parameters: Values substituted into path and query components.
        absolute: Include the configured trusted application origin.

    Returns:
        The generated route URL.

    Raises:
        RoutingContextError: If no application is active.
        RouteUrlError: If URL parameters or trusted origin are invalid.
    """
    return _url_generator().route(
        name,
        {} if parameters is None else parameters,
        absolute,
    )


def url(path: str, *, absolute: bool = False) -> str:
    """Generate a local or explicitly absolute application URL.

    Args:
        path: Absolute local path, including an optional query string.
        absolute: Prefix the configured trusted application origin.

    Returns:
        The local path or trusted-origin URL.

    Raises:
        RoutingContextError: If absolute generation lacks app context.
        RouteUrlError: If the path is unsafe or origin is missing.
    """
    return _url_generator().url(path, absolute)


def redirect() -> Redirector:
    """Return a redirect builder backed by active application services.

    Returns:
        Redirector using the same response factory and route definitions as
        endpoint dispatch.

    Raises:
        RoutingContextError: If the application context is not active.
    """
    active = active_application_context()
    if active is None:
        raise RoutingContextError(_REDIRECT_CONTEXT_ERROR)
    try:
        return Redirector(
            active.container.make(ResponseFactory),
            active.container.make(UriUrlGenerator),
        )
    except BindingResolutionError as error:
        raise RoutingContextError(_REDIRECT_CONTEXT_ERROR) from error


def current_route() -> RouteDefinition | None:
    """Return the route matched by the active native HTTP request.

    Returns:
        Current route definition, or None before a route is matched.

    Raises:
        RoutingContextError: If there is no active application/request.
    """
    current = _CURRENT_ROUTE.get()
    if current is not None:
        return current
    active = active_application_context()
    if active is None:
        raise RoutingContextError(_ROUTE_CONTEXT_ERROR)
    try:
        request = active.container.make(Request)
        route_value = request.attribute(_ROUTE_ATTRIBUTE)
    except BindingResolutionError:
        raise RoutingContextError(_ROUTE_CONTEXT_ERROR) from None
    return route_value if isinstance(route_value, RouteDefinition) else None


def current_route_name() -> str | None:
    """Return the name of the matched route in the active HTTP request.

    Returns:
        The registered name, or None when the current route is unnamed.

    Raises:
        RoutingContextError: If there is no active application/request.
    """
    current = current_route()
    return None if current is None else current.route_name


def _url_generator() -> UriUrlGenerator:
    """Resolve the native URL generator from active application services.

    Returns:
        The generator sharing the Router route catalog.

    Raises:
        RoutingContextError: If application routing is unavailable.
    """
    active = active_application_context()
    if active is None:
        raise RoutingContextError(_URL_CONTEXT_ERROR)
    try:
        return active.container.make(UriUrlGenerator)
    except BindingResolutionError as error:
        raise RoutingContextError(_URL_CONTEXT_ERROR) from error


__all__ = [
    "Redirector",
    "current_route",
    "current_route_name",
    "redirect",
    "route",
    "url",
]
