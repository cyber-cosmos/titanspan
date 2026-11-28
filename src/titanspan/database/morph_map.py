"""Store trusted aliases for SQLAlchemy-mapped polymorphic model classes.

The map resolves persisted discriminator values only to explicitly supplied
classes. It never imports a class named by database content.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from sqlalchemy import inspect as sa_inspect

from titanspan.database.exceptions import DatabaseConfigurationError


class MorphMap[ModelT]:
    """Hold an immutable, bidirectional polymorphic model map.

    Args:
        mappings: Explicit aliases mapped to SQLAlchemy model classes.

    Raises:
        DatabaseConfigurationError: If aliases or mapped models are invalid.
    """

    def __init__(
        self,
        mappings: Mapping[str, type[ModelT]] | None = None,
    ) -> None:
        """Validate and freeze a trusted alias-to-model mapping.

        Args:
            mappings: Explicit aliases mapped to SQLAlchemy model classes.

        Raises:
            DatabaseConfigurationError: If aliases or mapped models are
                invalid or ambiguous.
        """
        selected: Mapping[str, type[ModelT]] = (
            {} if mappings is None else mappings
        )
        by_alias: dict[str, type[ModelT]] = {}
        by_model: dict[type[ModelT], str] = {}
        raw_mappings = cast("Mapping[object, object]", selected)
        for raw_alias, raw_model in raw_mappings.items():
            if not isinstance(raw_alias, str) or not raw_alias.strip():
                message = "Database morph aliases must be non-empty strings."
                raise DatabaseConfigurationError(message)
            if not isinstance(raw_model, type):
                message = "Database morph values must be mapped model classes."
                raise DatabaseConfigurationError(message)
            model_type = cast("type[ModelT]", raw_model)
            if sa_inspect(model_type, raiseerr=False) is None or not callable(
                getattr(model_type, "query", None)
            ):
                message = (
                    "Database morph values must be mapped model classes "
                    "with Titanspan query APIs."
                )
                raise DatabaseConfigurationError(message)
            if model_type in by_model:
                message = "Each mapped model must have one morph alias."
                raise DatabaseConfigurationError(message)
            by_alias[raw_alias] = model_type
            by_model[model_type] = raw_alias

        self._by_alias = MappingProxyType(by_alias)
        self._by_model = MappingProxyType(by_model)

    @classmethod
    def from_config(cls, value: object) -> MorphMap[object]:
        """Validate a code-owned database configuration value.

        Args:
            value: Mapping from persisted aliases to imported model classes.

        Returns:
            An immutable map suitable for one application configuration.

        Raises:
            DatabaseConfigurationError: If the value is not a trusted map.
        """
        if value is None:
            return MorphMap.empty()
        if not isinstance(value, Mapping):
            message = "The database morph map must be a string-keyed map."
            raise DatabaseConfigurationError(message)
        raw_mappings = cast("Mapping[object, object]", value)
        validated: dict[str, type[object]] = {}
        for alias, model_type in raw_mappings.items():
            if not isinstance(alias, str) or not alias.strip():
                message = "Database morph aliases must be non-empty strings."
                raise DatabaseConfigurationError(message)
            if not isinstance(model_type, type):
                message = "Database morph values must be mapped model classes."
                raise DatabaseConfigurationError(message)
            validated[alias] = cast("type[object]", model_type)
        return MorphMap[object](validated)

    @classmethod
    def empty(cls) -> MorphMap[object]:
        """Create an empty map for a database configuration without aliases.

        Returns:
            An immutable, empty map that owns no application state.
        """
        return MorphMap[object]()

    def model_for(self, alias: str) -> type[ModelT] | None:
        """Return the explicitly mapped model class for one stored alias.

        Args:
            alias: Database discriminator read from a trusted row.

        Returns:
            The configured mapped class, or ``None`` for an unknown alias.
        """
        return self._by_alias.get(alias)

    def alias_for(self, model_type: type[ModelT]) -> str | None:
        """Return the configured alias for one exact model class.

        Args:
            model_type: Mapped class whose discriminator will be stored.

        Returns:
            The trusted alias, or ``None`` when the class is not configured.
        """
        return self._by_model.get(model_type)

    @property
    def mappings(self) -> Mapping[str, type[ModelT]]:
        """Expose the immutable alias mapping for inspection.

        Returns:
            A read-only mapping that preserves declaration order.
        """
        return self._by_alias


__all__ = ["MorphMap"]
