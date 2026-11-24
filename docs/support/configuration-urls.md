# Configuration URLs

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
        "url": "postgresql://app:p%40ss@db.example.test/catalog",
        "port": 5432,
        "pool_size": 10,
    }
)

assert settings == {
    "driver": "pgsql",
    "database": "catalog",
    "host": "db.example.test",
    "port": 5432,
    "username": "app",
    "password": "p@ss",
    "pool_size": 10,
}
```

The `parseConfiguration` spelling is available for source compatibility.
Python applications should use `parse_configuration`.

## Driver aliases

The parser includes aliases for common database, Redis, and Valkey URL schemes.
Applications can register another scheme when needed:

```python
ConfigurationUrlParser.add_driver_alias("custom-postgres", "pgsql")

assert parser.parse_configuration("custom-postgres://db/catalog")[
    "driver"
] == "pgsql"
```

Registration is process-wide and safe across threads. Both
`get_driver_aliases()` and its `getDriverAliases()` compatibility spelling
return a copy, so callers cannot mutate the shared registry through a
retrieved mapping.

## Query options

Query options are merged after the primary URL components. JSON scalar values
are converted to native Python values. PHP-style bracket keys become nested
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
that decodes to JSON `null` is omitted from primary options, matching the
upstream merge behavior.

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

## Errors and compatibility notes

- Empty URL values, including the string `"0"`, are removed and treated as
  absent to preserve upstream truthiness behavior.
- Non-string `url` values raise `TypeError`.
- Malformed URL authorities and ports raise `ValueError`.
- URL parsing does not establish or validate network connections.
- Host names follow `urllib.parse` normalization, including lowercasing.
- PHP query arrays are represented by Python mappings and lists; PHP-specific
  loose coercion and reference semantics are not emulated.

The compatibility baseline is Laravel framework `v13.44.1`, pinned to commit
[`8a8c4a84852869e13190d89f9da873cd9a70f14c`](https://github.com/laravel/framework/tree/8a8c4a84852869e13190d89f9da873cd9a70f14c).
See the [method-level compatibility inventory](/compatibility/laravel-support)
for status, tests, and documented adaptations.
