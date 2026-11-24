"""Define Python and Laravel-compatible contracts for trusted HTML values.

Structural protocols let rendering adapters accept either Titanspan's
snake_case methods or Laravel's original camelCase methods.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Htmlable(Protocol):
    """Expose an explicitly trusted HTML representation.

    Implementations are responsible for ensuring that returned markup is
    safe for the rendering context in which it is used.
    """

    def to_html(self) -> str:
        """Return trusted HTML markup.

        Returns:
            The HTML representation.
        """
        ...


@runtime_checkable
class LaravelHtmlable(Protocol):
    """Represent an object implementing Laravel's original HTML contract.

    This protocol accepts upstream-compatible objects without requiring them
    to implement Titanspan's Python-named method as well.
    """

    def toHtml(self) -> str:
        """Return trusted markup using Laravel's camelCase spelling.

        Returns:
            The HTML representation.
        """
        ...
        ...


__all__ = ["Htmlable", "LaravelHtmlable"]
