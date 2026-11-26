"""Define a native contract for explicitly trusted HTML values.

Structural typing lets rendering adapters accept safe markup without
depending on a concrete template or HTML library.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class HtmlRenderable(Protocol):
    """Expose an explicitly trusted HTML representation.

    Implementations are responsible for ensuring that returned markup is safe
    for the rendering context in which it is used.
    """

    def to_html(self) -> str:
        """Return trusted HTML markup.

        Returns:
            The HTML representation.
        """
        ...


__all__ = ["HtmlRenderable"]
