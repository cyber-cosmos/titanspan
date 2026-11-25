"""Persist configuration snapshots using a validated JSON envelope.

The cache never executes generated code or deserializes Python objects.
Unsupported values are rejected because stringifying them would change
application semantics and could conceal an unsafe configuration.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import cast

from titanspan.config.exceptions import ConfigurationCacheError

_CACHE_SCHEMA_VERSION = 1
_CACHE_DISTRIBUTION = "titanspan"
_MAX_CACHE_DEPTH = 64
_CACHE_FIELDS = frozenset(
    {"schema_version", "package_version", "configuration"}
)
_CACHE_DEPTH_ERROR = "configuration exceeds the supported nesting depth"
_CACHE_FLOAT_ERROR = "configuration contains a non-finite number"
_CACHE_CYCLE_ERROR = "configuration contains a recursive value"
_CACHE_KEY_ERROR = "configuration mapping keys must be text"
_CACHE_VALUE_ERROR = "configuration contains a non-JSON value"
_CACHE_PATH_ERROR = "cache path must be text or pathlib.Path"


def _package_version(path: Path) -> str:
    """Read installed Titanspan version for cache compatibility checks.

    Args:
        path: Cache path used for safe error reporting.

    Returns:
        Installed distribution version.

    Raises:
        ConfigurationCacheError: If distribution metadata is unavailable.
    """
    try:
        return version(_CACHE_DISTRIBUTION)
    except PackageNotFoundError:
        raise ConfigurationCacheError(
            str(path),
            "Titanspan distribution metadata is unavailable",
        ) from None


def _json_value(
    value: object,
    active: set[int],
    depth: int,
) -> object:
    """Validate and copy one value into the supported JSON data model.

    Args:
        value: Configuration value being validated.
        active: Container identities on the current recursion path.
        depth: Current nesting depth.

    Returns:
        A copied value containing only safe JSON primitives and containers.

    Raises:
        TypeError: If the value contains an unsupported Python object.
        ValueError: If the value is cyclic, too deeply nested, or non-finite.
    """
    if depth > _MAX_CACHE_DEPTH:
        raise ValueError(_CACHE_DEPTH_ERROR)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(_CACHE_FLOAT_ERROR)
        return value

    identity = id(value)
    if identity in active:
        raise ValueError(_CACHE_CYCLE_ERROR)
    if isinstance(value, Mapping):
        active.add(identity)
        try:
            result: dict[str, object] = {}
            mapping = cast("Mapping[object, object]", value)
            for key, item in mapping.items():
                if not isinstance(key, str):
                    raise TypeError(_CACHE_KEY_ERROR)
                result[key] = _json_value(item, active, depth + 1)
            return result
        finally:
            active.remove(identity)
    if isinstance(value, (list, tuple)):
        active.add(identity)
        try:
            items = cast("list[object] | tuple[object, ...]", value)
            return [_json_value(item, active, depth + 1) for item in items]
        finally:
            active.remove(identity)
    raise TypeError(_CACHE_VALUE_ERROR)


class ConfigCache:
    """Atomically write and validate a sensitive configuration snapshot.

    Cache files use UTF-8 JSON, include schema and distribution versions, and
    are created with owner-only permissions. Callers own the chosen location
    and must keep it out of version control and public artifacts.

    Attributes:
        path: The single cache file managed by this object.
    """

    def __init__(self, path: str | Path) -> None:
        """Select the cache file without touching the filesystem.

        Args:
            path: Explicit application cache path.

        Raises:
            TypeError: If the path is not text or a ``Path``.
        """
        self.path = Path(path)

    def write(self, configuration: Mapping[str, object]) -> None:
        """Validate and atomically persist a JSON-compatible snapshot.

        Args:
            configuration: Complete root configuration mapping.

        Raises:
            ConfigurationCacheError: If values are unsupported or filesystem
                operations fail.
        """
        try:
            safe_configuration = cast(
                "dict[str, object]",
                _json_value(configuration, set(), 0),
            )
            payload: dict[str, object] = {
                "schema_version": _CACHE_SCHEMA_VERSION,
                "package_version": _package_version(self.path),
                "configuration": safe_configuration,
            }
            serialized = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except ConfigurationCacheError:
            raise
        except (TypeError, ValueError, RecursionError) as error:
            raise ConfigurationCacheError(
                str(self.path),
                type(error).__name__,
            ) from None

        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_path.chmod(0o600)
                temporary_file.write(serialized)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            temporary_path.replace(self.path)
            temporary_path = None
        except OSError as error:
            raise ConfigurationCacheError(
                str(self.path),
                type(error).__name__,
            ) from None
        finally:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)

    def load(self) -> Mapping[str, object] | None:
        """Read and validate a cache created by the matching package version.

        Returns:
            The cached mapping, or ``None`` if the file does not exist.

        Raises:
            ConfigurationCacheError: If the file is linked, malformed,
                incompatible, or contains an invalid envelope.
        """
        if self.path.is_symlink():
            raise ConfigurationCacheError(
                str(self.path),
                "symbolic-link caches are not supported",
            )
        if not self.path.exists():
            return None
        payload = self._read_payload()
        return self._validate_payload(payload)

    def _read_payload(self) -> object:
        """Read the JSON cache without exposing parser diagnostics.

        Returns:
            The parsed JSON value for structural validation.

        Raises:
            ConfigurationCacheError: If the file cannot be read or parsed.
        """
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
            raise ConfigurationCacheError(
                str(self.path),
                "cache data could not be parsed",
            ) from None

    def _validate_payload(
        self,
        payload: object,
    ) -> Mapping[str, object]:
        """Validate cache identity and return its JSON configuration value.

        Args:
            payload: Parsed JSON value read from the configured cache path.

        Returns:
            Validated configuration mapping.

        Raises:
            ConfigurationCacheError: If the envelope or values are invalid.
        """
        if not isinstance(payload, dict):
            raise ConfigurationCacheError(
                str(self.path),
                "cache envelope is invalid",
            )
        payload_mapping = cast("dict[str, object]", payload)
        if frozenset(payload_mapping) != _CACHE_FIELDS:
            raise ConfigurationCacheError(
                str(self.path),
                "cache envelope is invalid",
            )
        if payload_mapping.get("schema_version") != _CACHE_SCHEMA_VERSION:
            raise ConfigurationCacheError(
                str(self.path),
                "cache schema version is incompatible",
            )
        if payload_mapping.get("package_version") != _package_version(
            self.path
        ):
            raise ConfigurationCacheError(
                str(self.path),
                "cache package version is incompatible",
            )

        configuration = payload_mapping.get("configuration")
        if not isinstance(configuration, dict):
            raise ConfigurationCacheError(
                str(self.path),
                "cached configuration root is invalid",
            )
        try:
            validated = _json_value(
                cast("dict[str, object]", configuration),
                set(),
                0,
            )
        except (TypeError, ValueError, RecursionError) as error:
            raise ConfigurationCacheError(
                str(self.path),
                type(error).__name__,
            ) from None
        # A mapping root stays a dict through _json_value's safe copy.
        return cast("dict[str, object]", validated)

    def clear(self) -> None:
        """Delete only the selected cache path, leaving its target untouched.

        Raises:
            ConfigurationCacheError: If the selected path cannot be removed.
        """
        try:
            self.path.unlink(missing_ok=True)
        except OSError as error:
            raise ConfigurationCacheError(
                str(self.path),
                type(error).__name__,
            ) from None


__all__ = ["ConfigCache"]
