r"""Provide nested-data utilities for Python mappings and sequences.

Operations work with Python mappings and sequences. Mutable helpers require
mutable mappings or lists; they never mutate an immutable input.
"""

from __future__ import annotations

import json
import locale
import random
import re
from collections.abc import (
    Callable,
    Hashable,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    MutableSequence,
    Sequence,
)
from decimal import Decimal, InvalidOperation
from itertools import product
from typing import TypeGuard, TypeVar, cast
from urllib.parse import quote, urlencode

from titanspan.support.exceptions import (
    ArrayConversionError,
    ArrayMutationError,
    ArrayValueError,
    InvalidSortCriterionError,
    MultipleMatchingArrayItemsError,
    NoMatchingArrayItemError,
    RandomSelectionError,
)

T = TypeVar("T")
K = TypeVar("K", bound=Hashable)
V = TypeVar("V")
Default = TypeVar("Default")
TWO_SORT_FIELDS = 2
_SORT_REGULAR = 0
_SORT_NUMERIC = 1
_SORT_STRING = 2
_SORT_LOCALE_STRING = 5
_SORT_NATURAL = 6
_SORT_FLAG_CASE = 8
type MutableArray[K: Hashable, V] = MutableMapping[K, V] | MutableSequence[V]
type ArrayData = dict[Hashable, object] | list[object]


def _natural_sort_value(value: str, case_sensitive: bool) -> str:
    """Normalize a string into a natural, numerically aware key.

    Args:
        value: The input text.
        case_sensitive: Whether letter case affects the result.

    Returns:
        A stable string key with digit runs ordered by numeric magnitude.
    """
    normalized: list[str] = []
    for segment in re.split(r"(\d+)", value):
        if segment.isdecimal():
            normalized.append(f"0{len(segment):020d}{segment}")
        else:
            text = segment if case_sensitive else segment.casefold()
            normalized.append(f"1{text}")
    return "".join(normalized)


def _decimal_sort_value(value: object) -> Decimal:
    """Convert a value to a finite decimal sort key.

    Args:
        value: The source value.

    Returns:
        Its decimal value, or zero for invalid and non-finite inputs.
    """
    text = ("1" if value else "0") if isinstance(value, bool) else str(value)
    try:
        result = Decimal(text)
    except InvalidOperation:
        return Decimal(0)
    return result if result.is_finite() else Decimal(0)


def _text_sort_value(
    value: object,
    mode: int,
    case_sensitive: bool,
) -> str:
    """Convert a value to the selected string ordering key.

    Args:
        value: The source value.
        mode: The configured string sorting mode.
        case_sensitive: Whether letter case affects the result.

    Returns:
        A normalized string sort key.
    """
    text = str(value)
    if mode == _SORT_LOCALE_STRING:
        return locale.strxfrm(text)
    if mode == _SORT_NATURAL:
        return _natural_sort_value(text, case_sensitive)
    return text if case_sensitive else text.casefold()


def _sort_representation(
    value: object,
    options: int,
) -> tuple[int, Decimal | str]:
    """Return a comparable category and normalized sort value.

    Args:
        value: The value to normalize.
        options: A sort mode and its flags.

    Returns:
        A stable category and typed payload pair.
    """
    mode = options & ~_SORT_FLAG_CASE
    case_sensitive = not bool(options & _SORT_FLAG_CASE)
    if mode == _SORT_NUMERIC:
        return 0, _decimal_sort_value(value)
    if mode in (_SORT_STRING, _SORT_LOCALE_STRING, _SORT_NATURAL):
        return 1, _text_sort_value(value, mode, case_sensitive)
    if value is None:
        return 4, ""
    if isinstance(value, (bool, int, float, Decimal)):
        decimal_value = _decimal_sort_value(value)
        if decimal_value.is_finite():
            return 0, decimal_value
    if isinstance(value, str):
        return 1, value
    if isinstance(value, bytes):
        return 2, value.hex()
    return 3, repr(value)


class _SortOrder:
    """Provide deterministic ordering for heterogeneous Python values.

    Numeric, string, byte, missing, and other values occupy stable type
    categories. This avoids coercive comparisons while supporting Python
    collections that mix otherwise incomparable values.
    """

    def __init__(
        self,
        value: object,
        descending: bool,
        options: int = _SORT_REGULAR,
    ) -> None:
        """Create an ordering key for one value.

        Args:
            value: The value used as a sort key.
            descending: Whether the key sorts in reverse order.
            options: A sort mode and case flag.
        """
        self.descending = descending
        self.category, self.value = _sort_representation(value, options)

    def __lt__(self, other: _SortOrder, /) -> bool:
        """Compare two sort keys using category and normalized values.

        Args:
            other: The other normalized sort key.

        Returns:
            Whether this key sorts before ``other``.
        """
        if self.category != other.category:
            result = self.category < other.category
            return not result if self.descending else result
        match self.value, other.value:
            case Decimal() as left, Decimal() as right:
                result = left < right
            case str() as left, str() as right:
                result = left < right
            case _:
                return False
        if self.value == other.value:
            return False
        return not result if self.descending else result


def _is_sort_pair(value: object) -> TypeGuard[tuple[object, object]]:
    """Check for a two-item selector and sort-direction tuple.

    Args:
        value: The candidate selector.

    Returns:
        Whether the value is a two-item tuple.
    """
    if not isinstance(value, tuple):
        return False
    # Tuple elements are read-only and covariant, so object is a safe view.
    pair = cast("Sequence[object]", value)
    return len(pair) == TWO_SORT_FIELDS


class _Missing:
    """Represent missing data separately from a stored ``None`` value.

    A dedicated sentinel preserves the distinction between an absent key
    and a key whose value is explicitly ``None``.
    """


_MISSING = _Missing()
_OMITTED = object()


def _is_mapping(value: object) -> TypeGuard[Mapping[Hashable, object]]:
    """Narrow an unknown object to the supported mapping protocol.

    Args:
        value: The candidate mapping.

    Returns:
        Whether the value implements ``Mapping``.
    """
    return isinstance(value, Mapping)


def _is_mutable_mapping(
    value: object,
) -> TypeGuard[MutableMapping[Hashable, object]]:
    """Narrow an unknown object to a mutable mapping.

    Args:
        value: The candidate mapping.

    Returns:
        Whether the value implements ``MutableMapping``.
    """
    return isinstance(value, MutableMapping)


def _is_mutable_sequence(
    value: object,
) -> TypeGuard[MutableSequence[object]]:
    """Narrow an unknown object to a mutable sequence.

    Args:
        value: The candidate sequence.

    Returns:
        Whether the value implements ``MutableSequence``.
    """
    return isinstance(value, MutableSequence)


def _is_iterable(value: object) -> TypeGuard[Iterable[object]]:
    """Narrow an unknown object to an iterable of objects.

    Args:
        value: The candidate iterable.

    Returns:
        Whether the value implements ``Iterable``.
    """
    return isinstance(value, Iterable)


def _is_positional_iterable(value: object) -> TypeGuard[Iterable[object]]:
    """Check for an iterable that can be treated as a positional array.

    Args:
        value: The candidate value.

    Returns:
        Whether the value is a non-text iterable.
    """
    return _is_sequence(value) or (
        _is_iterable(value) and not isinstance(value, (str, bytes, bytearray))
    )


def _is_sequence(value: object) -> TypeGuard[Sequence[object]]:
    """Check for a positional collection without treating text as a list.

    Args:
        value: The candidate collection.

    Returns:
        Whether the value is a non-text sequence.
    """
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


def _iter_items(value: object) -> Iterator[tuple[Hashable, object]]:
    """Yield keyed items without materializing a complete iterable.

    Args:
        value: The source mapping or sequence.

    Returns:
        An iterator of key and value pairs.
    """
    if _is_mapping(value):
        yield from value.items()
    elif _is_positional_iterable(value):
        yield from enumerate(value)


def _items(value: object) -> list[tuple[Hashable, object]]:
    """Materialize keyed items from mappings and positional iterables.

    Args:
        value: The source mapping or sequence.

    Returns:
        An ordered list of key and value pairs.
    """
    return list(_iter_items(value))


def _index(key: object) -> int | None:
    """Parse a non-negative sequence index from an integer-like key.

    Args:
        key: A mapping key or sequence index.

    Returns:
        The parsed index, or ``None`` when it is not a valid index.
    """
    if isinstance(key, bool):
        return None
    if isinstance(key, int):
        return key if key >= 0 else None
    if isinstance(key, str) and key.isdecimal():
        return int(key)
    return None


def _read(value: object, key: object) -> object:
    """Read a direct child while preserving missing-value information.

    Args:
        value: The candidate mapping or sequence.
        key: The key or index to read.

    Returns:
        The child value or the private missing sentinel.
    """
    if _is_mapping(value) and isinstance(key, Hashable):
        try:
            return value.get(key, _MISSING)
        except TypeError:
            return _MISSING
    if _is_sequence(value):
        index = _index(key)
        if index is not None and index < len(value):
            return value[index]
    return _MISSING


def _default_value(default: object) -> object:
    """Resolve a lazy default value.

    Args:
        default: A value or zero-argument callable returning the value.

    Returns:
        The default value, evaluating a callable only when requested.
    """
    if callable(default):
        # This dynamic boundary accepts a zero-argument lazy default.
        lazy_default = cast("Callable[[], object]", default)
        return lazy_default()
    return default


def _path(key: str | int | None) -> Sequence[object] | None:
    """Split dot notation while keeping a literal top-level key available.

    Args:
        key: A path, direct key, or ``None``.

    Returns:
        Path segments, or ``None`` for a request for the whole value.
    """
    if key is None:
        return None
    if isinstance(key, str):
        return key.split(".")
    return [key]


def _write_child(parent: object, key: object, value: object) -> None:
    """Write a child to a mutable mapping or list.

    Args:
        parent: The mutable container receiving the value.
        key: The mapping key or sequence index.
        value: The value to store.

    Raises:
        TypeError: If a list key is not a non-negative integer index.
    """
    if _is_mutable_mapping(parent) and isinstance(key, Hashable):
        parent[key] = value
        return
    if _is_mutable_sequence(parent):
        index = _index(key)
        if index is None:
            message = "Sequence paths require non-negative integer keys."
            raise TypeError(message)
        while len(parent) <= index:
            parent.append(None)
        parent[index] = value
        return
    message = "The target must be a mutable mapping or sequence."
    raise TypeError(message)


def _delete_child(parent: object, key: object) -> None:
    """Delete a child from a mutable mapping or list when it exists.

    Args:
        parent: The mutable container to update.
        key: The mapping key or sequence index to remove.
    """
    if _is_mutable_mapping(parent) and isinstance(key, Hashable):
        parent.pop(key, None)
        return
    if _is_mutable_sequence(parent):
        index = _index(key)
        if index is not None and index < len(parent):
            del parent[index]


def _invoke[V, K: Hashable, T](
    callback: Callable[[V, K], T],
    value: V,
    key: K,
) -> T:
    """Call a typed value-and-key callback.

    Args:
        callback: The callback to invoke.
        value: The current item.
        key: The current item key.

    Returns:
        The callback result.
    """
    return callback(value, key)


def _get_field(value: object, field: object) -> object:
    """Read a field from mappings, sequences, or Python objects.

    Args:
        value: The object to inspect.
        field: A dot-separated field path.

    Returns:
        The field value or ``None`` if any segment is absent.
    """
    if not isinstance(field, str):
        result = _read(value, field)
        return None if result is _MISSING else result
    current = value
    for part in field.split("."):
        result = _read(current, part)
        if result is _MISSING and not _is_mapping(current):
            result = cast("object", getattr(current, part, _MISSING))
        if result is _MISSING:
            return None
        current = result
    return current


def _array_data(value: object) -> ArrayData | None:
    """Convert a supported mapping, sequence, or iterable to array data.

    Args:
        value: The candidate Python value.

    Returns:
        A copied mapping or list, or ``None`` for unsupported values.
    """
    if _is_mapping(value):
        return dict(value)
    if _is_sequence(value):
        return list(value)
    if _is_iterable(value) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return list(value)
    return None


def _model_array_data(value: object) -> ArrayData | None:
    """Convert data exposed by a model-style Python object.

    Args:
        value: The candidate object.

    Returns:
        Converted model data, or ``None`` if no supported method exists.
    """
    for method_name in ("model_dump", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            converted: object = method()
            result = _array_data(converted)
            if result is not None:
                return result
    if hasattr(value, "__dict__"):
        attributes: object = vars(value)
        return _array_data(attributes)
    return None


def _json_array_data(value: object) -> ArrayData:
    """Convert JSON-serializable objects into mapping or sequence data.

    Args:
        value: The candidate value.

    Returns:
        A decoded mapping or list.

    Raises:
        ArrayConversionError: If JSON conversion does not yield array data.
    """
    try:
        encoded = json.dumps(value)
        decoded: object = json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise ArrayConversionError from error
    converted = _array_data(decoded)
    if converted is None:
        raise ArrayConversionError
    return converted


def _key_list(keys: object) -> list[object]:
    """Normalize one key or an iterable of keys.

    Args:
        keys: A key or key collection.

    Returns:
        A list containing the requested keys.
    """
    if isinstance(keys, (str, bytes)) or not _is_iterable(keys):
        return [keys]
    return list(keys)


def _query_pairs(value: object, prefix: str = "") -> list[tuple[str, str]]:
    """Flatten nested mappings into RFC 3986 query pairs.

    Args:
        value: The source value.
        prefix: The escaped parent key.

    Returns:
        Ordered key and value pairs suitable for URL encoding.
    """
    pairs: list[tuple[str, str]] = []
    if _is_mapping(value) or _is_sequence(value):
        for key, item in _items(value):
            child = f"{prefix}[{key}]" if prefix else str(key)
            pairs.extend(_query_pairs(item, child))
        return pairs
    if value is None:
        return pairs
    text = ("1" if value else "0") if isinstance(value, bool) else str(value)
    pairs.append((prefix, text))
    return pairs


def _resolve_sort_value(value: object, criterion: object) -> object:
    """Resolve a field path or callable used to sort a value.

    Args:
        value: The record being sorted.
        criterion: A field path or callable key selector.

    Returns:
        The resolved ordering value.

    Raises:
        InvalidSortCriterionError: If the criterion is unsupported.
    """
    if criterion is None:
        return value
    if isinstance(criterion, str):
        return _get_field(value, criterion)
    if callable(criterion):
        # Sorting specifications are dynamic by design; callers are narrowed
        # at the callback boundary and retain typed public signatures.
        callback = cast("Callable[[object], object]", criterion)
        return callback(value)
    raise InvalidSortCriterionError


def _sort_criteria(
    callback: object,
    descending: bool,
) -> list[tuple[object, bool]]:
    """Normalize one or more sort selectors and their directions.

    Args:
        callback: A selector, selector sequence, or ``None``.
        descending: The default direction for bare selectors.

    Returns:
        Normalized selector and direction pairs.

    Raises:
        InvalidSortCriterionError: If a selector or direction is invalid.
    """
    if callback is None or isinstance(callback, str) or callable(callback):
        return [(callback, descending)]
    if _is_sort_pair(callback):
        path, direction = callback
        if isinstance(path, str) and direction in (
            True,
            False,
            "asc",
            "desc",
            "ascending",
            "descending",
        ):
            selector = path
            reverse = direction in (True, "desc", "descending")
            return [(selector, reverse)]
    if not _is_sequence(callback):
        raise InvalidSortCriterionError
    criteria: list[tuple[object, bool]] = []
    for item in callback:
        if _is_sort_pair(item):
            path, direction = item
            if isinstance(path, str) and direction in (
                True,
                False,
                "asc",
                "desc",
                "ascending",
                "descending",
            ):
                reverse = direction in (True, "desc", "descending")
                criteria.append((path, reverse))
                continue
        if isinstance(item, str) or callable(item):
            criteria.append((item, descending))
            continue
        raise InvalidSortCriterionError
    return criteria


def _sort_array(
    array: object,
    callback: object,
    descending: bool,
) -> dict[Hashable, object] | list[object]:
    """Sort a mapping or iterable with stable multi-key ordering.

    Args:
        array: The source mapping or iterable.
        callback: The sort selector or sequence of selectors.
        descending: The default direction for unqualified selectors.

    Returns:
        A sorted dictionary for mappings and a list for other iterables.
    """
    items = _items(array)
    for criterion, reverse in reversed(_sort_criteria(callback, descending)):
        items.sort(
            key=lambda item: _SortOrder(
                _resolve_sort_value(item[1], criterion),
                reverse,
            )
        )
    if _is_mapping(array):
        return dict(items)
    return [value for _, value in items]


class Arr:
    """Expose static helpers for mapping-like data.

    Methods accept Python mappings and positional sequences where the
    operation is meaningful. Dot paths can traverse both forms. Mutating
    methods require a mutable mapping or list and mutate that object
    directly, reflecting Python's ordinary reference semantics.
    """

    SORT_REGULAR = _SORT_REGULAR
    SORT_NUMERIC = _SORT_NUMERIC
    SORT_STRING = _SORT_STRING
    SORT_LOCALE_STRING = _SORT_LOCALE_STRING
    SORT_NATURAL = _SORT_NATURAL
    SORT_FLAG_CASE = _SORT_FLAG_CASE

    @staticmethod
    def accessible(value: object) -> bool:
        """Return whether a value supports keyed access.

        Args:
            value: The value to inspect.

        Returns:
            Whether the value is a mapping or non-text sequence.
        """
        return isinstance(value, Mapping) or _is_sequence(value)

    @staticmethod
    def arrayable(value: object) -> bool:
        """Return whether a value can be converted to keyed items.

        Args:
            value: The value to inspect.

        Returns:
            Whether the value is a mapping, sequence, or iterable.
        """
        return Arr.accessible(value) or (
            isinstance(value, Iterable)
            and not isinstance(value, (str, bytes, bytearray))
        )

    @staticmethod
    def add(
        array: MutableArray[K, V],
        key: str | int,
        value: V,
    ) -> MutableArray[K, V]:
        """Add a value only when the resolved path currently yields ``None``.

        This operation treats an explicit ``None`` value like an absent
        value. Use ``has`` when key presence matters.

        Args:
            array: The mutable target.
            key: A direct key or dot-separated path.
            value: The value to add.

        Returns:
            The same mutated container.
        """
        if Arr.get(array, key) is None:
            Arr.set(array, key, value)
        return array

    @staticmethod
    def array(
        array: object,
        key: str | int | None,
        default: list[object] | None = None,
    ) -> dict[Hashable, object] | list[object]:
        """Return a nested value as a Python dictionary or list.

        Args:
            array: The source mapping or sequence.
            key: The path to resolve.
            default: A list used when the path is absent.

        Returns:
            A copied dictionary or list.

        Raises:
            ValueError: If the resolved value is not a mapping or sequence.
        """
        value = Arr.get(array, key, default)
        if _is_mapping(value):
            return dict(value)
        if _is_sequence(value):
            return list(value)
        raise ArrayValueError(key, "an array", value)

    @staticmethod
    def boolean(
        array: object,
        key: str | int | None,
        default: bool | None = None,
    ) -> bool:
        """Return a nested value only when it is a boolean.

        Args:
            array: The source mapping or sequence.
            key: The path to resolve.
            default: A boolean used when the path is absent.

        Returns:
            The resolved boolean.

        Raises:
            ValueError: If the resolved value is not a boolean.
        """
        value = Arr.get(array, key, default)
        if not isinstance(value, bool):
            raise ArrayValueError(key, "a boolean", value)
        return value

    @staticmethod
    def collapse(
        arrays: Iterable[object],
    ) -> list[object] | dict[Hashable, object]:
        """Merge a sequence of array-like values into one result.

        Numeric sequence keys are appended in order. Mapping keys are
        preserved, and later values replace earlier values with the same key.

        Args:
            arrays: An iterable of mappings and sequences.

        Returns:
            A list if every source is positional, otherwise a dictionary.
        """
        output: dict[Hashable, object] = {}
        positional: list[object] = []
        keyed = False
        next_index = 0
        for source in arrays:
            if _is_mapping(source):
                if not keyed:
                    # Flush earlier positional values before later mappings,
                    # Preserve input ordering when mappings follow sequences.
                    for value in positional:
                        output[next_index] = value
                        next_index += 1
                    positional.clear()
                keyed = True
                for key, value in source.items():
                    if isinstance(key, int) and not isinstance(key, bool):
                        output[next_index] = value
                        next_index += 1
                    else:
                        output[key] = value
            elif _is_sequence(source):
                if keyed:
                    for value in source:
                        output[next_index] = value
                        next_index += 1
                else:
                    positional.extend(source)
        return output if keyed else positional

    @staticmethod
    def cross_join(*arrays: Iterable[object]) -> list[list[object]]:
        """Return the Cartesian product of input iterables.

        Args:
            arrays: The iterables whose items form product rows.

        Returns:
            Product rows in left-to-right input order.
        """
        return [list(row) for row in product(*arrays)]

    @staticmethod
    def divide(array: Mapping[K, V]) -> tuple[list[K], list[V]]:
        """Split a mapping into ordered keys and values.

        Args:
            array: The source mapping.

        Returns:
            A pair containing keys followed by values.
        """
        return list(array), list(array.values())

    @staticmethod
    def dot(
        array: object,
        prepend: str = "",
        depth: int | float = float("inf"),
    ) -> dict[str, object]:
        """Flatten nested mappings and sequences using dotted keys.

        Empty nested containers are retained as leaf values.

        Args:
            array: The source mapping or sequence.
            prepend: A prefix for every generated key.
            depth: The maximum number of nested levels to expand.

        Returns:
            A dictionary keyed by flattened paths.
        """
        result: dict[str, object] = {}
        stack: list[tuple[object, str, int]] = [(array, prepend, 0)]
        while stack:
            current, prefix, level = stack.pop()
            for key, value in reversed(_items(current)):
                path = f"{prefix}{key}"
                nested = Arr.accessible(value) and bool(_items(value))
                if nested and level < depth:
                    stack.append((value, f"{path}.", level + 1))
                else:
                    result[path] = value
        return dict(reversed(list(result.items())))

    @staticmethod
    def undot(array: Mapping[str, object]) -> dict[Hashable, object]:
        """Expand dotted mapping keys into nested dictionaries.

        Args:
            array: A mapping whose string keys may contain dots.

        Returns:
            A nested dictionary. Later paths replace earlier leaf values.
        """
        result: dict[Hashable, object] = {}
        for key, value in array.items():
            Arr.set(result, str(key), value)
        return result

    @staticmethod
    def except_(
        array: Mapping[K, V],
        keys: object,
    ) -> dict[K, V]:
        """Return a copy without the requested direct or dotted paths.

        Args:
            array: The source mapping.
            keys: One key or an iterable of keys.

        Returns:
            A new mapping with each requested path removed.
        """
        result: dict[K, V] = dict(array)
        Arr.forget(result, keys)
        return result

    @staticmethod
    def except_values(
        array: Mapping[K, V],
        values: object,
        strict: bool = False,
    ) -> dict[K, V]:
        """Return entries whose values are not in the exclusion set.

        Args:
            array: The source mapping.
            values: One value or an iterable of values to remove.
            strict: Require matching Python types as well as equality.

        Returns:
            A new mapping retaining source key order.
        """
        excluded = _key_list(values)
        return {
            key: value
            for key, value in array.items()
            if not any(
                type(value) is type(candidate) and value == candidate
                if strict
                else value == candidate
                for candidate in excluded
            )
        }

    @staticmethod
    def exists(array: object, key: object) -> bool:
        """Check whether a direct key exists, including a stored ``None``.

        Args:
            array: The mapping or sequence to inspect.
            key: The direct key or sequence index.

        Returns:
            Whether the key is present.
        """
        return _read(array, key) is not _MISSING

    @staticmethod
    def first(
        array: object,
        callback: Callable[[object, Hashable], bool] | None = None,
        default: Default | Callable[[], Default] | None = None,
    ) -> object | Default | None:
        """Return the first value satisfying a predicate or the first value.

        Args:
            array: The mapping, sequence, or iterable to inspect.
            callback: An optional value and key predicate.
            default: A value or lazy value used if nothing matches.

        Returns:
            The selected value or resolved default.
        """
        items = _iter_items(array)
        if callback is None:
            first_item = next(items, None)
            return (
                first_item[1]
                if first_item is not None
                else _default_value(default)
            )
        for key, value in items:
            if _invoke(callback, value, key):
                return value
        return _default_value(default)

    @staticmethod
    def last(
        array: object,
        callback: Callable[[object, Hashable], bool] | None = None,
        default: Default | Callable[[], Default] | None = None,
    ) -> object | Default | None:
        """Return the final value satisfying a predicate or the final value.

        Args:
            array: The mapping, sequence, or iterable to inspect.
            callback: An optional value and key predicate.
            default: A value or lazy value used if nothing matches.

        Returns:
            The selected value or resolved default.
        """
        last_value: object = _MISSING
        for key, value in _iter_items(array):
            if callback is None or _invoke(callback, value, key):
                last_value = value
        return (
            last_value
            if last_value is not _MISSING
            else _default_value(default)
        )

    @staticmethod
    def take(
        array: Mapping[K, V] | Sequence[V], limit: int
    ) -> dict[K, V] | list[V]:
        """Take values from the beginning or end of a mapping or sequence.

        Args:
            array: The source container.
            limit: A positive leading count or negative trailing count.

        Returns:
            A container of the same broad shape with selected values.
        """
        if isinstance(array, Mapping):
            items = list(array.items())
            selected = items[:limit] if limit >= 0 else items[limit:]
            return dict(selected)
        values = list(array)
        return values[:limit] if limit >= 0 else values[limit:]

    @staticmethod
    def flatten(
        array: Iterable[object], depth: int | float = float("inf")
    ) -> list[object]:
        """Flatten nested mappings and sequences to the requested depth.

        Args:
            array: The outer iterable.
            depth: The number of levels to expand.

        Returns:
            Leaf values in depth-first iteration order.
        """
        output: list[object] = []
        stack: list[tuple[object, int]] = [
            (item, 0) for item in reversed(list(array))
        ]
        while stack:
            item, level = stack.pop()
            if level < depth and _is_mapping(item):
                children = list(item.values())
                stack.extend((child, level + 1) for child in reversed(children))
            elif level < depth and _is_sequence(item):
                children = list(item)
                stack.extend((child, level + 1) for child in reversed(children))
            else:
                output.append(item)
        return output

    @staticmethod
    def float(
        array: object,
        key: str | int | None,
        default: float | None = None,
    ) -> float:
        """Return a nested value only when it is a float.

        Args:
            array: The source mapping or sequence.
            key: The path to resolve.
            default: A float used when the path is absent.

        Returns:
            The resolved float.

        Raises:
            ValueError: If the resolved value is not a float.
        """
        value = Arr.get(array, key, default)
        if not isinstance(value, float):
            raise ArrayValueError(key, "a float", value)
        return value

    @staticmethod
    def forget[K: Hashable, V](
        array: MutableArray[K, V],
        keys: object,
    ) -> None:
        """Remove direct or dot-addressed paths from a mutable container.

        Args:
            array: The mutable mapping or list to update.
            keys: One path or an iterable of paths.

        Side Effects:
            Removes matching keys or list entries in place.
        """
        for key in _key_list(keys):
            if Arr.exists(array, key):
                _delete_child(array, key)
                continue
            segments = _path(str(key)) or []
            current: object = array
            for segment in segments[:-1]:
                child = _read(current, segment)
                if not Arr.accessible(child):
                    break
                current = child
            else:
                if _is_mutable_mapping(current) or _is_mutable_sequence(
                    current
                ):
                    _delete_child(current, segments[-1])

    @staticmethod
    def from_(items: object) -> dict[Hashable, object] | list[object]:
        """Convert a Python object to a mapping or list of its items.

        Args:
            items: A mapping, sequence, iterable, or model-like object.

        Returns:
            A copied dictionary or list.

        Raises:
            ValueError: If the input is a scalar or cannot be represented.
        """
        if _is_mapping(items) or _is_sequence(items):
            converted = _array_data(items)
            if converted is not None:
                return converted
        converted = _model_array_data(items)
        if converted is not None:
            return converted
        converted = _array_data(items)
        if converted is not None:
            return converted
        return _json_array_data(items)

    @staticmethod
    def get(
        array: object,
        key: str | int | None,
        default: Default | Callable[[], Default] | None = None,
    ) -> object | Default | None:
        """Get a value from a mapping or sequence using dot notation.

        Args:
            array: The source mapping or sequence.
            key: A direct key, dotted path, or ``None`` for the source.
            default: A value or lazy default for an absent path.

        Returns:
            The matching value or resolved default.
        """
        if key is None:
            return array
        direct = _read(array, key)
        if direct is not _MISSING:
            return direct
        segments = _path(key) or []
        current = array
        for segment in segments:
            current = _read(current, segment)
            if current is _MISSING:
                return _default_value(default)
        return current

    @staticmethod
    def has(array: object, keys: object) -> bool:
        """Check one or more direct or dot-addressed keys.

        Args:
            array: The source mapping or sequence.
            keys: One key or an iterable of keys.

        Returns:
            Whether every requested path exists, even if its value is None.
        """
        paths = _key_list(keys)
        if not Arr.accessible(array) or not paths:
            return False
        return all(Arr._path_exists(array, key) for key in paths)

    @staticmethod
    def _path_exists(array: object, key: object) -> bool:
        """Check a nested path without reading through a missing value.

        Args:
            array: The root mapping or sequence.
            key: A direct key or dotted path.

        Returns:
            Whether every path segment exists.
        """
        if Arr.exists(array, key):
            return True
        if not isinstance(key, str):
            return False
        current = array
        for segment in key.split("."):
            current = _read(current, segment)
            if current is _MISSING:
                return False
        return True

    @staticmethod
    def has_all(array: object, keys: object) -> bool:
        """Check that every requested key exists.

        Args:
            array: The source mapping or sequence.
            keys: One key or an iterable of keys.

        Returns:
            Whether the input is non-empty and all paths exist.
        """
        paths = _key_list(keys)
        return (
            bool(paths)
            and Arr.accessible(array)
            and all(Arr._path_exists(array, key) for key in paths)
        )

    @staticmethod
    def has_any(array: object, keys: object) -> bool:
        """Check whether any requested key exists.

        Args:
            array: The source mapping or sequence.
            keys: One key or an iterable of keys.

        Returns:
            Whether the input is non-empty and at least one path exists.
        """
        paths = _key_list(keys)
        return (
            bool(paths)
            and Arr.accessible(array)
            and any(Arr._path_exists(array, key) for key in paths)
        )

    @staticmethod
    def every(
        array: Iterable[object],
        callback: Callable[[object, Hashable], bool],
    ) -> bool:
        """Return whether all values satisfy a value and key predicate.

        Args:
            array: The keyed values to inspect.
            callback: A predicate accepting a value and optionally its key.

        Returns:
            Whether every item passes. Empty inputs return ``True``.
        """
        return all(
            _invoke(callback, value, key) for key, value in _iter_items(array)
        )

    @staticmethod
    def some(
        array: Iterable[object],
        callback: Callable[[object, Hashable], bool],
    ) -> bool:
        """Return whether any value satisfies a value and key predicate.

        Args:
            array: The keyed values to inspect.
            callback: A predicate accepting a value and optionally its key.

        Returns:
            Whether at least one item passes.
        """
        return any(
            _invoke(callback, value, key) for key, value in _iter_items(array)
        )

    @staticmethod
    def integer(
        array: object,
        key: str | int | None,
        default: int | None = None,
    ) -> int:
        """Return a nested value only when it is an integer.

        Args:
            array: The source mapping or sequence.
            key: The path to resolve.
            default: An integer used when the path is absent.

        Returns:
            The resolved integer.

        Raises:
            ValueError: If the resolved value is not an integer.
        """
        value = Arr.get(array, key, default)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ArrayValueError(key, "an integer", value)
        return value

    @staticmethod
    def is_assoc[K: Hashable, V](
        array: Mapping[K, V] | Sequence[V],
    ) -> bool:
        """Return whether keys are not sequential integer positions.

        Args:
            array: The source mapping or sequence.

        Returns:
            Whether the keys are associative.
        """
        if not _is_mapping(array):
            return False
        return list(array.keys()) != list(range(len(array)))

    @staticmethod
    def is_list(array: object) -> bool:
        """Return whether values form a zero-based positional list.

        Args:
            array: The candidate container.

        Returns:
            Whether it contains sequential integer keys from zero.
        """
        if _is_sequence(array):
            return True
        return _is_mapping(array) and list(array) == list(range(len(array)))

    @staticmethod
    def join(array: Iterable[object], glue: str, final_glue: str = "") -> str:
        """Join values with an optional separator before the final value.

        Args:
            array: The values to join.
            glue: Separator used between all earlier values.
            final_glue: Optional separator before the final value.

        Returns:
            The joined string.
        """
        values = [str(value) for value in array]
        if final_glue and len(values) > 1:
            return glue.join(values[:-1]) + final_glue + values[-1]
        return glue.join(values)

    @staticmethod
    def key_by(
        array: Iterable[object],
        key_by: str | Callable[[object], Hashable],
    ) -> dict[Hashable, object]:
        """Create a mapping keyed by a field or callback result.

        Args:
            array: The source items.
            key_by: A field path or a function deriving each key.

        Returns:
            Items keyed by the derived values; later duplicate keys win.
        """
        result: dict[Hashable, object] = {}
        for item in array:
            key = key_by(item) if callable(key_by) else _get_field(item, key_by)
            if isinstance(key, Hashable):
                result[key] = item
        return result

    @staticmethod
    def prepend_keys_with(
        array: Mapping[str, object],
        prepend_with: str,
    ) -> dict[str, object]:
        """Prefix each mapping key with a string.

        Args:
            array: The source mapping.
            prepend_with: The prefix to add to each key.

        Returns:
            A new mapping with prefixed string keys.
        """
        return {f"{prepend_with}{key}": value for key, value in array.items()}

    @staticmethod
    def only(
        array: Mapping[K, V],
        keys: object,
    ) -> dict[K, V]:
        """Return a copy containing only the requested direct keys.

        Args:
            array: The source mapping.
            keys: One key or an iterable of keys.

        Returns:
            A new mapping preserving source key order.
        """
        wanted = set(_key_list(keys))
        return {key: value for key, value in array.items() if key in wanted}

    @staticmethod
    def only_values(
        array: Mapping[K, V],
        values: object,
        strict: bool = False,
    ) -> dict[K, V]:
        """Return entries whose values match the selection set.

        Args:
            array: The source mapping.
            values: One value or an iterable of values to retain.
            strict: Require matching Python types as well as equality.

        Returns:
            A new mapping retaining source key order.
        """
        selected = _key_list(values)
        return {
            key: value
            for key, value in array.items()
            if any(
                type(value) is type(candidate) and value == candidate
                if strict
                else value == candidate
                for candidate in selected
            )
        }

    @staticmethod
    def select(
        array: Iterable[object], keys: object
    ) -> list[dict[object, object]]:
        """Project selected fields from each mapping or object.

        Args:
            array: The input records.
            keys: The fields to include in each result.

        Returns:
            One projected dictionary per input record.
        """
        fields = _key_list(keys)
        output: list[dict[object, object]] = []
        for item in array:
            selected: dict[object, object] = {}
            for key in fields:
                value = _read(item, key)
                if value is _MISSING and isinstance(key, str):
                    value = getattr(item, key, _MISSING)
                if value is not _MISSING:
                    selected[key] = value
            output.append(selected)
        return output

    @staticmethod
    def pluck(
        array: Iterable[object],
        value: str | int | Callable[[object], object],
        key: str | Callable[[object], Hashable] | None = None,
    ) -> list[object] | dict[Hashable, object]:
        """Extract one field from each item and optionally key the results.

        Args:
            array: The source records.
            value: A field path or value callback.
            key: An optional field path or key callback.

        Returns:
            A list or mapping of extracted values.
        """
        result: list[object] = []
        keyed: dict[Hashable, object] = {}
        for item in array:
            item_value = (
                value(item) if callable(value) else _get_field(item, value)
            )
            if key is None:
                result.append(item_value)
                continue
            item_key = key(item) if callable(key) else _get_field(item, key)
            if isinstance(item_key, Hashable):
                keyed[item_key] = item_value
        return result if key is None else keyed

    @staticmethod
    def map(
        array: Mapping[K, V],
        callback: Callable[[V, K], T],
    ) -> dict[K, T]:
        """Map values while retaining their original keys.

        Args:
            array: The source mapping.
            callback: A function receiving each value and optionally key.

        Returns:
            A new mapping with transformed values.
        """
        return {
            key: _invoke(callback, value, key) for key, value in array.items()
        }

    @staticmethod
    def map_with_keys(
        array: Mapping[K, V],
        callback: Callable[[V, K], Mapping[Hashable, T]],
    ) -> dict[Hashable, T]:
        """Map values into zero or more key/value pairs.

        Args:
            array: The source mapping.
            callback: A function returning a mapping for each entry.

        Returns:
            A merged mapping; later keys replace earlier values.
        """
        result: dict[Hashable, T] = {}
        for key, value in array.items():
            result.update(_invoke(callback, value, key))
        return result

    @staticmethod
    def map_spread(
        array: Mapping[K, Sequence[object]],
        callback: Callable[..., T],
    ) -> dict[K, T]:
        """Expand each sequence into callback positional arguments.

        The source key is appended as the final callback argument.

        Args:
            array: A mapping of keys to positional chunks.
            callback: A function accepting each chunk and its key.

        Returns:
            A mapping retaining the original source keys.
        """
        return {key: callback(*values, key) for key, values in array.items()}

    @staticmethod
    def prepend(
        array: Mapping[K, V] | Sequence[V],
        value: object,
        key: object = _OMITTED,
    ) -> dict[Hashable, object] | list[object]:
        """Prepend a value, optionally assigning it a mapping key.

        Args:
            array: The source mapping or sequence.
            value: The value to prepend.
            key: An explicit mapping key; omission means positional prepend.

        Returns:
            A new container with the value at the beginning.
        """
        if key is _OMITTED and not _is_mapping(array):
            return [value, *array]
        if key is _OMITTED:
            result: dict[Hashable, object] = {0: value}
            next_index = 1
            for source_key, item in _items(array):
                if isinstance(source_key, int) and not isinstance(
                    source_key,
                    bool,
                ):
                    result[next_index] = item
                    next_index += 1
                else:
                    result[source_key] = item
            return result
        if not isinstance(key, Hashable):
            message = "The prepend key must be hashable."
            raise TypeError(message)
        result = {key: value}
        for source_key, item in _items(array):
            if source_key not in result:
                result[source_key] = item
        return result

    @staticmethod
    def pull(
        array: MutableArray[K, V],
        key: str | int,
        default: Default | Callable[[], Default] | None = None,
    ) -> object | Default | None:
        """Read and remove a direct or dot-addressed value.

        Args:
            array: The mutable source container.
            key: The key or dotted path to remove.
            default: A value or lazy default if the path is missing.

        Returns:
            The old value or resolved default.
        """
        value = Arr.get(array, key, default)
        Arr.forget(array, key)
        return value

    @staticmethod
    def push[K: Hashable](
        array: MutableArray[K, object],
        key: str | int | None,
        *values: object,
    ) -> MutableArray[K, object]:
        """Append values to a nested list, creating it when absent.

        Args:
            array: The mutable root container.
            key: A direct key or dotted path; ``None`` selects the root.
            values: Values to append.

        Returns:
            The mutated root container.

        Raises:
            TypeError: If the selected value is not a mutable list.
        """
        target = array if key is None else Arr.get(array, key)
        if target is None and key is not None:
            target: object = []
            Arr.set(array, key, target)
        if not _is_mutable_sequence(target):
            raise ArrayMutationError
        target.extend(values)
        return array

    @staticmethod
    def query[K: Hashable, V](array: Mapping[K, V]) -> str:
        """Encode nested values as an RFC 3986 query string.

        Args:
            array: The values to encode.

        Returns:
            An encoded query string without a leading question mark.
        """
        pairs = _query_pairs(array)
        return urlencode(pairs, doseq=True, quote_via=quote)

    @staticmethod
    def random(
        array: Mapping[K, V] | Sequence[V],
        number: int | None = None,
        preserve_keys: bool = False,
    ) -> object | list[V] | dict[K, V] | None:
        """Select one or more random values without mutating the input.

        Args:
            array: The source mapping or sequence.
            number: Number of values, or ``None`` for one value.
            preserve_keys: Keep original mapping keys for multi-value results.

        Returns:
            One value, a list, a mapping, or ``None`` for an empty source.

        Raises:
            ValueError: If more values are requested than available.
        """
        if _is_mapping(array):
            items = list(array.items())
        else:
            items = list(enumerate(array))
        requested = 1 if number is None else number
        if not items or (number is not None and number <= 0):
            return None if number is None else []
        if requested > len(items):
            raise RandomSelectionError(requested, len(items))
        selected = random.SystemRandom().sample(items, requested)
        if number is None:
            return selected[0][1]
        if preserve_keys and isinstance(array, Mapping):
            return dict(selected)
        return [value for _, value in selected]

    @staticmethod
    def set(
        array: MutableArray[K, V],
        key: str | int | None,
        value: V,
    ) -> V | MutableArray[K, V]:
        """Set a direct or dot-addressed value on a mutable container.

        Args:
            array: The mutable root container.
            key: A direct key or dotted path; ``None`` denotes replacement.
            value: The value to assign.

        Returns:
            The assigned value for root replacement, otherwise the root.

        Raises:
            TypeError: If a nested path crosses an immutable container.
        """
        if key is None:
            return value
        segments = _path(key) or []
        current: object = array
        for segment in segments[:-1]:
            child = _read(current, segment)
            if not (_is_mutable_mapping(child) or _is_mutable_sequence(child)):
                child: object = {}
                _write_child(current, segment, child)
            current = child
        _write_child(current, segments[-1], value)
        return array

    @staticmethod
    def shuffle(array: Mapping[K, V] | Sequence[V]) -> list[V]:
        """Return a shuffled list of values from a mapping or sequence.

        Args:
            array: The values to shuffle.

        Returns:
            A new list containing every source value once.
        """
        if isinstance(array, Mapping):
            values = list(array.values())
        else:
            values = list(array)
        random.SystemRandom().shuffle(values)
        return values

    @staticmethod
    def sole(
        array: Iterable[object],
        callback: Callable[[object, Hashable], bool] | None = None,
    ) -> object:
        """Return the sole matching value or raise for zero/multiple values.

        Args:
            array: The source iterable.
            callback: An optional predicate restricting candidates.

        Returns:
            The unique matching value.

        Raises:
            LookupError: If no value matches.
            ValueError: If more than one value matches.
        """
        matching: object = _MISSING
        count = 0
        for key, value in _iter_items(array):
            if callback is not None and not _invoke(callback, value, key):
                continue
            count += 1
            if count > 1:
                raise MultipleMatchingArrayItemsError(count)
            matching = value
        if matching is _MISSING:
            raise NoMatchingArrayItemError
        return matching

    @staticmethod
    def sort[K: Hashable, V](
        array: Mapping[K, V] | Iterable[V],
        callback: str | Callable[[V], object] | Sequence[object] | None = None,
    ) -> dict[Hashable, object] | list[object]:
        """Sort values by a key, field path, or multiple selectors.

        Args:
            array: The source mapping or iterable.
            callback: A key function, dot path, or ordered selector sequence.

        Returns:
            A sorted mapping or list while preserving source key order.

        Notes:
            Mixed Python values use type-category ordering. Numeric values
            sort numerically, strings lexically, then bytes and other values.
        """
        return _sort_array(array, callback, descending=False)

    @staticmethod
    def sort_desc[K: Hashable, V](
        array: Mapping[K, V] | Iterable[V],
        callback: str | Callable[[V], object] | Sequence[object] | None = None,
    ) -> dict[Hashable, object] | list[object]:
        """Sort values in descending order using supported selectors.

        Args:
            array: The source mapping or iterable.
            callback: A key function, dot path, or ordered selector sequence.

        Returns:
            A descending mapping or list preserving source key order.
        """
        return _sort_array(array, callback, descending=True)

    @staticmethod
    def sort_recursive(
        array: Mapping[K, object] | Sequence[object],
        options: int = _SORT_REGULAR,
        descending: bool = False,
    ) -> dict[Hashable, object] | list[object]:
        """Recursively sort nested mappings and lists.

        Args:
            array: The source structure.
            options: A regular, numeric, string, locale, or natural mode.
            descending: Whether to reverse each sorted level.

        Returns:
            A recursively sorted container.
        """
        if _is_mapping(array):
            mapped = {
                key: Arr.sort_recursive(value, options, descending)
                if (_is_mapping(value) or _is_sequence(value))
                else value
                for key, value in array.items()
            }
            return dict(
                sorted(
                    mapped.items(),
                    key=lambda item: _SortOrder(
                        item[0],
                        descending,
                        options,
                    ),
                )
            )
        values: list[object] = []
        for value in array:
            if _is_mapping(value) or _is_sequence(value):
                values.append(Arr.sort_recursive(value, options, descending))
            else:
                values.append(value)
        return sorted(
            values,
            key=lambda value: _SortOrder(value, descending, options),
        )

    @staticmethod
    def sort_recursive_desc(
        array: Mapping[K, object] | Sequence[object],
        options: int = _SORT_REGULAR,
    ) -> dict[Hashable, object] | list[object]:
        """Recursively sort mapping keys and sequence values descending.

        Args:
            array: The source structure to sort.
            options: A regular, numeric, string, locale, or natural mode.

        Returns:
            A new recursively sorted mapping or list.

        Notes:
            Scalar values use native ordering; nested, non-orderable values
            use deterministic representation ordering.
        """
        return Arr.sort_recursive(array, options, descending=True)

    @staticmethod
    def string(
        array: object,
        key: str | int | None,
        default: str | None = None,
    ) -> str:
        """Return a nested value only when it is a string.

        Args:
            array: The source mapping or sequence.
            key: The path to resolve.
            default: A string used when the path is absent.

        Returns:
            The resolved string.

        Raises:
            ValueError: If the resolved value is not a string.
        """
        value = Arr.get(array, key, default)
        if not isinstance(value, str):
            raise ArrayValueError(key, "a string", value)
        return value

    @staticmethod
    def to_css_classes(values: object) -> str:
        """Compile class names and truthy conditional mapping entries.

        Args:
            values: A class string, sequence, or conditional mapping.

        Returns:
            A space-separated class list.
        """
        if isinstance(values, str):
            return values
        if not _is_iterable(values):
            return str(values)
        classes: list[str] = []
        entries = _items(values)
        for key, value in entries:
            if _is_mapping(values):
                if value:
                    classes.append(str(key))
            else:
                classes.append(str(value))
        return " ".join(classes)

    @staticmethod
    def to_css_styles(values: object) -> str:
        """Compile style strings and truthy conditional mapping entries.

        Args:
            values: A style string, sequence, or conditional mapping.

        Returns:
            A space-separated style list with semicolon terminators.
        """
        if isinstance(values, str):
            return (
                values if not values or values.endswith(";") else f"{values};"
            )
        if not _is_iterable(values):
            return str(values)
        styles: list[str] = []
        for key, value in _items(values):
            candidate = key if _is_mapping(values) else value
            enabled = bool(value) if _is_mapping(values) else True
            if enabled:
                text = str(candidate)
                styles.append(text if text.endswith(";") else f"{text};")
        return " ".join(styles)

    @staticmethod
    def where(
        array: Mapping[K, V],
        callback: Callable[[V, K], bool],
    ) -> dict[K, V]:
        """Filter entries using a value and key predicate.

        Args:
            array: The source mapping.
            callback: A predicate accepting each value and optionally key.

        Returns:
            A new mapping containing matching entries.
        """
        return {
            key: value
            for key, value in array.items()
            if _invoke(callback, value, key)
        }

    @staticmethod
    def reject(
        array: Mapping[K, V],
        callback: Callable[[V, K], bool],
    ) -> dict[K, V]:
        """Filter entries using the negation of a predicate.

        Args:
            array: The source mapping.
            callback: A predicate accepting each value and optionally key.

        Returns:
            A new mapping containing non-matching entries.
        """
        return {
            key: value
            for key, value in array.items()
            if not _invoke(callback, value, key)
        }

    @staticmethod
    def partition(
        array: Iterable[object],
        callback: Callable[[object, Hashable], bool],
    ) -> tuple[dict[Hashable, object], dict[Hashable, object]]:
        """Split entries into passing and failing mappings.

        Args:
            array: The input mapping or sequence.
            callback: A predicate accepting each value and optionally key.

        Returns:
            A pair of mappings: matching entries, then remaining entries.
        """
        passed: dict[Hashable, object] = {}
        failed: dict[Hashable, object] = {}
        for key, value in _items(array):
            target = passed if _invoke(callback, value, key) else failed
            target[key] = value
        return passed, failed

    @staticmethod
    def where_not_null(array: Mapping[K, V | None]) -> dict[K, V]:
        """Remove entries whose values are explicitly ``None``.

        Args:
            array: The source mapping.

        Returns:
            A mapping containing only non-None values.
        """
        return {key: value for key, value in array.items() if value is not None}

    @staticmethod
    def wrap(value: object) -> list[object] | tuple[object, ...]:
        """Wrap a scalar as a list while preserving existing sequences.

        Args:
            value: The source value or iterable.

        Returns:
            An empty list for ``None``, the original tuple, or a new list.
        """
        if value is None:
            return []
        if isinstance(value, tuple):
            return tuple(cast("Iterable[object]", value))
        if isinstance(value, list):
            return list(cast("Iterable[object]", value))
        if _is_iterable(value) and not isinstance(value, (str, bytes)):
            return list(value)
        return [value]


__all__ = ["Arr"]
