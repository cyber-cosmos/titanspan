"""Verify database URL and DSN parsing behavior.

Cases cover driver aliases, native query values, SQLite paths, and SQL Server
DSN options using only local data.
"""

from __future__ import annotations

import pytest

from titanspan.support import ConfigurationUrlParser

pytestmark = pytest.mark.unit

_DEFAULT_ALIASES = {
    "mssql": "sqlsrv",
    "mysql2": "mysql",
    "postgres": "pgsql",
    "postgresql": "pgsql",
    "sqlite3": "sqlite",
    "redis": "tcp",
    "rediss": "tls",
    "valkey": "tcp",
    "valkeys": "tls",
}


@pytest.fixture(autouse=True)
def reset_driver_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate driver alias registration between test cases.

    Args:
        monkeypatch: Fixture that restores the class registry after each case.
    """
    monkeypatch.setattr(
        ConfigurationUrlParser,
        "_driver_aliases",
        dict(_DEFAULT_ALIASES),
    )


def test_driver_aliases_are_exposed_and_can_be_extended() -> None:
    """Expose the built-in aliases and allow application-specific additions.

    New schemes resolve through the same parser registry.
    """
    assert ConfigurationUrlParser.get_driver_aliases() == _DEFAULT_ALIASES

    ConfigurationUrlParser.add_driver_alias("custom-db", "mysql")
    ConfigurationUrlParser.add_driver_alias("custom-pg", "pgsql")

    assert ConfigurationUrlParser.get_driver_aliases()["custom-db"] == "mysql"
    assert ConfigurationUrlParser.get_driver_aliases()["custom-pg"] == "pgsql"
    assert ConfigurationUrlParser().parse_configuration("custom-db://null") == {
        "driver": "mysql",
    }
    assert ConfigurationUrlParser().parse_configuration("custom-pg://null") == {
        "driver": "pgsql",
    }


def test_alias_snapshot_cannot_mutate_the_shared_registry() -> None:
    """Return a defensive alias snapshot instead of exposing registry state.

    Registration remains the only supported process-wide mutation path.
    """
    aliases = ConfigurationUrlParser.get_driver_aliases()
    aliases["mysql2"] = "sqlite"

    assert ConfigurationUrlParser.get_driver_aliases()["mysql2"] == "mysql"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "mysql://foo:bar@localhost/baz",  # pragma: allowlist secret
            {
                "driver": "mysql",
                "username": "foo",
                "password": "bar",  # pragma: allowlist secret
                "host": "localhost",
                "database": "baz",
            },
        ),
        (
            "mysql://foo:bar@localhost:134/baz",  # pragma: allowlist secret
            {
                "driver": "mysql",
                "username": "foo",
                "password": "bar",  # pragma: allowlist secret
                "host": "localhost",
                "port": 134,
                "database": "baz",
            },
        ),
        (
            "//foo:bar@localhost/baz",  # pragma: allowlist secret
            {
                "username": "foo",
                "password": "bar",  # pragma: allowlist secret
                "host": "localhost",
                "database": "baz",
            },
        ),
        (
            (
                "postgresql://user:"  # pragma: allowlist secret
                "p%40ss@db.example.test/app"
            ),
            {
                "driver": "pgsql",
                "username": "user",
                "password": "p@ss",  # pragma: allowlist secret
                "host": "db.example.test",
                "database": "app",
            },
        ),
    ],
)
def test_database_urls_parse_primary_options(
    url: str,
    expected: dict[str, object],
) -> None:
    """Parse common connection URLs into database options.

    Args:
        url: The connection URL or scheme-relative authority.
        expected: The expected normalized options.
    """
    assert ConfigurationUrlParser().parse_configuration(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            (
                "mysql://foo%3A:"  # pragma: allowlist secret
                "bar%2F@localhost/baz+baz%40"
            ),
            {
                "driver": "mysql",
                "username": "foo:",
                "password": "bar/",  # pragma: allowlist secret
                "host": "localhost",
                "database": "baz+baz@",
            },
        ),
        (
            "mysql://db%2Dprimary/catalog",
            {
                "driver": "mysql",
                "host": "db-primary",
                "database": "catalog",
            },
        ),
        (
            (
                "mysql://foo:"  # pragma: allowlist secret
                "bar%25bar@localhost/baz?timezone=%2B00%3A00"
            ),
            {
                "driver": "mysql",
                "username": "foo",
                "password": "bar%bar",  # pragma: allowlist secret
                "host": "localhost",
                "database": "baz",
                "timezone": "+00:00",
            },
        ),
        (
            (
                "sqlsrv://username:"  # pragma: allowlist secret
                "password@host:1433/database"
            ),
            {
                "driver": "sqlsrv",
                "username": "username",
                "password": "password",  # pragma: allowlist secret
                "host": "host",
                "port": 1433,
                "database": "database",
            },
        ),
        (
            "sqlite:////var/lib/titanspan.sqlite?foreign_key_constraints=true",
            {
                "driver": "sqlite",
                "database": "/var/lib/titanspan.sqlite",
                "foreign_key_constraints": True,
            },
        ),
    ],
)
def test_url_examples_preserve_decoding_and_options(
    url: str,
    expected: dict[str, object],
) -> None:
    """Preserve URL decoding and typed query options.

    Args:
        url: A database URL with encoded components and query options.
        expected: The expected normalized connection options.
    """
    assert ConfigurationUrlParser().parse_configuration(url) == expected


@pytest.mark.parametrize(
    ("scheme", "driver"),
    [
        ("redis", "tcp"),
        ("rediss", "tls"),
        ("valkey", "tcp"),
        ("valkeys", "tls"),
    ],
)
def test_cache_connection_scheme_aliases(
    scheme: str,
    driver: str,
) -> None:
    """Map Redis and Valkey URL schemes to transport driver names.

    Args:
        scheme: The URL scheme used by a cache connection.
        driver: The expected canonical transport name.
    """
    config: dict[str, object] = {
        "url": f"{scheme}://cache.example.test:6380/2",
        "database": 0,
    }

    assert ConfigurationUrlParser().parse_configuration(config) == {
        "driver": driver,
        "host": "cache.example.test",
        "port": 6380,
        "database": "2",
    }


@pytest.mark.parametrize(
    "url",
    [
        "redis://cache.example.test:6380",
        "redis://cache.example.test:6380/",
    ],
)
def test_urls_without_a_database_keep_the_configured_database(
    url: str,
) -> None:
    """Keep an existing database when a URL supplies no path value.

    Args:
        url: A cache URL with no database path or only a slash path.
    """
    config: dict[str, object] = {"url": url, "database": 2}

    assert ConfigurationUrlParser().parse_configuration(config) == {
        "driver": "tcp",
        "host": "cache.example.test",
        "port": 6380,
        "database": 2,
    }


@pytest.mark.parametrize(
    ("url", "database"),
    [
        ("sqlite://localhost/foo/database.sqlite", "foo/database.sqlite"),
        (
            "sqlite://localhost//var/data/database.sqlite",
            "/var/data/database.sqlite",
        ),
        ("sqlite:///foo/database.sqlite", "foo/database.sqlite"),
        (
            "sqlite:////var/data/database.sqlite",
            "/var/data/database.sqlite",
        ),
        ("sqlite:///:memory:", ":memory:"),
    ],
)
def test_sqlite_urls_preserve_relative_and_absolute_paths(
    url: str,
    database: str,
) -> None:
    """Preserve the leading-slash distinction in SQLite database paths.

    Args:
        url: The SQLite connection URL.
        database: The expected database path after removing URL syntax.
    """
    assert ConfigurationUrlParser().parse_configuration(url) == {
        "driver": "sqlite",
        "database": database,
    } | ({"host": "localhost"} if "localhost" in url else {})


def test_url_options_override_existing_values_and_keep_unset_options() -> None:
    """Merge URL-derived values over supplied config while preserving others.

    URL values take precedence, matching the original array merge order.
    """
    config = {
        "url": "mysql://root:pass@db/local",  # pragma: allowlist secret
        "driver": "sqlite",
        "host": "127.0.0.1",
        "port": "3306",
        "charset": "utf8mb4",
    }

    assert ConfigurationUrlParser().parse_configuration(config) == {
        "driver": "mysql",
        "host": "db",
        "port": "3306",
        "database": "local",
        "username": "root",
        "password": "pass",  # pragma: allowlist secret
        "charset": "utf8mb4",
    }
    assert config["host"] == "127.0.0.1"


def test_query_options_parse_native_values_and_nested_arrays() -> None:
    """Parse boolean, numeric, and bracketed query options.

    Query options override primary URL values and retain nested list structure.
    """
    url = (
        "mysql://root:@localhost/database?sticky=true&busy_timeout=5000"
        "&read[host][]=192.168.1.1&read[host][]=192.168.1.2"
    )

    assert ConfigurationUrlParser().parse_configuration(url) == {
        "driver": "mysql",
        "database": "database",
        "host": "localhost",
        "username": "root",
        "password": "",
        "sticky": True,
        "busy_timeout": 5000,
        "read": {"host": ["192.168.1.1", "192.168.1.2"]},
    }


def test_query_arrays_handle_nested_append_and_key_normalization() -> None:
    """Parse nested bracket keys and normalize option names.

    Repeated bracket entries remain ordered lists in the result.
    """
    url = (
        "mysql://localhost/db?read[][host]=db-a&read[][host]=db-b"
        "&options.foo+bar=%7B%22enabled%22%3Atrue%7D"
    )

    assert ConfigurationUrlParser().parse_configuration(url) == {
        "driver": "mysql",
        "host": "localhost",
        "database": "db",
        "read": [{"host": "db-a"}, {"host": "db-b"}],
        "options_foo_bar": {"enabled": True},
    }


def test_query_arrays_preserve_mixed_numeric_and_string_keys() -> None:
    """Preserve numeric and named keys in an ordered mapping.

    Contiguous append-only numeric arrays are exposed as lists separately.
    """
    url = "mysql://localhost/db?options[2]=two&options[name]=value"

    assert ConfigurationUrlParser().parse_configuration(url)["options"] == {
        2: "two",
        "name": "value",
    }


def test_malformed_bracket_notation_remains_a_literal_query_key() -> None:
    """Keep unmatched bracket text as a literal option name.

    This parser keeps malformed bracket text as a literal option name.
    """
    url = "mysql://localhost/db?options[broken]tail]=value"

    assert (
        ConfigurationUrlParser().parse_configuration(url)[
            "options[broken]tail]"
        ]
        == "value"
    )


def test_invalid_json_numeric_constants_remain_strings() -> None:
    """Leave non-standard JSON constants unchanged in query options.

    Non-standard JSON constants are rejected so the original string remains
    available to application-specific parsing.
    """
    url = "mysql://localhost/db?value=NaN"

    assert ConfigurationUrlParser().parse_configuration(url)["value"] == "NaN"


def test_missing_url_returns_a_copy_without_the_url_key() -> None:
    """Keep supplied config intact when it has no usable URL.

    Parsing does not mutate the caller's mapping.
    """
    config = {"url": "", "driver": "sqlite", "database": ":memory:"}

    assert ConfigurationUrlParser().parse_configuration(config) == {
        "driver": "sqlite",
        "database": ":memory:",
    }
    assert config["url"] == ""


def test_truthy_non_url_string_is_rejected_instead_of_ignored() -> None:
    """Reject a non-empty value that cannot identify a connection target.

    Python considers ``"0"`` truthy; parsing must not reuse foreign
    truthiness rules to treat it as an absent setting.
    """
    config = {"url": "0", "driver": "sqlite", "database": ":memory:"}

    with pytest.raises(ValueError, match="configuration URL is malformed"):
        ConfigurationUrlParser().parse_configuration(config)


def test_sql_server_dsn_maps_options_and_server_port() -> None:
    """Parse SQL Server DSN aliases, escaped braced values, and read-only mode.

    The DSN path preserves string options and converts documented booleans.
    """
    dsn = (
        "sqlsrv:Server=127.0.0.1,1444;Database=example;"
        "APP={Worker;Pool}}};ConnectionPooling=0;"
        "MultipleActiveResultSets=false;ApplicationIntent=ReadOnly"
    )

    assert ConfigurationUrlParser().parse_configuration(dsn) == {
        "driver": "sqlsrv",
        "database": "example",
        "host": "127.0.0.1",
        "port": 1444,
        "appname": "Worker;Pool}",
        "pooling": False,
        "multiple_active_result_sets": False,
        "readonly": True,
    }


def test_sql_server_dsn_maps_all_documented_options() -> None:
    """Map the supported SQL Server options and boolean values.

    Unrecognized boolean-like options remain strings.
    """
    dsn = (
        "sqlsrv:Server=localhost;Database=sample;Authentication=SqlPassword;"
        "ColumnEncryption=Enabled;ConnectionPooling=1;Encrypt=true;"
        "KeyStoreAuthentication=KeyVault;KeyStorePrincipalId=client;"
        "KeyStoreSecret=secret;LoginTimeout=30;"
        "MultipleActiveResultSets=false;MultiSubnetFailover=1;"
        "TransactionIsolation=READ_COMMITTED;TrustServerCertificate=true"
    )

    assert ConfigurationUrlParser().parse_configuration(dsn) == {
        "driver": "sqlsrv",
        "database": "sample",
        "host": "localhost",
        "authentication": "SqlPassword",
        "column_encryption": "Enabled",
        "pooling": True,
        "encrypt": "true",
        "key_store_authentication": "KeyVault",
        "key_store_principal_id": "client",
        "key_store_secret": "secret",  # pragma: allowlist secret
        "login_timeout": "30",
        "multiple_active_result_sets": False,
        "multi_subnet_failover": "1",
        "transaction_isolation": "READ_COMMITTED",
        "trust_server_certificate": "true",
    }


def test_sql_server_dsn_keeps_unknown_tokens_and_optional_host() -> None:
    """Preserve unknown boolean-like text and omit an absent server.

    SQL Server options only convert values recognized by filter semantics.
    """
    dsn = "sqlsrv:Database=sample;ConnectionPooling=perhaps"

    assert ConfigurationUrlParser().parse_configuration(dsn) == {
        "driver": "sqlsrv",
        "database": "sample",
        "pooling": "perhaps",
    }


def test_sql_server_configuration_url_and_existing_config_are_merged() -> None:
    """Allow a SQL Server DSN to override individual connection options.

    An ApplicationIntent key removes a preconfigured read-only flag unless
    its value requests the read-only mode.
    """
    config = {
        "driver": "sqlsrv",
        "host": "fallback",
        "readonly": True,
        "url": "sqlsrv:Server=db;ApplicationIntent=ReadWrite",
    }

    assert ConfigurationUrlParser().parse_configuration(config) == {
        "driver": "sqlsrv",
        "host": "db",
    }


def test_invalid_connection_urls_raise_value_errors() -> None:
    """Reject malformed authorities and invalid ports predictably.

    Error messages retain one stable category for URL parse failures.
    """
    parser = ConfigurationUrlParser()
    with pytest.raises(ValueError, match="configuration URL is malformed"):
        parser.parse_configuration("mysql://[invalid")
    with pytest.raises(ValueError, match="configuration URL is malformed"):
        parser.parse_configuration("mysql://localhost:99999/db")


def test_non_string_url_values_raise_a_type_error() -> None:
    """Reject invalid URL types instead of passing them to URI parsing.

    Other supplied settings are not mutated when validation fails.
    """
    config: dict[str, object] = {"url": 42, "driver": "mysql"}

    with pytest.raises(TypeError, match="must be a string"):
        ConfigurationUrlParser().parse_configuration(config)

    assert config == {"url": 42, "driver": "mysql"}
