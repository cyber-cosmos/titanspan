"""Escape untrusted values for HTML text contexts.

Encoding follows Python's standard-library ``html.escape`` behavior. Custom
encoder overrides are stored in a ContextVar so concurrent tasks do not share
mutable process-wide configuration.
"""

from __future__ import annotations

import html
import re
from contextvars import ContextVar
from enum import Enum
from typing import TYPE_CHECKING, ClassVar

from titanspan.contracts import (
    DeferredDisplayValue,
    HtmlRenderable,
)
from titanspan.support.html_string import HtmlString

if TYPE_CHECKING:
    from collections.abc import Callable

type HtmlEncodable = (
    str
    | int
    | float
    | bool
    | None
    | Enum
    | HtmlRenderable
    | DeferredDisplayValue
)
type HtmlEncoder = Callable[[str, bool], str]

_ENTITY_PATTERN = re.compile(
    r"(&(?:#[0-9]+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);)"
)
_ENCODER_CONTEXT: ContextVar[HtmlEncoder | None] = ContextVar(
    "titanspan_html_encoder",
    default=None,
)


class EncodedHtmlString(HtmlString):
    """Escape scalar content while preserving explicitly HtmlRenderable values.

    Attributes:
        _encoded_value: The original input awaiting conversion.
        _double_encode: Whether existing character entities are escaped.

    Notes:
        This class escapes HTML text and attribute characters. It does not
        sanitize URLs, CSS, JavaScript, or arbitrary HTML fragments.
    """

    _encoder_context: ClassVar[ContextVar[HtmlEncoder | None]] = (
        _ENCODER_CONTEXT
    )

    def __init__(
        self,
        html: HtmlEncodable = "",
        double_encode: bool = True,
    ) -> None:
        """Create a value that is escaped when rendered.

        Args:
            html: A scalar, enum, or explicitly trusted HTML value.
            double_encode: Whether existing character entities are escaped.
        """
        super().__init__("")
        self._encoded_value = html
        self._double_encode = double_encode

    @staticmethod
    def convert(
        value: str | None,
        with_quote: bool = True,
        double_encode: bool = True,
    ) -> str:
        """Escape text for an HTML text or quoted attribute context.

        Args:
            value: The source text, or ``None`` for an empty value.
            with_quote: Whether to escape quote characters.
            double_encode: Whether valid-looking entities are escaped.

        Returns:
            Escaped HTML text.
        """
        text = "" if value is None else value
        escaped = html.escape(text, quote=with_quote).replace(
            "&#x27;",
            "&#039;",
        )
        if double_encode:
            return escaped

        pieces = _ENTITY_PATTERN.split(text)
        return "".join(
            piece
            if _ENTITY_PATTERN.fullmatch(piece) is not None
            else html.escape(piece, quote=with_quote).replace(
                "&#x27;",
                "&#039;",
            )
            for piece in pieces
        )

    def to_html(self) -> str:
        """Render the input using a context-local override or safe defaults.

        Returns:
            The escaped value, or existing trusted HTML unchanged.
        """
        value = self._encoded_value
        if isinstance(value, DeferredDisplayValue):
            value = value.resolve_displayable_value()
        if isinstance(value, HtmlRenderable):
            return value.to_html()
        if isinstance(value, Enum):
            enum_value = value.value
            if isinstance(enum_value, (str, int, float, bool)):
                value = enum_value
            else:
                value = value.name
        if isinstance(value, bool):
            text = "1" if value else ""
        elif value is None:
            text = ""
        else:
            text = str(value)

        encoder = self._encoder_context.get()
        if encoder is not None:
            return encoder(text, self._double_encode)
        return self.convert(text, double_encode=self._double_encode)

    def is_empty(self) -> bool:
        """Check whether this value renders to an empty string.

        Returns:
            Whether the input is null or empty text.
        """
        return self._encoded_value is None or self._encoded_value == ""

    is_not_empty = HtmlString.is_not_empty

    @classmethod
    def encode_using(cls, factory: HtmlEncoder | None = None) -> None:
        """Set or clear the active execution context's encoder override.

        Args:
            factory: A callable accepting source text and double-encode mode.
                ``None`` restores the standard-library implementation.
        """
        cls._encoder_context.set(factory)

    @classmethod
    def flush_state(cls) -> None:
        """Clear the active execution context's encoder override.

        The standard-library HTML encoder is used after this call.
        """
        cls._encoder_context.set(None)


__all__ = ["EncodedHtmlString", "HtmlEncodable", "HtmlEncoder"]
