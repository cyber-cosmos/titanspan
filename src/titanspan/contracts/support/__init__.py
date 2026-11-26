"""Expose established Support display and message contracts.

These structural interfaces provide small extension points for display and
message functionality owned by the Support component.
"""

from titanspan.contracts.support.deferred_display_value import (
    DeferredDisplayValue,
)
from titanspan.contracts.support.html_renderable import HtmlRenderable
from titanspan.contracts.support.message_bag import (
    MessageBagProtocol,
    MessageKey,
    MessageProvider,
)

__all__ = [
    "DeferredDisplayValue",
    "HtmlRenderable",
    "MessageBagProtocol",
    "MessageKey",
    "MessageProvider",
]
