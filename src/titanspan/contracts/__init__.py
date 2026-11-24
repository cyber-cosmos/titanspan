"""Typed service protocols and abstraction boundaries.

Contracts remain independent of concrete infrastructure implementations.
"""

from titanspan.contracts.deferring_displayable_value import (
    DeferringDisplayableValue,
    LaravelDeferringDisplayableValue,
)
from titanspan.contracts.htmlable import Htmlable, LaravelHtmlable
from titanspan.contracts.message_bag import (
    MessageBagData,
    MessageKey,
    MessageProvider,
)

__all__ = [
    "DeferringDisplayableValue",
    "Htmlable",
    "LaravelDeferringDisplayableValue",
    "LaravelHtmlable",
    "MessageBagData",
    "MessageKey",
    "MessageProvider",
]
