"""Define a contract for values resolved at their point of display.

Deferred values are resolved by the rendering owner, which then applies
context-appropriate escaping to ordinary text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from titanspan.contracts.support.html_renderable import HtmlRenderable


@runtime_checkable
class DeferredDisplayValue(Protocol):
    """Describe a value resolved only when it is rendered.

    Implementations may return plain text or an explicitly trusted HTML
    value. Callers remain responsible for escaping plain text for its output
    context.
    """

    def resolve_displayable_value(self) -> HtmlRenderable | str:
        """Resolve the value at the point of rendering.

        Returns:
            Plain text or a trusted HTML representation.
        """
        ...


__all__ = ["DeferredDisplayValue"]
