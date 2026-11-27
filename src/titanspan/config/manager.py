"""Compose settings, file sources, overrides, and configuration caching.

The manager defines one deterministic source order and returns a fresh
repository for each application construction or explicit validation call.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from titanspan.config.cache import ConfigCache
from titanspan.config.exceptions import ConfigurationCacheError
from titanspan.config.loader import ConfigLoader
from titanspan.config.repository import Repository
from titanspan.config.settings import Settings

_SETTINGS_KEY_ERROR = "Settings mapping keys must be strings."


def _flatten_settings(
    values: Mapping[str, object],
    prefix: str = "",
) -> dict[str, object]:
    """Convert nested settings into dotted repository assignments.

    Args:
        values: Explicit settings values or a nested settings mapping.
        prefix: Dotted parent path for recursive values.

    Returns:
        Assignments that update only configured leaf paths.

    Raises:
        TypeError: If a nested mapping contains a non-string key.
    """
    assignments: dict[str, object] = {}
    mapping = cast("Mapping[object, object]", values)
    for key, value in mapping.items():
        if not isinstance(key, str):
            raise TypeError(_SETTINGS_KEY_ERROR)
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping) and value:
            nested = cast("Mapping[str, object]", value)
            assignments.update(_flatten_settings(nested, path))
        else:
            assignments[path] = value
    return assignments


class ConfigManager:
    """Coordinate application configuration source precedence.

    Source order for fresh configuration is framework defaults, package
    defaults, application files, explicitly declared settings fields, and
    final bootstrap overrides. Dotted environment variables only influence a
    value when a file or a typed setting explicitly maps them.

    Attributes:
        base_path: Resolved application root.
        settings: Validated Titanspan settings for this application.
        cache_path: Default sensitive cache location.
    """

    def __init__(
        self,
        base_path: str | Path,
        *,
        settings: Settings | None = None,
        package_defaults: Mapping[str, Mapping[str, object]] | None = None,
        environment_file: str | Path | None = None,
        load_environment_file: bool = True,
        cache_path: str | Path | None = None,
    ) -> None:
        """Create an application-specific configuration manager.

        Args:
            base_path: Application root used for files and the default cache.
            settings: Optional explicitly supplied typed settings instance.
            package_defaults: Optional namespace defaults contributed by
                framework packages.
            environment_file: Optional dotenv path selected within the root.
            load_environment_file: Whether the loader reads its dotenv file.
            cache_path: Optional cache location; defaults under ``bootstrap``.
        """
        self.base_path = Path(base_path).resolve()
        self._loader = ConfigLoader(
            self.base_path,
            environment_file=environment_file,
            load_environment_file=load_environment_file,
        )
        self._loader.register_defaults(
            "app",
            {"name": "Titanspan", "debug": False},
        )
        if package_defaults is not None:
            for namespace, values in package_defaults.items():
                self._loader.register_defaults(namespace, values)
        self._provided_settings = settings is not None
        self._settings = settings
        if cache_path is None:
            self.cache_path = (
                self.base_path / "bootstrap" / "cache" / "config.json"
            )
        else:
            selected_cache_path = Path(cache_path)
            if selected_cache_path.is_absolute():
                self.cache_path = selected_cache_path
            else:
                self.cache_path = (
                    self.base_path / selected_cache_path
                ).resolve()
                if not self.cache_path.is_relative_to(self.base_path):
                    raise ConfigurationCacheError(
                        str(self.cache_path),
                        "relative cache paths must stay inside the root",
                    )
        self._cache = ConfigCache(self.cache_path)

    @property
    def settings(self) -> Settings:
        """Resolve typed settings only when a fresh source load needs them.

        Returns:
            Validated settings for this application manager.

        Notes:
            A valid cached snapshot bypasses current settings sources unless
            the caller explicitly supplied a settings instance.
        """
        if self._settings is None:
            self._settings = Settings.from_environment(
                env_file=(
                    self._loader.environment_file
                    if self._loader.load_environment_file
                    else None
                )
            )
        return self._settings

    def load(
        self,
        *,
        use_cache: bool = True,
        overrides: Mapping[str, object] | None = None,
    ) -> Repository:
        """Load effective configuration and apply final bootstrap overrides.

        Args:
            use_cache: Whether to use a present compatible cache snapshot.
            overrides: Optional final path-to-value bootstrap overrides.

        Returns:
            An application-owned mutable repository.

        Raises:
            ConfigurationCacheError: If a present cache is invalid.
            ConfigurationLoadError: If application sources are invalid.
        """
        cached = self._cache.load() if use_cache else None
        if cached is None:
            repository = self._load_fresh()
            self._apply_settings(repository)
        else:
            repository = Repository(cached)
            if self._provided_settings:
                self._apply_settings(repository)
        if overrides is not None:
            repository.set(overrides)
        return repository

    def validate(self) -> Repository:
        """Load current source files without consulting or writing a cache.

        Returns:
            A repository containing freshly validated configuration values.
        """
        repository = self._load_fresh()
        self._apply_settings(repository)
        return repository

    def cache_configuration(self) -> Path:
        """Build and cache a fresh configuration snapshot atomically.

        Returns:
            The cache path containing the protected JSON snapshot.

        Raises:
            ConfigurationCacheError: If a configuration value cannot be
                represented safely or the file cannot be written.
        """
        repository = self.validate()
        self._cache.write(repository.all())
        return self.cache_path

    def clear_cache(self) -> None:
        """Remove only the configured cache file, if it exists.

        Raises:
            ConfigurationCacheError: If the cache path cannot be removed.
        """
        self._cache.clear()

    def _load_fresh(self) -> Repository:
        """Load files over framework and package defaults.

        Returns:
            Fresh repository values before typed and bootstrap overrides.
        """
        return self._loader.load()

    def _apply_settings(self, repository: Repository) -> None:
        """Apply explicitly supplied settings fields to matching paths.

        Args:
            repository: Target configuration repository.

        Notes:
            Unset Pydantic defaults do not replace application files. Nested
            mappings become dotted updates so unspecified sibling values
            remain intact.
        """
        # Exclude unset defaults so application files remain higher priority
        # than a model's declaration-time defaults.
        values = self.settings.to_dict(include_defaults=False)
        if "app_name" in values:
            values["app.name"] = values.pop("app_name")
        if "debug" in values:
            values["app.debug"] = values.pop("debug")

        assignments = _flatten_settings(values)
        if assignments:
            repository.set(assignments)


__all__ = ["ConfigManager"]
