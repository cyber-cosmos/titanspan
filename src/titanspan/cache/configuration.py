"""Validate cache store settings from the canonical Config repository.

Store options remain private to their named backend and are never rendered
through ordinary inspection.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, TypeGuard, cast

from titanspan.cache.exceptions import CacheConfigurationError

if TYPE_CHECKING:
    from titanspan.contracts.config import ConfigRepository

_DEFAULT_STORE = "memory"
_DEFAULT_NAMESPACE = "titanspan"
_DEFAULT_PREFIX = "titanspan"
_NAME_LIMIT = 128


def _empty_options() -> Mapping[str, object]:
    """Create a correctly typed empty backend option mapping.
    """  # fmt: skip
    return {}


@dataclass(frozen=True, slots=True)
class CacheStoreConfiguration:
    """Describe one named store without exposing secret option values.

    Attributes:
        driver: Registered backend name.
        options: Backend-specific trusted application configuration.
        events: Whether this store emits native cache events.
    """

    driver: str
    options: Mapping[str, object] = field(default_factory=_empty_options)
    events: bool = True

    def __post_init__(self) -> None:
        """Validate and freeze one backend's setting mapping.

        Raises:
            CacheConfigurationError: If the driver or options are invalid.
        """
        if not _valid_name(self.driver):
            msg = "Cache driver name is invalid."
            raise CacheConfigurationError(msg)
        if not _is_mapping(self.options):
            msg = "Cache store options must be a map."
            raise CacheConfigurationError(msg)
        if not all(_is_text(key) for key in self.options):
            msg = "Cache option names must be strings."
            raise CacheConfigurationError(msg)
        if type(self.events) is not bool:
            msg = "Cache store events must be a boolean."
            raise CacheConfigurationError(msg)
        object.__setattr__(
            self,
            "options",
            MappingProxyType(dict(self.options)),
        )

    def __repr__(self) -> str:
        """Render public settings without exposing backend option values.
        """  # fmt: skip
        return (
            "CacheStoreConfiguration("
            f"driver={self.driver!r}, options=<redacted>, "
            f"events={self.events!r})"
        )


@dataclass(frozen=True, slots=True)
class CacheConfiguration:
    """Hold validated cache namespaces, stores, and operation limits.

    Attributes:
        default: Name of the store selected by default.
        namespace: Application namespace shared by configured stores.
        prefix: Safe prefix applied to all namespaced keys.
        stores: Independent driver settings indexed by store name.
        max_batch_size: Maximum number of keys in one bulk operation.
        max_value_bytes: Maximum serialized value size in bytes.
        events: Whether cache events are emitted by default.
    """

    default: str = _DEFAULT_STORE
    namespace: str = _DEFAULT_NAMESPACE
    prefix: str = _DEFAULT_PREFIX
    stores: Mapping[str, CacheStoreConfiguration | Mapping[str, object]] = (
        field(
            default_factory=lambda: {
                _DEFAULT_STORE: CacheStoreConfiguration("memory"),
            }
        )
    )
    max_batch_size: int = 1000
    max_value_bytes: int = 1_000_000
    events: bool = True

    def __post_init__(self) -> None:
        """Validate store definitions and retain immutable snapshots.

        Raises:
            CacheConfigurationError: If names, stores, or limits are invalid.
        """
        _validate_cache_settings(self)
        normalized = _normalize_stores(self.stores)
        if self.default not in normalized:
            msg = "The default cache store is not configured."
            raise CacheConfigurationError(msg)
        object.__setattr__(self, "stores", MappingProxyType(normalized))

    @property
    def store_configurations(
        self,
    ) -> Mapping[str, CacheStoreConfiguration]:
        """Return the validated, immutable named store configurations.
        """  # fmt: skip
        return cast(
            "Mapping[str, CacheStoreConfiguration]",
            self.stores,
        )

    @classmethod
    def from_repository(
        cls,
        repository: ConfigRepository,
    ) -> CacheConfiguration:
        """Read and validate the application's ``cache`` configuration.

        Args:
            repository: Canonical application configuration contract.

        Returns:
            An immutable cache configuration snapshot.

        Raises:
            CacheConfigurationError: If application values are malformed.
        """
        raw = repository.get("cache", {})
        if not isinstance(raw, Mapping):
            msg = "The cache configuration value must be a map."
            raise CacheConfigurationError(msg)
        values = cast("Mapping[str, object]", raw)
        app_name = repository.get("app.name", _DEFAULT_NAMESPACE)
        namespace = values.get("namespace", app_name)
        if not isinstance(namespace, str):
            msg = "Cache namespace must be a string."
            raise CacheConfigurationError(msg)
        stores_value = values.get(
            "stores",
            {_DEFAULT_STORE: {"driver": "memory"}},
        )
        if not isinstance(stores_value, Mapping):
            msg = "Cache stores must be a map."
            raise CacheConfigurationError(msg)
        stores = cast(
            "Mapping[str, CacheStoreConfiguration | Mapping[str, object]]",
            stores_value,
        )
        return cls(
            default=_string_value(values, "default", _DEFAULT_STORE),
            namespace=namespace,
            prefix=_string_value(values, "prefix", _DEFAULT_PREFIX),
            stores=stores,
            max_batch_size=_int_value(values, "max_batch_size", 1000),
            max_value_bytes=_int_value(values, "max_value_bytes", 1_000_000),
            events=_bool_value(values, "events", True),
        )


def _store_configuration(
    values: Mapping[str, object],
) -> CacheStoreConfiguration:
    """Convert one plain store mapping into a validated value object.

    Args:
        values: Mapping loaded from the application repository.

    Returns:
        Validated store configuration.

    Raises:
        CacheConfigurationError: If a required value has the wrong type.
    """
    driver = values.get("driver")
    options = values.get("options", {})
    events = values.get("events", True)
    if not isinstance(driver, str):
        msg = "Cache store driver must be a string."
        raise CacheConfigurationError(msg)
    if not isinstance(options, Mapping):
        msg = "Cache store options must be a map."
        raise CacheConfigurationError(msg)
    if type(events) is not bool:
        msg = "Cache store events must be configured as a boolean."
        raise CacheConfigurationError(msg)
    return CacheStoreConfiguration(
        driver,
        cast("Mapping[str, object]", options),
        events,
    )


def _validate_cache_settings(configuration: CacheConfiguration) -> None:
    """Validate scalar cache settings before freezing configured stores.
    """  # fmt: skip
    names = (
        configuration.default,
        configuration.namespace,
        configuration.prefix,
    )
    if not all(_valid_name(name) for name in names):
        msg = "Cache names, namespace, and prefix must use safe characters."
        raise CacheConfigurationError(msg)
    if (
        type(configuration.max_batch_size) is not int
        or configuration.max_batch_size < 1
    ):
        msg = "Cache batch size must be a positive integer."
        raise CacheConfigurationError(msg)
    if (
        type(configuration.max_value_bytes) is not int
        or configuration.max_value_bytes < 1
    ):
        msg = "Cache value size must be a positive integer."
        raise CacheConfigurationError(msg)
    if type(configuration.events) is not bool:
        msg = "Cache events must be configured as a boolean."
        raise CacheConfigurationError(msg)


def _normalize_stores(
    values: Mapping[str, CacheStoreConfiguration | Mapping[str, object]],
) -> dict[str, CacheStoreConfiguration]:
    """Validate and convert configured stores to immutable value objects.
    """  # fmt: skip
    normalized: dict[str, CacheStoreConfiguration] = {}
    for name, value in values.items():
        if not _valid_name(name):
            msg = "Cache store name is invalid."
            raise CacheConfigurationError(msg)
        if isinstance(value, CacheStoreConfiguration):
            normalized[name] = value
        elif _is_mapping(value):
            normalized[name] = _store_configuration(value)
        else:
            msg = "Cache store definitions must be maps."
            raise CacheConfigurationError(msg)
    return normalized


def _string_value(
    values: Mapping[str, object],
    key: str,
    default: str,
) -> str:
    """Read one string option without rendering rejected input.

    Args:
        values: Cache configuration mapping.
        key: Option name.
        default: Value used when the option is absent.

    Returns:
        The selected string.
    """
    value = values.get(key, default)
    if not isinstance(value, str):
        msg = f"Cache option [{key}] must be text."
        raise CacheConfigurationError(msg)
    return value


def _int_value(
    values: Mapping[str, object],
    key: str,
    default: int,
) -> int:
    """Read a strict integer option.

    Args:
        values: Cache configuration mapping.
        key: Option name.
        default: Value used when the option is absent.

    Returns:
        The selected integer.
    """
    value = values.get(key, default)
    if type(value) is not int:
        msg = f"Cache option [{key}] must be an int."
        raise CacheConfigurationError(msg)
    return value


def _bool_value(
    values: Mapping[str, object],
    key: str,
    default: bool,
) -> bool:
    """Read a strict boolean option.

    Args:
        values: Cache configuration mapping.
        key: Option name.
        default: Value used when the option is absent.

    Returns:
        The selected boolean.
    """
    value = values.get(key, default)
    if type(value) is not bool:
        msg = f"Cache option [{key}] must be a boolean."
        raise CacheConfigurationError(msg)
    return value


def _is_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    """Check that untyped configuration data is a text-keyed mapping.
    """  # fmt: skip
    if not isinstance(value, Mapping):
        return False
    entries = cast("Mapping[object, object]", value)
    return all(isinstance(key, str) for key in entries)


def _is_text(value: object) -> TypeGuard[str]:
    """Check that runtime configuration data is text.
    """  # fmt: skip
    return isinstance(value, str)


def _valid_name(value: object) -> bool:
    """Accept bounded names that cannot add cache-key separators.

    Args:
        value: Store, prefix, or namespace name.

    Returns:
        Whether the name contains only safe ASCII characters.
    """
    return (
        _is_text(value)
        and 0 < len(value) <= _NAME_LIMIT
        and value[0].isalnum()
        and all(
            character.isascii() and (character.isalnum() or character in "-_.")
            for character in value
        )
    )


__all__ = ["CacheConfiguration", "CacheStoreConfiguration"]
