"""Provide a typed null-safe wrapper over Python values.

The wrapper adapts Laravel's ``Optional`` to Python mappings, sequences,
objects, and asynchronous methods without introducing magic event-loop
creation or a second dependency-resolution mechanism.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from typing import TypeVar, cast, overload

from titanspan.support.arr import Arr
from titanspan.support.exceptions import AsyncCallbackUsageError
from titanspan.support.macroable import Macroable

T = TypeVar("T")
R = TypeVar("R")
_MISSING = object()


class Optional[T](Macroable):
    """Expose null-safe reads and explicit delegation for a wrapped value.

    Mapping and sequence operations preserve the wrapped object's mutation
    behavior. Attribute reads are forwarded only when the wrapped value is
    not ``None``. Method calls use :meth:`call` so their dynamic nature is
    visible to static type checkers.

    Attributes:
        wrapped: The original value, which may be ``None``.

    Notes:
        A present key whose value is ``None`` exists for :meth:`has`, while
        :meth:`is_set` follows ``isset`` semantics and returns false.
    """

    def __init__(self, wrapped: T) -> None:
        """Create a null-safe wrapper around ``wrapped``.

        Args:
            wrapped: The object, mapping, sequence, scalar, or ``None``.
        """
        self.wrapped = wrapped

    def get(
        self,
        key: str | int,
        default: object = None,
    ) -> object:
        """Read a nested key, returning the default when the path is absent.

        Args:
            key: A direct key, sequence index, or dot-addressed path.
            default: A fallback value or zero-argument callback.

        Returns:
            The stored value or resolved fallback.
        """
        return Arr.get(self.wrapped, key, default)

    def has(self, key: str | int) -> bool:
        """Check whether a key exists, including when its value is ``None``.

        Args:
            key: A direct key, sequence index, or dot-addressed path.

        Returns:
            Whether the key path exists.
        """
        return Arr.has(self.wrapped, key)

    def is_set(self, key: str | int) -> bool:
        """Check whether a property exists and its value is not ``None``.

        Args:
            key: A direct key or object attribute name.

        Returns:
            Whether the value follows Python's null-safe ``isset`` rule.
        """
        wrapped: object = self.wrapped
        if isinstance(wrapped, Mapping):
            mapping = cast("Mapping[object, object]", wrapped)
            return mapping.get(key) is not None
        if isinstance(wrapped, (list, tuple)):
            sequence = cast("list[object] | tuple[object, ...]", wrapped)
            candidate = Arr.get(sequence, key)
            return candidate is not None
        if isinstance(key, str) and wrapped is not None:
            return getattr(wrapped, key, None) is not None
        return False

    def call(self, method_name: str, *args: object, **kwargs: object) -> object:
        """Invoke a wrapped object's method or a registered macro.

        Args:
            method_name: The method or macro identifier to invoke.
            *args: Positional call arguments.
            **kwargs: Keyword call arguments.

        Returns:
            The method or macro result, or ``None`` when the wrapped value
            is ``None``.

        Raises:
            AttributeError: If the wrapped object lacks the named method.
            TypeError: If the named attribute exists but is not callable.
        """
        if self.has_macro(method_name):
            return self.call_macro(method_name, *args, **kwargs)
        if self.wrapped is None:
            return None
        method = getattr(self.wrapped, method_name, _MISSING)
        if method is _MISSING:
            raise AttributeError
        if not callable(method):
            raise TypeError(method_name)
        return method(*args, **kwargs)

    async def call_async(
        self,
        method_name: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        """Invoke a wrapped method and await its result when necessary.

        Args:
            method_name: The method or macro identifier to invoke.
            *args: Positional call arguments.
            **kwargs: Keyword call arguments.

        Returns:
            The method result after any awaitable has completed.

        Notes:
            Cancellation propagates from the awaited operation unchanged.
        """
        result = self.call(method_name, *args, **kwargs)
        if inspect.isawaitable(result):
            return await cast("Awaitable[object]", result)
        return result

    def __getitem__(self, key: str | int) -> object:
        """Read a mapping key or sequence index without raising on absence.

        Args:
            key: A key, index, or dot-addressed path.

        Returns:
            The stored value, or ``None`` when it is absent.
        """
        return Arr.get(self.wrapped, key)

    def __setitem__(self, key: str | int, value: object) -> None:
        """Set a value when the wrapped object is a mutable mapping or list.

        Args:
            key: A key, index, or dot-addressed path.
            value: The value to assign.

        Raises:
            TypeError: If mutation crosses an immutable nested container.
        """
        wrapped: object = self.wrapped
        if isinstance(wrapped, MutableMapping):
            mapping = cast("MutableMapping[object, object]", wrapped)
            Arr.set(mapping, key, value)
        elif isinstance(wrapped, list):
            items = cast("list[object]", wrapped)
            Arr.set(items, key, value)

    def __delitem__(self, key: str | int) -> None:
        """Remove a value when the wrapped object supports mutation.

        Args:
            key: A key, index, or dot-addressed path to remove.
        """
        wrapped: object = self.wrapped
        if isinstance(wrapped, MutableMapping):
            mapping = cast("MutableMapping[object, object]", wrapped)
            Arr.forget(mapping, key)
        elif isinstance(wrapped, list):
            items = cast("list[object]", wrapped)
            Arr.forget(items, key)

    def __contains__(self, key: object) -> bool:
        """Check whether the wrapped mapping or sequence contains a key.

        Args:
            key: The key or index to search for.

        Returns:
            Whether the wrapped data contains the key.
        """
        return (
            self.has(key)
            if isinstance(
                key,
                (str, int),
            )
            else False
        )

    def __getattr__(self, name: str) -> object | None:
        """Return a wrapped object's attribute or ``None`` if unavailable.

        Args:
            name: The requested public attribute name.

        Returns:
            The attribute value, or ``None`` for a null or missing target.

        Raises:
            AttributeError: If a private wrapper attribute is requested.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        wrapped = self.__dict__.get("wrapped")
        if wrapped is None:
            return None
        return getattr(wrapped, name, None)


@overload
def optional[T](candidate: T) -> Optional[T]:
    """Describe the optional wrapper overload for static callers.

    The returned wrapper preserves the candidate's type parameter.
    """


@overload
def optional[T, R](
    candidate: T | None,
    callback: Callable[[T], R],
) -> R | None:
    """Describe the callback overload for static callers.

    The return type reflects callback execution only for non-null inputs.
    """


def optional(
    candidate: object = None,
    callback: Callable[..., object] | None = None,
) -> Optional[object] | object | None:
    """Wrap a value or run a callback only when the value is not ``None``.

    Args:
        candidate: The value to wrap or pass to ``callback``.
        callback: An optional synchronous callback.

    Returns:
        An :class:`Optional` wrapper without a callback, the callback result
        for a non-null value, or ``None`` for a null value.

    Raises:
        AsyncCallbackUsageError: If a synchronous callback returns an
            awaitable.
    """
    if callback is None:
        return Optional(candidate)
    if candidate is None:
        return None
    result = callback(candidate)
    if inspect.isawaitable(result):
        if inspect.iscoroutine(result):
            result.close()
        source = "optional callback"
        async_api = "optional_async"
        raise AsyncCallbackUsageError(source, async_api)
    return result


async def optional_async(
    candidate: object,
    callback: Callable[[object], object],
) -> object | None:
    """Apply a callback only for a non-null value and await its result.

    Args:
        candidate: The value supplied to the callback when non-null.
        callback: A callback that may return an awaitable.

    Returns:
        The callback result, or ``None`` when ``candidate`` is ``None``.

    Notes:
        Cancellation propagates from an awaited callback unchanged.
    """
    if candidate is None:
        return None
    result = callback(candidate)
    if inspect.isawaitable(result):
        return await cast("Awaitable[object]", result)
    return result


__all__ = ["Optional", "optional", "optional_async"]
