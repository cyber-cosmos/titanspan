"""Verify database configuration validation without opening a connection.

Unit tests cover URL safety, driver resolution, and application path handling.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest

from titanspan.database import (
    ConnectionConfiguration,
    DatabaseConfiguration,
    DatabaseConfigurationError,
)

pytestmark = pytest.mark.unit

if TYPE_CHECKING:
    from pathlib import Path

    from titanspan.contracts.foundation import ApplicationPaths

_FIXED_DATABASE_NAME = "catalog.sqlite"
_SAFE_TLS_PARAMETER = "sslmode=require"
_POSTGRES_DEFAULT_PORT = 5432


class _TestPaths:
    """Resolve relative database files below one temporary root.

    The small object satisfies the application's path contract in isolation.
    """

    def __init__(self, base_path: Path) -> None:
        """Retain the temporary application root.

        Args:
            base_path: Test-owned root used to resolve relative paths.
        """
        self._base_path = base_path

    @property
    def base_path(self) -> Path:
        """Return the root that owns relative database files.

        Returns:
            The temporary test directory.
        """
        return self._base_path

    def path(self, *parts: str) -> Path:
        """Join trusted path segments to the temporary root.

        Args:
            *parts: Relative path components.

        Returns:
            The path rooted below the temporary directory.
        """
        return self._base_path.joinpath(*parts)


def test_structured_sqlite_configuration_is_application_relative(
    tmp_path: Path,
) -> None:
    """Resolve relative SQLite files without connecting or creating them.

    Args:
        tmp_path: Temporary test directory used as the application root.
    """
    paths: ApplicationPaths = _TestPaths(tmp_path)

    configuration = DatabaseConfiguration.from_mapping(
        {
            "default": "local",
            "connections": {
                "local": {
                    "driver": "sqlite",
                    "database": f"storage/{_FIXED_DATABASE_NAME}",
                },
            },
        },
        paths,
    )

    connection = configuration.connections["local"]
    assert configuration.default == "local"
    assert connection.sync_url.drivername == "sqlite+pysqlite"
    assert connection.async_url.drivername == "sqlite+aiosqlite"
    assert connection.sync_url.database == str(
        (tmp_path / "storage" / _FIXED_DATABASE_NAME).resolve()
    )
    assert not (tmp_path / "storage" / _FIXED_DATABASE_NAME).exists()


def test_explicit_driver_urls_and_credentials_are_preserved_and_redacted(
    tmp_path: Path,
) -> None:
    """Honor explicit drivers while hiding credentials in diagnostics.

    Args:
        tmp_path: Temporary application root used for path resolution.
    """
    paths: ApplicationPaths = _TestPaths(tmp_path)
    configuration = ConnectionConfiguration.from_mapping(
        "postgres",
        {
            "sync_url": (
                "postgresql+psycopg://db_user:super-secret@localhost/app"
                "?token=token-secret&sslmode=require"
            ),
            "async_url": (
                "postgresql+asyncpg://db_user:super-secret@localhost/app"
            ),
        },
        paths,
    )

    assert configuration.sync_url.drivername == "postgresql+psycopg"
    assert configuration.async_url.drivername == "postgresql+asyncpg"
    assert "super-secret" not in configuration.redacted_url
    assert "token-secret" not in configuration.redacted_url
    assert _SAFE_TLS_PARAMETER in configuration.redacted_url


def test_direct_connection_fields_and_immutable_driver_options(
    tmp_path: Path,
) -> None:
    """Accept direct connection settings and snapshot nested driver options.

    Args:
        tmp_path: Temporary root for path resolution.
    """
    paths: ApplicationPaths = _TestPaths(tmp_path)
    connect_args = {"application_name": "titanspan"}
    configuration = DatabaseConfiguration.from_mapping(
        {
            "driver": "postgres",
            "database": "application",
            "username": "worker",
            "password": "secret",
            "host": "db.internal",
            "port": _POSTGRES_DEFAULT_PORT,
            "query": {"options": ["first", "second"]},
            "options": {
                "connect_args": connect_args,
                "echo": False,
                "pool_size": 4,
                "max_overflow": 2,
                "pool_timeout": 0.5,
                "pool_recycle": -1,
                "pool_pre_ping": True,
                "pool_use_lifo": False,
            },
        },
        paths,
    )

    engine_connect_args = configuration.connections["default"].engine_options[
        "connect_args"
    ]
    connect_args["application_name"] = "mutated"

    assert configuration.default == "default"
    assert (
        configuration.connections["default"].sync_url.port
        == _POSTGRES_DEFAULT_PORT
    )
    assert configuration.connections["default"].sync_url.query["options"] == (
        "first",
        "second",
    )
    assert isinstance(engine_connect_args, MappingProxyType)
    assert isinstance(engine_connect_args, Mapping)
    assert engine_connect_args["application_name"] == "titanspan"


def test_invalid_sqlalchemy_url_is_translated_to_configuration_error(
    tmp_path: Path,
) -> None:
    """Translate SQLAlchemy URL parser failures to a safe native error.

    Args:
        tmp_path: Temporary root for URL parsing.
    """
    paths: ApplicationPaths = _TestPaths(tmp_path)

    with pytest.raises(DatabaseConfigurationError, match="is invalid"):
        ConnectionConfiguration.from_mapping(
            "broken",
            {"url": "not a url"},
            paths,
        )


@pytest.mark.parametrize(
    ("settings", "expected_sync", "expected_async"),
    [
        (
            {"driver": "sqlite", "database": ":memory:"},
            "sqlite+pysqlite",
            "sqlite+aiosqlite",
        ),
        (
            {"driver": "postgres", "database": "app"},
            "postgresql+psycopg",
            "postgresql+psycopg",
        ),
        (
            {"driver": "mysql", "database": "app"},
            "mysql+pymysql",
            "mysql+asyncmy",
        ),
    ],
)
def test_default_drivers_are_selected_by_operation_mode(
    tmp_path: Path,
    settings: dict[str, object],
    expected_sync: str,
    expected_async: str,
) -> None:
    """Use maintained default drivers for the built-in dialects.

    Args:
        tmp_path: Temporary application root used for path resolution.
        settings: Structured SQLAlchemy connection fields.
        expected_sync: Expected sync driver name.
        expected_async: Expected async driver name.
    """
    paths: ApplicationPaths = _TestPaths(tmp_path)

    connection = ConnectionConfiguration.from_mapping(
        "main",
        settings,
        paths,
    )

    assert connection.sync_url.drivername == expected_sync
    assert connection.async_url.drivername == expected_async


@pytest.mark.parametrize(
    "value",
    [
        [],
        {"connections": []},
        {"connections": {"sqlite": []}},
        {"default": 1, "connections": {}},
        {"default": "missing", "connections": {}},
        {"connections": {"": {"driver": "sqlite"}}},
        {"connections": {1: {"driver": "sqlite"}}},
        {"connections": {"sqlite": {"port": 0}}},
        {"connections": {"sqlite": {"port": 65_536}}},
        {"connections": {"sqlite": {"port": True}}},
        {"connections": {"sqlite": {"query": {"ssl": 2}}}},
        {"connections": {"sqlite": {"username": 2}}},
        {
            "connections": {
                "sqlite": {"options": {"mispelled_pool_size": 3}},
            },
        },
        {"connections": {"sqlite": {"options": {"echo": "yes"}}}},
        {"connections": {"sqlite": {"options": {"pool_size": True}}}},
        {"connections": {"sqlite": {"options": {"pool_size": -1}}}},
        {"connections": {"sqlite": {"options": {"max_overflow": -2}}}},
        {"connections": {"sqlite": {"options": {"pool_recycle": -2}}}},
        {"connections": {"sqlite": {"options": {"pool_timeout": -0.1}}}},
        {"connections": {"sqlite": {"options": {"isolation_level": 4}}}},
        {"connections": {"sqlite": {"options": {"connect_args": []}}}},
    ],
)
def test_invalid_connection_configuration_fails_closed(
    tmp_path: Path,
    value: object,
) -> None:
    """Reject malformed connection mappings and unsupported options.

    Args:
        tmp_path: Temporary application root used for path resolution.
        value: Deliberately invalid configuration value.
    """
    paths: ApplicationPaths = _TestPaths(tmp_path)

    with pytest.raises(DatabaseConfigurationError):
        DatabaseConfiguration.from_mapping(value, paths)
