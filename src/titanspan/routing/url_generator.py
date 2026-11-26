"""Generate URLs from the canonical application route catalog.

Absolute URLs use an explicit trusted origin and never infer one from Host
or forwarded headers.
"""

from __future__ import annotations

import inspect
import math
import re
from typing import TYPE_CHECKING, SupportsFloat, TypeGuard, cast
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import UUID

from titanspan.contracts.routing import UriUrlGenerator
from titanspan.routing.exceptions import RouteUrlError
from titanspan.support.arr import Arr
from titanspan.support.uri import Uri

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
_ROUTE_CONVERTER_ERROR = (
    "A route parameter does not satisfy its registered converter."
)
_UNSUPPORTED_ROUTE_CONVERTER_ERROR = (
    "The route uses an unsupported path converter."
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
        """Build a URL for one unambiguous registered callable action.

        Args:
            action: Dotted or ordered callable identity.
            parameters: Values used for path and query parameters.
            absolute: Whether to include the configured origin.

        Raises:
            RouteUrlError: If no unique registered action matches.
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
            converter_name = "str" if converter is None else converter
            path_values[key] = _convert_path_value(
                converter_name,
                value,
            )
            safe = "/" if converter_name == "path" else ""
            encoded_value = quote(path_values[key], safe=safe)
            path_values[key] = encoded_value
            path = path.replace(
                match.group(0),
                encoded_value,
                1,
            )

        if self._path_reverser is not None and route.route_name is not None:
            try:
                path = self._path_reverser(route.route_name, path_values)
            except (AssertionError, KeyError, ValueError) as error:
                raise RouteUrlError(_REVERSER_FAILURE) from error

        if remaining:
            path = f"{path}?{Arr.query(remaining)}"
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


def _convert_path_value(converter: str, value: object) -> str:
    """Validate and normalize one supported route path value.

    Args:
        converter: Starlette-compatible converter name.
        value: Caller value for one path parameter.

    Returns:
        Canonical string value accepted by the route converter.

    Raises:
        RouteUrlError: If the converter is unsupported or rejects the value.
    """
    if converter == "path":
        return str(value)
    if converter == "str":
        return _convert_string_path_value(value)
    if converter == "int":
        return _convert_integer_path_value(value)
    if converter == "float":
        return _convert_float_path_value(value)
    if converter == "uuid":
        return _convert_uuid_path_value(value)
    raise RouteUrlError(_UNSUPPORTED_ROUTE_CONVERTER_ERROR)


def _convert_string_path_value(value: object) -> str:
    """Validate the default non-empty string path converter.

    Args:
        value: Caller value for one path segment.

    Returns:
        A valid string path segment.

    Raises:
        RouteUrlError: If the value is empty or contains a slash.
    """
    text = str(value)
    if not text or "/" in text:
        raise RouteUrlError(_ROUTE_CONVERTER_ERROR)
    return text


def _convert_integer_path_value(value: object) -> str:
    """Normalize a non-negative integer path value.

    Args:
        value: Caller value for one integer path parameter.

    Returns:
        Canonical decimal digits accepted by Starlette's integer converter.

    Raises:
        RouteUrlError: If the value is not a supported integer spelling.
    """
    text = str(value)
    if re.fullmatch(r"[0-9]+", text) is None:
        raise RouteUrlError(_ROUTE_CONVERTER_ERROR)
    try:
        return str(int(text))
    except ValueError as error:
        raise RouteUrlError(_ROUTE_CONVERTER_ERROR) from error


def _convert_float_path_value(value: object) -> str:
    """Normalize a finite, non-negative float path value.

    Args:
        value: Caller value for one float path parameter.

    Returns:
        Decimal text accepted by Starlette's float converter.

    Raises:
        RouteUrlError: If the value is outside the converter's accepted form.
    """
    if not isinstance(value, (str, SupportsFloat)):
        raise RouteUrlError(_ROUTE_CONVERTER_ERROR)
    try:
        numeric = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise RouteUrlError(_ROUTE_CONVERTER_ERROR) from error
    if not math.isfinite(numeric) or numeric < 0:
        raise RouteUrlError(_ROUTE_CONVERTER_ERROR)
    return f"{numeric:0.20f}".rstrip("0").rstrip(".")


def _convert_uuid_path_value(value: object) -> str:
    """Normalize a UUID path value to its canonical spelling.

    Args:
        value: Caller value for one UUID path parameter.

    Returns:
        Canonical lowercase UUID text accepted by Starlette.

    Raises:
        RouteUrlError: If the value is not a valid UUID.
    """
    try:
        return str(UUID(str(value)))
    except ValueError as error:
        raise RouteUrlError(_ROUTE_CONVERTER_ERROR) from error


__all__ = ["UrlGenerator"]
