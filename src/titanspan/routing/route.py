"""Represent one mutable-at-registration native route definition.

The owning router freezes definitions when it composes the ASGI matcher.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Self

from titanspan.routing.exceptions import InvalidRouteError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from titanspan.contracts.http import HttpMiddleware
    from titanspan.contracts.routing import RouteAction

_PARAMETER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::[^{}]+)?\}")
_INVALID_ROUTE_PATH = (
    "Route paths must be absolute and contain valid parameters."
)
_INVALID_CONSTRAINT = "Route constraints must be valid regular expressions."
_INVALID_METHOD_ERROR = "At least one valid HTTP method is required."
_INVALID_ROUTE_NAME_ERROR = "Route names must be non-empty tokens."
_INVALID_FINITE_CONSTRAINT_ERROR = "A finite route constraint needs values."
_INVALID_DEFAULT_PARAMETER_ERROR = "Route defaults must name path parameters."
_INVALID_DOMAIN_ERROR = "Route domains must be host names only."
_INVALID_STATUS_ERROR = "HTTP response status must be 100-599."
_MIN_HTTP_STATUS = 100
_MAX_HTTP_STATUS = 599
_MAX_CONSTRAINT_LENGTH = 256


@dataclass(frozen=True, slots=True)
class RouteMetadata:
    """Collect non-callable metadata shared by a route declaration.

    Group defaults and fluent route updates use these explicit values.
    """

    name_prefix: str = ""
    middleware: tuple[str | type[HttpMiddleware], ...] = ()
    constraints: Mapping[str, str] = field(
        default_factory=lambda: dict[str, str]()
    )
    defaults: Mapping[str, object] = field(
        default_factory=lambda: dict[str, object]()
    )
    domain: str | None = None
    tags: tuple[str, ...] = ()
    summary: str | None = None
    description: str | None = None
    deprecated: bool = False
    status_code: int | None = None


class RouteDefinition:
    """Store one endpoint and its registration-time routing metadata.

    Fluent methods mutate the definition until its owning application starts.
    The router then rejects all further mutations.
    """

    def __init__(
        self,
        path: str,
        methods: Sequence[str],
        action: RouteAction | None,
        metadata: RouteMetadata,
        *,
        ensure_mutable: Callable[[], None],
        validate_name: Callable[[str, RouteDefinition], None],
    ) -> None:
        """Create a route record after validating its stable path fields.

        Args:
            path: Absolute route template such as /documents/{document}.
            methods: Explicit HTTP methods accepted by this route.
            action: Callable, invokable controller, or controller/method pair.
            metadata: Group-inherited and route-specific descriptive values.
            ensure_mutable: Guard owned by the containing Router.
            validate_name: Callback enforcing collection-wide name uniqueness.

        Raises:
            InvalidRouteError: If the path or method list is malformed.
        """
        self._path = _validate_path(path)
        self._methods = tuple(
            dict.fromkeys(method.upper() for method in methods)
        )
        if not self._methods or any(
            not method.isalpha() for method in self._methods
        ):
            raise InvalidRouteError(_INVALID_METHOD_ERROR)
        self._action = action
        self._ensure_mutable = ensure_mutable
        self._validate_name = validate_name
        self._metadata = metadata
        self._name_prefix = metadata.name_prefix
        self._route_name: str | None = None
        self._middleware = list(metadata.middleware)
        self._excluded_middleware: list[str | type[HttpMiddleware]] = []
        self._constraints = dict(metadata.constraints)
        self._defaults = dict(metadata.defaults)
        self._domain = metadata.domain
        self._tags = list(metadata.tags)
        self._summary = metadata.summary
        self._description = metadata.description
        self._deprecated = metadata.deprecated
        self._status_code = metadata.status_code
        for parameter, pattern in self._constraints.items():
            _validate_constraint(self._path, parameter, pattern)

    @property
    def path(self) -> str:
        """Return the route path template.

        Returns:
            The absolute path registered with the owning router.
        """
        return self._path

    @property
    def methods(self) -> tuple[str, ...]:
        """Return accepted methods in their deterministic order.

        Returns:
            The uppercase HTTP methods registered for this path.
        """
        return self._methods

    @property
    def action(self) -> RouteAction | None:
        """Return the application callable or controller action.

        Returns:
            The endpoint action, or None while a decorator is being applied.
        """
        return self._action

    @property
    def route_name(self) -> str | None:
        """Return the route's unique name, if one was assigned.

        Returns:
            The group-prefixed route name or None.
        """
        return self._route_name

    @property
    def middleware_types(self) -> tuple[str | type[HttpMiddleware], ...]:
        """Return route middleware declarations in execution order.

        Returns:
            The inherited and route-local middleware declarations.
        """
        return tuple(self._middleware)

    @property
    def excluded_middleware(self) -> tuple[str | type[HttpMiddleware], ...]:
        """Return middleware declarations excluded from this route.

        Returns:
            The route-local middleware exclusions.
        """
        return tuple(self._excluded_middleware)

    @property
    def constraints(self) -> Mapping[str, str]:
        """Return path constraints as a read-only view.

        Returns:
            Parameter names mapped to their compiled regex expressions.
        """
        return MappingProxyType(self._constraints)

    @property
    def default_values(self) -> Mapping[str, object]:
        """Return parameter defaults as a read-only view.

        Returns:
            Route parameter defaults configured during registration.
        """
        return MappingProxyType(self._defaults)

    @property
    def domain_name(self) -> str | None:
        """Return the exact host constraint when configured.

        Returns:
            A normalized host name or None for any host.
        """
        return self._domain

    @property
    def tag_values(self) -> tuple[str, ...]:
        """Return OpenAPI tags in registration order.

        Returns:
            The operation tag names.
        """
        return tuple(self._tags)

    @property
    def summary_text(self) -> str | None:
        """Return the OpenAPI summary, if configured.

        Returns:
            The operation summary or None.
        """
        return self._summary

    @property
    def description_text(self) -> str | None:
        """Return the OpenAPI description, if configured.

        Returns:
            The operation description or None.
        """
        return self._description

    @property
    def is_deprecated(self) -> bool:
        """Return whether the operation is marked deprecated.

        Returns:
            True when generated OpenAPI should flag this operation.
        """
        return self._deprecated

    @property
    def response_status(self) -> int | None:
        """Return the optional default response status.

        Returns:
            The configured status code or None.
        """
        return self._status_code

    def name(self, value: str) -> Self:
        """Assign a unique name, applying any inherited group prefix.

        Args:
            value: Non-empty application route name.

        Returns:
            This definition for further fluent configuration.

        Raises:
            InvalidRouteError: If the name is empty or contains whitespace.
        """
        self._ensure_mutable()
        if not value or any(character.isspace() for character in value):
            raise InvalidRouteError(_INVALID_ROUTE_NAME_ERROR)
        candidate = f"{self._name_prefix}{value}"
        self._validate_name(candidate, self)
        self._route_name = candidate
        return self

    def middleware(
        self,
        values: (
            str | type[HttpMiddleware] | Sequence[str | type[HttpMiddleware]]
        ),
    ) -> Self:
        """Append route middleware while preserving declared order.

        Args:
            values: Middleware alias, class, or ordered sequence of either.

        Returns:
            This definition for further fluent configuration.
        """
        self._ensure_mutable()
        additions = (values,) if isinstance(values, (str, type)) else values
        for item in additions:
            if item not in self._middleware:
                self._middleware.append(item)
        return self

    def without_middleware(
        self,
        values: (
            str | type[HttpMiddleware] | Sequence[str | type[HttpMiddleware]]
        ),
    ) -> Self:
        """Record route-local exclusions for explicitly named middleware.

        Args:
            values: Middleware alias, class, or ordered sequence of either.

        Returns:
            This definition for further fluent configuration.
        """
        self._ensure_mutable()
        exclusions = (values,) if isinstance(values, (str, type)) else values
        for item in exclusions:
            if item not in self._excluded_middleware:
                self._excluded_middleware.append(item)
        return self

    def where(self, parameter: str, pattern: str) -> Self:
        """Constrain one path parameter with a trusted regular expression.

        Args:
            parameter: Name present in this path template.
            pattern: Python regular expression matched against one segment.

        Returns:
            This definition for further fluent configuration.

        Raises:
            InvalidRouteError: If the parameter or expression is invalid.
        """
        self._ensure_mutable()
        _validate_constraint(self._path, parameter, pattern)
        self._constraints[parameter] = pattern
        return self

    def where_number(self, parameter: str) -> Self:
        """Restrict a path parameter to decimal digits.

        Args:
            parameter: Name present in this path template.

        Returns:
            This definition for further fluent configuration.
        """
        return self.where(parameter, r"[0-9]+")

    def where_alpha(self, parameter: str) -> Self:
        """Restrict a path parameter to ASCII letters.

        Args:
            parameter: Name present in this path template.

        Returns:
            This definition for further fluent configuration.
        """
        return self.where(parameter, r"[A-Za-z]+")

    def where_alpha_numeric(self, parameter: str) -> Self:
        """Restrict a path parameter to ASCII letters and digits.

        Args:
            parameter: Name present in this path template.

        Returns:
            This definition for further fluent configuration.
        """
        return self.where(parameter, r"[A-Za-z0-9]+")

    def where_uuid(self, parameter: str) -> Self:
        """Restrict a path parameter to a canonical UUID spelling.

        Args:
            parameter: Name present in this path template.

        Returns:
            This definition for further fluent configuration.
        """
        return self.where(
            parameter,
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{12}",
        )

    def where_in(self, parameter: str, values: Sequence[str]) -> Self:
        """Restrict a path parameter to a finite set of literal values.

        Args:
            parameter: Name present in this path template.
            values: Non-empty values accepted by the route.

        Returns:
            This definition for further fluent configuration.

        Raises:
            InvalidRouteError: If no values were supplied.
        """
        if not values:
            raise InvalidRouteError(_INVALID_FINITE_CONSTRAINT_ERROR)
        return self.where(
            parameter,
            "(?:" + "|".join(re.escape(value) for value in values) + ")",
        )

    def defaults(self, values: Mapping[str, object]) -> Self:
        """Set metadata defaults for path parameters.

        Args:
            values: Parameter names and their application-owned defaults.

        Returns:
            This definition for further fluent configuration.

        Raises:
            InvalidRouteError: If a default names no route parameter.
        """
        self._ensure_mutable()
        unknown = set(values).difference(_path_parameters(self._path))
        if unknown:
            raise InvalidRouteError(_INVALID_DEFAULT_PARAMETER_ERROR)
        self._defaults.update(values)
        return self

    def domain(self, value: str) -> Self:
        """Restrict matching to one configured host name.

        Args:
            value: Host name without a scheme, port, or wildcard.

        Returns:
            This definition for further fluent configuration.

        Raises:
            InvalidRouteError: If the host value is not a simple host name.
        """
        self._ensure_mutable()
        candidate = value.lower().rstrip(".")
        if (
            not candidate
            or "/" in candidate
            or "://" in candidate
            or ":" in candidate
        ):
            raise InvalidRouteError(_INVALID_DOMAIN_ERROR)
        self._domain = candidate
        return self

    def tags(self, values: Sequence[str]) -> Self:
        """Set OpenAPI tags for the operation.

        Args:
            values: Ordered tag names.

        Returns:
            This definition for further fluent configuration.
        """
        self._ensure_mutable()
        self._tags = list(dict.fromkeys(values))
        return self

    def summary(self, value: str) -> Self:
        """Set the operation summary exposed in generated OpenAPI.

        Args:
            value: Short operation summary.

        Returns:
            This definition for further fluent configuration.
        """
        self._ensure_mutable()
        self._summary = value
        return self

    def description(self, value: str) -> Self:
        """Set the operation description exposed in generated OpenAPI.

        Args:
            value: Detailed operation description.

        Returns:
            This definition for further fluent configuration.
        """
        self._ensure_mutable()
        self._description = value
        return self

    def deprecated(self, value: bool = True) -> Self:
        """Mark or unmark the operation as deprecated for API clients.

        Args:
            value: Whether generated OpenAPI should mark the operation old.

        Returns:
            This definition for further fluent configuration.
        """
        self._ensure_mutable()
        self._deprecated = value
        return self

    def status_code(self, value: int) -> Self:
        """Set a default HTTP status returned by this route.

        Args:
            value: Status code between 100 and 599.

        Returns:
            This definition for further fluent configuration.

        Raises:
            InvalidRouteError: If the status is outside the HTTP range.
        """
        self._ensure_mutable()
        if not _MIN_HTTP_STATUS <= value <= _MAX_HTTP_STATUS:
            raise InvalidRouteError(_INVALID_STATUS_ERROR)
        self._status_code = value
        return self

    def set_action(self, action: RouteAction) -> Self:
        """Attach the callable supplied by a decorator registration.

        Args:
            action: Callable or controller action registered by the decorator.
        """
        self._ensure_mutable()
        self._action = action
        return self


def _validate_path(path: str) -> str:
    """Normalize and verify an absolute path template.

    Args:
        path: Caller-provided path string.

    Returns:
        The canonical path beginning with one slash.

    Raises:
        InvalidRouteError: If braces are unbalanced or path is not absolute.
    """
    if not path.startswith("/") or "//" in path or "?" in path or "#" in path:
        raise InvalidRouteError(_INVALID_ROUTE_PATH)
    if path.count("{") != path.count("}"):
        raise InvalidRouteError(_INVALID_ROUTE_PATH)
    for segment in re.findall(r"\{([^{}]*)\}", path):
        name = segment.split(":", maxsplit=1)[0]
        if not name.isidentifier():
            raise InvalidRouteError(_INVALID_ROUTE_PATH)
    remainder = _PARAMETER_PATTERN.sub("", path)
    if "{" in remainder or "}" in remainder:
        raise InvalidRouteError(_INVALID_ROUTE_PATH)
    return path if path == "/" else path.rstrip("/")


def _validate_constraint(path: str, parameter: str, pattern: str) -> None:
    """Validate a parameter name and compile its regex expression.

    Args:
        path: Route path template containing the parameter.
        parameter: Parameter name selected for the expression.
        pattern: Python regular expression supplied by the application.

    Raises:
        InvalidRouteError: If the target is missing or expression is invalid.
    """
    if (
        parameter not in _path_parameters(path)
        or len(pattern) > _MAX_CONSTRAINT_LENGTH
    ):
        raise InvalidRouteError(_INVALID_CONSTRAINT)
    try:
        re.compile(pattern)
    except re.error as error:
        raise InvalidRouteError(_INVALID_CONSTRAINT) from error


def _path_parameters(path: str) -> tuple[str, ...]:
    """Extract ordered parameter names from a route path template.

    Args:
        path: Validated route template.

    Returns:
        Parameter names in path appearance order.
    """
    return tuple(match.group(1) for match in _PARAMETER_PATTERN.finditer(path))


__all__ = ["RouteDefinition", "RouteMetadata"]
