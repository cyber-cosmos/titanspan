"""Parse database settings into immutable SQLAlchemy URL definitions.

Configuration validation stays in Titanspan while SQLAlchemy constructs and
quotes connection URLs and delegates dialect behavior.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from titanspan.database.exceptions import DatabaseConfigurationError

if TYPE_CHECKING:
    from titanspan.contracts.config import ConfigRepository
    from titanspan.contracts.foundation import ApplicationPaths

type _QueryValue = str | Sequence[str]

_MAX_TCP_PORT = 65_535


@dataclass(frozen=True, slots=True)
class ConnectionConfiguration:
    """Store one named connection's sync, async, and engine settings.

    Attributes:
        name: Application configuration key for this connection.
        sync_url: SQLAlchemy URL used by synchronous operations.
        async_url: SQLAlchemy URL used by asynchronous operations.
        engine_options: Validated engine options with parameter hiding enabled.
    """

    name: str
    sync_url: URL
    async_url: URL
    engine_options: Mapping[str, object]

    @classmethod
    def from_mapping(
        cls,
        name: str,
        values: object,
        paths: ApplicationPaths,
    ) -> ConnectionConfiguration:
        """Build a connection definition from one trusted configuration map.

        Args:
            name: Name used to select this application connection.
            values: Structured fields or an explicit SQLAlchemy URL.
            paths: Application path contract used for relative SQLite files.

        Returns:
            A connection definition with separate sync and async URLs.

        Raises:
            DatabaseConfigurationError: If a field has an invalid type.
        """
        connection_values = _mapping(values, f"connections.{name}")
        base_url = _build_url(connection_values, paths, "url")
        sync_source = _build_url(
            connection_values,
            paths,
            "sync_url",
            base_url,
        )
        async_source = _build_url(
            connection_values,
            paths,
            "async_url",
            base_url,
        )
        options = _engine_options(connection_values)
        return cls(
            name=name,
            sync_url=_driver_url(sync_source, asynchronous=False),
            async_url=_driver_url(async_source, asynchronous=True),
            engine_options=MappingProxyType(options),
        )

    @property
    def redacted_url(self) -> str:
        """Return the sync URL with passwords and secret query fields hidden.

        Returns:
            A printable URL suitable for bounded diagnostics.
        """
        query: dict[str, str | Sequence[str]] = {}
        for key, value in self.sync_url.query.items():
            query[key] = "[REDACTED]" if _secret_key(key) else value
        return self.sync_url.set(query=query).render_as_string(
            hide_password=True
        )

    @property
    def target_identity(self) -> str:
        """Return the configured target URL without credential material.

        Returns:
            A stable target identifier with all query options removed.
        """
        return self.sync_url.set(
            username=None,
            password=None,
            query={},
        ).render_as_string(hide_password=True)


@dataclass(frozen=True, slots=True)
class DatabaseConfiguration:
    """Represent the configured default and named database connections.

    Attributes:
        default: Name selected when a connection is not specified.
        connections: Immutable mapping of configured connection definitions.
    """

    default: str | None
    connections: Mapping[str, ConnectionConfiguration]

    @classmethod
    def from_repository(
        cls,
        repository: ConfigRepository,
        paths: ApplicationPaths,
    ) -> DatabaseConfiguration:
        """Read and validate the canonical ``database`` configuration path.

        Args:
            repository: Application-owned configuration contract.
            paths: Application-relative path resolver.

        Returns:
            Validated named connections without opening any engine.
        """
        raw = repository.get("database", {})
        values = _mapping(raw, "database")
        return cls.from_mapping(values, paths)

    @classmethod
    def from_mapping(
        cls,
        values: object,
        paths: ApplicationPaths,
    ) -> DatabaseConfiguration:
        """Build settings from a configuration snapshot.

        Args:
            values: Database settings and named connection definitions.
            paths: Application-relative path resolver.

        Returns:
            Validated connection settings without network activity.

        Raises:
            DatabaseConfigurationError: If names or connection values are
                invalid or the selected default is not configured.
        """
        database_values = _mapping(values, "database")
        default = _optional_string(database_values, "default")
        raw_connections = database_values.get("connections")
        if raw_connections is None and _has_connection_fields(database_values):
            selected_default = default or "default"
            raw_connections = {selected_default: database_values}
            default = selected_default

        if raw_connections is None:
            raw_connections = {}
        connection_values = _mapping(raw_connections, "connections")
        connections: dict[str, ConnectionConfiguration] = {}
        for name, raw in connection_values.items():
            if not name:
                msg = "Database connection names must not be empty."
                raise DatabaseConfigurationError(msg)
            connections[name] = ConnectionConfiguration.from_mapping(
                name,
                raw,
                paths,
            )

        if default is not None and default not in connections:
            msg = "The default database connection is not configured."
            raise DatabaseConfigurationError(msg)
        return cls(
            default=default,
            connections=MappingProxyType(connections),
        )


def _mapping(value: object, name: str) -> Mapping[str, object]:
    """Require a string-keyed mapping without rendering its values.

    Args:
        value: Configuration value to inspect.
        name: Safe configuration path used in the error message.

    Returns:
        The validated mapping.

    Raises:
        DatabaseConfigurationError: If the value is not a string-keyed map.
    """
    if not isinstance(value, Mapping):
        msg = f"Database configuration [{name}] must be a string-keyed map."
        raise DatabaseConfigurationError(msg)
    keys = cast("Mapping[object, object]", value)
    if any(not isinstance(key, str) for key in keys):
        msg = f"Database configuration [{name}] must be a string-keyed map."
        raise DatabaseConfigurationError(msg)
    return cast("Mapping[str, object]", value)


def _optional_string(
    values: Mapping[str, object],
    key: str,
    default: str | None = None,
) -> str | None:
    """Read an optional string without exposing rejected values.

    Args:
        values: Configuration fields to inspect.
        key: Field name being validated.
        default: Value used when the key is absent.

    Returns:
        The configured string or the supplied default.

    Raises:
        DatabaseConfigurationError: If a present field is not a string.
    """
    value = values.get(key, default)
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"Database configuration [{key}] must be a string."
        raise DatabaseConfigurationError(msg)
    return value


def _build_url(
    values: Mapping[str, object],
    paths: ApplicationPaths,
    url_key: str,
    fallback: URL | None = None,
) -> URL:
    """Construct a SQLAlchemy URL from structured or explicit settings.

    Args:
        values: Trusted connection fields.
        paths: Application path contract.
        url_key: Optional explicit URL field to parse.
        fallback: Previously built URL used for mode-specific overrides.

    Returns:
        An immutable SQLAlchemy URL with relative SQLite paths resolved.

    Raises:
        DatabaseConfigurationError: If URL or structured fields are invalid.
    """
    explicit_url = values.get(url_key)
    if explicit_url is not None:
        if not isinstance(explicit_url, str):
            msg = f"Database configuration [{url_key}] must be a string."
            raise DatabaseConfigurationError(msg)
        try:
            url = make_url(explicit_url)
        except (ArgumentError, TypeError, ValueError) as error:
            msg = f"Database configuration [{url_key}] is invalid."
            raise DatabaseConfigurationError(msg) from error
    elif fallback is not None:
        url = fallback
    else:
        driver = _driver_name(values)
        database = _optional_string(values, "database")
        username = _optional_string(values, "username")
        password = _optional_string(values, "password")
        host = _optional_string(values, "host")
        port = _optional_port(values)
        query = _query_mapping(values.get("query"))
        try:
            url = URL.create(
                drivername=driver,
                username=username,
                password=password,
                host=host,
                port=port,
                database=database,
                query=query,
            )
        except (ArgumentError, TypeError, ValueError) as error:
            msg = "Structured database URL fields are invalid."
            raise DatabaseConfigurationError(msg) from error
    return _resolve_sqlite_path(url, paths)


def _driver_name(values: Mapping[str, object]) -> str:
    """Return a validated base SQLAlchemy dialect name.

    Args:
        values: Connection settings.

    Returns:
        The explicit driver or SQLite's development default.

    Raises:
        DatabaseConfigurationError: If the driver field is not a string.
    """
    driver = _optional_string(values, "driver", "sqlite") or "sqlite"
    normalized = driver.casefold()
    if normalized == "postgres":
        return "postgresql"
    if normalized == "mariadb":
        return "mysql"
    return normalized


def _optional_port(values: Mapping[str, object]) -> int | None:
    """Validate an optional TCP port.

    Args:
        values: Connection settings.

    Returns:
        A configured port or ``None``.

    Raises:
        DatabaseConfigurationError: If the port is outside the valid range.
    """
    value = values.get("port")
    if value is None:
        return None
    if type(value) is not int or not 1 <= value <= _MAX_TCP_PORT:
        msg = "Database configuration [port] must be between 1 and 65535."
        raise DatabaseConfigurationError(msg)
    return value


def _query_mapping(value: object) -> Mapping[str, _QueryValue]:
    """Validate URL query fields for SQLAlchemy URL construction.

    Args:
        value: Optional mapping of URL query names to string values.

    Returns:
        An immutable query mapping.

    Raises:
        DatabaseConfigurationError: If a key or value has an invalid type.
    """
    if value is None:
        return MappingProxyType({})
    mapping = _mapping(value, "query")
    result: dict[str, _QueryValue] = {}
    for key, item in mapping.items():
        if isinstance(item, str):
            result[key] = item
        elif isinstance(item, Sequence) and all(
            isinstance(entry, str) for entry in cast("Sequence[object]", item)
        ):
            result[key] = tuple(cast("Sequence[str]", item))
        else:
            msg = "Database URL query values must be strings or string lists."
            raise DatabaseConfigurationError(msg)
    return MappingProxyType(result)


def _resolve_sqlite_path(url: URL, paths: ApplicationPaths) -> URL:
    """Anchor relative SQLite files to the selected application root.

    Args:
        url: Parsed SQLAlchemy URL.
        paths: Application-relative path contract.

    Returns:
        The original URL or a copy with an absolute SQLite database path.
    """
    database = url.database
    if (
        url.get_backend_name() != "sqlite"
        or database is None
        or database in ("", ":memory:")
    ):
        return url
    database_path = Path(database)
    if database_path.is_absolute():
        return url
    return url.set(database=str((paths.base_path / database_path).resolve()))


def _engine_options(values: Mapping[str, object]) -> dict[str, object]:
    """Validate supported pooling and engine options with safe defaults.

    Args:
        values: Connection settings.

    Returns:
        Engine keyword arguments with SQL parameter hiding enabled.

    Raises:
        DatabaseConfigurationError: If an option has an invalid type.
    """
    raw_options = _mapping(values.get("options", {}), "options")
    option_names = {
        "echo",
        "pool_size",
        "max_overflow",
        "pool_timeout",
        "pool_recycle",
        "pool_pre_ping",
        "pool_use_lifo",
        "isolation_level",
        "connect_args",
    }
    if set(raw_options) - option_names:
        msg = "Database engine options contain an unsupported setting."
        raise DatabaseConfigurationError(msg)
    options = {
        name: value
        for name, value in raw_options.items()
        if name in option_names
    }
    for name in ("echo", "pool_pre_ping", "pool_use_lifo"):
        value = options.get(name)
        if value is not None and type(value) is not bool:
            msg = f"Database engine option [{name}] must be boolean."
            raise DatabaseConfigurationError(msg)
    for name in (
        "pool_size",
        "max_overflow",
        "pool_recycle",
    ):
        value = options.get(name)
        if value is not None and (
            type(value) is not int or value < _minimum_pool_value(name)
        ):
            msg = f"Database engine option [{name}] must be an integer."
            raise DatabaseConfigurationError(msg)
    timeout = options.get("pool_timeout")
    if timeout is not None and (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout < 0
    ):
        msg = (
            "Database engine option [pool_timeout] must be a "
            "non-negative number."
        )
        raise DatabaseConfigurationError(msg)
    isolation = options.get("isolation_level")
    if isolation is not None and not isinstance(isolation, str):
        msg = "Database engine option [isolation_level] must be a string."
        raise DatabaseConfigurationError(msg)
    connect_args = options.get("connect_args")
    if connect_args is not None:
        options["connect_args"] = MappingProxyType(
            dict(_mapping(connect_args, "options.connect_args"))
        )
    options["hide_parameters"] = True
    return options


def _driver_url(url: URL, *, asynchronous: bool) -> URL:
    """Select a maintained default driver for a built-in dialect.

    Args:
        url: Parsed base URL.
        asynchronous: Whether the engine uses SQLAlchemy's async API.

    Returns:
        A URL using a bundled or optional driver for the selected mode.
    """
    if "+" in url.drivername:
        return url
    backend = url.get_backend_name()
    drivers = {
        "sqlite": (
            "sqlite+pysqlite",
            "sqlite+aiosqlite",
        ),
        "postgresql": (
            "postgresql+psycopg",
            "postgresql+psycopg",
        ),
        "mysql": (
            "mysql+pymysql",
            "mysql+asyncmy",
        ),
    }
    selected = drivers.get(backend)
    if selected is None:
        return url
    drivername = selected[1 if asynchronous else 0]
    return url.set(drivername=drivername)


def _has_connection_fields(values: Mapping[str, object]) -> bool:
    """Check for direct single-connection configuration fields.

    Args:
        values: Database namespace values.

    Returns:
        Whether the map can serve as one named connection definition.
    """
    return any(
        key in values
        for key in (
            "driver",
            "url",
            "sync_url",
            "async_url",
            "database",
            "host",
            "port",
            "username",
            "password",
            "query",
            "options",
        )
    )


def _minimum_pool_value(name: str) -> int:
    """Return the documented lower bound for SQLAlchemy pool settings.

    Args:
        name: Validated pool option name.

    Returns:
        Zero for size, minus one for overflow or recycling intervals.
    """
    return 0 if name == "pool_size" else -1


def _secret_key(key: str) -> bool:
    """Classify URL query names that must be hidden in diagnostics.

    Args:
        key: Query parameter name.

    Returns:
        Whether the normalized name resembles a credential.
    """
    normalized = "".join(
        character for character in key.casefold() if character.isalnum()
    )
    return any(
        marker in normalized
        for marker in ("password", "secret", "token", "credential", "key")
    )


__all__ = ["ConnectionConfiguration", "DatabaseConfiguration"]
