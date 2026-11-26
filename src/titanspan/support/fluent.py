"""Provide mutable, expressive attribute data with Python-facing APIs.

``Fluent`` combines Python mapping behavior with nested data access,
conditional callbacks, macros, and explicit dynamic setter calls. Its
serialization remains based on the Python standard library.
"""

from __future__ import annotations

import json
from collections.abc import Hashable, Iterable, Iterator, Mapping
from typing import Self, TypeVar, cast, overload

from titanspan.support.conditionable import Conditionable
from titanspan.support.helpers import data_get, data_has, data_set
from titanspan.support.macroable import Macroable

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")
_MISSING = object()
_PAIR_LENGTH = 2


class Fluent[K: Hashable, V](Macroable, Conditionable):
    """Store mapping data behind fluent, attribute-oriented operations.

    The class accepts mappings, iterables of key/value pairs, iterables of
    values, and model-like objects that expose ``model_dump`` or ``to_dict``.
    Dynamic property access is available for convenience; explicit mapping
    access and :meth:`dynamic_call` remain the statically visible APIs.

    Attributes:
        attributes: The mutable mapping owned by this Fluent instance.

    Notes:
        Stored values use Python object identity and mutation semantics.
        Reading a missing dynamic attribute returns ``None`` for convenience;
        use :meth:`value` when a fallback is needed.
    """

    attributes: dict[K, V]

    def __init__(self, attributes: object = None) -> None:
        """Create a Fluent instance from supported mapping-like input.

        Args:
            attributes: A mapping, iterable, Pydantic-style model, or object.

        Raises:
            TypeError: If ``attributes`` cannot be represented as key/value
                data.
        """
        object.__setattr__(self, "attributes", {})
        self.fill(attributes)

    @classmethod
    def make(cls: type[Self], attributes: object = None) -> Self:
        """Construct a new instance of the receiving Fluent subclass.

        Args:
            attributes: The input data used to initialize the new instance.

        Returns:
            A new instance of ``cls``.
        """
        return cls(attributes)

    def get(
        self,
        key: str | int | K,
        default: object = None,
    ) -> object:
        """Read a nested attribute using dot-separated path syntax.

        Args:
            key: A key or path to retrieve.
            default: A fallback value or zero-argument callable.

        Returns:
            The matching data or resolved fallback.
        """
        if isinstance(key, (str, int)):
            return data_get(self.attributes, key, default)
        try:
            candidate = self.attributes.get(key, _MISSING)
        except TypeError:
            candidate = _MISSING
        if candidate is not _MISSING:
            return candidate
        return default() if callable(default) else default

    def set(self, key: str | int | K, value: V) -> Self:
        """Set a direct or nested attribute and return this instance.

        Args:
            key: A key or dot-separated path.
            value: The value assigned at the path.

        Returns:
            This instance for fluent chaining.
        """
        if isinstance(key, (str, int)):
            data_set(self.attributes, key, value)
        else:
            self.attributes[key] = value
        return self

    def has(self, key: str | int) -> bool:
        """Check whether a direct or nested key exists, including ``None``.

        Args:
            key: A direct key or dot-separated path.

        Returns:
            Whether the requested path exists.
        """
        return data_has(self.attributes, key)

    def is_set(self, key: str) -> bool:
        """Check a direct attribute using null-aware ``isset`` semantics.

        Args:
            key: The direct string key to inspect.

        Returns:
            Whether the key exists and contains a non-``None`` value.
        """
        return self.attributes.get(cast("K", key)) is not None

    def fill(self, attributes: object) -> Self:
        """Merge supported key/value data into this instance.

        Mappings and iterable key/value pairs preserve their keys. Other
        iterables become integer-indexed attributes. Model-like values are
        converted through their public ``model_dump`` or ``to_dict`` method.

        Args:
            attributes: The data to merge into the current attributes.

        Returns:
            This instance after the merge.

        Raises:
            TypeError: If the input is not representable as key/value data.
        """
        converted = _coerce_attributes(attributes)
        for key, value in converted.items():
            self.attributes[cast("K", key)] = cast("V", value)
        return self

    def value(self, key: K, default: object = None) -> V | object:
        """Read a direct key without interpreting dots in its name.

        Args:
            key: The direct key to look up.
            default: A fallback value or zero-argument callable.

        Returns:
            The stored value or resolved fallback.
        """
        candidate = self.attributes.get(key, _MISSING)
        if candidate is not _MISSING:
            return candidate
        return default() if callable(default) else default

    def scope(self, key: str | int, default: object = None) -> Self:
        """Create a new Fluent instance from a nested value.

        Args:
            key: The nested path to convert.
            default: The value used when the path is absent.

        Returns:
            A new instance of the same Fluent subclass.
        """
        return type(self)(_coerce_attributes(self.get(key, default)))

    @overload
    def all(self: Fluent[K, V], keys: None = None) -> dict[K, V]:
        """Describe the full-attributes overload of :meth:`all`.

        The return type retains the key and value parameters.
        """

    @overload
    def all(
        self,
        keys: str | int | Iterable[str | int],
        *more_keys: str | int,
    ) -> dict[K, V]:
        """Describe the selected-attributes overload of :meth:`all`.

        The result retains the Fluent key and value parameters.
        """

    def all(
        self,
        keys: str | int | Iterable[str | int] | None = None,
        *more_keys: str | int,
    ) -> dict[K, V]:
        """Return all attributes or a nested subset of requested paths.

        Args:
            keys: An optional path or iterable of paths to select.
            *more_keys: Additional paths supplied as separate arguments.

        Returns:
            A shallow copy of all attributes or a nested selected mapping.
        """
        if keys is None:
            return dict(self.attributes)
        if isinstance(keys, (str, int)):
            selected_keys: list[str | int] = [keys, *more_keys]
        else:
            selected_keys = list(keys) + list(more_keys)
        if not selected_keys:
            return dict(self.attributes)

        result: dict[Hashable, object] = {}
        for key in selected_keys:
            data_set(result, key, data_get(self.attributes, key))
        return cast("dict[K, V]", result)

    def to_json(
        self,
        *,
        indent: int | None = None,
        ensure_ascii: bool = True,
    ) -> str:
        """Encode attributes as JSON with standard library options.

        Args:
            indent: Optional indentation width for readable output.
            ensure_ascii: Escape non-ASCII code points when true.

        Returns:
            A JSON string generated by Python's standard library.

        Raises:
            TypeError: If an attribute value cannot be serialized.
            ValueError: If an attribute contains non-finite numeric values.
        """
        separators = None if indent is not None else (",", ":")
        return json.dumps(
            self.attributes,
            indent=indent,
            ensure_ascii=ensure_ascii,
            separators=separators,
            allow_nan=False,
        )

    def to_pretty_json(self, *, ensure_ascii: bool = True) -> str:
        """Encode attributes as indented JSON.

        Args:
            ensure_ascii: Escape non-ASCII code points when true.

        Returns:
            A JSON string indented by four spaces.
        """
        return self.to_json(indent=4, ensure_ascii=ensure_ascii)

    def is_empty(self) -> bool:
        """Return whether this instance has no attributes.

        Returns:
            Whether the attribute mapping is empty.
        """
        return not self.attributes

    def is_not_empty(self) -> bool:
        """Return whether this instance has any attributes.

        Returns:
            Whether the attribute mapping is non-empty.
        """
        return not self.is_empty()

    def dynamic_call(self, name: str, *arguments: object) -> object:
        """Invoke a macro or set an attribute through an explicit call API.

        Args:
            name: The macro or attribute name.
            *arguments: The first argument becomes the stored value; when no
                argument is supplied, the value is ``True``.

        Returns:
            This instance for fluent chaining.
        """
        if self.has_macro(name):
            return self.call_macro(name, *arguments)
        value = arguments[0] if arguments else True
        self.attributes[cast("K", name)] = cast("V", value)
        return self

    def __getitem__(self, key: K) -> V | None:
        """Retrieve a direct key, returning ``None`` when it is absent.

        Args:
            key: The key to retrieve.

        Returns:
            The matching value or ``None`` for an absent key.
        """
        return self.attributes.get(key)

    def __setitem__(self, key: K, value: V) -> None:
        """Assign a direct key using Python mapping semantics.

        Args:
            key: The key to set.
            value: The value to store.
        """
        self.attributes[key] = value

    def __delitem__(self, key: K) -> None:
        """Delete a direct key using Python mapping semantics.

        Args:
            key: The key to delete.

        """
        del self.attributes[key]

    def __contains__(self, key: object) -> bool:
        """Check whether a direct key exists, even when its value is null.

        Args:
            key: The key to search for.

        Returns:
            Whether the key exists.
        """
        try:
            return cast("K", key) in self.attributes
        except TypeError:
            return False

    def __iter__(self) -> Iterator[K]:
        """Iterate over attribute keys in insertion order.

        Returns:
            An iterator over mapping keys.
        """
        return iter(self.attributes)

    def __len__(self) -> int:
        """Return the number of direct attributes.

        Returns:
            The number of stored keys.
        """
        return len(self.attributes)

    def __getattr__(self, name: str) -> V | None:
        """Read an attribute value, returning ``None`` when absent.

        Args:
            name: The dynamic attribute name.

        Returns:
            The stored value or ``None``.

        Raises:
            AttributeError: If a private attribute is requested.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        stored = self.__dict__.get("attributes")
        if not isinstance(stored, dict):
            return None
        values = cast("dict[Hashable, object]", stored)
        return cast("V | None", values.get(name))

    def __setattr__(self, name: str, value: object) -> None:
        """Store public dynamic attributes without shadowing Fluent methods.

        Args:
            name: The attribute name.
            value: The value to store.
        """
        if name.startswith("_") or name == "attributes":
            object.__setattr__(self, name, value)
            return
        if hasattr(type(self), name):
            stored = self.__dict__.get("attributes")
            if isinstance(stored, dict):
                stored[cast("K", name)] = cast("V", value)
                return
        values = self.__dict__.get("attributes")
        if isinstance(values, dict):
            values[cast("K", name)] = cast("V", value)
            return
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        """Delete a dynamic attribute or a normal Python instance attribute.

        Args:
            name: The attribute name to delete.

        Raises:
            AttributeError: If neither the mapping nor object has the name.
        """
        values = self.__dict__.get("attributes")
        if isinstance(values, dict) and name in values:
            del values[name]
            return
        object.__delattr__(self, name)


def _coerce_attributes(source: object) -> dict[Hashable, object]:
    """Convert Python mapping-like values to an attribute dictionary.

    Args:
        source: The input mapping, iterable, model, or object.

    Returns:
        A new dictionary of keys and values.

    Raises:
        TypeError: If the input has no supported mapping representation.
    """
    if source is None:
        return {}
    if isinstance(source, Mapping):
        mapping = cast("Mapping[Hashable, object]", source)
        return dict(mapping.items())
    converted = _object_mapping(source)
    if converted is not None:
        return converted
    if isinstance(source, Iterable) and not isinstance(
        source,
        (str, bytes, bytearray),
    ):
        values = list(cast("Iterable[object]", source))
        if values and all(_is_pair(item) for item in values):
            return {
                cast("Hashable", item[0]): item[1]
                for item in cast("list[tuple[object, object]]", values)
            }
        return dict(enumerate(values))
    return {0: source}


def _object_mapping(source: object) -> dict[Hashable, object] | None:
    """Read public model or object data without calling private APIs.

    Args:
        source: The object to inspect for a conversion method.

    Returns:
        Converted public mapping data, or ``None`` when no method applies.
    """
    for method_name in ("model_dump", "to_dict"):
        method = getattr(source, method_name, None)
        if not callable(method):
            continue
        result = method()
        if isinstance(result, Mapping):
            mapping = cast("Mapping[Hashable, object]", result)
            return dict(mapping.items())
    attributes = getattr(source, "__dict__", None)
    if isinstance(attributes, dict):
        mapping = cast("dict[Hashable, object]", attributes)
        return {
            key: value
            for key, value in mapping.items()
            if not (isinstance(key, str) and key.startswith("_"))
        }
    return None


def _is_pair(candidate: object) -> bool:
    """Check whether an iterable item can represent a key/value pair.

    Args:
        candidate: The value to inspect.

    Returns:
        Whether it is a two-item sequence with a hashable first value.
    """
    if not isinstance(candidate, tuple):
        return False
    pair = cast("tuple[object, ...]", candidate)
    if len(pair) != _PAIR_LENGTH:
        return False
    try:
        hash(pair[0])
    except TypeError:
        return False
    return True


__all__ = ["Fluent"]
