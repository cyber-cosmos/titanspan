"""Build immutable URI values with nested query-data operations.

The implementation uses Python's standard-library URL parser and delegates
nested mutation and RFC 3986 query encoding to Titanspan's Arr helpers.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self, TypeGuard
from urllib.parse import (
    SplitResult,
    quote,
    unquote,
    urlsplit,
    urlunsplit,
)

from titanspan.contracts import HtmlRenderable
from titanspan.contracts.routing import UriUrlGenerator
from titanspan.support.arr import Arr
from titanspan.support.conditionable import Conditionable
from titanspan.support.exceptions import UriContextError
from titanspan.support.helpers import data_get, data_has, enum_value
from titanspan.support.macroable import Macroable
from titanspan.support.stringable import Stringable
from titanspan.support.tappable import Tappable
from titanspan.support.uri_query_string import UriQueryString

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Mapping, Sequence
    from enum import Enum

    from titanspan.contracts.http import HttpResponse, ResponseFactory

type _UriText = str | Stringable
type _QueryData = dict[str | int, object]
type _QueryContainer = _QueryData | list[object]
_MISSING = object()
_USER_SAFE = "!$&'()*+,;="
_USERINFO_AFTER_SEPARATOR_SAFE = "!$&'()*+,;=:"
_MAX_PORT = 65535
_MAX_INTEGER_KEY_LENGTH = len(str(sys.maxsize))
_PORT_ERROR = "URI port must be between 0 and 65535"
_RESOLVER_ERROR = "URI factories require an active application context."
_RESPONSE_FACTORY_ERROR = "URI redirects require an active application context."
_REDIRECT_HEADER_OVERRIDE_ERROR = (
    "Redirect headers cannot replace the validated Location value."
)
_QUERY_INDEX_ERROR = "URI query list indexes must be contiguous"


def _is_query_mapping(value: object) -> TypeGuard[_QueryData]:
    """Narrow parser-owned mappings to their validated key and value types.

    Args:
        value: An arbitrary nested query value.

    Returns:
        Whether the value is a dictionary built by the URI parser.
    """
    return isinstance(value, dict)


def _is_query_list(value: object) -> TypeGuard[list[object]]:
    """Narrow parser-owned lists to their recursive query value type.

    Args:
        value: An arbitrary nested query value.

    Returns:
        Whether the value is a list built by the URI parser.
    """
    return isinstance(value, list)


def _is_query_container(value: object) -> TypeGuard[_QueryContainer]:
    """Check whether a value can be traversed as a query container.

    Args:
        value: An arbitrary nested query value.

    Returns:
        Whether the value is a parser-owned mapping or list.
    """
    return _is_query_mapping(value) or _is_query_list(value)


def _array_key(value: str) -> str | int:
    """Convert canonical decimal query indexes to integer keys.

    Args:
        value: A query key token from bracket notation.

    Returns:
        An integer for canonical decimal keys or the original string.
    """
    if not value.isascii():
        return value
    if value == "0":
        return 0
    digits = value[1:] if value.startswith("-") else value
    if digits and digits.isdecimal() and len(digits) <= _MAX_INTEGER_KEY_LENGTH:
        numeric = int(value)
        if -sys.maxsize - 1 <= numeric <= sys.maxsize and str(numeric) == value:
            return numeric
    return value


def _unique_values(values: Iterable[object]) -> list[object]:
    """Return values in first-seen order without requiring hashability.

    Args:
        values: Values to compare and retain.

    Returns:
        A list containing one instance of each equal value.
    """
    unique: list[object] = []
    for value in values:
        if not any(value == existing for existing in unique):
            unique.append(value)
    return unique


@dataclass(frozen=True, slots=True)
class _UriComponents:
    """Store parsed URI components and explicit empty delimiters.

    The delimiter flags preserve distinctions that :func:`urlsplit` drops,
    such as a missing query versus an explicitly empty query.
    """

    scheme: str
    authority: str
    path: str
    query: str
    fragment: str
    has_query: bool
    has_fragment: bool


def _components(value: str) -> _UriComponents:
    """Parse a URI and remember whether empty delimiters were present.

    Args:
        value: The URI string to parse.

    Returns:
        Parsed components with query and fragment delimiter state.
    """
    parsed = urlsplit(value)
    before_fragment, fragment_separator, _ = value.partition("#")
    return _UriComponents(
        scheme=parsed.scheme,
        authority=parsed.netloc,
        path=parsed.path,
        query=parsed.query,
        fragment=parsed.fragment,
        has_query="?" in before_fragment,
        has_fragment=bool(fragment_separator),
    )


def _render(components: _UriComponents) -> str:
    """Render components while preserving explicit empty delimiters.

    Args:
        components: The URI components to serialize.

    Returns:
        A URI string with an empty query or fragment delimiter preserved.
    """
    value = urlunsplit(
        (
            components.scheme,
            components.authority,
            components.path,
            components.query,
            components.fragment,
        )
    )
    if components.has_query and not components.query:
        fragment_index = value.find("#")
        if fragment_index < 0:
            value += "?"
        else:
            value = f"{value[:fragment_index]}?{value[fragment_index:]}"
    if components.has_fragment and not components.fragment:
        value += "#"
    return value


def _query_tokens(key: str) -> list[str]:
    """Split bracket notation into root and nested query keys.

    Args:
        key: A decoded key from the URI query string.

    Returns:
        The root key followed by bracketed keys, or the literal key.
    """
    opening = key.find("[")
    if opening < 0 or not key.endswith("]"):
        return [key]
    root = key[:opening]
    if not root:
        return [key]
    remainder = key[opening:]
    tokens = [root]
    cursor = 0
    while cursor < len(remainder):
        if remainder[cursor] != "[":
            return [key]
        end = remainder.find("]", cursor + 1)
        tokens.append(remainder[cursor + 1 : end])
        cursor = end + 1
    return tokens


def _ensure_child(
    container: _QueryContainer,
    key: str | int,
    next_key: str,
) -> _QueryContainer:
    """Return a compatible child mapping or list for nested assignment.

    Args:
        container: The current mutable query node.
        key: The key leading to the child node.
        next_key: The next path component.

    Returns:
        An existing or newly allocated nested container.
    """
    if next_key == "":
        expected: _QueryContainer = list[object]()
    else:
        expected = dict[str | int, object]()
    if _is_query_mapping(container):
        current = container.get(key, _MISSING)
        if not _is_query_container(current):
            container[key] = expected
            current = expected
        return current
    if not _is_query_list(container):
        raise ValueError(_QUERY_INDEX_ERROR)
    if key == "":
        container.append(expected)
        return expected
    if not isinstance(key, int) or not 0 <= key <= len(container):
        raise ValueError(_QUERY_INDEX_ERROR)
    if key == len(container):
        container.append(expected)
        return expected
    current = container[key]
    if _is_query_container(current):
        return current
    container[key] = expected
    return expected


def _store_query_value(
    container: _QueryContainer,
    key: str | int,
    value: str,
) -> None:
    """Store a scalar while retaining duplicate query keys as a list.

    Args:
        container: The current mutable query node.
        key: The scalar key to assign.
        value: The decoded query value.
    """
    if _is_query_mapping(container):
        current = container.get(key, _MISSING)
        if current is _MISSING:
            container[key] = value
        elif _is_query_list(current):
            current.append(value)
        else:
            container[key] = [current, value]
    elif not _is_query_list(container):
        raise ValueError(_QUERY_INDEX_ERROR)
    elif key == "":
        container.append(value)
    elif not isinstance(key, int) or not 0 <= key <= len(container):
        raise ValueError(_QUERY_INDEX_ERROR)
    elif key == len(container):
        container.append(value)
    else:
        container[key] = value


def _assign_query_value(data: _QueryData, key: str, value: str) -> None:
    """Assign a query value into nested bracket-notation data.

    Args:
        data: The root query mapping to mutate.
        key: The decoded query key.
        value: The decoded query value.
    """
    tokens = _query_tokens(key)
    current: _QueryContainer = data
    for index, token in enumerate(tokens):
        last = index == len(tokens) - 1
        next_token = "" if last else tokens[index + 1]
        parsed_key = _array_key(token)
        if last and token == "":
            _store_query_value(current, "", value)
        elif last:
            _store_query_value(current, parsed_key, value)
        else:
            current = _ensure_child(current, parsed_key, next_token)


def _normalize_query_value(value: object, *, as_list: bool = True) -> object:
    """Convert contiguous integer-key mappings into Python lists.

    Args:
        value: A nested query value.
        as_list: Whether a contiguous integer-key mapping can become a list.

    Returns:
        A recursively normalized value while retaining the requested root.
    """
    if _is_query_list(value):
        return [_normalize_query_value(item) for item in value]
    if _is_query_mapping(value):
        normalized: _QueryData = {
            key: _normalize_query_value(item) for key, item in value.items()
        }
        integer_keys = [
            key
            for key in normalized
            if isinstance(key, int) and not isinstance(key, bool)
        ]
        if (
            as_list
            and len(integer_keys) == len(normalized)
            and sorted(integer_keys) == list(range(len(integer_keys)))
        ):
            return [normalized[index] for index in range(len(integer_keys))]
        return normalized
    return value


def _userinfo(user: str | None, password: str | None) -> str:
    """Encode optional URI credentials without exposing raw separators.

    Args:
        user: The username, or ``None`` to omit credentials.
        password: The password, if one is supplied.

    Returns:
        Encoded user information followed by ``@``, or an empty string.
    """
    if user is None and password is None:
        return ""
    # A colon is legal only after the user/password separator; preserving it
    # in the username would change the parsed credential boundary.
    encoded_user = quote(user or "", safe=_USER_SAFE)
    encoded_password = (
        ""
        if password is None
        else f":{quote(password, safe=_USERINFO_AFTER_SEPARATOR_SAFE)}"
    )
    return f"{encoded_user}{encoded_password}@"


_URL_GENERATOR: ContextVar[Callable[[], UriUrlGenerator] | None] = ContextVar(
    "titanspan_uri_url_generator",
    default=None,
)
_RESPONSE_FACTORY: ContextVar[Callable[[], ResponseFactory] | None] = (
    ContextVar(
        "titanspan_uri_response_factory",
        default=None,
    )
)


@contextmanager
def bind_uri_services(
    url_generator: Callable[[], UriUrlGenerator] | None,
    response_factory: Callable[[], ResponseFactory] | None,
) -> Generator[None, None, None]:
    """Bind URI integrations for one application execution context.

    Foundation enters this context alongside its canonical application
    context. ContextVar tokens restore nested apps and concurrent tasks.

    Args:
        url_generator: Optional resolver for route-aware URI factories.
        response_factory: Optional resolver for native URI redirects.

    Yields:
        Control while both application-owned services remain addressable.
    """
    generator_token = _URL_GENERATOR.set(url_generator)
    factory_token = _RESPONSE_FACTORY.set(response_factory)
    try:
        yield
    finally:
        _RESPONSE_FACTORY.reset(factory_token)
        _URL_GENERATOR.reset(generator_token)


class Uri(
    Macroable,
    Conditionable,
    Tappable,
    HtmlRenderable,
):
    """Represent an immutable URI with fluent component updates.

    URL parsing and component composition use :mod:`urllib.parse`. Query
    serialization delegates to :class:`Arr`; route generation uses the
    active application's native URL generator.

    Notes:
        The string value retains credentials by design. ``repr`` removes
        user information so accidental diagnostic output does not expose it.
        This class parses URLs but does not validate destinations for SSRF.
    """

    def __init__(self, uri: _UriText | SplitResult = "") -> None:
        """Create a URI from a string, Stringable, or parsed standard value.

        Args:
            uri: The URI representation to preserve.

        Raises:
            ValueError: If Python's URI parser rejects malformed authority data.
        """
        if isinstance(uri, SplitResult):
            value = urlunsplit(uri)
        elif isinstance(uri, Stringable):
            value = uri.to_string()
        else:
            value = uri
        # Validate the parser-visible authority at construction time so port
        # and IPv6 errors do not surface later from unrelated property reads.
        parsed = urlsplit(value)
        _ = parsed.port
        self._value = value

    @classmethod
    def of(cls, uri: _UriText | SplitResult = "") -> Self:
        """Create a URI instance using the concrete subclass.

        Args:
            uri: The source URI.

        Returns:
            A new URI instance.
        """
        return cls(uri)

    @classmethod
    def to(cls, path: str) -> Self:
        """Build a URI from the configured URL generator's path helper.

        Args:
            path: The application path to resolve.

        Returns:
            A URI containing the generated absolute or relative URL.

        Raises:
            UriContextError: If no application context is active.
        """
        return cls(cls._generator().to(path))

    @classmethod
    def route(
        cls,
        name: str | Enum,
        parameters: Mapping[str, object] | None = None,
        absolute: bool = True,
    ) -> Self:
        """Build a URI for a named route using the configured URL generator.

        Args:
            name: The route name or a scalar-backed enum member.
            parameters: Values used to generate route parameters.
            absolute: Whether to include the route origin.

        Returns:
            A URI containing the generated route.

        Raises:
            UriContextError: If no application context is active.
        """
        route_name = enum_value(name)
        return cls(
            cls._generator().route(
                str(route_name),
                parameters or {},
                absolute,
            )
        )

    @classmethod
    def signed_route(
        cls,
        name: str | Enum,
        parameters: Mapping[str, object] | None = None,
        expiration: object = None,
        absolute: bool = True,
    ) -> Self:
        """Build a signed URI for a named route.

        Args:
            name: The route name or a scalar-backed enum member.
            parameters: Values used to generate route parameters.
            expiration: The requested signature expiration value.
            absolute: Whether to include the route origin.

        Returns:
            A URI containing the signed route.
        """
        route_name = enum_value(name)
        return cls(
            cls._generator().signed_route(
                str(route_name),
                parameters or {},
                expiration,
                absolute,
            )
        )

    @classmethod
    def temporary_signed_route(
        cls,
        name: str | Enum,
        expiration: object,
        parameters: Mapping[str, object] | None = None,
        absolute: bool = True,
    ) -> Self:
        """Build a temporary signed route through the signed-route API.

        Args:
            name: The route name or a scalar-backed enum member.
            expiration: The requested signature expiration value.
            parameters: Values used to generate route parameters.
            absolute: Whether to include the route origin.

        Returns:
            A URI containing the temporary signed route.
        """
        return cls.signed_route(name, parameters, expiration, absolute)

    @classmethod
    def action(
        cls,
        action: str | Sequence[str],
        parameters: Mapping[str, object] | None = None,
        absolute: bool = True,
    ) -> Self:
        """Build a URI for a controller action.

        Args:
            action: The action name or an ordered action descriptor.
            parameters: Values used to generate action parameters.
            absolute: Whether to include the action origin.

        Returns:
            A URI containing the generated action.
        """
        return cls(cls._generator().action(action, parameters or {}, absolute))

    def authority(self) -> str | None:
        """Return the encoded authority, including credentials if present.

        Returns:
            The authority component, or ``None`` when absent.
        """
        return self._components().authority or None

    def scheme(self) -> str | None:
        """Return the parsed scheme in lowercase.

        Returns:
            The scheme component, or ``None`` for a relative URI.
        """
        return self._components().scheme or None

    def user(self, with_password: bool = False) -> str | None:
        """Return the username, optionally including its password.

        Args:
            with_password: Whether to include a supplied password.

        Returns:
            The decoded username or user information, or ``None``.
        """
        parsed = self._parsed()
        username = parsed.username
        if username is None:
            return None
        decoded_user = unquote(username, encoding="utf-8", errors="replace")
        if not with_password or parsed.password is None:
            return decoded_user
        decoded_password = unquote(
            parsed.password,
            encoding="utf-8",
            errors="replace",
        )
        return f"{decoded_user}:{decoded_password}"

    def password(self) -> str | None:
        """Return the percent-decoded password component.

        Returns:
            The password, or ``None`` when credentials omit one.
        """
        password = self._parsed().password
        if password is None:
            return None
        return unquote(password, encoding="utf-8", errors="replace")

    def host(self) -> str | None:
        """Return the hostname without credentials or port information.

        Returns:
            The hostname, or ``None`` when no host is present.
        """
        return self._parsed().hostname

    def port(self) -> int | None:
        """Return the validated numeric port.

        Returns:
            The port number, or ``None`` when the URI omits a port.
        """
        return self._parsed().port

    def origin(self) -> str | None:
        """Return a normalized hierarchical origin when one exists.

        Returns:
            A lowercase origin with a default port removed, or ``None`` for
            relative and opaque URIs.
        """
        parsed = self._parsed()
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        if not scheme or not hostname or scheme == "file":
            return None
        host = f"[{hostname}]" if ":" in hostname else hostname.lower()
        port = parsed.port
        defaults = {
            "http": 80,
            "https": 443,
            "ws": 80,
            "wss": 443,
            "ftp": 21,
        }
        suffix = (
            f":{port}"
            if port is not None and defaults.get(scheme) != port
            else ""
        )
        return f"{scheme}://{host}{suffix}"

    def path(self) -> str:
        """Return the path without leading or trailing slashes.

        Empty paths are represented as a single slash for stable URI output.

        Returns:
            A normalized path string.
        """
        path = self._components().path.strip("/")
        return path or "/"

    def path_segments(self) -> tuple[str, ...]:
        """Return path components without empty leading or trailing entries.

        Returns:
            An immutable tuple of path segments.
        """
        path = self.path()
        return () if path == "/" else tuple(path.split("/"))

    def query(self) -> UriQueryString:
        """Create a read-only view over the current query component.

        Returns:
            The URI's query-string adapter.
        """
        return UriQueryString(self)

    def fragment(self) -> str | None:
        """Return the encoded fragment or ``None`` when the URI has none.

        Returns:
            The fragment component as represented in the URI.
        """
        return self._components().fragment or None

    def with_scheme(self, scheme: _UriText) -> Self:
        """Return a URI with a replacement scheme.

        Args:
            scheme: The new scheme, with or without a trailing colon.

        Returns:
            A new URI preserving the remaining components.
        """
        value = scheme.to_string() if isinstance(scheme, Stringable) else scheme
        return self._replace(scheme=value.removesuffix(":"))

    def with_user(
        self,
        user: _UriText | None,
        password: _UriText | None = None,
    ) -> Self:
        """Return a URI with replaced or removed user information.

        Args:
            user: The new username, or ``None`` to remove credentials.
            password: An optional password encoded as URI user information.

        Returns:
            A new URI; the source object is unchanged.
        """
        user_text = user.to_string() if isinstance(user, Stringable) else user
        password_text = (
            password.to_string()
            if isinstance(password, Stringable)
            else password
        )
        components = self._components()
        host = components.authority.rsplit("@", 1)[-1]
        authority = _userinfo(user_text, password_text) + host
        return self._replace(authority=authority)

    def with_host(self, host: _UriText) -> Self:
        """Return a URI with a replacement hostname.

        Args:
            host: The hostname or bracketed IPv6 address.

        Returns:
            A new URI preserving credentials, port, and other components.
        """
        host_text = host.to_string() if isinstance(host, Stringable) else host
        components = self._components()
        user_info, separator, _ = components.authority.rpartition("@")
        old_host = self._parsed().hostname
        port = self._parsed().port
        if old_host and ":" in old_host and not host_text.startswith("["):
            host_text = f"[{host_text}]"
        host_port = host_text
        if port is not None:
            host_port = f"{host_port}:{port}"
        prefix = f"{user_info}@" if separator else ""
        return self._replace(authority=prefix + host_port)

    def with_port(self, port: int | None) -> Self:
        """Return a URI with a replacement or removed port.

        Args:
            port: A valid TCP or UDP port, or ``None`` to remove it.

        Returns:
            A new URI with the updated authority.

        Raises:
            ValueError: If ``port`` is outside the valid numeric range.
        """
        if port is not None and (
            isinstance(port, bool) or not 0 <= port <= _MAX_PORT
        ):
            raise ValueError(_PORT_ERROR)
        components = self._components()
        user_info, separator, _ = components.authority.rpartition("@")
        parsed = self._parsed()
        host = parsed.hostname
        if host is None:
            user_info, separator, _ = components.authority.rpartition("@")
            prefix = f"{user_info}@" if separator else ""
            suffix = "" if port is None else f":{port}"
            return self._replace(authority=f"{prefix}{suffix}")
        if ":" in host:
            host = f"[{host}]"
        suffix = "" if port is None else f":{port}"
        prefix = f"{user_info}@" if separator else ""
        return self._replace(authority=f"{prefix}{host}{suffix}")

    def with_path(self, path: _UriText) -> Self:
        """Return a URI with a path that begins with a slash.

        Args:
            path: The replacement path.

        Returns:
            A new URI preserving the authority and query components.
        """
        path_text = path.to_string() if isinstance(path, Stringable) else path
        if not path_text.startswith("/"):
            path_text = f"/{path_text}"
        return self._replace(path=path_text)

    def with_query(
        self,
        query: Mapping[str | int, object],
        merge: bool = True,
    ) -> Self:
        """Merge nested query values or replace the full query mapping.

        Args:
            query: The query values to encode.
            merge: Whether to merge into existing query values.

        Returns:
            A new URI with RFC 3986 encoded query data.
        """
        values: _QueryData = self.query().all() if merge else {}
        for key, value in query.items():
            Arr.set(values, key, value)
        encoded = Arr.query(values)
        return self._replace(
            query=encoded,
            has_query=bool(encoded),
        )

    def with_query_if_missing(
        self,
        query: Mapping[str | int, object],
    ) -> Self:
        """Add query values only where nested keys are currently absent.

        Args:
            query: Candidate values to add.

        Returns:
            A new URI preserving current values for present keys.
        """
        values = dict(query)
        current = self.query().all()
        for key in tuple(values):
            if data_has(current, key):
                values.pop(key)
        return self.with_query(values)

    def push_onto_query(self, key: str, value: object) -> Self:
        """Append values to a query parameter, preserving unique list items.

        Args:
            key: The nested query key to extend.
            value: One item or a sequence of items to append.

        Returns:
            A new URI with the extended parameter.
        """
        current = data_get(self.query().all(), key)
        values = Arr.wrap(value)
        if _is_query_list(current):
            combined = current + list(values)
            pushed: object = _unique_values(combined)
        elif _is_query_mapping(current):
            # Preserve named keys and append numeric values after existing
            # sequence entries.
            pushed: object = dict(current)
            next_index = (
                max(
                    (item for item in pushed if isinstance(item, int)),
                    default=-1,
                )
                + 1
            )
            for offset, item in enumerate(values):
                pushed[next_index + offset] = item
        elif current is None:
            pushed = values
        else:
            pushed = [current, *values]
        return self.with_query({key: pushed})

    def without_query(self, keys: str | Iterable[str]) -> Self:
        """Return a URI after removing one or more nested query keys.

        Args:
            keys: A key or sequence of keys to remove.

        Returns:
            A new URI with selected query values omitted.
        """
        return self.replace_query(Arr.except_(self.query().all(), keys))

    def replace_query(self, query: Mapping[str | int, object]) -> Self:
        """Replace the query mapping instead of merging with it.

        Args:
            query: The complete replacement query mapping.

        Returns:
            A new URI containing only the supplied values.
        """
        return self.with_query(query, merge=False)

    def with_fragment(self, fragment: str) -> Self:
        """Return a URI with a replacement fragment.

        Args:
            fragment: The replacement fragment text.

        Returns:
            A new URI preserving all non-fragment components.
        """
        return self._replace(fragment=fragment, has_fragment=True)

    def without_fragment(self) -> Self:
        """Return a URI without its fragment component.

        Returns:
            A new URI preserving all non-fragment components.
        """
        return self._replace(fragment="", has_fragment=False)

    def redirect(
        self,
        status: int = 302,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        """Create a redirect through the active native response factory.

        Args:
            status: The HTTP redirect status code.
            headers: Optional response headers.

        Returns:
            Native response with a validated Location header.

        Raises:
            UriContextError: If no application response factory is active.
            ValueError: If the destination violates redirect policy.
        """
        resolver = _RESPONSE_FACTORY.get()
        if resolver is None:
            raise UriContextError(_RESPONSE_FACTORY_ERROR)
        response = resolver().redirect(self.value(), status=status)
        for name, value in (headers or {}).items():
            if name.casefold() == "location":
                raise ValueError(_REDIRECT_HEADER_OVERRIDE_ERROR)
            response.with_header(name, value)
        return response

    def to_stringable(self) -> Stringable:
        """Wrap the URI string in Titanspan's fluent string type.

        Returns:
            A new Stringable value.
        """
        return Stringable(self.value())

    def to_html(self) -> str:
        """Return the URI string through the HtmlRenderable protocol.

        Returns:
            The URI string without HTML escaping.

        Security:
            Escape this URI for the target HTML context before embedding it.
        """
        return self.value()

    def decode(self) -> str:
        """Decode percent escapes in the query component only.

        Returns:
            The URI with its query percent-decoded and fragment preserved.
        """
        query = self.query()
        if not query.all():
            return self.value()
        components = self._components()
        decoded = query.decode()
        return self._replace_value(
            replace(components, query=decoded, has_query=bool(decoded))
        )

    def value(self) -> str:
        """Return the serialized URI value.

        Returns:
            The URI string.
        """
        return self._value

    def to_string(self) -> str:
        """Return the serialized URI using the explicit conversion API.

        Returns:
            The URI string.
        """
        return self.value()

    def is_empty(self) -> bool:
        """Check whether the URI contains only whitespace.

        Returns:
            Whether its string representation is blank.
        """
        return not self._value.strip()

    def is_not_empty(self) -> bool:
        """Check whether the URI contains non-whitespace text.

        Returns:
            Whether its string representation is non-empty.
        """
        return not self.is_empty()

    def dump(self, *values: object) -> Self:
        """Print this URI and optional values, then return the URI itself.

        Args:
            *values: Additional values printed after the URI string.

        Returns:
            This same URI instance.
        """
        sys.stdout.write(f"{self.value()!r}\n")
        for value in values:
            sys.stdout.write(f"{value!r}\n")
        return self

    def get_uri(self) -> SplitResult:
        """Return Python's parsed URI representation.

        Returns:
            The standard-library SplitResult for native interoperability.
        """
        return self._parsed()

    def __str__(self) -> str:
        """Return the URI string through Python's string protocol.

        Returns:
            The URI value.
        """
        return self.value()

    def __repr__(self) -> str:
        """Return a constructor-like representation without credentials.

        Returns:
            A URI representation that omits username and password values.
        """
        components = self._components()
        _, separator, authority = components.authority.rpartition("@")
        if separator:
            components = replace(components, authority=authority)
        return f"Uri({_render(components)!r})"

    def _components(self) -> _UriComponents:
        """Parse the preserved value into URI components.

        Returns:
            Parsed components with explicit delimiter state.
        """
        return _components(self._value)

    def _parsed(self) -> SplitResult:
        """Return the standard-library parsed URI result.

        Returns:
            The parsed URI components.
        """
        return urlsplit(self._value)

    def _replace(self, **changes: str | bool) -> Self:
        """Create a new URI with selected parsed components replaced.

        Args:
            **changes: Fields from the private immutable component record.

        Returns:
            A new URI instance.
        """
        updated = replace(self._components(), **changes)
        return type(self)(self._replace_value(updated))

    @staticmethod
    def _replace_value(components: _UriComponents) -> str:
        """Serialize a component record with empty delimiters preserved.

        Args:
            components: Components to serialize.

        Returns:
            The serialized URI string.
        """
        return _render(components)

    def _query_data(self) -> _QueryData:
        """Decode query data with nested bracket-notation keys.

        Returns:
            A nested Python mapping containing decoded string values.
        """
        data: _QueryData = {}
        raw_query = self._components().query
        for pair in raw_query.split("&"):
            if not pair:
                continue
            raw_key, separator, raw_value = pair.partition("=")
            # League's default RFC 3986 mode leaves ``+`` literal. The
            # form-oriented ``parse_qsl`` default would incorrectly turn it
            # into a space here.
            key = unquote(raw_key, encoding="utf-8", errors="replace")
            value = unquote(
                raw_value if separator else "",
                encoding="utf-8",
                errors="replace",
            )
            _assign_query_value(data, key, value)
        # The public query result is always a mapping. Only nested numeric
        # maps should become lists, matching bracket-array notation.
        normalized = _normalize_query_value(data, as_list=False)
        if _is_query_mapping(normalized):
            return normalized
        return {}

    @classmethod
    def _generator(cls) -> UriUrlGenerator:
        """Resolve the URL generator from the active execution context.

        Returns:
            The configured URL generator.

        Raises:
            UriContextError: If no application context is active.
        """
        resolver = _URL_GENERATOR.get()
        if resolver is None:
            raise UriContextError(_RESOLVER_ERROR)
        return resolver()


__all__ = ["Uri", "UriUrlGenerator"]
