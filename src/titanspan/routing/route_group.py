"""Represent immutable nested registration attributes and fluent builders.

Each Router stores group stacks in an instance-owned ContextVar.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING

from titanspan.contracts.http import MiddlewareDeclaration

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping, Sequence

    from titanspan.contracts.http import MiddlewareItem
    from titanspan.routing.router import Router

_INVALID_PREFIX_ERROR = (
    "Route prefixes must be absolute path prefixes without query data."
)


@dataclass(frozen=True, slots=True)
class RouteGroup:
    """Collect immutable route defaults inherited by nested registrations.

    Child values extend or replace parent values in a deterministic order.
    """

    prefix: str = ""
    name_prefix: str = ""
    middleware: tuple[MiddlewareItem, ...] = ()
    constraints: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType(dict[str, str]())
    )
    defaults: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType(dict[str, object]())
    )
    domain_name: str | None = None

    def merged(self, child: RouteGroup) -> RouteGroup:
        """Combine nested group metadata without mutating either input.

        Args:
            child: Group attributes declared inside this group.

        Returns:
            A new group with inherited and child attributes combined.
        """
        prefix = _join_paths(self.prefix, child.prefix)
        constraints: dict[str, str] = dict(self.constraints)
        constraints.update(child.constraints)
        defaults: dict[str, object] = dict(self.defaults)
        defaults.update(child.defaults)
        return RouteGroup(
            prefix=prefix,
            name_prefix=self.name_prefix + child.name_prefix,
            middleware=tuple(
                dict.fromkeys((*self.middleware, *child.middleware))
            ),
            constraints=MappingProxyType(constraints),
            defaults=MappingProxyType(defaults),
            domain_name=child.domain_name or self.domain_name,
        )


class RouteGroupBuilder:
    """Build one group value and enter it for route registrations.

    The builder itself is local to a declaration; active groups are isolated
    by the Router's context-local stack.
    """

    def __init__(self, router: Router, prefix: str = "") -> None:
        """Create a builder for one path prefix and later group metadata.

        Args:
            router: Router whose context-local group stack will be used.
            prefix: Optional absolute path prefix inherited by child routes.
        """
        self._router = router
        self._attributes = RouteGroup(prefix=_normalize_prefix(prefix))

    def prefix(self, value: str) -> RouteGroupBuilder:
        """Set the path prefix for routes within this group.

        Args:
            value: Absolute path prefix, or an empty string.

        Returns:
            This builder for further fluent configuration.
        """
        self._attributes = replace(
            self._attributes,
            prefix=_normalize_prefix(value),
        )
        return self

    def name(self, value: str) -> RouteGroupBuilder:
        """Set a route-name prefix inherited by child routes.

        Args:
            value: Name prefix, conventionally ending with a period.

        Returns:
            This builder for further fluent configuration.
        """
        self._attributes = replace(
            self._attributes,
            name_prefix=value,
        )
        return self

    def middleware(
        self,
        values: (MiddlewareItem | Sequence[MiddlewareItem]),
    ) -> RouteGroupBuilder:
        """Append inherited middleware without duplicating declarations.

        Args:
            values: Middleware alias, class, or ordered declaration sequence.

        Returns:
            This builder for further fluent configuration.
        """
        additions = (
            (values,)
            if isinstance(values, (str, type, MiddlewareDeclaration))
            else values
        )
        self._attributes = replace(
            self._attributes,
            middleware=tuple(
                dict.fromkeys((*self._attributes.middleware, *additions))
            ),
        )
        return self

    def where(self, parameter: str, pattern: str) -> RouteGroupBuilder:
        """Add a path constraint inherited by each child route.

        Args:
            parameter: Name of a path parameter used by a child route.
            pattern: Trusted regular expression for that parameter.

        Returns:
            This builder for further fluent configuration.
        """
        constraints = dict(self._attributes.constraints)
        constraints[parameter] = pattern
        self._attributes = replace(
            self._attributes,
            constraints=MappingProxyType(constraints),
        )
        return self

    def defaults(self, values: Mapping[str, object]) -> RouteGroupBuilder:
        """Add default parameter values inherited by child routes.

        Args:
            values: Route parameter names mapped to default values.

        Returns:
            This builder for further fluent configuration.
        """
        defaults = dict(self._attributes.defaults)
        defaults.update(values)
        self._attributes = replace(
            self._attributes,
            defaults=MappingProxyType(defaults),
        )
        return self

    def domain(self, value: str) -> RouteGroupBuilder:
        """Set an exact host constraint inherited by child routes.

        Args:
            value: Host name without scheme, port, or wildcard.

        Returns:
            This builder for further fluent configuration.
        """
        self._attributes = replace(
            self._attributes,
            domain_name=value,
        )
        return self

    @contextmanager
    def group(self) -> Generator[None, None, None]:
        """Apply this group while preserving nested and concurrent state.

        Yields:
            Control while route declarations inherit these attributes.
        """
        with self._router.group_context(self._attributes):
            yield


def _normalize_prefix(value: str) -> str:
    """Normalize an optional route prefix to one absolute path.

    Args:
        value: Caller-provided path prefix.

    Returns:
        Empty text or a slash-prefixed path without a trailing slash.

    Raises:
        ValueError: If a prefix contains a query, fragment, or duplicate slash.
    """
    if not value:
        return ""
    if not value.startswith("/") or "//" in value or "?" in value:
        raise ValueError(_INVALID_PREFIX_ERROR)
    return value.rstrip("/")


def _join_paths(parent: str, child: str) -> str:
    """Join two canonical path prefixes without duplicating separators.

    Args:
        parent: Prefix inherited from an outer group.
        child: Prefix declared by an inner group.

    Returns:
        Combined absolute path prefix.
    """
    if not parent:
        return child
    if not child:
        return parent
    return f"{parent}/{child.lstrip('/')}"


__all__ = ["RouteGroup", "RouteGroupBuilder"]
