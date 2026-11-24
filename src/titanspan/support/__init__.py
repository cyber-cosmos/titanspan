"""Expose Titanspan's shared support utilities and compatibility helpers.

The module exports array operations, nested-data helpers, null-safe optional
values, macro and conditional mixins, and typed support exceptions.
"""

from titanspan.support.arr import Arr
from titanspan.support.conditionable import Conditionable
from titanspan.support.encoded_html_string import EncodedHtmlString
from titanspan.support.exceptions import (
    ArrayConversionError,
    ArrayMutationError,
    ArrayValueError,
    AsyncCallbackUsageError,
    InvalidMacroCallbackError,
    InvalidMacroNameError,
    InvalidSortCriterionError,
    MacroNotFoundError,
    MultipleMatchingArrayItemsError,
    NoMatchingArrayItemError,
    RandomSelectionError,
)
from titanspan.support.fluent import Fluent
from titanspan.support.helpers import (
    HigherOrderTapProxy,
    blank,
    data_fill,
    data_forget,
    data_get,
    data_has,
    data_set,
    e,
    enum_value,
    filled,
    head,
    last,
    tap,
    tap_async,
    throw_if,
    throw_unless,
    transform,
    value,
    with_,
)
from titanspan.support.html_string import HtmlString
from titanspan.support.macroable import Macroable
from titanspan.support.message_bag import MessageBag
from titanspan.support.optional import Optional, optional, optional_async
from titanspan.support.str import Str
from titanspan.support.stringable import Stringable
from titanspan.support.tappable import Tappable

__all__ = [
    "Arr",
    "ArrayConversionError",
    "ArrayMutationError",
    "ArrayValueError",
    "AsyncCallbackUsageError",
    "Conditionable",
    "EncodedHtmlString",
    "Fluent",
    "HigherOrderTapProxy",
    "HtmlString",
    "InvalidMacroCallbackError",
    "InvalidMacroNameError",
    "InvalidSortCriterionError",
    "MacroNotFoundError",
    "Macroable",
    "MessageBag",
    "MultipleMatchingArrayItemsError",
    "NoMatchingArrayItemError",
    "Optional",
    "RandomSelectionError",
    "Str",
    "Stringable",
    "Tappable",
    "blank",
    "data_fill",
    "data_forget",
    "data_get",
    "data_has",
    "data_set",
    "e",
    "enum_value",
    "filled",
    "head",
    "last",
    "optional",
    "optional_async",
    "tap",
    "tap_async",
    "throw_if",
    "throw_unless",
    "transform",
    "value",
    "with_",
]
