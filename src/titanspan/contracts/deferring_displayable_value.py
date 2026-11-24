"""Contracts for values that defer their display representation.

Separate protocols preserve native Python typing while accepting objects
that implement Laravel's original public method spelling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from titanspan.contracts.htmlable import Htmlable, LaravelHtmlable


@runtime_checkable
class DeferringDisplayableValue(Protocol):
    """Describe a value resolved only when it is rendered.

    Implementations may return plain text or an explicitly trusted HTML
    value. Callers remain responsible for escaping plain text for the output
    context in which it is rendered.
    """

    def resolve_displayable_value(
        self,
    ) -> Htmlable | LaravelHtmlable | str:
        """Resolve the display value at the point of rendering.

        Returns:
            Plain text or an HTML-aware value.
        """
        ...


@runtime_checkable
class LaravelDeferringDisplayableValue(Protocol):
    """Represent the upstream camelCase deferred-value contract.

    This protocol accepts Laravel-compatible implementations without
    requiring a second Python-named method.
    """

    def resolveDisplayableValue(
        self,
    ) -> Htmlable | LaravelHtmlable | str:
        """Resolve a value using Laravel's original method name.

        Returns:
            Plain text or an HTML-aware value.
        """
        ...


__all__ = [
    "DeferringDisplayableValue",
    "LaravelDeferringDisplayableValue",
]
