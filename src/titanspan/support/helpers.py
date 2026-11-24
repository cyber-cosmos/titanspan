"""Provide shared value, nested-data, and exception helpers.

The functions adapt Laravel's global Support and Collections helpers to
Python mappings, sequences, enums, and object attributes. Mutating helpers
operate on mutable objects and return the resulting root value.
"""

from __future__ import annotations

import builtins
import inspect
import numbers
import re
from collections.abc import (
    Awaitable,
    Callable,
    Iterable,
    Mapping,
    MutableMapping,
    Sequence,
    Sized,
)
from enum import Enum
from typing import TypeVar, cast, overload

from titanspan.support.encoded_html_string import (
    EncodedHtmlString,
    HtmlEncodable,
)
from titanspan.support.env import Env
from titanspan.support.exceptions import AsyncCallbackUsageError

T = TypeVar("T")
R = TypeVar("R")
D = TypeVar("D")
_MISSING = object()
_Path = str | int | Sequence[object] | None
_Segment = str | int | None


class HigherOrderTapProxy[T]:
    """Forward a method call to a value and return that original value.

    This proxy supports the callback-free ``tap`` form for objects with
    callable attributes. Direct attribute access is intentionally not
    forwarded because it would be ambiguous with proxy methods.
    """

    def __init__(self, target: T) -> None:
        """Store the value whose method calls should be tapped.

        Args:
            target: The value to preserve after a forwarded call.
        """
        self._target = target

    def call(self, method_name: str, *args: object, **kwargs: object) -> T:
        """Call a target method and return the original target.

        Args:
            method_name: The callable attribute name on the target.
            *args: Positional arguments for the target method.
            **kwargs: Keyword arguments for the target method.

        Returns:
            The original target, regardless of the method result.

        Raises:
            AttributeError: If the target has no callable attribute.
            AsyncCallbackUsageError: If the method returns an awaitable.
        """
        method = getattr(self._target, method_name, None)
        if not callable(method):
            raise TypeError(method_name)

        result = method(*args, **kwargs)
        _reject_awaitable(result, method_name)
        return self._target

    def __getattr__(self, method_name: str) -> Callable[..., T]:
        """Create a callable that forwards to the target's named method.

        Args:
            method_name: The target method to forward when called.

        Returns:
            A callable that invokes the target and returns the target.

        Raises:
            AttributeError: If the requested target method is missing.
        """
        if method_name.startswith("_"):
            raise AttributeError(method_name)

        def forward(*args: object, **kwargs: object) -> T:
            """Invoke the stored method and preserve the target value.

            Args:
                *args: Positional arguments for the target method.
                **kwargs: Keyword arguments for the target method.

            Returns:
                The original target after the method completes.
            """
            return self.call(method_name, *args, **kwargs)

        return forward


def blank(candidate: object) -> bool:
    """Return whether a value is null, whitespace, or an empty container.

    Numeric values and booleans are always considered filled, including
    zero and ``False``. This avoids treating Python's falsey scalar values
    as empty data.

    Args:
        candidate: The value to inspect.

    Returns:
        Whether the value is blank under Titanspan's Laravel adaptation.
    """
    if candidate is None:
        return True
    if isinstance(candidate, str):
        return not candidate.strip()
    if isinstance(candidate, (bytes, bytearray)):
        return not candidate.strip()
    if isinstance(candidate, (bool, numbers.Number)):
        return False
    return isinstance(candidate, Sized) and len(candidate) == 0


def filled(candidate: object) -> bool:
    """Return whether a value is not blank.

    Args:
        candidate: The value to inspect.

    Returns:
        The inverse of :func:`blank`.
    """
    return not blank(candidate)


def env(key: str, default: object = None) -> object:
    """Read a normalized environment value through the Env utility.

    Args:
        key: Environment variable name to read.
        default: Constant or zero-argument callback used when absent.

    Returns:
        The normalized environment value or its resolved default.
    """
    return Env.get(key, default)


@overload
def value[T](candidate: Callable[..., T], *args: object) -> T:
    """Describe the deferred-callable overload of :func:`value`.

    This signature preserves the callable result type for static callers.
    """


@overload
def value[T](candidate: T, *args: object) -> T:
    """Describe the constant-value overload of :func:`value`.

    This signature preserves the original value type for static callers.
    """


def value(candidate: object, *args: object) -> object:
    """Resolve a callable value or return a constant unchanged.

    Unlike PHP, Python has many callable objects. Titanspan therefore treats
    any callable as a deferred value and invokes it with ``args``.

    Args:
        candidate: A constant or callable value.
        *args: Arguments supplied only when ``candidate`` is callable.

    Returns:
        The constant or the callable result.
    """
    if callable(candidate):
        return candidate(*args)
    return candidate


def with_[T, R](
    candidate: T,
    callback: Callable[[T], R] | None = None,
) -> T | R:
    """Return a value or pass it through a callback.

    Args:
        candidate: The value to return or transform.
        callback: An optional callback receiving ``candidate``.

    Returns:
        The original value without a callback, otherwise the callback result.
    """
    if callback is None:
        return candidate
    return callback(candidate)


@overload
def tap[T](candidate: T) -> HigherOrderTapProxy[T]:
    """Describe the proxy-returning overload of :func:`tap`.

    This signature is used when no callback is supplied.
    """


@overload
def tap[T](
    candidate: T,
    callback: Callable[[T], object],
) -> T:
    """Describe the callback-returning overload of :func:`tap`.

    This signature preserves the candidate's type for typed callers.
    """


@overload
def tap[T](candidate: T, callback: None) -> HigherOrderTapProxy[T]:
    """Describe the explicit-None proxy overload of :func:`tap`.

    This signature matches the callback-free runtime behavior.
    """


def tap[T](
    candidate: T,
    callback: Callable[[T], object] | None = None,
) -> T | HigherOrderTapProxy[T]:
    """Run a side-effect callback and return the original value.

    A callback-free call returns a proxy whose :meth:`call` method invokes
    one target method before returning the target.

    Args:
        candidate: The value to observe or mutate.
        callback: An optional synchronous side-effect callback.

    Returns:
        The original value, or a higher-order method proxy.

    Raises:
        AsyncCallbackUsageError: If the callback returns an awaitable.
    """
    if callback is None:
        return HigherOrderTapProxy(candidate)
    result = callback(candidate)
    _reject_awaitable(result, "tap callback")
    return candidate


async def tap_async[T](
    candidate: T,
    callback: Callable[[T], object],
) -> T:
    """Await an optional asynchronous side effect and return its value.

    Args:
        candidate: The value to observe or mutate.
        callback: A callback that may return an awaitable.

    Returns:
        The original value after the callback completes.
    """
    result = callback(candidate)
    if inspect.isawaitable(result):
        await cast("Awaitable[object]", result)
    return candidate


def transform[T, R, D](
    candidate: T,
    callback: Callable[[T], R],
    default: D | Callable[[T], D] | None = None,
) -> R | D | None:
    """Transform a filled value or resolve a default for a blank one.

    Args:
        candidate: The value to inspect and potentially transform.
        callback: The function applied to a filled value.
        default: A fallback value or callback receiving the original value.

    Returns:
        The transformed value or resolved default.
    """
    if filled(candidate):
        return callback(candidate)
    if callable(default):
        default_callback = cast("Callable[[T], D]", default)
        return default_callback(candidate)
    return default


def head[T](items: Iterable[T]) -> T | bool:
    """Return the first iterable item, or ``False`` when empty.

    Args:
        items: The iterable to inspect.

    Returns:
        Its first item, or ``False`` for an empty iterable.
    """
    return next(iter(items), False)


def last[T](items: Iterable[T]) -> T | bool:
    """Return the last iterable item using constant auxiliary memory.

    Args:
        items: The iterable to consume.

    Returns:
        Its last item, or ``False`` for an empty iterable.
    """
    found = False
    result: T | bool = False
    for item in items:
        result = item
        found = True
    return result if found else False


def data_get[T, D](
    target: object,
    key: _Path,
    default: D | Callable[[], D] | None = None,
) -> object | D | None:
    """Retrieve nested mapping, sequence, or object data.

    Dot paths support sequence indexes, wildcard selection, escaped special
    segments, and ``{first}``/``{last}`` selectors. Wildcard results preserve
    iteration order and flatten one level when another wildcard remains.

    Args:
        target: The root value to traverse.
        key: A dot path, explicit path segments, or ``None`` for the target.
        default: A value or zero-argument callback for missing paths.

    Returns:
        The resolved value or default.
    """
    if key is None:
        return target

    segments = _path_segments(key)
    current = target
    for index, segment in enumerate(segments):
        remainder = segments[index + 1 :]
        if segment is None:
            return current
        if segment == "*":
            values = _iter_values(current)
            if values is None:
                return value(default)
            matches = [data_get(item, remainder, default) for item in values]
            if "*" in remainder:
                flattened: list[object] = []
                for match in matches:
                    if isinstance(match, Iterable) and not isinstance(
                        match,
                        (str, bytes, Mapping),
                    ):
                        values = cast("Iterable[object]", match)
                        flattened.extend(values)
                    else:
                        flattened.append(cast("object", match))
                return flattened
            return matches

        resolved_segment = _resolve_special_segment(current, segment)
        next_value = _read_segment(current, resolved_segment)
        if next_value is _MISSING:
            return value(default)
        current = next_value
    return current


def data_has(target: object, key: _Path) -> bool:
    """Return whether every segment in a nested path exists.

    Explicit ``None`` values count as existing values. Wildcard characters
    are treated as ordinary path segments, matching Laravel's ``data_has``.

    Args:
        target: The root value to inspect.
        key: A dot path or explicit sequence of path segments.

    Returns:
        Whether the full path exists.
    """
    if key is None:
        return False
    segments = _path_segments(key)
    if not segments:
        return False

    current = target
    for segment in segments:
        if segment is None:
            return False
        next_value = _read_segment(current, segment)
        if next_value is _MISSING:
            return False
        current = next_value
    return True


def data_set(
    target: object,
    key: _Path,
    new_value: object,
    overwrite: bool = True,
) -> object:
    """Set nested data in mutable mappings, lists, or object attributes.

    The returned root is significant when ``target`` is an immutable scalar
    or tuple: Python cannot replace a caller's local reference by mutation.
    Mutable mappings and lists are changed in place.

    Args:
        target: The root value to update.
        key: A dot path or explicit sequence of path segments.
        new_value: The assigned value.
        overwrite: Whether existing leaf values may be replaced.

    Returns:
        The mutated target or a new mutable root when required.
    """
    segments = _path_segments(key)
    if not segments:
        return target
    return _set_path(target, segments, new_value, overwrite)


def data_fill(
    target: object,
    key: _Path,
    new_value: object,
) -> object:
    """Set nested data only where a leaf is missing.

    Args:
        target: The root value to update.
        key: A dot path or explicit sequence of path segments.
        new_value: The assigned fallback value.

    Returns:
        The mutated target or a new mutable root when required.
    """
    return data_set(target, key, new_value, overwrite=False)


def data_forget(target: object, key: _Path) -> object:
    """Remove a nested key from mutable data or object attributes.

    Wildcard paths apply the remainder of the path to each mapping or list
    child. Removing an element from a list shifts later indexes, as Python
    list deletion requires.

    Args:
        target: The root value to update.
        key: A dot path or explicit sequence of path segments.

    Returns:
        The same root value after applicable removals.
    """
    segments = _path_segments(key)
    if segments:
        _forget_path(target, segments)
    return target


def enum_value(
    candidate: object,
    default: object = None,
) -> object:
    """Return a scalar value for an enum or resolve a null default.

    Python enums may contain arbitrary objects. Scalar-backed enums return
    their value; other enums return their member name.

    Args:
        candidate: An enum member, ordinary value, or ``None``.
        default: A value or zero-argument callback for ``None``.

    Returns:
        A scalar enum value, enum name, original value, or resolved default.
    """
    if isinstance(candidate, Enum):
        if isinstance(candidate.value, (str, int, float, bool)):
            return candidate.value
        return candidate.name
    if candidate is None:
        return value(default)
    return candidate


def e(
    candidate: HtmlEncodable,
    double_encode: bool = True,
) -> str:
    """Escape HTML special characters with quote-safe output.

    Deferred display values are resolved before escaping. Values implementing
    the explicit Htmlable contract are trusted and returned without another
    escaping pass.

    Args:
        candidate: The scalar value to escape.
        double_encode: Whether existing character references are escaped.

    Returns:
        HTML-escaped text using PHP-compatible apostrophe references.
    """
    return EncodedHtmlString(candidate, double_encode).to_html()


def throw_if[T](
    condition: T,
    exception: str
    | Exception
    | type[Exception]
    | Callable[..., Exception] = "RuntimeError",
    *parameters: object,
) -> T:
    """Raise an exception when a condition is truthy.

    Args:
        condition: The value whose truthiness controls raising.
        exception: An exception, exception class, message, or factory.
        *parameters: Arguments passed to exception classes or factories.

    Returns:
        The original condition when it is falsey.

    Raises:
        Exception: The requested instance or constructed exception.
        TypeError: If the exception specification is invalid.
    """
    if condition:
        raise _make_exception(exception, parameters)
    return condition


def throw_unless[T](
    condition: T,
    exception: str
    | Exception
    | type[Exception]
    | Callable[..., Exception] = "RuntimeError",
    *parameters: object,
) -> T:
    """Raise an exception unless a condition is truthy.

    Args:
        condition: The value whose truthiness controls raising.
        exception: An exception, exception class, message, or factory.
        *parameters: Arguments passed to exception classes or factories.

    Returns:
        The original condition when it is truthy.

    Raises:
        Exception: The requested instance or constructed exception.
        TypeError: If the exception specification is invalid.
    """
    if not condition:
        raise _make_exception(exception, parameters)
    return condition


def _make_exception(
    exception: str | Exception | type[Exception] | Callable[..., Exception],
    parameters: tuple[object, ...],
) -> Exception:
    """Build the exception selected by a throw helper.

    Args:
        exception: An exception instance, class, message, or factory.
        parameters: Arguments for a class or factory.

    Returns:
        A concrete exception instance.

    Raises:
        TypeError: If the selected value is not an exception.
    """
    if isinstance(exception, Exception):
        return exception
    if isinstance(exception, str):
        builtin_exception = getattr(builtins, exception, None)
        if isinstance(builtin_exception, type) and issubclass(
            builtin_exception,
            Exception,
        ):
            return builtin_exception(*parameters)
        return RuntimeError(exception)
    if isinstance(exception, type) and issubclass(exception, Exception):
        return exception(*parameters)
    factory = cast("Callable[..., object]", exception)
    result = factory(*parameters)
    if isinstance(result, Exception):
        return result
    message = "The exception argument must produce an Exception."
    raise TypeError(message)


def _path_segments(key: _Path) -> list[_Segment]:
    """Normalize supported path forms to typed mapping segments.

    Args:
        key: A string path, integer index, explicit path, or ``None``.

    Returns:
        Path segments. ``None`` is retained as a no-op segment.
    """
    if key is None:
        return []
    if isinstance(key, str):
        return cast("list[_Segment]", key.split("."))
    if isinstance(key, int):
        return [key]
    return cast("list[_Segment]", list(key))


def _iter_values(target: object) -> list[object] | None:
    """Return ordered target values for wildcard expansion.

    Args:
        target: A mapping or iterable to inspect.

    Returns:
        Ordered values or ``None`` when the target is not iterable data.
    """
    if isinstance(target, Mapping):
        mapping = cast("Mapping[object, object]", target)
        return list(mapping.values())
    if isinstance(target, Iterable) and not isinstance(
        target,
        (str, bytes, bytearray),
    ):
        return list(cast("Iterable[object]", target))
    return None


def _resolve_special_segment(target: object, segment: _Segment) -> _Segment:
    """Resolve Laravel wildcard escapes and endpoint selectors.

    Args:
        target: The current container.
        segment: The original path segment.

    Returns:
        The literal or resolved path segment.
    """
    if segment == r"\*":
        return "*"
    if segment == r"\{first}":
        return "{first}"
    if segment == r"\{last}":
        return "{last}"
    if segment in ("{first}", "{last}"):
        keys = _iter_keys(target)
        if not keys:
            return cast("_Segment", _MISSING)
        return keys[0] if segment == "{first}" else keys[-1]
    return segment


def _iter_keys(target: object) -> list[_Segment]:
    """Return ordered keys for mapping and sequence containers.

    Args:
        target: The container to inspect.

    Returns:
        Keys in iteration order, or an empty list for non-containers.
    """
    if isinstance(target, Mapping):
        mapping = cast("Mapping[object, object]", target)
        return cast("list[_Segment]", list(mapping.keys()))
    if isinstance(target, Sequence) and not isinstance(
        target,
        (str, bytes, bytearray),
    ):
        sequence = cast("Sequence[object]", target)
        return list(range(len(sequence)))
    return []


def _read_segment(target: object, segment: _Segment) -> object:
    """Read one path segment without conflating missing and ``None``.

    Args:
        target: The current value.
        segment: The key, index, or attribute name to read.

    Returns:
        The value or the private missing sentinel.
    """
    if segment is _MISSING:
        return _MISSING
    if isinstance(target, Mapping):
        mapping = cast("Mapping[object, object]", target)
        return _read_mapping(mapping, segment)
    if isinstance(target, Sequence) and not isinstance(
        target,
        (str, bytes, bytearray),
    ):
        sequence = cast("Sequence[object]", target)
        return _read_sequence(sequence, segment)
    return _read_attribute(target, segment)


def _read_mapping(
    target: Mapping[object, object],
    segment: _Segment,
) -> object:
    """Read a mapping key while preserving explicit ``None`` values.

    Args:
        target: The mapping to query.
        segment: The requested key.

    Returns:
        The mapped value or the missing sentinel.
    """
    try:
        return target.get(segment, _MISSING)
    except TypeError:
        return _MISSING


def _read_sequence(
    target: Sequence[object],
    segment: _Segment,
) -> object:
    """Read a sequence index and handle missing indexes.

    Args:
        target: The sequence to query.
        segment: The requested integer-like index.

    Returns:
        The item or the missing sentinel.
    """
    index = _sequence_index(segment)
    if index is None:
        return _MISSING
    try:
        return target[index]
    except IndexError:
        return _MISSING


def _read_attribute(target: object, segment: _Segment) -> object:
    """Read a named object attribute without hiding other failures.

    Args:
        target: The object to query.
        segment: The requested attribute name.

    Returns:
        The attribute value or the missing sentinel.
    """
    if not isinstance(segment, str):
        return _MISSING
    try:
        return getattr(target, segment)
    except AttributeError:
        return _MISSING


def _sequence_index(segment: _Segment) -> int | None:
    """Convert an integer-like path segment to a sequence index.

    Args:
        segment: The path value to interpret as an index.

    Returns:
        An integer index or ``None`` for a non-index segment.
    """
    if isinstance(segment, int):
        return segment
    if isinstance(segment, str) and re.fullmatch(r"-?[0-9]+", segment):
        return int(segment)
    return None


def _new_container(segment: _Segment) -> dict[object, object] | list[object]:
    """Choose a mutable child container for the next path segment.

    Args:
        segment: The next segment to be assigned.

    Returns:
        A list for integer indexes or a mapping for string keys.
    """
    if _sequence_index(segment) is not None:
        return []
    return {}


def _set_path(
    target: object,
    segments: list[_Segment],
    new_value: object,
    overwrite: bool,
) -> object:
    """Apply a mutable nested assignment recursively.

    Args:
        target: The current container.
        segments: Remaining path segments.
        new_value: The leaf value to assign.
        overwrite: Whether existing leaves may be replaced.

    Returns:
        The current container, replacing immutable or scalar containers.
    """
    if not segments:
        return target
    segment = segments[0]
    remainder = segments[1:]
    if segment == "*":
        return _set_wildcard(target, remainder, new_value, overwrite)
    if isinstance(target, MutableMapping):
        mapping = cast("MutableMapping[object, object]", target)
        return _set_mapping(mapping, segment, remainder, new_value, overwrite)
    if isinstance(target, list):
        items = cast("list[object]", target)
        return _set_list(items, segment, remainder, new_value, overwrite)
    return _set_object_or_replacement(
        target,
        segment,
        remainder,
        new_value,
        overwrite,
    )


def _set_wildcard(
    target: object,
    remainder: list[_Segment],
    new_value: object,
    overwrite: bool,
) -> object:
    """Apply a wildcard assignment across a mutable container.

    Args:
        target: The mapping or list to update.
        remainder: The remaining path after the wildcard.
        new_value: The value assigned at each matching leaf.
        overwrite: Whether existing leaves may be replaced.

    Returns:
        The same mutable container or an empty list for scalar input.
    """
    if isinstance(target, MutableMapping):
        mapping = cast("MutableMapping[object, object]", target)
        for key in list(mapping):
            if remainder:
                mapping[key] = _set_path(
                    mapping[key],
                    remainder,
                    new_value,
                    overwrite,
                )
            elif overwrite:
                mapping[key] = new_value
        return mapping
    if isinstance(target, list):
        items = cast("list[object]", target)
        for index, child in enumerate(items):
            if remainder:
                items[index] = _set_path(
                    child,
                    remainder,
                    new_value,
                    overwrite,
                )
            elif overwrite:
                items[index] = new_value
        return items
    return []


def _set_mapping(
    target: MutableMapping[object, object],
    segment: _Segment,
    remainder: list[_Segment],
    new_value: object,
    overwrite: bool,
) -> object:
    """Set one mapping item and recursively update nested data.

    Args:
        target: The mutable mapping to update.
        segment: The mapping key.
        remainder: The remaining path.
        new_value: The value assigned at the leaf.
        overwrite: Whether existing leaves may be replaced.

    Returns:
        The same mutable mapping.
    """
    try:
        exists = segment in target
    except TypeError:
        return target
    if remainder:
        child = target.get(segment, _MISSING)
        if child is _MISSING:
            child = _new_container(remainder[0])
        target[segment] = _set_path(child, remainder, new_value, overwrite)
    elif overwrite or not exists:
        target[segment] = new_value
    return target


def _set_list(
    target: list[object],
    segment: _Segment,
    remainder: list[_Segment],
    new_value: object,
    overwrite: bool,
) -> object:
    """Set one list item while extending missing positive indexes.

    Args:
        target: The mutable list to update.
        segment: The integer-like list index.
        remainder: The remaining path.
        new_value: The value assigned at the leaf.
        overwrite: Whether existing leaves may be replaced.

    Returns:
        The same mutable list.
    """
    index = _sequence_index(segment)
    if index is None or index < 0:
        return target
    existed = index < len(target)
    while len(target) <= index:
        target.append(None)
    if remainder:
        child = target[index]
        if child is _MISSING:
            child = _new_container(remainder[0])
        target[index] = _set_path(child, remainder, new_value, overwrite)
    elif overwrite or not existed:
        target[index] = new_value
    return target


def _set_object_or_replacement(
    target: object,
    segment: _Segment,
    remainder: list[_Segment],
    new_value: object,
    overwrite: bool,
) -> object:
    """Set an object attribute or create a mutable replacement root.

    Args:
        target: The current object or scalar.
        segment: The current path segment.
        remainder: The remaining path.
        new_value: The value assigned at the leaf.
        overwrite: Whether existing leaves may be replaced.

    Returns:
        The mutated object or a new mapping/list root.
    """
    if isinstance(segment, str):
        current = _read_segment(target, segment)
        if remainder:
            child = (
                _new_container(remainder[0]) if current is _MISSING else current
            )
            updated = _set_path(child, remainder, new_value, overwrite)
            try:
                setattr(target, segment, updated)
            except (AttributeError, TypeError):
                pass
            else:
                return target
        elif overwrite or current is _MISSING:
            try:
                setattr(target, segment, new_value)
            except (AttributeError, TypeError):
                pass
            else:
                return target

    replacement = _new_container(segment)
    return _set_path(replacement, [segment, *remainder], new_value, overwrite)


def _forget_path(target: object, segments: list[_Segment]) -> None:
    """Remove one path from a mutable mapping, list, or object.

    Args:
        target: The current value.
        segments: The remaining path to remove.
    """
    if not segments:
        return
    segment = segments[0]
    remainder = segments[1:]
    if segment == "*":
        _forget_wildcard(target, remainder)
        return
    if isinstance(target, MutableMapping):
        mapping = cast("MutableMapping[object, object]", target)
        _forget_mapping(mapping, segment, remainder)
        return
    if isinstance(target, list):
        items = cast("list[object]", target)
        _forget_list(items, segment, remainder)
        return
    _forget_object(target, segment, remainder)


def _forget_wildcard(
    target: object,
    remainder: list[_Segment],
) -> None:
    """Apply a nested removal to every child in a mutable container.

    Args:
        target: The mapping or list to traverse.
        remainder: The path below each child.
    """
    if isinstance(target, MutableMapping):
        mapping = cast("MutableMapping[object, object]", target)
        children: list[object] = list(mapping.values())
    elif isinstance(target, list):
        items = cast("list[object]", target)
        children = list(items)
    else:
        children = []
    for child in children:
        _forget_path(child, remainder)


def _forget_mapping(
    target: MutableMapping[object, object],
    segment: _Segment,
    remainder: list[_Segment],
) -> None:
    """Remove a mapping key or recurse into its value.

    Args:
        target: The mutable mapping to update.
        segment: The key to remove or traverse.
        remainder: The path below that key.
    """
    try:
        if segment not in target:
            return
    except TypeError:
        return
    if remainder:
        _forget_path(target[segment], remainder)
    else:
        del target[segment]


def _forget_list(
    target: list[object],
    segment: _Segment,
    remainder: list[_Segment],
) -> None:
    """Remove an indexed list item or recurse into it.

    Args:
        target: The mutable list to update.
        segment: The integer-like index to remove or traverse.
        remainder: The path below that item.
    """
    index = _sequence_index(segment)
    if index is None or index < 0 or index >= len(target):
        return
    if remainder:
        _forget_path(target[index], remainder)
    else:
        del target[index]


def _forget_object(
    target: object,
    segment: _Segment,
    remainder: list[_Segment],
) -> None:
    """Delete an object attribute or recurse through it.

    Args:
        target: The object to inspect.
        segment: The attribute name.
        remainder: The path below that attribute.
    """
    if not isinstance(segment, str):
        return
    child = _read_segment(target, segment)
    if child is _MISSING:
        return
    if remainder:
        _forget_path(child, remainder)
        return
    try:
        delattr(target, segment)
    except (AttributeError, TypeError):
        return


def _reject_awaitable(result: object, context: str) -> None:
    """Reject asynchronous callback results from synchronous APIs.

    Args:
        result: The value returned by a synchronous callback.
        context: A short label for the callback location.

    Raises:
        AsyncCallbackUsageError: If ``result`` is awaitable.
    """
    if not inspect.isawaitable(result):
        return
    if inspect.iscoroutine(result):
        result.close()
    raise AsyncCallbackUsageError(context, "an explicit async helper")


__all__ = [
    "HigherOrderTapProxy",
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
    "tap",
    "tap_async",
    "throw_if",
    "throw_unless",
    "transform",
    "value",
    "with_",
]
