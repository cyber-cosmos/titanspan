"""Register explicit REST action sets through the canonical Router.

Resources expand into ordinary route definitions, so dispatch, metadata, and
URL generation retain one source of truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from titanspan.contracts.http import MiddlewareDeclaration
from titanspan.routing.exceptions import InvalidRouteError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from titanspan.contracts.http import MiddlewareItem
    from titanspan.routing.route import RouteDefinition
    from titanspan.routing.route_group import RouteGroup
    from titanspan.routing.router import Router

_RESOURCE_ACTIONS = (
    "index",
    "create",
    "store",
    "show",
    "edit",
    "update",
    "destroy",
)
_API_RESOURCE_ACTIONS = (
    "index",
    "store",
    "show",
    "update",
    "destroy",
)
_SINGLETON_ACTIONS = ("show", "edit", "update")
_API_SINGLETON_ACTIONS = ("show", "update")
_INVALID_RESOURCE_NAME_ERROR = (
    "Resource names must contain non-empty relative path segments."
)
_INVALID_ACTION_SELECTION_ERROR = (
    "Resource action selection contains an unknown action."
)
_INVALID_ACTION_EXCLUSION_ERROR = (
    "Resource action exclusion contains an unknown action."
)
_INVALID_PARAMETER_MAP_ERROR = (
    "Resource parameters must name segments and use identifiers."
)
_INVALID_ACTION_NAMES_ERROR = (
    "Resource action names must map known actions to non-empty names."
)
_IRREGULAR_RESOURCE_SUFFIX_LENGTH = len("ies")
_UNCOUNTABLE_RESOURCES = frozenset({"news", "series", "species"})
_COLLECTION_ACTIONS = frozenset({"index", "create", "store"})
_ITEM_ACTIONS = frozenset({"show", "edit", "update", "destroy"})
_ACTION_METHODS: Mapping[str, tuple[str, ...]] = {
    "index": ("GET",),
    "create": ("GET",),
    "store": ("POST",),
    "show": ("GET",),
    "edit": ("GET",),
    "update": ("PUT", "PATCH"),
    "destroy": ("DELETE",),
}


@dataclass(frozen=True, slots=True)
class ResourceOptions:
    """Collect route-generation choices for one resource registrar.

    Attributes:
        api_only: Whether browser create and edit actions are omitted.
        parameter: Optional custom parameter for the final resource segment.
        singleton: Whether item actions omit an identifier segment.
        group: Registration group captured when the resource was declared.
    """

    api_only: bool
    parameter: str | None
    singleton: bool
    group: RouteGroup


class ResourceRegistrar:
    """Configure REST controller routes in one native route collection.

    The registrar supports route filtering, nested names and parameters,
    shallow item routes, and singleton action sets before startup.
    """

    def __init__(
        self,
        router: Router,
        resource: str,
        controller: type[object],
        options: ResourceOptions,
    ) -> None:
        """Create route definitions for one controller resource.

        Args:
            router: Application router receiving the definitions.
            resource: Resource path, using dots or slashes for nesting.
            controller: Controller resolved by the native service container.
            options: API, parameter, singleton, and captured group settings.

        Raises:
            InvalidRouteError: If the resource name or parameter is invalid.
        """
        if (
            not resource
            or resource.startswith("/")
            or "?" in resource
            or resource.endswith("/")
        ):
            raise InvalidRouteError(_INVALID_RESOURCE_NAME_ERROR)
        segments: tuple[str, ...] = tuple(
            resource.replace("/", ".").split("."),
        )
        if any(not segment.isidentifier() for segment in segments):
            raise InvalidRouteError(_INVALID_RESOURCE_NAME_ERROR)
        self._router = router
        self._controller = controller
        self._segments: tuple[str, ...] = segments
        self._last_segment: str = segments[-1]
        self._resource_name = ".".join(segments)
        self._api_only = options.api_only
        self._singleton = options.singleton
        self._shallow = False
        self._group = options.group
        self._parameters = {
            segment: _singularize(segment) for segment in segments
        }
        if options.parameter is not None:
            self._parameters[segments[-1]] = _validate_parameter(
                options.parameter,
            )
        self._names: dict[str, str] = {}
        self._middleware: list[MiddlewareItem] = []
        self._routes: dict[str, list[RouteDefinition]] = {
            action: [] for action in _RESOURCE_ACTIONS
        }
        if options.singleton:
            self._enabled_actions: set[str] = set(
                _API_SINGLETON_ACTIONS
                if options.api_only
                else _SINGLETON_ACTIONS
            )
        else:
            actions: tuple[str, ...] = (
                _API_RESOURCE_ACTIONS if options.api_only else _RESOURCE_ACTIONS
            )
            self._enabled_actions = set(actions)
        self._register_enabled_actions()

    def only(self, actions: Sequence[str]) -> ResourceRegistrar:
        """Keep only the selected controller actions.

        Args:
            actions: Resource action names retained in the collection.

        Returns:
            This registrar for further filtering.

        Raises:
            InvalidRouteError: If an unknown action is requested.
        """
        unknown = set(actions).difference(_RESOURCE_ACTIONS)
        if unknown:
            raise InvalidRouteError(_INVALID_ACTION_SELECTION_ERROR)
        selected = set(actions)
        self._remove_actions(
            action
            for action in tuple(self._enabled_actions)
            if action not in selected
        )
        self._enabled_actions.intersection_update(selected)
        return self

    def except_(self, actions: Sequence[str]) -> ResourceRegistrar:
        """Remove selected controller actions from the resource.

        Args:
            actions: Resource action names removed from the collection.

        Returns:
            This registrar for further filtering.

        Raises:
            InvalidRouteError: If an unknown action is excluded.
        """
        unknown = set(actions).difference(_RESOURCE_ACTIONS)
        if unknown:
            raise InvalidRouteError(_INVALID_ACTION_EXCLUSION_ERROR)
        excluded = set(actions)
        self._remove_actions(excluded)
        self._enabled_actions.difference_update(excluded)
        return self

    def shallow(self, enabled: bool = True) -> ResourceRegistrar:
        """Shorten nested item paths and names while retaining collections.

        Args:
            enabled: Whether nested item actions omit their parent segments.

        Returns:
            This registrar for further configuration.
        """
        if enabled == self._shallow:
            return self
        self._shallow = enabled
        self._refresh_routes()
        return self

    def parameters(
        self,
        values: Mapping[str, str],
    ) -> ResourceRegistrar:
        """Set path parameter names for resource segments.

        Args:
            values: Resource segment names mapped to Python identifiers.

        Returns:
            This registrar for further configuration.

        Raises:
            InvalidRouteError: If a key or replacement is invalid.
        """
        unknown = set(values).difference(self._segments)
        if unknown:
            raise InvalidRouteError(_INVALID_PARAMETER_MAP_ERROR)
        replacements = {
            key: _validate_parameter(value) for key, value in values.items()
        }
        old = dict(self._parameters)
        self._parameters.update(replacements)
        self._refresh_routes(old)
        return self

    def names(self, values: Mapping[str, str]) -> ResourceRegistrar:
        """Set custom names for selected resource actions.

        Args:
            values: Action names mapped to route names within the active group.

        Returns:
            This registrar for further configuration.

        Raises:
            InvalidRouteError: If an action or name is invalid.
        """
        if any(
            action not in _RESOURCE_ACTIONS or not name.strip()
            for action, name in values.items()
        ):
            raise InvalidRouteError(_INVALID_ACTION_NAMES_ERROR)
        self._names.update(values)
        self._refresh_names()
        return self

    def middleware(
        self,
        values: MiddlewareItem | Sequence[MiddlewareItem],
    ) -> ResourceRegistrar:
        """Add ordered middleware declarations to each resource route.

        Args:
            values: Middleware alias, class, or declaration sequence.

        Returns:
            This registrar for further configuration.
        """
        additions = (
            (values,)
            if isinstance(values, (str, type, MiddlewareDeclaration))
            else values
        )
        for declaration in additions:
            if declaration not in self._middleware:
                self._middleware.append(declaration)
        for routes in self._routes.values():
            for route in routes:
                route.middleware(additions)
        return self

    def creatable(self) -> ResourceRegistrar:
        """Add the creation actions supported by this singleton resource.

        Returns:
            This registrar for further configuration.

        Raises:
            InvalidRouteError: If called for an ordinary collection resource.
        """
        if not self._singleton:
            raise InvalidRouteError(_INVALID_ACTION_SELECTION_ERROR)
        additions = ("store",) if self._api_only else ("create", "store")
        self._add_actions(additions)
        return self

    def destroyable(self) -> ResourceRegistrar:
        """Add only the delete action to a singleton resource.

        Returns:
            This registrar for further configuration.

        Raises:
            InvalidRouteError: If called for an ordinary collection resource.
        """
        if not self._singleton:
            raise InvalidRouteError(_INVALID_ACTION_SELECTION_ERROR)
        self._add_actions(("destroy",))
        return self

    def _register_enabled_actions(self) -> None:
        """Register each currently enabled action through the native router.

        Side Effects:
            Adds ordinary route definitions to the shared route collection.
        """
        for action in _RESOURCE_ACTIONS:
            if action in self._enabled_actions:
                self._add_action(action)

    def _add_actions(self, actions: Iterable[str]) -> None:
        """Register newly enabled actions exactly once.

        Args:
            actions: Resource actions to add to this registrar.
        """
        for action in actions:
            if action not in self._enabled_actions:
                self._enabled_actions.add(action)
                self._add_action(action)

    def _add_action(self, action: str) -> None:
        """Create one route and apply all current registrar metadata.

        Args:
            action: Resource action selected for registration.
        """
        path = self._path_for(action)
        definition = self._router.register_resource_route(
            path,
            (self._controller, action),
            _ACTION_METHODS[action],
            self._group,
        )
        definition.name(self._name_for(action))
        definition.middleware(self._middleware)
        self._routes[action].append(definition)

    def _remove_actions(self, actions: Iterable[str]) -> None:
        """Remove selected definitions from the canonical route collection.

        Args:
            actions: Names whose route definitions must be removed.
        """
        for action in actions:
            for route in self._routes[action]:
                self._router.routes.remove(route)
            self._routes[action].clear()

    def _refresh_routes(
        self,
        previous_parameters: Mapping[str, str] | None = None,
    ) -> None:
        """Rebuild path names in place without changing route identities.

        Args:
            previous_parameters: Prior mapping when parameter names changed.
        """
        old_parameters = (
            dict(self._parameters)
            if previous_parameters is None
            else dict(previous_parameters)
        )
        name_map = {
            old_parameters[segment]: self._parameters[segment]
            for segment in self._segments
        }
        for action, routes in self._routes.items():
            for route in routes:
                path = self._path_for(action)
                active_names = set(_parameters_in(path))
                remap = {
                    previous: (
                        replacement if replacement in active_names else None
                    )
                    for previous, replacement in name_map.items()
                }
                self._router.routes.replace_path(route, path, remap)
        self._refresh_names()

    def _refresh_names(self) -> None:
        """Apply current default or custom names to registered routes.

        Route objects remain in place so the catalog retains their identity.
        """
        for action, routes in self._routes.items():
            for route in routes:
                route.name(self._name_for(action))

    def _path_for(self, action: str) -> str:
        """Return the URI path for one collection or item action.

        Args:
            action: Resource action name.

        Returns:
            Native absolute path with nested and shallow semantics applied.
        """
        if (
            self._shallow
            and len(self._segments) > 1
            and action in _ITEM_ACTIONS
        ):
            collection = f"/{self._last_segment}"
        else:
            parts: list[str] = []
            for index, segment in enumerate(self._segments):
                parts.append(segment)
                if index < len(self._segments) - 1:
                    parts.append(f"{{{self._parameters[segment]}}}")
            collection = "/" + "/".join(parts)

        if action in {"create", "edit"}:
            return f"{collection}/{action}"
        if action in _ITEM_ACTIONS and not self._singleton:
            return f"{collection}/{{{self._parameters[self._last_segment]}}}"
        return collection

    def _name_for(self, action: str) -> str:
        """Return the action name with custom and shallow conventions.

        Args:
            action: Resource action name.

        Returns:
            Route name before an inherited group name prefix is applied.
        """
        custom = self._names.get(action)
        if custom is not None:
            return custom
        resource = self._resource_name
        if (
            self._shallow
            and len(self._segments) > 1
            and action in _ITEM_ACTIONS
        ):
            resource = self._last_segment
        return f"{resource}.{action}"


def _validate_parameter(value: str) -> str:
    """Validate a resource parameter as a Python identifier.

    Args:
        value: Caller-provided path parameter name.

    Returns:
        The validated identifier.

    Raises:
        InvalidRouteError: If the value cannot name a route parameter.
    """
    if not value.isidentifier():
        raise InvalidRouteError(_INVALID_PARAMETER_MAP_ERROR)
    return value


def _parameters_in(path: str) -> tuple[str, ...]:
    """Extract path placeholders needed to remap resource metadata.

    Args:
        path: Route path generated for one resource action.

    Returns:
        Parameter names in path order.
    """
    return tuple(re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)", path))


def _singularize(value: str) -> str:
    """Apply predictable English singularization to common resource names.

    Args:
        value: URI resource segment.

    Returns:
        A parameter name for common plural forms.

    Notes:
        Irregular nouns should pass an explicit parameter name.
    """
    if value in _UNCOUNTABLE_RESOURCES:
        return value
    if value.endswith("ies") and len(value) > _IRREGULAR_RESOURCE_SUFFIX_LENGTH:
        return value[:-3] + "y"
    if value.endswith("sses"):
        return value[:-2]
    if value.endswith("s") and not value.endswith("ss"):
        return value[:-1]
    return value


__all__ = ["ResourceRegistrar"]
