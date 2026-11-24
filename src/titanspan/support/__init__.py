"""Expose Titanspan's shared support utilities and compatibility helpers.

The module exports array operations, nested-data helpers, null-safe optional
values, macro and conditional mixins, and typed support exceptions.
"""

from titanspan.support.arr import Arr
from titanspan.support.benchmark import Benchmark
from titanspan.support.binary_codec import BinaryCodec
from titanspan.support.conditionable import Conditionable
from titanspan.support.configuration_url_parser import ConfigurationUrlParser
from titanspan.support.encoded_html_string import EncodedHtmlString
from titanspan.support.env import Env
from titanspan.support.exceptions import (
    ArrayConversionError,
    ArrayMutationError,
    ArrayValueError,
    AsyncCallbackUsageError,
    InvalidMacroCallbackError,
    InvalidMacroNameError,
    InvalidNumberParseTypeError,
    InvalidNumberPrecisionError,
    InvalidNumberPrecisionTypeError,
    InvalidNumberStepError,
    InvalidNumberValueError,
    InvalidRetryConfigurationError,
    InvalidRetryConfigurationTypeError,
    InvalidSortCriterionError,
    MacroNotFoundError,
    MissingNumberDependencyError,
    MultipleMatchingArrayItemsError,
    NoMatchingArrayItemError,
    NonAdvancingNumberRangeError,
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
    env,
    filled,
    head,
    last,
    retry,
    retry_async,
    tap,
    tap_async,
    throw_if,
    throw_unless,
    transform,
    value,
    with_,
)
from titanspan.support.html_string import HtmlString
from titanspan.support.lottery import Lottery
from titanspan.support.macroable import Macroable
from titanspan.support.message_bag import MessageBag
from titanspan.support.namespaced_item_resolver import NamespacedItemResolver
from titanspan.support.number import Number, NumberParseType
from titanspan.support.optional import Optional, optional, optional_async
from titanspan.support.sleep import Sleep
from titanspan.support.str import Str
from titanspan.support.stringable import Stringable
from titanspan.support.tappable import Tappable
from titanspan.support.timebox import Timebox
from titanspan.support.uri import Uri, UriUrlGenerator
from titanspan.support.uri_query_string import UriQueryString

__all__ = [
    "Arr",
    "ArrayConversionError",
    "ArrayMutationError",
    "ArrayValueError",
    "AsyncCallbackUsageError",
    "Benchmark",
    "BinaryCodec",
    "Conditionable",
    "ConfigurationUrlParser",
    "EncodedHtmlString",
    "Env",
    "Fluent",
    "HigherOrderTapProxy",
    "HtmlString",
    "InvalidMacroCallbackError",
    "InvalidMacroNameError",
    "InvalidNumberParseTypeError",
    "InvalidNumberPrecisionError",
    "InvalidNumberPrecisionTypeError",
    "InvalidNumberStepError",
    "InvalidNumberValueError",
    "InvalidRetryConfigurationError",
    "InvalidRetryConfigurationTypeError",
    "InvalidSortCriterionError",
    "Lottery",
    "MacroNotFoundError",
    "Macroable",
    "MessageBag",
    "MissingNumberDependencyError",
    "MultipleMatchingArrayItemsError",
    "NamespacedItemResolver",
    "NoMatchingArrayItemError",
    "NonAdvancingNumberRangeError",
    "Number",
    "NumberParseType",
    "Optional",
    "RandomSelectionError",
    "Sleep",
    "Str",
    "Stringable",
    "Tappable",
    "Timebox",
    "Uri",
    "UriQueryString",
    "UriUrlGenerator",
    "blank",
    "data_fill",
    "data_forget",
    "data_get",
    "data_has",
    "data_set",
    "e",
    "enum_value",
    "env",
    "filled",
    "head",
    "last",
    "optional",
    "optional_async",
    "retry",
    "retry_async",
    "tap",
    "tap_async",
    "throw_if",
    "throw_unless",
    "transform",
    "value",
    "with_",
]
