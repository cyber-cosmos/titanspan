"""Declare consumer-specific dependency selection rules.

Builders are short-lived registration interfaces. The container stores
immutable rules and applies them only while composing its dependency graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Sequence


class ContextualKind(Enum):
    """Select how a contextual constructor value is produced.

    Each kind maps to a typed dependency source in the private graph adapter.
    """

    IMPLEMENTATION = "implementation"
    VALUE = "value"
    CONFIG = "config"
    NAMED = "named"
    TAGGED = "tagged"


@dataclass(frozen=True, slots=True)
class ContextualBinding:
    """Store one immutable consumer and dependency selection rule.

    Attributes:
        consumers: Classes whose constructors receive the selected value.
        dependency: Constructor parameter type or exact parameter name.
        kind: Source used to produce the injected value.
        value: Implementation, configured key, tag, or explicit value.
    """

    consumers: tuple[type[object], ...]
    dependency: Hashable
    kind: ContextualKind
    value: object


class ContextualBindingBuilder:
    """Choose one dependency selector for one or more consumers.

    The returned needs builder owns the eventual registration operation.
    """

    def __init__(
        self,
        consumers: Sequence[type[object]],
        register: Callable[
            [tuple[type[object], ...], Hashable, ContextualKind, object],
            None,
        ],
    ) -> None:
        """Retain consumer keys and the container's registration callback.

        Args:
            consumers: Non-empty consumer type sequence.
            register: Native registration method owned by the container.
        """
        self._consumers = tuple(consumers)
        self._register = register

    def needs(
        self,
        dependency: Hashable,
    ) -> NeedsBindingBuilder:
        """Select a typed service or constructor parameter by name.

        Args:
            dependency: Type annotation or exact constructor parameter name.

        Returns:
            A builder for selecting the dependency's value source.
        """
        return NeedsBindingBuilder(
            self._consumers,
            dependency,
            self._register,
        )

    _consumers: tuple[type[object], ...]
    _register: Callable[
        [tuple[type[object], ...], Hashable, ContextualKind, object],
        None,
    ]


class NeedsBindingBuilder:
    """Choose a concrete, configured, tagged, or literal dependency value.

    Rules are exact to their consumer and either the dependency type or name.
    """

    def __init__(
        self,
        consumers: Sequence[type[object]],
        dependency: Hashable,
        register: Callable[
            [tuple[type[object], ...], Hashable, ContextualKind, object],
            None,
        ],
    ) -> None:
        """Retain the registration target for one contextual rule.

        Args:
            consumers: Consumer classes that receive the selected value.
            dependency: Type or parameter name matched in those constructors.
            register: Container-owned immutable rule registration method.
        """
        self._consumers = tuple(consumers)
        self._dependency = dependency
        self._register = register

    def give[ServiceT](
        self,
        implementation: type[ServiceT] | Callable[..., ServiceT],
    ) -> None:
        """Resolve a concrete implementation or typed factory.

        Args:
            implementation: Class or annotated factory used for the value.
        """
        self._add(ContextualKind.IMPLEMENTATION, implementation)

    def give_value(self, value: object) -> None:
        """Supply one literal value without treating callables as factories.

        Args:
            value: Explicitly supplied object for the selected parameter.
        """
        self._add(ContextualKind.VALUE, value)

    def give_config(self, key: str) -> None:
        """Resolve a value from the registered configuration reader.

        Args:
            key: Dotted key retrieved from ``ConfigReader``.
        """
        self._add(ContextualKind.CONFIG, key)

    def give_tagged(self, name: str) -> None:
        """Resolve ordered services from the named container tag.

        Args:
            name: Registered tag whose services fill the dependency.
        """
        self._add(ContextualKind.TAGGED, name)

    def give_named(self, name: str) -> None:
        """Resolve one dependency through a registered alias.

        Args:
            name: Registered service alias selected for this parameter.
        """
        self._add(ContextualKind.NAMED, name)

    def _add(self, kind: ContextualKind, value: object) -> None:
        """Commit one rule through the owning container registry.

        Args:
            kind: Source used to produce the injected constructor value.
            value: Source metadata interpreted during graph composition.
        """
        self._register(self._consumers, self._dependency, kind, value)

    _consumers: tuple[type[object], ...]
    _dependency: Hashable
    _register: Callable[
        [tuple[type[object], ...], Hashable, ContextualKind, object],
        None,
    ]


__all__ = [
    "ContextualBinding",
    "ContextualBindingBuilder",
    "ContextualKind",
    "NeedsBindingBuilder",
]
