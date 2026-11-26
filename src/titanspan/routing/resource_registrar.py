"""Register explicit REST action sets through the canonical Router.

Resources expand into ordinary route definitions, so dispatch, metadata, and
URL generation retain one source of truth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.routing.exceptions import InvalidRouteError

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from titanspan.routing.route import RouteDefinition
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
_INVALID_RESOURCE_NAME_ERROR = (
    "Resource names must be relative URI path segments."
)
_INVALID_ACTION_SELECTION_ERROR = (
    "Resource action selection contains an unknown action."
)
_INVALID_ACTION_EXCLUSION_ERROR = (
    "Resource action exclusion contains an unknown action."
)
_IRREGULAR_RESOURCE_SUFFIX_LENGTH = len("ies")
_UNCOUNTABLE_RESOURCES = frozenset({"news", "series", "species"})


class ResourceRegistrar:
    """Configure a REST resource whose actions are native route definitions.

    The registrar supports filtering before the owning Router is frozen.
    """

    def __init__(
        self,
        router: Router,
        resource: str,
        controller: type[object],
        *,
        api_only: bool,
        parameter: str | None = None,
    ) -> None:
        """Expand one controller into conventional resource routes.

        Args:
            router: Application router receiving the definitions.
            resource: Resource URI segment or nested path.
            controller: Controller class whose methods handle each action.
            api_only: Omit HTML-oriented create and edit routes.
            parameter: Optional item identifier used in URI templates.

        Raises:
            InvalidRouteError: If the resource path is empty or malformed.
        """
        if not resource or resource.startswith("/") or "?" in resource:
            raise InvalidRouteError(_INVALID_RESOURCE_NAME_ERROR)
        self._router = router
        self._resource = resource.rstrip("/")
        segment = self._resource.rsplit("/", maxsplit=1)[-1]
        self._parameter = parameter or _singularize(segment)
        self._routes: dict[str, list[RouteDefinition]] = {
            action: [] for action in _RESOURCE_ACTIONS
        }
        self._register(controller, api_only=api_only)

    def only(self, actions: Sequence[str]) -> ResourceRegistrar:
        """Keep only the selected controller actions.

        Args:
            actions: Resource action names retained in the route collection.

        Returns:
            This registrar for further filtering.

        Raises:
            InvalidRouteError: If an unknown action is requested.
        """
        unknown = set(actions).difference(_RESOURCE_ACTIONS)
        if unknown:
            raise InvalidRouteError(_INVALID_ACTION_SELECTION_ERROR)
        selected: set[str] = set(actions)
        self._remove_actions(
            action for action in _RESOURCE_ACTIONS if action not in selected
        )
        return self

    def except_(self, actions: Sequence[str]) -> ResourceRegistrar:
        """Remove selected controller actions from the resource.

        Args:
            actions: Resource action names removed from the route collection.

        Returns:
            This registrar for further filtering.

        Raises:
            InvalidRouteError: If an unknown action is excluded.
        """
        unknown = set(actions).difference(_RESOURCE_ACTIONS)
        if unknown:
            raise InvalidRouteError(_INVALID_ACTION_EXCLUSION_ERROR)
        self._remove_actions(set(actions))
        return self

    def _register(self, controller: type[object], *, api_only: bool) -> None:
        """Create conventional routes with explicit controller/method pairs.

        Args:
            controller: Class resolved by the native service container.
            api_only: Whether HTML resource actions should be omitted.
        """
        collection_path = f"/{self._resource}"
        item_path = f"{collection_path}/{{{self._parameter}}}"
        actions = _API_RESOURCE_ACTIONS if api_only else _RESOURCE_ACTIONS
        declarations = {
            "index": (("GET",), collection_path),
            "create": (("GET",), f"{collection_path}/create"),
            "store": (("POST",), collection_path),
            "show": (("GET",), item_path),
            "edit": (("GET",), f"{item_path}/edit"),
            "update": (("PUT", "PATCH"), item_path),
            "destroy": (("DELETE",), item_path),
        }
        for action in actions:
            methods, path = declarations[action]
            definition = self._router.match(
                methods,
                path,
                (controller, action),
            )
            definition.name(f"{self._resource.replace('/', '.')}.{action}")
            self._routes[action].append(definition)

    def _remove_actions(self, actions: Iterable[str]) -> None:
        """Remove action routes while registration remains open.

        Args:
            actions: Names whose route definitions must be removed.
        """
        for action in actions:
            for route in self._routes[action]:
                self._router.routes.remove(route)
            self._routes[action].clear()


def _singularize(value: str) -> str:
    """Apply predictable English singularization to common resource names.

    Args:
        value: Last URI resource segment.

    Returns:
        A parameter name for common plural forms.

    Notes:
        Irregular nouns should pass an explicit parameter name. Common
        uncountable names retain their registered spelling.
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
