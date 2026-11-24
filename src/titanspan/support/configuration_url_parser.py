"""Parse connection URLs into application configuration mappings.

The parser follows Illuminate Support's configuration URL behavior while
using Python's standard URI, query-string, and JSON facilities.
"""

from __future__ import annotations

import json
import re
from threading import RLock
from typing import TYPE_CHECKING, ClassVar, NoReturn, TypeGuard
from urllib.parse import parse_qsl, unquote, urlsplit

if TYPE_CHECKING:
    from collections.abc import Mapping

type _QueryNode = dict[str, object]

_DRIVER_ALIASES = {
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
_SQL_SERVER_OPTION_ALIASES = {
    "app": "appname",
    "authentication": "authentication",
    "columnencryption": "column_encryption",
    "connectionpooling": "pooling",
    "encrypt": "encrypt",
    "keystoreauthentication": "key_store_authentication",
    "keystoreprincipalid": "key_store_principal_id",
    "keystoresecret": "key_store_secret",  # pragma: allowlist secret
    "logintimeout": "login_timeout",
    "multipleactiveresultsets": "multiple_active_result_sets",
    "multisubnetfailover": "multi_subnet_failover",
    "transactionisolation": "transaction_isolation",
    "trustservercertificate": "trust_server_certificate",
}
_SQL_SERVER_OPTION = re.compile(
    r"(?:^|;)\s*([^=;]+?)\s*=\s*(\{(?:[^}]|}})*\}|[^;]*)",
)
_SQL_SERVER_PORT = re.compile(r"^(.*),\s*(\d+)$")
_QUERY_BRACKET = re.compile(r"\[([^\]]*)\]")
_MALFORMED_URL_ERROR = "The database configuration URL is malformed."
_URL_TYPE_ERROR = "The database configuration URL must be a string."


class ConfigurationUrlParser:
    """Hydrate connection options from URL or SQL Server DSN values.

    Existing mappings are copied before URL-derived values are merged. URL
    options take precedence, and driver aliases are shared by all instances.

    Attributes:
        _driver_aliases: Class-level scheme aliases for supported backends.

    Notes:
        Alias registration is process-wide and guarded for concurrent access.
        Parsing performs no network access and does not verify destinations.
    """

    _driver_aliases: ClassVar[dict[str, str]] = dict(_DRIVER_ALIASES)
    _aliases_lock: ClassVar[RLock] = RLock()

    def parse_configuration(
        self,
        config: Mapping[str, object] | str,
    ) -> dict[str, object]:
        """Parse a connection URL and merge its values into configuration.

        Args:
            config: Existing connection values or a URL string.

        Returns:
            A new mapping with URL-derived primary and query options applied.

        Raises:
            TypeError: If the configured URL is not a string.
            ValueError: If the URL authority or port is malformed.

        Notes:
            The input mapping is not mutated. URL and query values that are
            valid JSON scalars are converted to Python native types.
        """
        values: dict[str, object] = (
            {"url": config} if isinstance(config, str) else dict(config)
        )
        url = values.pop("url", None)
        if not url or (isinstance(url, str) and url == "0"):
            return values
        if not isinstance(url, str):
            raise TypeError(_URL_TYPE_ERROR)
        if self._is_sql_server_dsn(url):
            return _parse_sql_server_dsn(values, url)

        components = _parse_url_components(url)
        primary = self._primary_options(components)
        query = _parse_query_options(components.get("query"))
        return values | primary | query

    @classmethod
    def get_driver_aliases(cls) -> dict[str, str]:
        """Return a copy of the current connection scheme aliases.

        Returns:
            A new mapping of URL schemes to database driver names.
        """
        with cls._aliases_lock:
            return dict(cls._driver_aliases)

    @classmethod
    def add_driver_alias(cls, alias: str, driver: str) -> None:
        """Register or replace a URL scheme alias.

        Args:
            alias: The scheme accepted in a connection URL.
            driver: The canonical driver name stored in parsed options.

        Notes:
            The update is process-wide and immediately visible to instances.
        """
        with cls._aliases_lock:
            cls._driver_aliases[alias] = driver

    @classmethod
    def _is_sql_server_dsn(cls, url: str) -> bool:
        """Check whether a connection value uses SQL Server DSN syntax.

        Args:
            url: The connection string being parsed.

        Returns:
            Whether it starts with ``sqlsrv:`` and is not a URL authority.
        """
        normalized = url.lower()
        return normalized.startswith("sqlsrv:") and not normalized.startswith(
            "sqlsrv://"
        )

    @classmethod
    def _primary_options(
        cls,
        components: Mapping[str, object],
    ) -> dict[str, object]:
        """Select and rename primary connection values from URL components.

        Args:
            components: Parsed scheme, authority, path, and query values.

        Returns:
            The non-null driver, database, host, port, and credentials.
        """
        scheme = components.get("scheme")
        driver: object = None
        if isinstance(scheme, str) and scheme:
            with cls._aliases_lock:
                driver = cls._driver_aliases.get(scheme, scheme)

        options: dict[str, object] = {
            "driver": driver,
            "database": _database_from_path(components.get("path")),
            "host": components.get("host"),
            "port": components.get("port"),
            "username": components.get("user"),
            "password": components.get("password"),
        }
        return {
            key: value for key, value in options.items() if value is not None
        }

    # Keep the original Illuminate method names as explicit aliases.
    parseConfiguration = parse_configuration
    getDriverAliases = get_driver_aliases
    addDriverAlias = add_driver_alias


def _parse_url_components(url: str) -> dict[str, object]:
    """Parse and normalize standard URL components.

    Args:
        url: The database URL to split into its standard components.

    Returns:
        Parsed values with credentials and path percent-decoded.

    Raises:
        ValueError: If the URL authority, encoding, or port is malformed.
    """
    try:
        parsed = urlsplit(url)
        host = _decode_component(parsed.hostname)
        port = parsed.port
        user = _decode_component(parsed.username)
        password = _decode_component(parsed.password)
        path = _decode_component(parsed.path) if parsed.path else None
    except (UnicodeError, ValueError) as error:
        raise ValueError(_MALFORMED_URL_ERROR) from error

    return {
        "scheme": _parse_native_value(parsed.scheme) if parsed.scheme else None,
        "host": _parse_native_value(host) if host is not None else None,
        "port": port,
        "user": _parse_native_value(user) if user is not None else None,
        "password": (
            _parse_native_value(password) if password is not None else None
        ),
        "path": _parse_native_value(path) if path is not None else None,
        "query": parsed.query,
    }


def _decode_component(value: str | None) -> str | None:
    """Percent-decode an optional URL component as UTF-8.

    Args:
        value: A parser-returned user, password, or path component.

    Returns:
        The decoded component or ``None`` when it was absent.
    """
    if value is None:
        return None
    return unquote(value, encoding="utf-8", errors="strict")


def _database_from_path(path: object) -> object:
    """Remove the URL separator from a database path.

    Args:
        path: The decoded path component after native scalar conversion.

    Returns:
        The database name or path, preserving an extra leading slash.
    """
    if not path or path == "/":
        return None
    return str(path)[1:]


def _parse_query_options(query: object) -> dict[str, object]:
    """Parse bracketed query keys and convert JSON scalar values.

    Args:
        query: The raw URL query component, if present.

    Returns:
        A mapping of query option names to nested native values.
    """
    if not isinstance(query, str) or not query:
        return {}

    result: dict[str, object] = {}
    for key, value in parse_qsl(query, keep_blank_values=True):
        _assign_query_value(result, _query_tokens(key), value)
    return {key: _parse_nested_value(value) for key, value in result.items()}


def _query_tokens(key: str) -> list[str]:
    """Split a PHP-style bracket key into a root and child keys.

    Args:
        key: A decoded query option name.

    Returns:
        The parsed bracket path or the normalized literal name.
    """
    normalized = key.replace(".", "_").replace(" ", "_")
    opening = normalized.find("[")
    if opening <= 0 or not normalized.endswith("]"):
        return [normalized]

    root = normalized[:opening]
    suffix = normalized[opening:]
    tokens = [root]
    cursor = 0
    while cursor < len(suffix):
        match = _QUERY_BRACKET.match(suffix, cursor)
        if match is None:
            return [normalized]
        tokens.append(match.group(1))
        cursor = match.end()
    return tokens


def _assign_query_value(
    values: dict[str, object],
    tokens: list[str],
    value: object,
) -> None:
    """Store a query value under a nested bracket path.

    Args:
        values: The root query mapping being populated.
        tokens: The normalized root and bracket keys.
        value: The already percent-decoded query value.
    """
    node: _QueryNode = values
    for token in tokens[:-1]:
        key = _query_array_key(node, token)
        child = node.get(key)
        if not _is_query_mapping(child):
            child = _new_query_node()
            node[key] = child
        node = child
    node[_query_array_key(node, tokens[-1])] = value


def _query_array_key(node: _QueryNode, token: str) -> str:
    """Resolve a bracket token to an explicit key or append index.

    Args:
        node: The current PHP-style array represented as an ordered mapping.
        token: The current bracket token, empty for append notation.

    Returns:
        The explicit key or the next available non-negative numeric key.
    """
    if token:
        return token
    indexes = [
        int(key)
        for key in node
        if key.isdecimal() and (key == "0" or not key.startswith("0"))
    ]
    return str(max(indexes, default=-1) + 1)


def _new_query_node() -> _QueryNode:
    """Create a mapping for a nested query array.

    Returns:
        An empty mapping whose numeric keys can be normalized after parsing.
    """
    node: _QueryNode = {}
    return node


def _parse_nested_value(value: object) -> object:
    """Convert JSON-encoded leaves throughout a query value tree.

    Args:
        value: A scalar or nested value parsed from the query string.

    Returns:
        The value with valid JSON scalar and container strings converted.
    """
    if _is_query_mapping(value):
        normalized = {
            key: _parse_nested_value(item) for key, item in value.items()
        }
        if _is_consecutive_numeric_array(normalized):
            return [normalized[str(index)] for index in range(len(normalized))]
        return {
            _native_array_key(key): item for key, item in normalized.items()
        }
    return _parse_native_value(value)


def _is_query_mapping(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow a value to a string-keyed mapping produced by query parsing.

    Args:
        value: The dynamically typed value under inspection.

    Returns:
        Whether the value is a dictionary with string keys.
    """
    return isinstance(value, dict)


def _is_consecutive_numeric_array(values: dict[str, object]) -> bool:
    """Check whether insertion-ordered numeric keys form a Python list.

    Args:
        values: A query-created mapping after its values were converted.

    Returns:
        Whether keys appear as ``0`` through ``len(values) - 1`` in order.
    """
    return list(values) == [str(index) for index in range(len(values))]


def _native_array_key(key: str) -> str | int:
    """Convert canonical PHP numeric array keys to Python integer keys.

    Args:
        key: A string key from a parsed query array.

    Returns:
        An integer for canonical numeric keys or the original string.
    """
    if key.isdecimal() and (key == "0" or not key.startswith("0")):
        return int(key)
    return key


def _parse_native_value(value: object) -> object:
    """Convert a string to a native JSON value when the whole string is JSON.

    Args:
        value: The string or already-native URL component to convert.

    Returns:
        The decoded JSON value or the original value when decoding fails.
    """
    if not isinstance(value, str):
        return value
    try:
        parsed: object = json.loads(value, parse_constant=_reject_json_constant)
    except ValueError:
        return value
    return parsed


def _reject_json_constant(value: str) -> NoReturn:
    """Reject non-standard numeric constants accepted by Python's JSON parser.

    Args:
        value: The non-standard value token supplied by ``json.loads``.

    Raises:
        ValueError: Every non-standard constant is invalid JSON.
    """
    raise ValueError(value)


def _parse_sql_server_dsn(
    config: dict[str, object],
    dsn: str,
) -> dict[str, object]:
    """Hydrate SQL Server options from a semicolon-delimited DSN.

    Args:
        config: Existing connection settings without the URL key.
        dsn: A ``sqlsrv:`` DSN string.

    Returns:
        Merged SQL Server settings with DSN values taking precedence.
    """
    options = _parse_sql_server_options(dsn)
    server = options.get("server")
    host, port = _parse_sql_server_server(server)
    if "applicationintent" in options:
        config.pop("readonly", None)

    result = config | _sql_server_configuration_options(options)
    primary: dict[str, object] = {
        "driver": "sqlsrv",
        "database": options.get("database"),
        "host": host,
        "port": port,
    }
    return result | {
        key: value for key, value in primary.items() if value is not None
    }


def _parse_sql_server_options(dsn: str) -> dict[str, str]:
    """Parse named options and braced values from a SQL Server DSN.

    Args:
        dsn: A DSN beginning with the ``sqlsrv:`` prefix.

    Returns:
        Lowercase option names mapped to their decoded string values.
    """
    options: dict[str, str] = {}
    for match in _SQL_SERVER_OPTION.finditer(dsn[len("sqlsrv:") :]):
        name = match.group(1).strip().lower()
        value = match.group(2).strip()
        if value.startswith("{") and value.endswith("}"):
            value = value[1:-1].replace("}}", "}")
        options[name] = value
    return options


def _parse_sql_server_server(
    server: str | None,
) -> tuple[str | None, int | None]:
    """Separate an optional comma-delimited port from a SQL Server host.

    Args:
        server: The raw ``Server`` option, if one was supplied.

    Returns:
        The host and an optional integer port.
    """
    if server is None:
        return None, None
    match = _SQL_SERVER_PORT.match(server)
    if match is None:
        return server, None
    return match.group(1).strip(), int(match.group(2))


def _sql_server_configuration_options(
    options: Mapping[str, str],
) -> dict[str, object]:
    """Map documented SQL Server DSN aliases into config option names.

    Args:
        options: Parsed lowercase DSN options.

    Returns:
        Recognized values with boolean and read-only options converted.
    """
    result: dict[str, object] = {
        target: options[source]
        for source, target in _SQL_SERVER_OPTION_ALIASES.items()
        if source in options
    }
    for key in ("connectionpooling", "multipleactiveresultsets"):
        if key in options:
            result[_SQL_SERVER_OPTION_ALIASES[key]] = _parse_boolean(
                options[key]
            )
    if options.get("applicationintent", "").lower() == "readonly":
        result["readonly"] = True
    return result


def _parse_boolean(value: str) -> bool | str:
    """Convert recognized textual boolean values without guessing others.

    Args:
        value: The string supplied in an SQL Server DSN option.

    Returns:
        A boolean for recognized tokens or the original value otherwise.
    """
    normalized = value.lower()
    if normalized in {"1", "true", "on", "yes"}:
        return True
    if normalized in {"", "0", "false", "off", "no"}:
        return False
    return value


__all__ = ["ConfigurationUrlParser"]
