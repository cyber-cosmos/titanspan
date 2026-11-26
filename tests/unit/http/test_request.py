"""Verify native HTTP request metadata and payload semantics.

Local fixtures keep these assertions deterministic.
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field

import pytest

from titanspan.http.exceptions import (
    RequestBodyConsumedError,
    RequestError,
    RequestInputError,
)
from titanspan.http.request import Request
from titanspan.http.uploaded_file import UploadedFile

pytestmark = pytest.mark.unit
_EXPECTED_INTEGER = 7
_INTEGER_DEFAULT = 9
_EXPECTED_RATIO = 2.0
_REQUEST_URL = "https://example.test/documents?page=1"


@dataclass
class RequestBackendFake:
    """Provide deterministic incoming request data without an ASGI server.

    Local fixtures keep these assertions deterministic.
    """

    method: str = "GET"
    headers: tuple[tuple[str, str], ...] = ()
    query_items: tuple[tuple[str, str], ...] = ()
    body_content: bytes = b""
    form_data: Mapping[str, object] | None = None
    repeated_form_values: Mapping[str, Sequence[object]] | None = None
    chunks: tuple[bytes, ...] = ()
    client_address: tuple[str, int] | None = ("127.0.0.1", 43123)
    body_error: Exception | None = None
    form_error: Exception | None = None
    url: str = field(init=False, default=_REQUEST_URL)
    path: str = field(init=False, default="/documents")
    host: str = field(init=False, default="example.test")
    scheme: str = field(init=False, default="https")
    cookies: Mapping[str, str] = field(
        init=False,
        default_factory=lambda: {"session": "cookie-value"},
    )
    client: tuple[str, int] | None = field(init=False)
    _body_content: bytes = field(init=False)
    _form_values: dict[str, object] = field(init=False)
    _repeated_form_values: dict[str, Sequence[object]] = field(init=False)
    _chunks: tuple[bytes, ...] = field(init=False)
    _body_error: Exception | None = field(init=False)
    _form_error: Exception | None = field(init=False)
    body_reads: int = field(init=False, default=0)
    stream_reads: int = field(init=False, default=0)
    closed: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        """Snapshot configured request values for deterministic operations.

        Form mappings are copied so tests cannot mutate parsed values after
        fake construction. Other inputs are immutable or treated read-only.
        """
        self.client = self.client_address
        self._body_content = self.body_content
        self._form_values = dict(self.form_data or {})
        self._repeated_form_values = dict(self.repeated_form_values or {})
        self._chunks = self.chunks
        self._body_error = self.body_error
        self._form_error = self.form_error

    def header(self, name: str, default: str | None) -> str | None:
        """Return one header by case-insensitive name.

        Local fixtures keep these assertions deterministic.
        """
        for key, value in self.headers:
            if key.lower() == name.lower():
                return value
        return default

    async def body(self) -> bytes:
        """Return the configured buffered body and count reads.

        Local fixtures keep these assertions deterministic.
        """
        self.body_reads += 1
        if self._body_error is not None:
            raise self._body_error
        return self._body_content

    async def stream(self) -> AsyncIterator[bytes]:
        """Yield configured chunks in order and count stream starts.

        Local fixtures keep these assertions deterministic.
        """
        self.stream_reads += 1
        for chunk in self._chunks:
            yield chunk

    async def form(
        self,
        *,
        max_files: int,
        max_fields: int,
        max_part_size: int,
    ) -> Mapping[str, object]:
        """Return configured parsed form data.

        Local fixtures keep these assertions deterministic.
        """
        del max_files, max_fields, max_part_size
        if self._form_error is not None:
            raise self._form_error
        return self._form_values

    async def form_values(
        self,
        key: str,
        *,
        max_files: int,
        max_fields: int,
        max_part_size: int,
    ) -> Sequence[object]:
        """Return one configured form value as a repeated-value sequence.

        Local fixtures keep these assertions deterministic.
        """
        del max_files, max_fields, max_part_size
        if key in self._repeated_form_values:
            return self._repeated_form_values[key]
        value = self._form_values.get(key)
        return () if value is None else (value,)

    async def aclose(self) -> None:
        """Record request-owned resource finalization.

        Local fixtures keep these assertions deterministic.
        """
        self.closed = True


def _request(
    backend: RequestBackendFake,
    *,
    content_type: str | None = None,
) -> Request:
    """Create a request wrapper with representative multipart limits.

    Local fixtures keep these assertions deterministic.
    """
    headers = list(backend.headers)
    if content_type is not None:
        headers.append(("content-type", content_type))
        backend.headers = tuple(headers)
    return Request(
        backend,
        request_id="req-unit-test",
        max_form_files=4,
        max_form_fields=16,
        max_part_size=1024,
    )


class _RouteMetadataFake:
    """Expose only the route name required by the Routing boundary.

    Request metadata reads this value through the established attributes.
    """

    @property
    def route_name(self) -> str | None:
        """Return a deterministic route name for request assertions.

        The fake matches the structural metadata shape consumed by Request.
        """
        return "users.show"


def test_request_metadata_preserves_repeated_query_and_secure_headers() -> None:
    """Expose normalized metadata without consuming the body.

    The assertions verify the public result and its error paths.
    """
    backend = RequestBackendFake(
        method="post",
        headers=(
            ("Accept", "text/html, application/json;q=0.8"),
            ("Authorization", "Bearer token-value"),
        ),
        query_items=(("tag", "first"), ("tag", "second")),
    )
    request = _request(backend)

    assert request.method == "POST"
    assert request.url.startswith("https://example.test/")
    assert request.full_url == request.url
    assert request.path == "/documents"
    assert request.host == "example.test"
    assert request.is_secure()
    assert request.is_method("PoSt")
    assert request.query_values("tag") == ("first", "second")
    assert request.query("tag") == "second"
    assert request.bearer_token() == "token-value"
    assert request.expects_json()
    assert request.accepts("application/json")
    assert backend.body_reads == 0


def test_accept_negotiation_respects_quality_and_wildcards() -> None:
    """Honor wildcard media ranges and reject explicitly zero quality.

    The assertions verify the public result and its error paths.
    """
    request = _request(
        RequestBackendFake(
            headers=(
                (
                    "accept",
                    "application/json;q=0, text/*;q=0.5",
                ),
            )
        )
    )

    assert not request.accepts("application/json")
    assert request.accepts("text/plain")


def test_metadata_defaults_and_immutable_snapshots() -> None:
    """Handle absent headers and peer metadata without body access.

    The assertions verify the public result and its error paths.
    """
    backend = RequestBackendFake(
        method="get",
        headers=(("X-Requested-With", "XMLHttpRequest"),),
        query_items=(("page", "0"),),
        client_address=None,
    )
    request = _request(backend)

    assert request.request_id == "req-unit-test"
    assert request.method == "GET"
    assert request.scheme == "https"
    assert request.client is None
    assert request.content_type is None
    assert request.query("absent", 0) == 0
    assert request.cookie("absent", "fallback") == "fallback"
    assert request.accepts("application/json")
    assert request.expects_json()
    assert request.bearer_token() is None
    assert request.headers["x-requested-with"] == "XMLHttpRequest"
    assert request.cookies["session"] == "cookie-value"

    with pytest.raises(TypeError):
        request.headers["x-new"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        request.cookies["session"] = "changed"  # type: ignore[index]
    assert backend.body_reads == 0


@pytest.mark.parametrize(
    "authorization",
    ["Basic abc", "Bearer", "Bearer   ", "Bearer\ttoken"],
)
def test_malformed_bearer_values_are_not_returned(
    authorization: str,
) -> None:
    """Ignore authorization values that do not contain a bearer token.

    The assertions verify the public result and its error paths.
    """
    request = _request(
        RequestBackendFake(headers=(("authorization", authorization),))
    )

    assert request.bearer_token() is None


def test_invalid_accept_quality_is_treated_as_unacceptable() -> None:
    """Fail closed when an Accept range has malformed quality metadata.

    The assertions verify the public result and its error paths.
    """
    request = _request(
        RequestBackendFake(headers=(("accept", "application/json;q=bad"),))
    )

    assert not request.accepts("application/json")


@pytest.mark.parametrize(
    ("accept", "expects_json"),
    [
        ("*/*", False),
        ("application/json;q=0, */*;q=1", False),
        ("application/*;q=0.8", True),
        ("application/json;q=0.5, text/html;q=1", True),
        ("application/json;q=1.2", False),
    ],
)
def test_json_negotiation_obeys_specificity_and_quality(
    accept: str,
    expects_json: bool,
) -> None:
    """Honor the most specific Accept range and reject invalid weights.

    Explicit quality zero overrides less specific wildcards.
    """
    request = _request(RequestBackendFake(headers=(("accept", accept),)))

    assert request.expects_json() is expects_json


def test_json_and_ajax_detection_and_route_metadata_are_explicit() -> None:
    """Expose JSON, AJAX, correlation, and native route metadata.

    Routing values remain in the request's existing attribute boundary.
    """
    request = _request(
        RequestBackendFake(
            headers=(
                ("content-type", "application/problem+json"),
                ("x-requested-with", "XMLHttpRequest"),
                ("x-correlation-id", "trace-42"),
            ),
        )
    )
    request.set_attribute("titanspan.route", _RouteMetadataFake())
    request.set_attribute(
        "titanspan.route_parameters",
        {"user_id": 42},
    )

    assert request.is_json()
    assert request.is_ajax()
    assert request.expects_json()
    assert request.correlation_id == "trace-42"
    assert request.route_name == "users.show"
    assert request.route_parameters == {"user_id": 42}


def test_content_type_parameters_and_accept_parameters_are_parsed() -> None:
    """Ignore unrelated media parameters while matching accepted ranges.

    The assertions verify the public result and its error paths.
    """
    request = _request(
        RequestBackendFake(
            headers=(
                (
                    "accept",
                    "text/plain; charset=utf-8, application/json;q=0.5",
                ),
            )
        ),
        content_type="application/problem+json; charset=utf-8",
    )

    assert request.content_type == "application/problem+json"
    assert request.accepts("text/plain")
    assert request.accepts("application/json")
    assert not request.accepts("image/png")


def test_negotiation_and_route_accessors_reject_invalid_metadata() -> None:
    """Handle absent and malformed optional request metadata consistently.

    Invalid route values become native request errors without leaking Pydantic
    internals to the HTTP caller.
    """
    request = _request(
        RequestBackendFake(
            headers=(
                ("x-correlation-id", "bad\nvalue"),
                ("accept", "invalid-range, application/json;q=bad"),
            )
        )
    )
    request.set_attribute("titanspan.route_parameters", ["not", "a mapping"])

    assert request.correlation_id == "req-unit-test"
    assert not request.accepts("malformed")
    assert not request.expects_json()
    with pytest.raises(RequestError, match="route parameters"):
        _ = request.route_parameters

    no_accept = _request(RequestBackendFake())
    assert no_accept.accepts("text/plain")
    assert not no_accept.expects_json()


@pytest.mark.anyio
async def test_body_values_override_query_without_losing_false_or_none() -> (
    None
):
    """Keep falsey body data distinct from missing query and body fields.

    The assertions verify the public result and its error paths.
    """
    backend = RequestBackendFake(
        query_items=(("active", "query"), ("page", "3")),
        body_content=b'{"active":false,"count":0,"empty":null}',
    )
    request = _request(backend, content_type="application/json")

    assert await request.input("active") is False
    assert await request.input("count") == 0
    assert await request.has("empty")
    assert await request.input("empty", "fallback") is None
    assert await request.input("missing", "fallback") == "fallback"
    assert await request.input("page") == "3"
    assert await request.filled("active")
    assert await request.filled("count")
    assert not await request.filled("empty")
    assert backend.body_reads == 1


@pytest.mark.anyio
async def test_typed_accessors_validate_values_and_preserve_defaults() -> None:
    """Parse supported wire text while rejecting bool and shape confusion.

    The assertions verify the public result and its error paths.
    """
    backend = RequestBackendFake(
        query_items=(
            ("count", "-12"),
            ("price", "2.75"),
            ("active", "off"),
            ("labels", "wrong-shape"),
            ("flag", "yes"),
        )
    )
    request = _request(backend)

    assert await request.integer("count") == NEGATIVE_COUNT
    assert await request.float("price") == ITEM_PRICE
    assert await request.boolean("active") is False
    assert await request.boolean("flag") is True
    assert await request.string("absent", "fallback") == "fallback"
    assert await request.array("absent", []) == []

    with pytest.raises(RequestInputError, match="an integer"):
        await request.integer("flag")
    with pytest.raises(RequestInputError, match="a mapping or list"):
        await request.array("labels")


@pytest.mark.anyio
async def test_json_is_cached_and_malformed_body_does_not_leak_payload() -> (
    None
):
    """Cache decoded JSON and keep invalid request content out of errors.

    The assertions verify the public result and its error paths.
    """
    backend = RequestBackendFake(body_content=b'{"name":"safe"}')
    request = _request(backend, content_type="application/json")

    assert await request.json() == {"name": "safe"}
    assert await request.json() == {"name": "safe"}
    assert backend.body_reads == 1

    malformed = _request(
        RequestBackendFake(body_content=b"private-value"),
        content_type="application/json",
    )
    with pytest.raises(RequestInputError) as error:
        await malformed.json()
    assert "private-value" not in str(error.value)


@pytest.mark.anyio
async def test_stream_is_single_use_and_buffered_body_can_be_replayed() -> None:
    """Reject a second streaming read while preserving cached buffered reads.

    The assertions verify the public result and its error paths.
    """
    backend = RequestBackendFake(chunks=(b"one", b"two"))
    request = _request(backend)
    assert [chunk async for chunk in request.stream()] == [b"one", b"two"]
    with pytest.raises(RequestBodyConsumedError):
        _ = [chunk async for chunk in request.stream()]

    buffered_backend = RequestBackendFake(body_content=b"complete")
    buffered = _request(buffered_backend)
    assert await buffered.body() == b"complete"
    assert [chunk async for chunk in buffered.stream()] == [b"complete"]

    consumed = _request(RequestBackendFake(chunks=(b"first", b"second")))
    assert [chunk async for chunk in consumed.stream()] == [b"first", b"second"]
    with pytest.raises(RequestBodyConsumedError):
        await consumed.body()


@pytest.mark.anyio
async def test_close_finalizes_backend_and_rejects_body_access() -> None:
    """Finalize request resources once and reject post-scope body reads.

    The assertions verify the public result and its error paths.
    """
    backend = RequestBackendFake()
    request = _request(backend)

    await request.aclose()
    await request.aclose()

    assert backend.closed
    with pytest.raises(RequestError, match="lifecycle has already ended"):
        await request.body()


@pytest.mark.anyio
async def test_selection_merges_body_and_query_values_predictably() -> None:
    """Return selected and excluded input while preserving false values.

    The assertions verify the public result and its error paths.
    """
    backend = RequestBackendFake(
        query_items=(("page", "4"), ("name", "query")),
        body_content=b'{"name":"body","active":false,"password":"x"}',
    )
    request = _request(backend, content_type="application/json")

    assert await request.all() == {
        "page": "4",
        "name": "body",
        "active": False,
        "password": "x",
    }
    assert await request.only(["name", "active", "absent"]) == {
        "name": "body",
        "active": False,
    }
    assert await request.except_(["password", "absent"]) == {
        "page": "4",
        "name": "body",
        "active": False,
    }


@pytest.mark.anyio
async def test_body_and_form_errors_are_translated_without_losing_limits() -> (
    None
):
    """Translate parser failures and preserve native body-limit exceptions.

    The assertions verify the public result and its error paths.
    """
    body = _request(
        RequestBackendFake(body_error=RuntimeError("backend stream ended"))
    )
    with pytest.raises(RequestBodyConsumedError):
        await body.body()

    form = _request(
        RequestBackendFake(form_error=ValueError("malformed form")),
        content_type="application/x-www-form-urlencoded",
    )
    with pytest.raises(RequestInputError, match="form is invalid"):
        await form.form()

    native_error = RequestBodyConsumedError("body already consumed")
    native = _request(
        RequestBackendFake(form_error=native_error),
        content_type="application/x-www-form-urlencoded",
    )
    with pytest.raises(RequestBodyConsumedError) as captured:
        await native.form()
    assert captured.value is native_error


@pytest.mark.anyio
async def test_json_shape_empty_body_and_vendor_media_types() -> None:
    """Accept empty JSON null bodies but require objects for form inputs.

    The assertions verify the public result and its error paths.
    """
    empty = _request(
        RequestBackendFake(body_content=b""),
        content_type="application/json",
    )
    assert await empty.all() == {}

    array = _request(
        RequestBackendFake(body_content=b"[1,2]"),
        content_type="application/vnd.titanspan+json; version=1",
    )
    with pytest.raises(RequestInputError, match="Object-shaped JSON"):
        await array.input("value")

    text = _request(
        RequestBackendFake(body_content=b'{"hidden":true}'),
        content_type="text/plain",
    )
    assert await text.input("hidden", "missing") == "missing"


@pytest.mark.anyio
async def test_typed_input_rejects_null_and_non_finite_numbers() -> None:
    """Reject null and non-finite values instead of coercing them.

    The assertions verify the public result and its error paths.
    """
    request = _request(
        RequestBackendFake(
            body_content=b'{"null":null,"infinite":"Infinity",'
            b'"not_numeric":"many","boolean":true,'
            b'"invalid_bool":"maybe","mapping":{"1":"bad"}}'
        ),
        content_type="application/json",
    )

    with pytest.raises(RequestInputError, match="a string"):
        await request.string("null")
    with pytest.raises(RequestInputError, match="finite number"):
        await request.float("infinite")
    with pytest.raises(RequestInputError, match="finite number"):
        await request.float("boolean")
    with pytest.raises(RequestInputError, match="finite number"):
        await request.float("not_numeric")
    with pytest.raises(RequestInputError, match="boolean"):
        await request.boolean("invalid_bool")
    assert await request.array("mapping") == {"1": "bad"}


@pytest.mark.anyio
async def test_typed_accessors_cover_native_values_and_invalid_shapes() -> None:
    """Return valid scalar/container values and reject type mismatches.

    The assertions verify the public result and its error paths.
    """
    backend = RequestBackendFake(
        body_content=(
            b'{"text":"ready","number":7,"ratio":2,"enabled":true,'
            b'"items":[1,2],"blank":"","object":{}}'
        )
    )
    request = _request(backend, content_type="application/json")

    assert await request.string("text") == "ready"
    assert await request.integer("number") == _EXPECTED_INTEGER
    assert await request.integer("missing", _INTEGER_DEFAULT) == (
        _INTEGER_DEFAULT
    )
    assert await request.float("ratio") == _EXPECTED_RATIO
    assert await request.float("missing") is None
    assert await request.boolean("enabled") is True
    assert await request.boolean("missing", False) is False
    assert await request.array("items") == [1, 2]
    assert await request.array("object") == {}
    assert not await request.filled("blank")
    assert not await request.filled("missing")

    with pytest.raises(RequestInputError, match="a string"):
        await request.string("number")

    malformed_mapping = _request(
        RequestBackendFake(form_data={"mapping": {1: "invalid"}}),
        content_type="application/x-www-form-urlencoded",
    )
    with pytest.raises(RequestInputError, match="string-keyed mapping"):
        await malformed_mapping.array("mapping")


@pytest.mark.anyio
async def test_form_upload_access_and_body_consumption_rules() -> None:
    """Expose uploads through file APIs and reject streams after form parse.

    The assertions verify the public result and its error paths.
    """
    upload = UploadedFile(
        filename="report.txt",
        content_type="text/plain",
        size=4,
        read_bytes=_upload_bytes,
        close_file=_close_upload,
    )
    backend = RequestBackendFake(
        form_data={"upload": upload, "title": "report"},
        repeated_form_values={"upload": (upload, upload)},
    )
    request = _request(backend, content_type="multipart/form-data")

    assert await request.file("upload") is upload
    assert await request.file("title") is None
    assert await request.files("upload") == (upload, upload)
    assert await request.files("absent") == ()
    assert await request.input("title") == "report"
    with pytest.raises(RequestBodyConsumedError):
        _ = [chunk async for chunk in request.stream()]


NEGATIVE_COUNT = -12
ITEM_PRICE = 2.75


async def _upload_bytes(size: int) -> bytes:
    """Return a small deterministic payload for an upload wrapper.

    Local fixtures keep these assertions deterministic.
    """
    content = b"data"
    return content if size < 0 else content[:size]


async def _close_upload() -> None:
    """Provide an async finalizer for the request upload fixture.

    Local fixtures keep these assertions deterministic.
    """
