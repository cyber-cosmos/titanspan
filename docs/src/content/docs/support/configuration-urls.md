---
title: "Configuration URLs"
---

<span id="configuration-urls"></span>

`ConfigurationUrlParser` turns a database connection URL or SQL Server DSN
into settings that can be merged with an application's existing connection
configuration. Parsing uses Python's standard library and does not open a
connection.

## Parse a database URL

The URL-derived driver, database, host, port, username, and password override
the corresponding supplied settings. Other settings remain in the returned
mapping. The input mapping is copied and is not mutated.

```python
from titanspan.support import ConfigurationUrlParser

parser = ConfigurationUrlParser()
settings = parser.parse_configuration(
    {
        "url": "postgresql://db.example.test/catalog",
        "port": 5432,
        "pool_size": 10,
    }
)

assert settings == {
    "driver": "pgsql",
    "database": "catalog",
    "host": "db.example.test",
    "port": 5432,
    "pool_size": 10,
}
```

Use `parse_configuration` as the native Python entry point.

## Driver aliases

The parser includes aliases for common database, Redis, and Valkey URL schemes.
Applications can register another scheme when needed:

```python
ConfigurationUrlParser.add_driver_alias("custom-postgres", "pgsql")

assert parser.parse_configuration("custom-postgres://db/catalog")[
    "driver"
] == "pgsql"
```

Registration is process-wide and safe across threads. `get_driver_aliases()`
returns a copy, so callers cannot mutate the shared registry through a
retrieved mapping.

## Query options

Query options are merged after the primary URL components. JSON scalar values
are converted to native Python values. Bracketed query keys become nested
mappings; contiguous append-only numeric keys become Python lists.

```python
settings = parser.parse_configuration(
    "mysql://app@db/catalog?sticky=true&read[host][]=replica-a"
    "&read[host][]=replica-b"
)

assert settings["sticky"] is True
assert settings["read"] == {"host": ["replica-a", "replica-b"]}
```

An explicit `None` from a decoded query value is retained. A URL component
that decodes to JSON `null` is omitted from primary options.

## SQL Server DSNs

SQL Server's semicolon-delimited DSN syntax is supported alongside ordinary
URLs. Braced values can contain semicolons, and doubled closing braces decode
to a single brace.

```python
settings = parser.parse_configuration(
    "sqlsrv:Server=db.example.test,1444;Database=reports;"
    "ApplicationIntent=ReadOnly;ConnectionPooling=0"
)

assert settings["driver"] == "sqlsrv"
assert settings["host"] == "db.example.test"
assert settings["port"] == 1444
assert settings["readonly"] is True
assert settings["pooling"] is False
```

Recognized connection-pooling and multiple-active-result-set values are
converted to booleans. Unrecognized values remain strings. When an
`ApplicationIntent` option is present, a supplied `readonly` value is
discarded unless the DSN explicitly requests read-only access.

## Errors and edge cases

- Empty URL values, including the string `"0"`, are removed and treated as
  absent.
- Non-string `url` values raise `TypeError`.
- Malformed URL authorities and ports raise `ValueError`.
- URL parsing does not establish or validate network connections.
- Host names follow `urllib.parse` normalization, including lowercasing.
- Bracketed query values are represented by Python mappings and lists.

See the [Support specification](/titanspan/specifications/support) for component
ownership and verification boundaries.
