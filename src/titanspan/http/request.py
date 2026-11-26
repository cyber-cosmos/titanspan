"""Provide native incoming request metadata and explicit body operations.

Metadata is synchronous; body reads remain explicit and asynchronous.
"""

import math
from collections.abc import AsyncIterator, Mapping, Sequence
from enum import Enum, auto
from types import MappingProxyType
from typing import Protocol, TypeVar, cast

from pydantic import TypeAdapter, ValidationError

from titanspan.contracts.http import HttpRequest, JsonValue
from titanspan.http.exceptions import (
    RequestBodyConsumedError,
    RequestError,
    RequestInputError,
)
from titanspan.http.uploaded_file import UploadedFile
from titanspan.support import Arr

DefaultT = TypeVar("DefaultT")


class _Missing(Enum):
    """Represent absence without colliding with valid request values.

    Metadata is synchronous; body reads remain explicit and asynchronous.
    """

    VALUE = auto()


_MISSING = _Missing.VALUE
_JSON_ADAPTER = TypeAdapter(JsonValue)
_INVALID_JSON_BODY_ERROR = "The request body is not valid JSON."
_BODY_ALREADY_CONSUMED_ERROR = "The request body stream was already consumed."
_INVALID_FORM_ERROR = "The request form is invalid."
_OBJECT_JSON_REQUIRED_ERROR = "Object-shaped JSON is required for input."
_REQUEST_LIFECYCLE_ENDED_ERROR = "The request lifecycle has already ended."
_EMPTY_ATTRIBUTE_NAME_ERROR = "Request attribute names cannot be empty."


class RequestBackend(Protocol):
    """Describe private operations required from the ASGI adapter.

    Metadata is synchronous; body reads remain explicit and asynchronous.
    """

    @property
    def method(self) -> str:
        """Return the normalized method received by the server adapter.

        The value is uppercase and does not consume request content.
        """
        ...

    @property
    def url(self) -> str:
        """Return the complete URL assembled for this request.

        The adapter preserves the server-provided scheme, host, path, and
        query string without reading the body.
        """
        ...

    @property
    def path(self) -> str:
        """Return the URL path without its query string.

        Path access does not trigger request-body consumption.
        """
        ...

    @property
    def host(self) -> str:
        """Return the host supplied by the HTTP server boundary.

        The adapter does not trust an unvalidated forwarded host header.
        """
        ...

    @property
    def scheme(self) -> str:
        """Return the connection scheme reported by the server boundary.

        Proxy-derived scheme values are controlled by server configuration.
        """
        ...

    @property
    def headers(self) -> tuple[tuple[str, str], ...]:
        """Return an immutable header snapshot preserving duplicate values.

        Header lookup through the public Request API remains
        case-insensitive.
        """
        ...

    @property
    def query_items(self) -> tuple[tuple[str, str], ...]:
        """Return decoded query pairs in their original order.

        Repeated names remain separate pairs for multi-value access.
        """
        ...

    @property
    def cookies(self) -> Mapping[str, str]:
        """Return parsed cookie names and values for this request.

        Cookie parsing uses the server adapter and does not consume the body.
        """
        ...

    @property
    def client(self) -> tuple[str, int] | None:
        """Return the peer address or None when the server omits it.

        The peer value is server-observed and is not proxy identity metadata.
        """
        ...

    def header(self, name: str, default: str | None) -> str | None:
        """Return a case-insensitive header value or its supplied default.

        Args:
            name: Header name to search.
            default: Value returned when the name is absent.

        Returns:
            The last matching header value or the default.
        """
        ...

    async def body(self) -> bytes:
        """Buffer and return the request body under the configured limit.

        Returns:
            The complete body bytes retained by the request adapter.
        """
        ...

    def stream(self) -> AsyncIterator[bytes]:
        """Return the one-shot asynchronous body stream.

        Yields:
            Non-empty request body chunks in transport order.
        """
        ...

    async def form(
        self,
        *,
        max_files: int,
        max_fields: int,
        max_part_size: int,
    ) -> Mapping[str, object]:
        """Parse form input with explicit file, field, and part limits.

        Args:
            max_files: Maximum number of accepted upload parts.
            max_fields: Maximum number of non-file fields.
            max_part_size: Maximum non-file part size in bytes.

        Returns:
            Parsed fields and upload wrappers owned by the request.
        """
        ...

    async def form_values(
        self,
        key: str,
        *,
        max_files: int,
        max_fields: int,
        max_part_size: int,
    ) -> Sequence[object]:
        """Return all parsed values for a form field in input order.

        Args:
            key: Form field name whose repeated values are requested.
            max_files: Maximum number of accepted upload parts.
            max_fields: Maximum number of non-file fields.
            max_part_size: Maximum non-file part size in bytes.

        Returns:
            Values in input order, including upload wrappers where present.
        """
        ...

    async def aclose(self) -> None:
        """Release parser and upload resources owned by this request.

        Repeated close calls are safe and do not transfer ownership to the
        application code inspecting the request.
        """
        ...


class Request(HttpRequest):
    """Expose request metadata synchronously and content asynchronously.

    Query, header, cookie and connection access does not consume the body.
    Body parsers cache their result. The incremental ``stream`` operation is
    single-consumption unless the body was already explicitly buffered.
    """

    def __init__(
        self,
        backend: RequestBackend,
        *,
        request_id: str,
        max_form_files: int,
        max_form_fields: int,
        max_part_size: int,
    ) -> None:
        """Wrap an ASGI request adapter created by Foundation middleware.

        Args:
            backend: Private adapter around the active ASGI request.
            request_id: Bounded correlation identifier assigned by middleware.
            max_form_files: Maximum multipart files accepted by the parser.
            max_form_fields: Maximum non-file form fields accepted.
            max_part_size: Maximum non-file multipart part size.
        """
        self._backend = backend
        self._request_id = request_id
        self._max_form_files = max_form_files
        self._max_form_fields = max_form_fields
        self._max_part_size = max_part_size
        self._cached_body: bytes | None = None
        self._cached_json: JsonValue | _Missing = _MISSING
        self._cached_form: Mapping[str, object] | None = None
        self._attributes: dict[str, object] = {}
        self._stream_started = False
        self._closed = False

    @property
    def request_id(self) -> str:
        """Return the bounded correlation identifier for this request.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        return self._request_id

    @property
    def method(self) -> str:
        """Return the uppercase HTTP method.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        return self._backend.method.upper()

    @property
    def url(self) -> str:
        """Return the request URL as a string.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        return self._backend.url

    @property
    def full_url(self) -> str:
        """Return the complete URL including query parameters.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        return self.url

    @property
    def path(self) -> str:
        """Return the URL path without query parameters.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        return self._backend.path

    @property
    def host(self) -> str:
        """Return the host component without a port when available.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        return self._backend.host

    @property
    def scheme(self) -> str:
        """Return the request URL scheme.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        return self._backend.scheme

    @property
    def headers(self) -> Mapping[str, str]:
        """Return an immutable lower-case header snapshot.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        values = {name.lower(): value for name, value in self._backend.headers}
        return MappingProxyType(values)

    @property
    def cookies(self) -> Mapping[str, str]:
        """Return an immutable snapshot of parsed request cookies.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        return MappingProxyType(dict(self._backend.cookies))

    @property
    def client(self) -> tuple[str, int] | None:
        """Return the connected peer address if ASGI supplied one.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        return self._backend.client

    @property
    def content_type(self) -> str | None:
        """Return the declared request media type, without parameters.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        value = self.header("content-type")
        return (
            None if value is None else value.split(";", maxsplit=1)[0].strip()
        )

    def is_method(self, method: str) -> bool:
        """Check the request method without case-sensitive comparison.

        Args:
            method: Method name to compare against the current request.

        Returns:
            Whether both method names match after uppercase normalization.
        """
        return self.method == method.upper()

    def is_secure(self) -> bool:
        """Return whether the request scheme is HTTPS.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        return self.scheme.lower() == "https"

    def header(self, name: str, default: str | None = None) -> str | None:
        """Return a header value using case-insensitive matching.

        Args:
            name: Header name to find.
            default: Value returned if the header is absent.

        Returns:
            Header value or the supplied default.
        """
        return self._backend.header(name, default)

    def query(
        self, key: str, default: DefaultT | None = None
    ) -> object | DefaultT | None:
        """Return one query parameter without reading the request body.

        Args:
            key: Query parameter name or dotted path.
            default: Value returned when the parameter is absent.

        Returns:
            The last matching query value or the supplied default.
        """
        data = dict(self._backend.query_items)
        value = Arr.get(data, key, _MISSING)
        return default if value is _MISSING else value

    def query_values(self, key: str) -> tuple[str, ...]:
        """Return every query value for a repeated parameter.

        Args:
            key: Query parameter name.

        Returns:
            Values in their original request order.
        """
        return tuple(
            value for name, value in self._backend.query_items if name == key
        )

    def attribute(self, key: str, default: object = None) -> object:
        """Read one request-local attribute without consuming the body.

        Args:
            key: Middleware or routing metadata name.
            default: Value returned when the attribute is absent.

        Returns:
            The stored request-local value or default.

        Raises:
            RequestError: If the owning request scope has already closed.
        """
        self._ensure_open()
        return self._attributes.get(key, default)

    def set_attribute(self, key: str, value: object) -> None:
        """Store execution-local metadata for middleware and dispatch.

        Args:
            key: Non-empty attribute name.
            value: Metadata value owned by the active request scope.

        Raises:
            RequestError: If the owning request scope has already closed.
            ValueError: If the attribute key is empty.
        """
        self._ensure_open()
        if not key:
            raise ValueError(_EMPTY_ATTRIBUTE_NAME_ERROR)
        self._attributes[key] = value

    def cookie(self, key: str, default: str | None = None) -> str | None:
        """Return one parsed cookie value.

        Args:
            key: Cookie name.
            default: Value returned if the cookie is absent.

        Returns:
            Cookie value or the supplied default.
        """
        return self._backend.cookies.get(key, default)

    def bearer_token(self) -> str | None:
        """Return a token from a correctly formed authorization header.

        Malformed or non-bearer authorization values return ``None``.
        """
        authorization = self.header("authorization")
        if authorization is None:
            return None
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token.strip():
            return None
        return token.strip()

    def accepts(self, media_type: str) -> bool:
        """Check the Accept header for one media type or a matching wildcard.

        Args:
            media_type: Concrete type such as ``application/json``.

        Returns:
            Whether a positive-quality Accept range covers the media type.
        """
        accepted = self.header("accept")
        if accepted is None or not accepted.strip():
            return True
        target_type, _, target_subtype = media_type.lower().partition("/")
        for item in accepted.split(","):
            value, *parameters = item.strip().lower().split(";")
            quality = 1.0
            for parameter in parameters:
                name, separator, raw = parameter.partition("=")
                if separator and name.strip() == "q":
                    try:
                        quality = float(raw.strip())
                    except ValueError:
                        quality = 0.0
            accepted_type, _, accepted_subtype = value.partition("/")
            if (
                quality > 0
                and accepted_type in {"*", target_type}
                and accepted_subtype in {"*", target_subtype}
            ):
                return True
        return False

    def expects_json(self) -> bool:
        """Return whether JSON is explicitly preferred by the Accept header.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        accepted = self.header("accept", "") or ""
        requested_with = self.header("x-requested-with", "") or ""
        return (
            "json" in accepted.lower()
            or requested_with.lower() == "xmlhttprequest"
        )

    async def has(self, key: str) -> bool:
        """Check body and query presence without conflating null or false.

        Args:
            key: Input path to search.

        Returns:
            Whether a value exists at the selected path.
        """
        return await self._input_value(key) is not _MISSING

    async def filled(self, key: str) -> bool:
        """Check whether an input exists and is not an empty value.

        ``False`` and zero count as filled values. Only ``None``, an empty
        string, and empty containers are considered empty.

        Args:
            key: Input path to inspect.

        Returns:
            Whether the path exists and contains a non-empty value.
        """
        value = await self._input_value(key)
        return value is not _MISSING and value not in (None, "", [], {})

    async def string(
        self,
        key: str,
        default: str | None = None,
    ) -> str | None:
        """Retrieve a string value or reject incompatible input.

        Args:
            key: Input path to inspect.
            default: Value returned when the path is absent.

        Returns:
            The exact string value or the absent-value default.

        Raises:
            RequestInputError: If a present value is not a string.
        """
        value = await self._input_value(key)
        if value is _MISSING:
            return default
        if not isinstance(value, str):
            raise _invalid_input_type(key, "a string")
        return value

    async def integer(
        self,
        key: str,
        default: int | None = None,
    ) -> int | None:
        """Retrieve an integer without accepting booleans or decimal text.

        Query and form strings must contain a base-ten integer. JSON values
        must have the exact integer type, since Python booleans subclass int.

        Args:
            key: Input path to inspect.
            default: Value returned when the path is absent.

        Returns:
            The validated integer or absent-value default.

        Raises:
            RequestInputError: If a present value is not an integer.
        """
        value = await self._input_value(key)
        if value is _MISSING:
            return default
        if type(value) is int:
            return value
        if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
            return int(value)
        raise _invalid_input_type(key, "an integer")

    async def float(
        self,
        key: str,
        default: float | None = None,
    ) -> float | None:
        """Retrieve a finite number, parsing numeric query and form strings.

        Args:
            key: Input path to inspect.
            default: Value returned when the path is absent.

        Returns:
            The finite float or absent-value default.

        Raises:
            RequestInputError: If a present value is not a finite number.
        """
        value = await self._input_value(key)
        if value is _MISSING:
            return default
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result = float(value)
        elif isinstance(value, str):
            try:
                result = float(value)
            except ValueError as error:
                raise _invalid_input_type(key, "a finite number") from error
        else:
            raise _invalid_input_type(key, "a finite number")
        if not math.isfinite(result):
            raise _invalid_input_type(key, "a finite number")
        return result

    async def boolean(
        self,
        key: str,
        default: bool | None = None,
    ) -> bool | None:
        """Retrieve a boolean from JSON or a documented textual value.

        Text values ``true``, ``false``, ``1``, ``0``, ``yes``, ``no``,
        ``on``, and ``off`` are accepted case-insensitively.

        Args:
            key: Input path to inspect.
            default: Value returned when the path is absent.

        Returns:
            The validated boolean or absent-value default.

        Raises:
            RequestInputError: If a present value is not a supported boolean.
        """
        value = await self._input_value(key)
        if value is _MISSING:
            return default
        if type(value) is bool:
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        raise _invalid_input_type(key, "a supported boolean")

    async def array(
        self,
        key: str,
        default: Mapping[str, object] | list[object] | None = None,
    ) -> Mapping[str, object] | list[object] | None:
        """Retrieve a mapping or list without coercing scalar values.

        Args:
            key: Input path to inspect.
            default: Value returned when the path is absent.

        Returns:
            The mapping/list or absent-value default.

        Raises:
            RequestInputError: If a present value is not array-shaped.
        """
        value = await self._input_value(key)
        if value is _MISSING:
            return default
        if isinstance(value, Mapping):
            candidate: Mapping[object, object] = cast(
                "Mapping[object, object]",
                value,
            )
            if any(not isinstance(path, str) for path in candidate):
                raise _invalid_input_type(key, "a string-keyed mapping")
            # Keys are checked; the contract intentionally leaves values opaque.
            return cast("Mapping[str, object]", value)
        if isinstance(value, list):
            return cast("list[object]", value)
        raise _invalid_input_type(key, "a mapping or list")

    async def input(
        self,
        key: str,
        default: DefaultT | None = None,
    ) -> object | DefaultT | None:
        """Read an input path, with body values overriding query values.

        The first access to JSON or form input consumes and caches parsed
        content. Query access alone remains synchronous through ``query``.

        Args:
            key: Dotted path in merged query and body data.
            default: Value returned for an absent path.

        Returns:
            The body-over-query value or the supplied default.
        """
        value = await self._input_value(key)
        return default if value is _MISSING else value

    async def all(self) -> Mapping[str, object]:
        """Return query and parsed body values, with body values winning.

        Returns:
            A new shallow mapping of merged request input.
        """
        values: dict[str, object] = dict(self._backend.query_items)
        body = await self._body_values()
        values.update(body)
        return values

    async def only(self, keys: Sequence[str]) -> Mapping[str, object]:
        """Return a flat mapping containing only requested input paths.

        Args:
            keys: Input paths to retain.

        Returns:
            A mapping keyed by the exact requested path names.
        """
        result: dict[str, object] = {}
        for key in keys:
            value = await self._input_value(key)
            if value is not _MISSING:
                result[key] = value
        return result

    async def except_(self, keys: Sequence[str]) -> Mapping[str, object]:
        """Return merged input excluding the exact selected top-level keys.

        Args:
            keys: Names omitted from the returned mapping.

        Returns:
            A new mapping containing every remaining input entry.
        """
        result = dict(await self.all())
        for key in keys:
            result.pop(key, None)
        return result

    async def body(self) -> bytes:
        """Read and cache the complete body within the configured byte limit.

        Returns:
            The buffered body bytes.

        Raises:
            RequestBodyConsumedError: If a prior streaming read consumed it.
        """
        self._ensure_open()
        if self._stream_started and self._cached_body is None:
            raise RequestBodyConsumedError(_BODY_ALREADY_CONSUMED_ERROR)
        if self._cached_body is None:
            try:
                self._cached_body = await self._backend.body()
            except RequestError:
                raise
            except RuntimeError as error:
                raise RequestBodyConsumedError(
                    _BODY_ALREADY_CONSUMED_ERROR
                ) from error
        return self._cached_body

    async def json(self) -> JsonValue:
        """Parse the body as validated JSON and cache the resulting value.

        An empty body returns ``None``. An explicit JSON ``null`` remains a
        parsed null value and is distinct when object-shaped input is required.

        Returns:
            A JSON-compatible scalar, list, or mapping.

        Raises:
            RequestInputError: If the body is malformed or unsupported JSON.
        """
        self._ensure_open()
        if self._cached_json is not _MISSING:
            return self._cached_json
        try:
            body = await self.body()
            parsed = None if not body else _JSON_ADAPTER.validate_json(body)
        except (ValidationError, ValueError) as error:
            raise RequestInputError(_INVALID_JSON_BODY_ERROR) from error
        self._cached_json = parsed
        return parsed

    async def form(self) -> Mapping[str, object]:
        """Parse form fields and uploads with explicit parser limits.

        Returns:
            The last value for each form field. Use ``form_values`` for
            repeated fields.

        Raises:
            RequestInputError: If the form is malformed or exceeds parser
                limits.
        """
        self._ensure_open()
        if self._cached_form is None:
            try:
                values = await self._backend.form(
                    max_files=self._max_form_files,
                    max_fields=self._max_form_fields,
                    max_part_size=self._max_part_size,
                )
            except RequestError:
                raise
            except Exception as error:
                raise RequestInputError(_INVALID_FORM_ERROR) from error
            self._cached_form = MappingProxyType(dict(values))
        return self._cached_form

    async def file(self, key: str) -> UploadedFile | None:
        """Return one uploaded file by form field name.

        Args:
            key: Multipart file field.

        Returns:
            The upload or ``None`` when the field is absent or not a file.
        """
        value = (await self.form()).get(key)
        return value if isinstance(value, UploadedFile) else None

    async def files(self, key: str) -> tuple[UploadedFile, ...]:
        """Return all uploaded files submitted under one field name.

        Args:
            key: Multipart file field.

        Returns:
            Uploads in the order submitted by the client.
        """
        return tuple(
            value
            for value in await self._backend.form_values(
                key,
                max_files=self._max_form_files,
                max_fields=self._max_form_fields,
                max_part_size=self._max_part_size,
            )
            if isinstance(value, UploadedFile)
        )

    async def stream(self) -> AsyncIterator[bytes]:
        """Stream the unbuffered body once with backpressure.

        Yields:
            Body chunks received from the ASGI server.

        Raises:
            RequestBodyConsumedError: If buffered or form access consumed the
                body first.
        """
        self._ensure_open()
        if self._cached_body is not None:
            yield self._cached_body
            return
        if self._stream_started or self._cached_form is not None:
            raise RequestBodyConsumedError(_BODY_ALREADY_CONSUMED_ERROR)
        self._stream_started = True
        async for chunk in self._backend.stream():
            yield chunk

    async def aclose(self) -> None:
        """Finalize form parser resources and reject later body operations.

        Metadata is synchronous; body reads remain explicit and asynchronous.
        """
        if self._closed:
            return
        self._closed = True
        await self._backend.aclose()

    async def _body_values(self) -> dict[str, object]:
        """Return parsed JSON or form values for input merging.

        Returns:
            A shallow dictionary for mapping-shaped request content.

        Raises:
            RequestInputError: If parsed JSON is not a mapping.
        """
        if self.content_type == "application/json" or (
            self.content_type is not None
            and self.content_type.endswith("+json")
        ):
            payload = await self.json()
            if isinstance(payload, dict):
                return dict(payload)
            if payload is None and not await self.body():
                return {}
            raise RequestInputError(_OBJECT_JSON_REQUIRED_ERROR)
        if self.content_type in {
            "application/x-www-form-urlencoded",
            "multipart/form-data",
        }:
            return dict(await self.form())
        return {}

    async def _input_value(self, key: str) -> object:
        """Find one value from body-over-query merged input.

        Args:
            key: Direct key or dotted path.

        Returns:
            The selected value or the private missing sentinel.
        """
        values: dict[str, object] = dict(self._backend.query_items)
        values.update(await self._body_values())
        return Arr.get(values, key, _MISSING)

    def _ensure_open(self) -> None:
        """Reject body access after the owning ASGI scope closes.

        Raises:
            RequestError: If request-owned parser resources were finalized.
        """
        if self._closed:
            raise RequestError(_REQUEST_LIFECYCLE_ENDED_ERROR)

    _backend: RequestBackend
    _request_id: str
    _max_form_files: int
    _max_form_fields: int
    _max_part_size: int
    _cached_body: bytes | None
    _cached_json: JsonValue | _Missing
    _cached_form: Mapping[str, object] | None
    _attributes: dict[str, object]
    _stream_started: bool
    _closed: bool


def _invalid_input_type(key: str, expected: str) -> RequestInputError:
    """Build a value-safe typed-input error for one request key.

    Args:
        key: Input path that failed type validation.
        expected: Public type description, without the supplied value.

    Returns:
        A native exception that does not include untrusted input content.
    """
    return RequestInputError(f"Request input [{key}] must be {expected}.")


__all__ = ["Request"]
