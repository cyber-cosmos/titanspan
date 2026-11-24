"""Represent trusted HTML without applying automatic escaping.

This type is intended for markup created by trusted application code. It also
implements ``__html__`` for interoperability with HTML-aware Python tools.
"""

from __future__ import annotations

from titanspan.contracts import Htmlable


class HtmlString(Htmlable):
    """Wrap trusted HTML and expose explicit rendering operations.

    Attributes:
        _html: The original trusted markup, or ``None``.

    Security:
        Never construct this class from untrusted user input without a
        context-appropriate escaping or sanitization step.
    """

    def __init__(self, html: str | None = "") -> None:
        """Create a wrapper around trusted markup.

        Args:
            html: The markup to preserve, or ``None`` for an empty string.
        """
        self._html = html

    def to_html(self) -> str:
        """Return the original markup without escaping.

        Returns:
            The wrapped HTML, with ``None`` normalized to an empty string.
        """
        return self._html or ""

    def is_empty(self) -> bool:
        """Check whether the wrapped value is empty.

        Returns:
            Whether the value is ``None`` or an empty string.
        """
        return self._html is None or self._html == ""

    def is_not_empty(self) -> bool:
        """Check whether the wrapped value contains any characters.

        Returns:
            Whether the value is non-empty.
        """
        return not self.is_empty()

    def __str__(self) -> str:
        """Return markup through Python's string conversion protocol.

        Returns:
            The wrapped HTML.
        """
        return self.to_html()

    def __html__(self) -> str:
        """Return markup for compatible auto-escaping template engines.

        Returns:
            The trusted HTML representation.
        """
        return self.to_html()

    toHtml = to_html
    isEmpty = is_empty
    isNotEmpty = is_not_empty


__all__ = ["HtmlString"]
