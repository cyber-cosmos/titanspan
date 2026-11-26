"""Persist safe route inspection metadata as validated JSON snapshots.

The cache never reconstructs routes or serializes live application objects.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from titanspan.routing.exceptions import (
    RouteCacheError,
    StaleRouteCacheError,
    UnsupportedRouteCacheError,
)

if TYPE_CHECKING:
    from types import FunctionType

    from titanspan.contracts.routing.types import RouteAction
    from titanspan.routing.router import Router

_CACHE_VERSION = 1
_CONTROLLER_ACTION_PARTS = 2
_CACHE_VERSION_ERROR = "The route cache format is unsupported."
_CACHE_READ_ERROR = "The route metadata cache could not be read."
_CACHE_WRITE_ERROR = "The route metadata cache could not be written."
_STALE_CACHE_ERROR = "The route metadata cache is stale."
_UNSUPPORTED_CACHE_VALUE_ERROR = (
    "Route metadata cache requires a stable identity and JSON-safe values."
)


@dataclass(frozen=True, slots=True)
class RouteCacheEntry:
    """Represent one validated, immutable route inspection record.

    The action field stores its import identity, never a live callable object.
    """

    methods: tuple[str, ...]
    path: str
    protocol: str
    name: str | None
    action: str
    middleware: tuple[str, ...]
    domain: str | None
    constraints: Mapping[str, str]
    defaults: Mapping[str, object]

    def __post_init__(self) -> None:
        """Freeze the mappings retained by this inspection record.

        Nested JSON values cannot mutate the frozen cache entry afterward.
        """
        object.__setattr__(
            self,
            "constraints",
            MappingProxyType(dict(self.constraints)),
        )
        object.__setattr__(
            self,
            "defaults",
            MappingProxyType(
                {
                    key: _freeze_json_value(value)
                    for key, value in self.defaults.items()
                },
            ),
        )


class RouteCache:
    """Write and validate an application-specific route metadata file.

    Applications still discover routes normally; this cache provides a
    validated metadata snapshot for read-only tooling.
    """

    def __init__(self, path: Path) -> None:
        """Retain the exact JSON cache path selected by the application.

        Args:
            path: File used for safe routing metadata snapshots.
        """
        self._path = path

    def write(self, router: Router) -> None:
        """Atomically persist metadata from the canonical route catalog.

        Args:
            router: Application router whose registration order is retained.

        Raises:
            UnsupportedRouteCacheError: If any live route value is unsafe.
            RouteCacheError: If the JSON file cannot be written.
        """
        entries = _serialized_entries(router)
        document = {
            "version": _CACHE_VERSION,
            "fingerprint": _fingerprint(entries),
            "routes": entries,
        }
        temporary_path: Path | None = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as output:
                temporary_path = Path(output.name)
                json.dump(
                    document,
                    output,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                output.write("\n")
            temporary_path.replace(self._path)
        except OSError as error:
            raise RouteCacheError(_CACHE_WRITE_ERROR) from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def read(self, router: Router) -> tuple[RouteCacheEntry, ...]:
        """Read metadata only when it exactly matches the current catalog.

        Args:
            router: Current router used to detect stale route metadata.

        Returns:
            Immutable route records in declaration order.

        Raises:
            RouteCacheError: If the file is missing, invalid, or unsupported.
            StaleRouteCacheError: If live route metadata differs from the file.
            UnsupportedRouteCacheError: If live actions lack stable identity.
        """
        try:
            raw_document = json.loads(
                self._path.read_text(encoding="utf-8"),
            )
        except (OSError, json.JSONDecodeError) as error:
            raise RouteCacheError(_CACHE_READ_ERROR) from error
        if not isinstance(raw_document, dict):
            raise RouteCacheError(_CACHE_VERSION_ERROR)
        document = cast("dict[str, object]", raw_document)
        if document.get("version") != _CACHE_VERSION:
            raise RouteCacheError(_CACHE_VERSION_ERROR)
        raw_entries = document.get("routes")
        if not isinstance(raw_entries, list):
            raise RouteCacheError(_CACHE_READ_ERROR)
        cached_entries: list[dict[str, object]] = []
        for entry in cast("list[object]", raw_entries):
            if not isinstance(entry, dict):
                raise RouteCacheError(_CACHE_READ_ERROR)
            cached_entries.append(cast("dict[str, object]", entry))
        entries = _serialized_entries(router)
        if (
            document.get("fingerprint") != _fingerprint(entries)
            or cached_entries != entries
        ):
            raise StaleRouteCacheError(_STALE_CACHE_ERROR)
        return tuple(_entry_from_dict(entry) for entry in entries)


def _serialized_entries(router: Router) -> list[dict[str, object]]:
    """Convert current route definitions into safe JSON metadata.

    Args:
        router: Canonical route collection owner.

    Returns:
        JSON-compatible records in declaration order.

    Raises:
        UnsupportedRouteCacheError: If a route has unstable live metadata.
    """
    entries: list[dict[str, object]] = []
    for route in router.routes.all():
        action = route.action
        if action is None:
            raise UnsupportedRouteCacheError(
                _UNSUPPORTED_CACHE_VALUE_ERROR,
            )
        entries.append(
            {
                "methods": list(route.methods),
                "path": route.path,
                "protocol": route.protocol,
                "name": route.route_name,
                "action": _action_identity(action),
                "middleware": [
                    _middleware_identity(item)
                    for item in route.middleware_types
                ],
                "domain": route.domain_name,
                "constraints": dict(route.constraints),
                "defaults": _json_value(dict(route.default_values)),
            },
        )
    return entries


def _action_identity(action: RouteAction) -> str:
    """Return a stable import identity without retaining the live callable.

    Args:
        action: Native route action value.

    Returns:
        A module-qualified controller or function identity.

    Raises:
        UnsupportedRouteCacheError: If the action is local or stateful.
    """
    if isinstance(action, tuple):
        return _controller_action_identity(
            cast("tuple[object, ...]", action),
        )
    if isinstance(action, type):
        return f"controller:{_type_identity(action)}.__call__"
    if inspect.ismethod(action):
        if action.__self__ is not None and not isinstance(
            action.__self__,
            type,
        ):
            raise UnsupportedRouteCacheError(
                _UNSUPPORTED_CACHE_VALUE_ERROR,
            )
        action = action.__func__
    if inspect.isfunction(action):
        return _function_identity(action)
    raise UnsupportedRouteCacheError(_UNSUPPORTED_CACHE_VALUE_ERROR)


def _controller_action_identity(action: tuple[object, ...]) -> str:
    """Describe a valid controller and method pair for route metadata.

    Args:
        action: Candidate controller action tuple.

    Returns:
        Stable controller class and method identity.

    Raises:
        UnsupportedRouteCacheError: If the action tuple is malformed.
    """
    if len(action) != _CONTROLLER_ACTION_PARTS:
        raise UnsupportedRouteCacheError(_UNSUPPORTED_CACHE_VALUE_ERROR)
    controller, method = action
    if isinstance(controller, type) and isinstance(method, str):
        return f"controller:{_type_identity(controller)}.{method}"
    raise UnsupportedRouteCacheError(_UNSUPPORTED_CACHE_VALUE_ERROR)


def _function_identity(action: FunctionType) -> str:
    """Build a stable identity for one importable route function.

    Args:
        action: Route function selected from the native metadata.

    Returns:
        Stable module or source-file identity and qualified function name.

    Raises:
        UnsupportedRouteCacheError: If the action is local or unstable.
    """
    module = action.__module__
    qualified_name = action.__qualname__
    if "<locals>" in qualified_name or "<lambda>" in qualified_name:
        raise UnsupportedRouteCacheError(_UNSUPPORTED_CACHE_VALUE_ERROR)
    if module.startswith("_titanspan_routes_"):
        source = Path(action.__code__.co_filename)
        if source.is_file():
            return f"callable-file:{source.resolve()}:{qualified_name}"
        raise UnsupportedRouteCacheError(_UNSUPPORTED_CACHE_VALUE_ERROR)
    return f"callable:{module}.{qualified_name}"


def _type_identity(value: type[object]) -> str:
    """Build a stable class identity for cache metadata.

    Args:
        value: Controller or middleware class.

    Returns:
        Module-qualified class name.

    Raises:
        UnsupportedRouteCacheError: If the class is local to a callable.
    """
    qualified_name = value.__qualname__
    if "<locals>" in qualified_name:
        raise UnsupportedRouteCacheError(_UNSUPPORTED_CACHE_VALUE_ERROR)
    return f"{value.__module__}.{qualified_name}"


def _middleware_identity(value: str | type[object]) -> str:
    """Describe a middleware alias or class without serializing the object.

    Args:
        value: Route middleware alias or implementation type.

    Returns:
        Stable text identity for the route inspection snapshot.
    """
    if isinstance(value, str):
        return f"alias:{value}"
    return f"middleware:{_type_identity(value)}"


def _json_value(value: object) -> object:
    """Convert only JSON-safe metadata values into builtin containers.

    Args:
        value: Route default metadata selected by the application.

    Returns:
        A JSON scalar, list, or string-keyed mapping.

    Raises:
        UnsupportedRouteCacheError: If the value needs custom serialization.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        raise UnsupportedRouteCacheError(_UNSUPPORTED_CACHE_VALUE_ERROR)
    if isinstance(value, (list, tuple)):
        sequence = cast("Sequence[object]", value)
        return [_json_value(item) for item in sequence]
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        if not all(isinstance(key, str) for key in mapping):
            raise UnsupportedRouteCacheError(_UNSUPPORTED_CACHE_VALUE_ERROR)
        string_mapping = cast("Mapping[str, object]", mapping)
        return {key: _json_value(item) for key, item in string_mapping.items()}
    raise UnsupportedRouteCacheError(_UNSUPPORTED_CACHE_VALUE_ERROR)


def _fingerprint(entries: list[dict[str, object]]) -> str:
    """Hash canonical route metadata with stable key ordering.

    Args:
        entries: JSON-compatible route records.

    Returns:
        SHA-256 hex digest for stale-metadata detection.
    """
    encoded = json.dumps(
        entries,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _entry_from_dict(entry: dict[str, object]) -> RouteCacheEntry:
    """Validate one metadata object already matched against live routes.

    Args:
        entry: Cached JSON object equal to its live metadata counterpart.

    Returns:
        Immutable route cache entry.
    """
    return RouteCacheEntry(
        methods=tuple(cast("list[str]", entry["methods"])),
        path=cast("str", entry["path"]),
        protocol=cast("str", entry["protocol"]),
        name=cast("str | None", entry["name"]),
        action=cast("str", entry["action"]),
        middleware=tuple(cast("list[str]", entry["middleware"])),
        domain=cast("str | None", entry["domain"]),
        constraints=cast("dict[str, str]", entry["constraints"]),
        defaults=cast("dict[str, object]", entry["defaults"]),
    )


def _freeze_json_value(value: object) -> object:
    """Recursively freeze a JSON value retained by a cache record.

    Args:
        value: JSON scalar, mapping, or list.

    Returns:
        Immutable mapping or tuple for every nested container.
    """
    if isinstance(value, dict):
        return MappingProxyType(
            {
                key: _freeze_json_value(item)
                for key, item in cast("dict[str, object]", value).items()
            },
        )
    if isinstance(value, list):
        return tuple(
            _freeze_json_value(item) for item in cast("list[object]", value)
        )
    return value


__all__ = [
    "RouteCache",
    "RouteCacheEntry",
]
