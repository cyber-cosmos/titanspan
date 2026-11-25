"""Discover trusted application configuration files deterministically.

Python files execute as trusted local application code. TOML and JSON files
are parsed as data; every source produces one named configuration namespace.
"""

from __future__ import annotations

import json
import runpy
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from dotenv import dotenv_values

from titanspan.config.exceptions import ConfigurationLoadError
from titanspan.config.repository import Repository
from titanspan.support.env import Env

_SUPPORTED_SUFFIXES = frozenset({".json", ".py", ".toml"})
_ENVIRONMENT_PATH_ERROR = "environment_file must be inside base_path."
_CONFIG_NAMESPACE_ERROR = "Configuration namespace must be an identifier."


def _merge_values(
    lower_priority: Mapping[str, object],
    higher_priority: Mapping[str, object],
) -> dict[str, object]:
    """Recursively merge two configuration mappings in source order.

    Args:
        lower_priority: Defaults or earlier configuration values.
        higher_priority: Later values that take precedence.

    Returns:
        A new dictionary with nested mappings merged and other values replaced.
    """
    result = dict(lower_priority)
    for key, value in higher_priority.items():
        existing = result.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            lower = cast("Mapping[str, object]", existing)
            higher = cast("Mapping[str, object]", value)
            nested = _merge_values(lower, higher)
            result[key] = nested
        else:
            result[key] = value
    return result


class ConfigLoader:
    """Load package defaults and trusted application configuration files.

    File discovery uses the application ``config`` directory and stable
    alphabetical order. Python files must assign a mapping named ``config``;
    loading them executes trusted application code and is not a sandbox.

    Attributes:
        base_path: Resolved application root used for discovery.
        config_path: Resolved application config directory.
        environment_file: Optional dotenv file scoped to file evaluation.

    Notes:
        Process environment values take precedence over dotenv values through
        the canonical Support ``Env`` helper. The loader never writes to
        ``os.environ``.
    """

    def __init__(
        self,
        base_path: str | Path,
        *,
        package_defaults: Mapping[str, Mapping[str, object]] | None = None,
        environment_file: str | Path | None = None,
        load_environment_file: bool = True,
    ) -> None:
        """Create a loader rooted at a trusted application directory.

        Args:
            base_path: Application root containing optional ``config`` and
                ``.env`` files.
            package_defaults: Initial package-owned namespace defaults.
            environment_file: Explicit dotenv path inside the application
                root; by default the root ``.env`` is selected.
            load_environment_file: Whether to read the selected dotenv file.

        Raises:
            TypeError: If defaults or paths have invalid types.
            ValueError: If a dotenv path escapes the application root.
        """
        self.base_path = Path(base_path).resolve()
        self.config_path = self.base_path / "config"
        selected_env = (
            self.base_path / ".env"
            if environment_file is None
            else Path(environment_file)
        )
        if not selected_env.is_absolute():
            selected_env = self.base_path / selected_env
        self._environment_file_is_symlink = selected_env.is_symlink()
        self.environment_file = selected_env.resolve()
        if self.base_path not in self.environment_file.parents:
            raise ValueError(_ENVIRONMENT_PATH_ERROR)
        self.load_environment_file = load_environment_file
        self._package_defaults: dict[str, dict[str, object]] = {}
        if package_defaults is not None:
            for namespace, values in package_defaults.items():
                self.register_defaults(namespace, values)

    def register_defaults(
        self,
        namespace: str,
        values: Mapping[str, object],
    ) -> None:
        """Register package defaults for one named config namespace.

        Defaults contributed to the same namespace merge in registration
        order; trusted application values are loaded later and win.

        Args:
            namespace: Config filename stem such as ``database``.
            values: Package-provided defaults.

        Raises:
            ValueError: If the namespace is not a Python identifier.
        """
        if not namespace.isidentifier():
            raise ValueError(_CONFIG_NAMESPACE_ERROR)
        current = self._package_defaults.get(namespace, {})
        self._package_defaults[namespace] = _merge_values(current, values)

    def load(self) -> Repository:
        """Load defaults and application config files into one repository.

        Returns:
            A new repository with defaults below application configuration.

        Raises:
            ConfigurationLoadError: If files are ambiguous, malformed,
                outside the trusted directory, or export invalid values.
        """
        values = {
            namespace: dict(defaults)
            for namespace, defaults in self._package_defaults.items()
        }
        files = self._discover_files()
        dotenv = self._load_environment_values()

        with Env.using(dotenv):
            for path in files:
                namespace = path.stem
                loaded = self._load_file(path)
                values[namespace] = _merge_values(
                    values.get(namespace, {}),
                    loaded,
                )
        return Repository(values)

    def _discover_files(self) -> tuple[Path, ...]:
        """Return supported files after validating names and trusted paths.

        Returns:
            Supported files sorted by filename.

        Raises:
            ConfigurationLoadError: If a path escapes the config directory,
                has an invalid namespace, or duplicates another source name.
        """
        if not self.config_path.exists():
            return ()
        resolved_root = self._resolve_config_directory()
        try:
            candidates = tuple(
                sorted(
                    (
                        path
                        for path in resolved_root.iterdir()
                        if path.is_file() and path.suffix in _SUPPORTED_SUFFIXES
                    ),
                    key=lambda path: path.name,
                )
            )
        except OSError as error:
            raise ConfigurationLoadError(
                str(self.config_path),
                type(error).__name__,
            ) from None
        self._validate_config_files(resolved_root, candidates)
        return candidates

    def _resolve_config_directory(self) -> Path:
        """Resolve and validate the trusted configuration directory.

        Returns:
            A concrete directory path within the application root.

        Raises:
            ConfigurationLoadError: If directory access or containment fails.
        """
        try:
            resolved_root = self.config_path.resolve(strict=True)
        except OSError as error:
            raise ConfigurationLoadError(
                str(self.config_path),
                type(error).__name__,
            ) from None
        if self.base_path not in resolved_root.parents:
            raise ConfigurationLoadError(
                str(self.config_path),
                "configuration directory outside application root",
            )
        if not resolved_root.is_dir():
            raise ConfigurationLoadError(
                str(self.config_path),
                "configuration path is not a directory",
            )
        return resolved_root

    def _validate_config_files(
        self,
        resolved_root: Path,
        candidates: tuple[Path, ...],
    ) -> None:
        """Validate file containment and unique Python namespaces.

        Args:
            resolved_root: Trusted configuration directory.
            candidates: Supported files sorted by filename.

        Raises:
            ConfigurationLoadError: If a file escapes or names collide.
        """
        namespaces: set[str] = set()
        for path in candidates:
            try:
                resolved = path.resolve(strict=True)
            except OSError as error:
                raise ConfigurationLoadError(
                    str(path),
                    type(error).__name__,
                ) from None
            if resolved_root not in resolved.parents:
                raise ConfigurationLoadError(
                    str(path),
                    "configuration file outside trusted directory",
                )
            if not path.stem.isidentifier():
                raise ConfigurationLoadError(
                    str(path),
                    "invalid configuration namespace",
                )
            if path.stem in namespaces:
                raise ConfigurationLoadError(
                    str(path),
                    "ambiguous duplicate configuration namespace",
                )
            namespaces.add(path.stem)

    def _load_environment_values(self) -> Mapping[str, str | None]:
        """Parse an optional dotenv file without mutating process state.

        Returns:
            Parsed values with quoted values decoded by python-dotenv.

        Raises:
            ConfigurationLoadError: If the selected file cannot be parsed.
        """
        if not self.load_environment_file or not self.environment_file.exists():
            return {}
        if self._environment_file_is_symlink:
            raise ConfigurationLoadError(
                str(self.environment_file),
                "dotenv symlinks are not supported",
            )
        try:
            parsed = dotenv_values(self.environment_file, encoding="utf-8")
        except (OSError, UnicodeError, ValueError) as error:
            raise ConfigurationLoadError(
                str(self.environment_file),
                type(error).__name__,
            ) from None
        return parsed

    def _load_file(self, path: Path) -> Mapping[str, object]:
        """Parse one config file and validate its exported mapping.

        Args:
            path: Trusted file previously returned by discovery.

        Returns:
            The file's ``config`` mapping or parsed data mapping.

        Raises:
            ConfigurationLoadError: If execution, parsing, or validation fails.
        """
        try:
            if path.suffix == ".py":
                namespace = runpy.run_path(str(path))
                configured: object = namespace.get("config")
            elif path.suffix == ".json":
                configured = json.loads(path.read_text(encoding="utf-8"))
            else:
                configured = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as error:
            # Configuration code may include secrets in exception text. Keep
            # the source and exception category, not its message or traceback.
            raise ConfigurationLoadError(
                str(path),
                type(error).__name__,
            ) from None

        if not isinstance(configured, Mapping):
            raise ConfigurationLoadError(
                str(path),
                "config export must be a mapping",
            )
        values = cast("Mapping[object, object]", configured)
        if not all(isinstance(key, str) for key in values):
            raise ConfigurationLoadError(
                str(path),
                "configuration keys must be strings",
            )
        return cast("Mapping[str, object]", values)


__all__ = ["ConfigLoader"]
