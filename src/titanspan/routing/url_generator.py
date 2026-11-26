"""Generate URLs from the canonical application route catalog.

Absolute URLs use an explicit trusted origin and never infer one from Host
or forwarded headers.
"""

from __future__ import annotations

import inspect
import re
from typing import TYPE_CHECKING, TypeGuard, cast
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from titanspan.routing.exceptions import RouteUrlError
from titanspan.support.uri import Uri, UriUrlGenerator

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from titanspan.contracts.routing import (
        ControllerAction,
        RouteAction,
        RouteCatalog,
        RouteInfo,
    )

_PATH_PARAMETER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::([^{}]+))?\}")
_MISSING_PARAMETER = "Missing required route parameter."
_UNTRUSTED_ORIGIN = "Absolute route URLs require a configured trusted origin."
_LOCAL_PATH_ERROR = "URL paths must be local absolute paths."
_SIGNED_ROUTE_ERROR = (
    "Signed routes require the framework key-management component."
)
_ACTION_ROUTE_NOT_FOUND = "No route is registered for the requested action."
_AMBIGUOUS_ACTION_ROUTE = (
    "The requested action is registered at multiple route paths."
)
_INVALID_ORIGIN_ERROR = "Configured application origin is invalid."
_ORIGIN_DOMAIN_MISMATCH = (
    "Configured trusted origin does not match the route domain."
)
_ROUTE_CONSTRAINT_ERROR = (
    "A route parameter does not satisfy its registered constraint."
)
_REVERSER_ALREADY_SET = "The route path reverser is already configured."
_REVERSER_FAILURE = "The registered route could not be reversed."
_CONTROLLER_ACTION_PARTS = 2


class UrlGenerator(UriUrlGenerator):
    """Build path and named-route URLs using application-owned metadata.

    The generator does not trust request Host headers and does not sign URLs
    until the framework key-management boundary is available.
    """

    def __init__(
        self,
        routes: RouteCatalog,
        *,
        origin: str | None = None,
    ) -> None:
        """Retain the route catalog and validate an optional origin.

        Args:
            routes: Canonical route catalog used by matching and inspection.
            origin: Trusted HTTP(S) origin configured by the application.

        Raises:
            RouteUrlError: If origin contains credentials or non-origin data.
        """
        self._routes = routes
        self._origin = _validate_origin(origin)
        self._path_reverser: Callable[[str, Mapping[str, str]], str] | None = (
            None
        )

    def configure_path_reverser(
        self,
        reverser: Callable[[str, Mapping[str, str]], str],
    ) -> None:
        """Install the ASGI backend's supported named-path reversal hook.

        The canonical route catalog remains the authority for route identity;
        this hook delegates parameter substitution and encoding after route
        compilation.

        Args:
            reverser: Backend callback accepting a native route name and path
                values and returning a local encoded path.

        Raises:
            RuntimeError: If a route reverser was already installed.
        """
        if self._path_reverser is not None:
            raise RuntimeError(_REVERSER_ALREADY_SET)
        self._path_reverser = reverser

    def to(self, path: str) -> str:
        """Resolve an application path against the trusted configured origin.

        Args:
            path: Absolute application path beginning with one slash.

        Returns:
            An absolute URL using the configured origin.

        Raises:
            RouteUrlError: If the path is not local or no origin is configured.
        """
        if not path.startswith("/") or path.startswith("//"):
            raise RouteUrlError(_LOCAL_PATH_ERROR)
        return self._absolute(path)

    def route(
        self,
        name: str,
        parameters: Mapping[str, object],
        absolute: bool,
    ) -> str:
        """Build a named route URL with encoded path and query values.

        Args:
            name: Registered route name.
            parameters: Values used for path placeholders or query pairs.
            absolute: Whether to prefix the configured trusted origin.

        Returns:
            Relative path or absolute URL for the named route.

        Raises:
            RouteUrlError: If a required parameter is missing or unsafe.
            RouteNotFoundError: If the route name is unknown.
        """
        route = self._routes.named(name)
        return self._generate(route, parameters, absolute)

    def signed_route(
        self,
        name: str,
        parameters: Mapping[str, object],
        expiration: object,
        absolute: bool,
    ) -> str:
        """Reject signing until a managed application key contract exists.

        Args:
            name: Registered route name.
            parameters: Path and query values for the route.
            expiration: Expiration value that would be signed.
            absolute: Whether the generated URL would be absolute.

        Raises:
            RouteUrlError: Signed URLs require a key-management component.
        """
        _ = name, parameters, expiration, absolute
        raise RouteUrlError(_SIGNED_ROUTE_ERROR)

    def action(
        self,
        action: str | Sequence[str],
        parameters: Mapping[str, object],
        absolute: bool,
    ) -> str:
        """Reject action-based lookup in favor of stable route names.

        Args:
            action: Controller action identifier from a caller.
            parameters: Candidate action parameters.
            absolute: Whether the requested result would be absolute.

        Raises:
            RouteUrlError: Action lookup is not an implemented route identity.
        """
        identity = _requested_action(action)
        matches = [
            route
            for route in self._routes.all()
            if _matches_action(route, identity)
        ]
        if not matches:
            raise RouteUrlError(_ACTION_ROUTE_NOT_FOUND)
        distinct_paths = {route.path for route in matches}
        if len(distinct_paths) > 1:
            raise RouteUrlError(_AMBIGUOUS_ACTION_ROUTE)
        return self._generate(matches[0], parameters, absolute)

    def _generate(
        self,
        route: RouteInfo,
        parameters: Mapping[str, object],
        absolute: bool,
    ) -> str:
        """Substitute route values and compose remaining query data.

        Args:
            route: Canonical route metadata selected by name or action.
            parameters: Caller path and query values.
            absolute: Whether to prefix the configured trusted origin.

        Returns:
            Encoded local path or trusted-origin absolute URL.

        Raises:
            RouteUrlError: If a placeholder is missing or reversal fails.
        """
        remaining = dict(parameters)
        path_values: dict[str, str] = {}
        path = route.path
        supports_backend_reverse = True
        for match in _PATH_PARAMETER.finditer(route.path):
            key, converter = match.groups()
            value = remaining.pop(key, route.default_values.get(key))
            if value is None:
                message = f"{_MISSING_PARAMETER} {key!r}."
                raise RouteUrlError(message)
            constraint = route.constraints.get(key)
            if (
                constraint is not None
                and re.fullmatch(
                    constraint,
                    str(value),
                )
                is None
            ):
                raise RouteUrlError(_ROUTE_CONSTRAINT_ERROR)
            safe = "/" if converter == "path" else ""
            if converter is not None:
                supports_backend_reverse = False
            path_values[key] = quote(str(value), safe=safe)
            path = path.replace(
                match.group(0),
                path_values[key],
                1,
            )

        if (
            self._path_reverser is not None
            and route.route_name is not None
            and supports_backend_reverse
        ):
            try:
                path = self._path_reverser(route.route_name, path_values)
            except (KeyError, ValueError) as error:
                raise RouteUrlError(_REVERSER_FAILURE) from error

        if remaining:
            path = f"{path}?{_encode_query(remaining)}"
        if not absolute:
            return path
        return self._absolute(path, route_domain=route.domain_name)

    def _absolute(
        self,
        path: str,
        *,
        route_domain: str | None = None,
    ) -> str:
        """Join a safe application path to the trusted origin.

        Args:
            path: Application path and optional query string.
            route_domain: Optional exact host required by the route.

        Returns:
            Absolute URL using the configured origin.

        Raises:
            RouteUrlError: If origin is absent or does not match the route.
        """
        if self._origin is None:
            raise RouteUrlError(_UNTRUSTED_ORIGIN)
        origin_host = urlsplit(self._origin).hostname
        if (
            route_domain is not None
            and origin_host is not None
            and origin_host.lower().rstrip(".") != route_domain
        ):
            raise RouteUrlError(_ORIGIN_DOMAIN_MISMATCH)
        origin = Uri(self._origin).get_uri()
        target = Uri(path).get_uri()
        return urlunsplit(
            (
                origin.scheme,
                origin.netloc,
                target.path,
                target.query,
                target.fragment,
            )
        )


def _validate_origin(origin: str | None) -> str | None:
    """Validate origin-only HTTP(S) configuration.

    Args:
        origin: Optional configured application origin.

    Returns:
        A normalized scheme and authority, or None.

    Raises:
        RouteUrlError: If the origin includes credentials or path data.
    """
    if origin is None:
        return None
    parsed = urlsplit(origin)
    try:
        port = parsed.port
    except ValueError as error:
        raise RouteUrlError(_INVALID_ORIGIN_ERROR) from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise RouteUrlError(_INVALID_ORIGIN_ERROR)
    _ = port
    return f"{parsed.scheme}://{parsed.netloc}"


def _requested_action(action: str | Sequence[str]) -> str:
    """Convert an action selector into a stable dotted identifier.

    Args:
        action: Dotted identifier or ordered identifier components.

    Returns:
        Normalized dotted action identifier.

    Raises:
        RouteUrlError: If the action selector is empty or malformed.
    """
    if isinstance(action, str):
        identity = action.strip(".")
    else:
        parts = tuple(action)
        if not parts or any(not part for part in parts):
            identity = ""
        else:
            identity = ".".join(parts)
    if not identity:
        raise RouteUrlError(_ACTION_ROUTE_NOT_FOUND)
    return identity


def _matches_action(route: RouteInfo, requested: str) -> bool:
    """Compare an action selector to route callable metadata.

    Args:
        route: Candidate route metadata from the canonical catalog.
        requested: Dotted action identifier selected by the caller.

    Returns:
        Whether the route action has the requested qualified identity.
    """
    action = route.action
    if action is None:
        return False
    identifiers = _action_identifiers(action)
    return any(
        requested == identifier or identifier.endswith(f".{requested}")
        for identifier in identifiers
    )


def _action_identifiers(action: RouteAction) -> frozenset[str]:
    """Describe a route callable without constructing an endpoint service.

    Args:
        action: Callable or controller declaration retained by the route.

    Returns:
        Qualified and short identities suitable for action lookup.
    """
    if _is_controller_action(action):
        controller, method = action
        qualified = _type_identity(controller)
        return frozenset(
            {
                f"{qualified}.{method}",
                f"{controller.__qualname__}.{method}",
                f"{controller.__name__}.{method}",
            }
        )
    if isinstance(action, type):
        qualified = _type_identity(action)
        return frozenset(
            {
                qualified,
                f"{qualified}.__call__",
                f"{action.__qualname__}.__call__",
            }
        )
    if not callable(action):
        return frozenset()
    target = action.__func__ if inspect.ismethod(action) else action
    module = getattr(target, "__module__", None)
    qualified_name = getattr(target, "__qualname__", None)
    if not isinstance(module, str) or not isinstance(qualified_name, str):
        return frozenset()
    return frozenset({f"{module}.{qualified_name}", qualified_name})


def _is_controller_action(value: object) -> TypeGuard[ControllerAction]:
    """Validate controller-action tuple contents before unpacking.

    Args:
        value: Route metadata value to inspect.

    Returns:
        Whether it is exactly a controller type and public method name.
    """
    if not isinstance(value, tuple):
        return False
    parts = cast("tuple[object, ...]", value)
    return (
        len(parts) == _CONTROLLER_ACTION_PARTS
        and isinstance(parts[0], type)
        and isinstance(parts[1], str)
    )


def _type_identity(value: type[object]) -> str:
    """Return the module-qualified identity of one controller type.

    Args:
        value: Controller or invokable action type.

    Returns:
        Stable dotted type identity for route lookup.
    """
    return f"{value.__module__}.{value.__qualname__}"


def _encode_query(parameters: Mapping[str, object]) -> str:
    """Encode leftover values without changing repeated-value semantics.

    Args:
        parameters: Query names and scalar or repeated values.

    Returns:
        RFC 3986 query text without a leading question mark.
    """
    pairs: list[tuple[str, str]] = []
    for key, value in parameters.items():
        values = (
            cast("Sequence[object]", value)
            if isinstance(value, (list, tuple))
            else (value,)
        )
        pairs.extend((key, str(item)) for item in values)
    return urlencode(pairs)


__all__ = ["UrlGenerator"]
