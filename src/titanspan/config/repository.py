"""Provide a mutable, typed repository for application configuration.

Nested lookups delegate to Titanspan's shared data helpers; mapping access
uses standard Python missing-key and deletion behavior.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeGuard, cast, overload

from titanspan.config.exceptions import ConfigValueError
from titanspan.contracts.config import (
    ConfigArray,
    ConfigDiagnostics,
    ConfigKeySequence,
    ConfigRepository,
    ScopedConfigOverrides,
    TypedConfigReader,
)
from titanspan.support.arr import Arr
from titanspan.support.macroable import Macroable

_UNSET = object()
_CONFIG_MAPPING_ERROR = "Configuration keys must be strings."
_BATCH_VALUE_ERROR = "A batch update does not accept a value."
_LIST_VALUE_ERROR = "Configuration value [{key}] must be a list."
_MAX_DIAGNOSTIC_DEPTH = 32
type _DiagnosticSequence = (
    list[object] | tuple[object, ...] | set[object] | frozenset[object]
)


@dataclass(frozen=True, slots=True)
class _OverrideLayer:
    """Store one patch layer or a complete scoped mutation snapshot.

    Attributes:
        values: Immutable-by-convention configuration values for the layer.
        replace: Whether the layer replaces the accumulated view entirely.
    """

    values: Mapping[str, object]
    replace: bool


def _is_exact_type[TValue](
    value: object,
    expected_type: type[TValue],
) -> TypeGuard[TValue]:
    """Narrow a value only when its concrete type matches exactly.

    Args:
        value: Configuration value being checked.
        expected_type: Exact Python type required by an accessor.

    Returns:
        Whether the value has precisely the requested type.
    """
    return type(value) is expected_type


def _copy_structure(value: object, memo: dict[int, object]) -> object:
    """Copy built-in configuration containers without cloning service values.

    Args:
        value: Value being copied for a snapshot or scoped override.
        memo: Identity map preserving repeated and recursive containers.

    Returns:
        A structural copy for built-in containers or the original leaf value.
    """
    identity = id(value)
    if identity in memo:
        return memo[identity]

    if isinstance(value, Mapping):
        result: dict[object, object] = {}
        memo[identity] = result
        mapping = cast("Mapping[object, object]", value)
        for key, item in mapping.items():
            result[key] = _copy_structure(item, memo)
        return result
    if isinstance(value, list):
        result_list: list[object] = []
        memo[identity] = result_list
        items = cast("list[object]", value)
        result_list.extend(_copy_structure(item, memo) for item in items)
        return result_list
    if isinstance(value, tuple):
        items = cast("tuple[object, ...]", value)
        result_tuple = tuple(_copy_structure(item, memo) for item in items)
        memo[identity] = result_tuple
        return result_tuple
    if isinstance(value, set):
        result_set: set[object] = set()
        memo[identity] = result_set
        items = cast("set[object]", value)
        result_set.update(_copy_structure(item, memo) for item in items)
        return result_set
    if isinstance(value, frozenset):
        result_frozen = frozenset(
            _copy_structure(item, memo)
            for item in cast("frozenset[object]", value)
        )
        memo[identity] = result_frozen
        return result_frozen
    return value


def _clone(value: object) -> object:
    """Return an independent structural copy of a configuration value.

    Args:
        value: Value to copy.

    Returns:
        A copy of built-in mapping and sequence containers.
    """
    return _copy_structure(value, {})


def _merge_override(
    target: dict[str, object],
    overrides: Mapping[str, object],
) -> None:
    """Apply one override layer while preserving unrelated nested values.

    Args:
        target: Mutable effective configuration snapshot.
        overrides: Dotted or top-level values in the override layer.

    """
    for key, value in overrides.items():
        existing = Arr.get(target, key, _UNSET)
        if (
            "." not in key
            and isinstance(existing, Mapping)
            and isinstance(value, Mapping)
        ):
            nested = dict(cast("Mapping[str, object]", existing))
            _merge_override(nested, cast("Mapping[str, object]", value))
            target[key] = nested
        else:
            Arr.set(target, key, _clone(value))


def _is_secret_key(key: str) -> bool:
    """Check common credential names before producing diagnostics.

    Args:
        key: Mapping key to inspect.

    Returns:
        Whether the key resembles a credential or private value.
    """
    normalized = "".join(
        character for character in key.casefold() if character.isalnum()
    )
    return any(
        marker in normalized
        for marker in (
            "password",
            "passwd",
            "secret",
            "token",
            "apikey",
            "authorization",
            "cookie",
            "privatekey",
            "accesskey",
            "credential",
        )
    )


def _safe_diagnostic(value: object, depth: int = 0) -> object:
    """Convert values into bounded, non-executable diagnostic data.

    Args:
        value: Configuration value to represent.
        depth: Current recursive nesting depth.

    Returns:
        JSON-compatible data with secrets masked and objects summarized.
    """
    if depth > _MAX_DIAGNOSTIC_DEPTH:
        return "<maximum depth>"
    if isinstance(value, float) and not math.isfinite(value):
        return "<non-finite float>"
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        mapping = cast("Mapping[object, object]", value)
        for key, item in mapping.items():
            name = (
                key if isinstance(key, str) else f"<{type(key).__name__} key>"
            )
            result[name] = (
                "[REDACTED]"
                if _is_secret_key(name)
                else _safe_diagnostic(item, depth + 1)
            )
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        items = cast("_DiagnosticSequence", value)
        return [_safe_diagnostic(item, depth + 1) for item in items]
    return f"<{type(value).__name__}>"


class Repository(
    Macroable,
    ConfigRepository,
    TypedConfigReader,
    ScopedConfigOverrides,
    ConfigDiagnostics,
):
    """Store and retrieve nested application configuration values.

    The repository implements the canonical Titanspan ``ConfigRepository``
    protocol and provides strict typed accessors and mapping syntax. Reads are
    synchronous. Configure values before serving traffic; concurrent mutation
    is not guaranteed to be safe.

    Attributes:
        _items: Structurally copied root mapping owned by the repository.
        _overrides: Context-local stack of temporary configuration layers.

    Notes:
        Literal mapping keys containing dots take precedence during reads.
        Mapping deletion removes the path and raises ``KeyError`` when it is
        absent.
    """

    def __init__(self, items: Mapping[str, object] | None = None) -> None:
        """Create a repository from a mapping of configuration namespaces.

        Args:
            items: Optional initial mapping. Built-in container values are
                structurally copied; opaque leaf objects retain their
                identity.

        Raises:
            TypeError: If the supplied root is not a mapping of string keys.
        """
        if items is None:
            self._items: dict[str, object] = {}
        else:
            self._validate_mapping(items)
            self._items = cast("dict[str, object]", _clone(items))
        self._overrides: ContextVar[tuple[_OverrideLayer, ...]] = ContextVar(
            f"titanspan_config_overrides_{id(self)}",
            default=(),
        )

    @staticmethod
    def _validate_mapping[Key](items: Mapping[Key, object]) -> None:
        """Require string keys for path-addressable configuration roots.

        Args:
            items: Mapping supplied to construction or batch mutation.

        Raises:
            TypeError: If any root key is not a string.
        """
        if not all(isinstance(key, str) for key in items):
            raise TypeError(_CONFIG_MAPPING_ERROR)

    def _effective_items(self) -> dict[str, object]:
        """Return the stored mapping or a merged snapshot for active scopes.

        Returns:
            The base mapping when no overrides are active, otherwise an
            independent nested snapshot with each override applied in order.
        """
        layers = self._overrides.get()
        if not layers:
            return self._items
        snapshot = cast("dict[str, object]", _clone(self._items))
        for layer in layers:
            if layer.replace:
                snapshot = cast("dict[str, object]", _clone(layer.values))
            else:
                _merge_override(snapshot, layer.values)
        return snapshot

    def _store_updates(self, updates: Mapping[str, object]) -> None:
        """Apply validated assignments to base or execution-local state.

        Scoped writes materialize the effective view and replace only the
        current ContextVar layer. The tuple and its mappings are never mutated
        in place, so child tasks cannot alter a parent's configuration view.

        Args:
            updates: Dotted paths and values to assign.
        """
        layers = self._overrides.get()
        target = (
            cast("dict[str, object]", _clone(self._effective_items()))
            if layers
            else cast("dict[str, object]", _clone(self._items))
        )
        for path, value in updates.items():
            Arr.set(target, path, _clone(value))

        if not layers:
            self._items = target
            return

        replacement = _OverrideLayer(
            values=MappingProxyType(target),
            replace=True,
        )
        self._overrides.set((*layers[:-1], replacement))

    def has(self, key: str) -> bool:
        """Check whether a configuration path exists.

        Args:
            key: A direct key or dotted path.

        Returns:
            Whether the path exists, including when its value is ``None``.
        """
        return Arr.has(self._effective_items(), key)

    @overload
    def get(
        self,
        key: str,
        default: object = None,
    ) -> object:
        """Retrieve one path with an optional fallback.

        Args:
            key: Direct key or dotted configuration path.
            default: Value or zero-argument callback used when absent.

        Returns:
            The stored value or the resolved fallback.
        """

    @overload
    def get(
        self,
        key: ConfigKeySequence,
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve several paths using one fallback value.

        Args:
            key: Ordered paths to retrieve.
            default: Shared fallback for missing paths.

        Returns:
            A mapping from each requested path to its resolved value.
        """

    @overload
    def get(
        self,
        key: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Retrieve paths with an individual fallback for each path.

        Args:
            key: Paths mapped to their respective fallback values.

        Returns:
            A mapping from requested paths to resolved values.
        """

    def get(
        self,
        key: str | Sequence[str] | Mapping[str, object],
        default: object = None,
    ) -> object:
        """Retrieve one path or multiple configured paths.

        Args:
            key: Path, sequence of paths, or per-path fallback mapping.
            default: Fallback for one path or for all sequence paths.

        Returns:
            The configured value or mapping of requested paths.

        Raises:
            TypeError: If a requested path is not text.
        """
        if isinstance(key, str):
            return _clone(Arr.get(self._effective_items(), key, default))
        if isinstance(key, Mapping):
            return self.get_many(key)
        return self.get_many(key, default)

    def get_many(
        self,
        keys: Sequence[str] | Mapping[str, object],
        default: object = None,
    ) -> Mapping[str, object]:
        """Resolve several paths with shared or per-path defaults.

        Args:
            keys: Ordered paths or a mapping of paths to fallback values.
            default: Shared fallback used only for a sequence of paths.

        Returns:
            A regular dictionary keyed by the requested path strings.

        Raises:
            TypeError: If a path is not text.
        """
        if isinstance(keys, Mapping):
            pairs = keys.items()
        else:
            pairs = ((key, default) for key in keys)

        result: dict[str, object] = {}
        items = self._effective_items()
        for key, fallback in pairs:
            result[key] = _clone(Arr.get(items, key, fallback))
        return result

    def all(self) -> Mapping[str, object]:
        """Return an independent read-only snapshot of all values.

        Returns:
            A mapping proxy around copied built-in containers. Custom leaf
            objects retain their identity and are not implicitly serialized.
        """
        snapshot = cast("dict[str, object]", _clone(self._effective_items()))
        return MappingProxyType(snapshot)

    def set(
        self,
        key: str | Mapping[str, object],
        value: object = _UNSET,
    ) -> None:
        """Assign one dotted path or apply a batch of path assignments.

        Batch updates validate all keys and apply to a structural copy before
        replacing the stored root, so invalid batches do not partially apply.

        Args:
            key: Dotted path or mapping of dotted paths to values.
            value: Assigned value when ``key`` is a string. ``None`` is a
                valid value; omission is distinguished internally.

        Raises:
            TypeError: If a path or batch key is not a string.
        """
        if isinstance(key, Mapping):
            if value is not _UNSET:
                raise TypeError(_BATCH_VALUE_ERROR)
            self._validate_mapping(key)
            self._store_updates(key)
            return
        assigned = None if value is _UNSET else value
        self._store_updates({key: assigned})

    def prepend(self, key: str, value: object) -> None:
        """Insert a value before an existing list-valued setting.

        Args:
            key: Dotted path to the list.
            value: Value inserted at index zero.

        Raises:
            TypeError: If the existing setting is not a list.
        """
        existing = self.get(key, [])
        if not isinstance(existing, list):
            raise TypeError(_LIST_VALUE_ERROR.format(key=key))
        items = cast("list[object]", existing)
        self.set(key, [value, *items])

    def push(self, key: str, value: object) -> None:
        """Append a value to an existing list-valued setting.

        Args:
            key: Dotted path to the list.
            value: Value appended after existing list entries.

        Raises:
            TypeError: If the existing setting is not a list.
        """
        existing = self.get(key, [])
        if not isinstance(existing, list):
            raise TypeError(_LIST_VALUE_ERROR.format(key=key))
        items = cast("list[object]", existing)
        self.set(key, [*items, value])

    def string(
        self,
        key: str,
        default: str | Callable[[], str] | None = None,
    ) -> str:
        """Return a configured string without coercing other values.

        Args:
            key: Configuration path to retrieve.
            default: Optional string value or lazy string fallback.

        Returns:
            The stored string or resolved fallback.

        Raises:
            ConfigValueError: If the resolved value is not a string.
        """
        return self._typed_value(key, default, str, "a string")

    def integer(
        self,
        key: str,
        default: int | Callable[[], int] | None = None,
    ) -> int:
        """Return a configured integer while rejecting booleans.

        Args:
            key: Configuration path to retrieve.
            default: Optional integer value or lazy integer fallback.

        Returns:
            The stored integer or resolved fallback.

        Raises:
            ConfigValueError: If the value is not an integer or is a boolean.
        """
        value = self.get(key, default)
        if not _is_exact_type(value, int):
            raise ConfigValueError(key, "an integer", value)
        return value

    def float(
        self,
        key: str,
        default: float | Callable[[], float] | None = None,
    ) -> float:
        """Return a configured float without accepting integers or strings.

        Args:
            key: Configuration path to retrieve.
            default: Optional float value or lazy float fallback.

        Returns:
            The stored float or resolved fallback.

        Raises:
            ConfigValueError: If the resolved value is not a float.
        """
        value = self.get(key, default)
        if not _is_exact_type(value, float):
            raise ConfigValueError(key, "a float", value)
        return value

    def boolean(
        self,
        key: str,
        default: bool | Callable[[], bool] | None = None,
    ) -> bool:
        """Return a configured boolean without numeric coercion.

        Args:
            key: Configuration path to retrieve.
            default: Optional boolean value or lazy boolean fallback.

        Returns:
            The stored boolean or resolved fallback.

        Raises:
            ConfigValueError: If the resolved value is not a boolean.
        """
        value = self.get(key, default)
        if not _is_exact_type(value, bool):
            raise ConfigValueError(key, "a boolean", value)
        return value

    def array(
        self,
        key: str,
        default: ConfigArray | Callable[[], ConfigArray] | None = None,
    ) -> ConfigArray:
        """Return a mapping or list setting without coercion.

        Args:
            key: Configuration path to retrieve.
            default: Optional mapping/list value or lazy fallback.

        Returns:
            The stored mapping/list or resolved fallback.

        Raises:
            ConfigValueError: If the resolved value is not a mapping or list.
        """
        value = self.get(key, default)
        if isinstance(value, (Mapping, list)):
            return cast("ConfigArray", value)
        raise ConfigValueError(key, "a mapping or list", value)

    def _typed_value[TValue](
        self,
        key: str,
        default: TValue | Callable[[], TValue] | None,
        expected_type: type[TValue],
        expected: str,
    ) -> TValue:
        """Validate a configured value against one precise runtime type.

        Args:
            key: Configuration path to retrieve.
            default: Optional typed fallback.
            expected_type: Runtime type required by the accessor.
            expected: Safe human-readable type description.

        Returns:
            The matching stored value.

        Raises:
            ConfigValueError: If the resolved value has another type.
        """
        value = self.get(key, default)
        if not _is_exact_type(value, expected_type):
            raise ConfigValueError(key, expected, value)
        return value

    @contextmanager
    def override(
        self,
        values: Mapping[str, object],
    ) -> Generator[None, None, None]:
        """Apply temporary path overrides in the active execution context.

        Overrides are copied and restored with a ContextVar token, including
        when an exception or cancellation exits the context.

        Args:
            values: Dotted or nested values to override temporarily.

        Yields:
            Control while this context sees the effective override.
        """
        self._validate_mapping(values)
        layer = cast("Mapping[str, object]", _clone(values))
        previous = self._overrides.get()
        token: Token[tuple[_OverrideLayer, ...]] = self._overrides.set(
            (*previous, _OverrideLayer(values=layer, replace=False))
        )
        try:
            yield
        finally:
            self._overrides.reset(token)

    def redacted(self) -> Mapping[str, object]:
        """Return a safe diagnostic snapshot with common secrets masked.

        Returns:
            A bounded mapping suitable for inspection and serialization.
        """
        safe = cast(
            "dict[str, object]",
            _safe_diagnostic(self._effective_items()),
        )
        return MappingProxyType(safe)

    def __getitem__(self, key: str) -> object:
        """Retrieve a mapping-style value, raising for absent paths.

        Args:
            key: Direct key or dotted path.

        Returns:
            The configured value.

        Raises:
            KeyError: If the path does not exist.
        """
        if not self.has(key):
            raise KeyError(key)
        return self.get(key)

    def __setitem__(self, key: str, value: object) -> None:
        """Assign a mapping-style path through the repository API.

        Args:
            key: Direct key or dotted path.
            value: Value to store, including explicit ``None``.
        """
        self.set(key, value)

    def __contains__(self, key: object) -> bool:
        """Check whether a text path exists in the repository.

        Args:
            key: Candidate configuration key.

        Returns:
            Whether the string path exists.
        """
        return isinstance(key, str) and self.has(key)

    def __delitem__(self, key: str) -> None:
        """Remove a configured path using mapping deletion semantics.

        Args:
            key: Direct key or dotted path to remove.

        Raises:
            KeyError: If the path does not exist in the base configuration.
        """
        target = self._effective_items()
        if not Arr.has(target, key):
            raise KeyError(key)
        Arr.forget(target, key)
        layers = self._overrides.get()
        if not layers:
            self._items = target
            return
        replacement = _OverrideLayer(
            values=MappingProxyType(target),
            replace=True,
        )
        self._overrides.set((*layers[:-1], replacement))

    def __repr__(self) -> str:
        """Render a safe representation without exposing secret values.

        Returns:
            A redacted structural representation.
        """
        return f"Repository({dict(self.redacted())!r})"


__all__ = ["ConfigArray", "Repository"]
