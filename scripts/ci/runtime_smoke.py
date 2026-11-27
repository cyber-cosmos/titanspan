"""Exercise the installed Titanspan package through a reference application.

The script runs outside the repository import path. It invokes the installed
CLI generator and sends native ASGI requests through the installed wheel.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, TypedDict, cast

import anyio

from titanspan.console import Console
from titanspan.contracts.filesystem import StorageManager
from titanspan.contracts.routing import ControllerAction, UriUrlGenerator
from titanspan.facades import Event, Hash, Http, Log, Storage
from titanspan.testing import AsyncApplicationTest

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from starlette.types import ASGIApp, Message, Scope

    from titanspan import Application

_DOCUMENT_CONTROLLER_NAME = "DocumentController"
_DOCUMENT_CONTROLLER_ACTION = "index"
_GENERATOR_TIMEOUT_SECONDS = 30
_GENERATED_CONTROLLER_MODULE = "_titanspan_installed_document_controller"
_REFERENCE_APPLICATION_MODULE = "_titanspan_document_processor_example"
_REFERENCE_APPLICATION_PATH = (
    Path(__file__).resolve().parents[2] / "examples" / "document_processor.py"
)
_MULTIPART_BOUNDARY = "titanspan-installed-reference-boundary"
_INVALID_CATEGORY = "runtime-smoke-secret/../"
_UNSUPPORTED_JSON_CATEGORY = "private-report-token"
_DOCUMENT_CONTENT = b"native reference workflow"
_EXPECTED_STORED_CONTENT = b"native reference workflow\n"
_FAKE_DOCUMENT_PATH = "guides/fake-reference.txt"
_FAKE_DOCUMENT_CONTENT = b"isolated fake workflow\n"
_FAKE_HTTP_URL = "https://service.example.test/status"
_HASH_SAMPLE_TEXT = "local reference password sample"
_EXPECTED_HEALTH = {
    "status": "ok",
    "application": "Document Processor",
}
_EXPECTED_GENERATED_DOCUMENT = {"resource": "Document"}
_EXPECTED_JSON_METADATA = {"category": "guides"}
_EXPECTED_COOKIE_RESPONSE = {"status": "issued"}
_EXPECTED_COOKIE_COUNT = 2
_HEADER_PAIR_LENGTH = 2
_EXPECTED_UPLOADED_DOCUMENT = {
    "path": "guides/reference.txt",
    "bytes": len(_EXPECTED_STORED_CONTENT),
    "event_count": 1,
}
_HTTP_OK_STATUS = 200
_HTTP_UNPROCESSABLE_STATUS = 422


class _ValidationRejection(TypedDict):
    """Describe one safe validation error observed by the smoke.

    Attributes:
        status: HTTP response status for invalid metadata.
        body: Safe framework validation response.
    """

    status: int
    body: object


class _SmokeResult(TypedDict):
    """Describe the observable results from the reference application.

    Attributes:
        health: Readiness endpoint payload.
        documents: Generated controller endpoint payload.
        uploaded_document: Successful document workflow receipt.
        invalid_upload: Status and payload for rejected input.
        json_metadata: Validated typed JSON metadata response.
        json_validation_safe: Whether invalid JSON receives a safe 422.
        response_cookie_verified: Whether native cookies retain attributes.
        middleware_verified: Whether global and route middleware ran.
        component_fakes: Results from application-scoped fake services.
        password_hash_verified: Whether native hashing verifies its result.
        console_document_count: Count returned through an injected command.
        testing_context_verified: Whether native app testing served a route.
    """

    health: object
    documents: object
    uploaded_document: object
    invalid_upload: _ValidationRejection
    json_metadata: object
    json_validation_safe: bool
    response_cookie_verified: bool
    middleware_verified: bool
    component_fakes: _ComponentFakeResults
    password_hash_verified: bool
    console_document_count: int
    testing_context_verified: bool


class _ComponentFakeResults(TypedDict):
    """Summarize fake-backed application service observations.

    Attributes:
        storage_isolated: Whether the fake write stayed out of local storage.
        event_count: Number of document events captured by the event fake.
        log_captured: Whether the active fake logger captured the request.
        http_status: Status returned by the fake outgoing HTTP transport.
    """

    storage_isolated: bool
    event_count: int
    log_captured: bool
    http_status: int


@dataclass(frozen=True, slots=True)
class _AsgiResponse:
    """Retain one JSON response emitted by the reference application.

    Attributes:
        status: HTTP status code from the ASGI response start event.
        body: Decoded JSON response value.
        raw_body: Response bytes used for safe-data assertions.
        headers: All response headers, preserving repeated values.
    """

    status: int
    body: object
    raw_body: bytes
    headers: tuple[tuple[bytes, bytes], ...]


class _SmokeRoutes(TypedDict):
    """Store named paths resolved from the reference route catalog.

    Attributes:
        health: Health endpoint path.
        generated: Path for the generated controller action.
        upload: Multipart upload path.
        metadata: Typed JSON metadata path.
        cookie: Response-cookie path.
    """

    health: str
    generated: str
    upload: str
    metadata: str
    cookie: str


class _PrimaryHttpResults(TypedDict):
    """Retain core application request results from real ASGI calls.

    Attributes:
        health: Health endpoint response.
        generated: Generated controller response.
        upload: Successful multipart workflow response.
        invalid_upload: Safe rejection for invalid multipart input.
        middleware_verified: Whether global and upload middleware ran.
    """

    health: _AsgiResponse
    generated: _AsgiResponse
    upload: _AsgiResponse
    invalid_upload: _AsgiResponse
    middleware_verified: bool


class _NativeHttpResults(TypedDict):
    """Retain JSON, cookie, and middleware integration observations.

    Attributes:
        json_metadata: Typed JSON metadata response body.
        json_validation_safe: Whether JSON rejection omits user input.
        response_cookie_verified: Whether cookie headers preserve attributes.
        middleware_verified: Whether metadata route middleware ran.
    """

    json_metadata: object
    json_validation_safe: bool
    response_cookie_verified: bool
    middleware_verified: bool


async def run_smoke() -> _SmokeResult:
    """Run CLI generation and a local document workflow through ASGI.

    Raises:
        RuntimeError: If route reversal, response behavior, validation
            safety, or storage verification fails.
        TypeError: If dynamic CLI registration or ASGI output is malformed.

    Returns:
        Application, fake-service, hashing, and rejection results.
    """
    with TemporaryDirectory(prefix="titanspan-reference-") as directory:
        base_path = Path(directory)
        (base_path / "routes").mkdir()
        generated_path = await anyio.to_thread.run_sync(
            _generate_document_controller,
            base_path,
            abandon_on_cancel=False,
        )
        application = _load_reference_application(base_path)
        application.router.get(
            "/generated-documents",
            _load_document_action(generated_path),
        ).name("generated.documents.index")

        routes = _resolve_smoke_routes(application)

        async with application.asgi.router.lifespan_context(application.asgi):
            primary_http = await _exercise_primary_http(application, routes)
            native_http = await _exercise_native_http(application, routes)

            fake_results = await _exercise_application_fakes(
                application,
                routes["upload"],
            )
            password_hash_verified = await _verify_application_hasher(
                application,
            )
            console_document_count = await _run_document_count_command(
                application,
            )
            testing_context_verified = await _verify_application_testing()

    return {
        "health": primary_http["health"].body,
        "documents": primary_http["generated"].body,
        "uploaded_document": primary_http["upload"].body,
        "invalid_upload": {
            "status": primary_http["invalid_upload"].status,
            "body": primary_http["invalid_upload"].body,
        },
        "json_metadata": native_http["json_metadata"],
        "json_validation_safe": native_http["json_validation_safe"],
        "response_cookie_verified": native_http["response_cookie_verified"],
        "middleware_verified": (
            primary_http["middleware_verified"]
            and native_http["middleware_verified"]
        ),
        "component_fakes": fake_results,
        "password_hash_verified": password_hash_verified,
        "console_document_count": console_document_count,
        "testing_context_verified": testing_context_verified,
    }


def _resolve_smoke_routes(application: Application) -> _SmokeRoutes:
    """Resolve the reference routes through the canonical URI contract.

    Args:
        application: Reference application with its routes registered.

    Returns:
        Relative paths from the application's authoritative route catalog.

    Raises:
        RuntimeError: If a named route produces an unexpected path.
    """
    generator = application.make(UriUrlGenerator)
    routes: _SmokeRoutes = {
        "health": generator.route("runtime.health", {}, absolute=False),
        "generated": generator.route(
            "generated.documents.index",
            {},
            absolute=False,
        ),
        "upload": generator.route("documents.store", {}, absolute=False),
        "metadata": generator.route(
            "documents.metadata",
            {},
            absolute=False,
        ),
        "cookie": generator.route(
            "documents.session-cookie",
            {},
            absolute=False,
        ),
    }
    expected = {
        "health": "/health",
        "generated": "/generated-documents",
        "upload": "/documents",
        "metadata": "/documents/metadata",
        "cookie": "/documents/session-cookie",
    }
    if routes != expected:
        message = "The reference application's named routes are invalid."
        raise RuntimeError(message)
    return routes


async def _exercise_primary_http(
    application: Application,
    routes: _SmokeRoutes,
) -> _PrimaryHttpResults:
    """Exercise health, generated, and multipart routes through ASGI.

    Args:
        application: Started application using production HTTP services.
        routes: Named paths from the canonical route catalog.

    Returns:
        Core successful and rejected request responses.

    Raises:
        RuntimeError: If routing, middleware, validation, or storage fails.
    """
    health = await _send_request(application.asgi, routes["health"])
    _expect_response(
        health,
        status=_HTTP_OK_STATUS,
        body=_EXPECTED_HEALTH,
    )
    request_ids = _header_values(health, "x-request-id")
    if len(request_ids) != 1 or not request_ids[0]:
        message = "Global middleware omitted the request identifier."
        raise RuntimeError(message)

    generated = await _send_request(application.asgi, routes["generated"])
    _expect_response(
        generated,
        status=_HTTP_OK_STATUS,
        body=_EXPECTED_GENERATED_DOCUMENT,
    )

    upload_body = _multipart_body(
        category="guides",
        filename="../../reference.txt",
        content=_DOCUMENT_CONTENT,
    )
    upload = await _send_request(
        application.asgi,
        routes["upload"],
        method="POST",
        headers=_multipart_headers(upload_body),
        body=upload_body,
    )
    _expect_response(
        upload,
        status=_HTTP_OK_STATUS,
        body=_EXPECTED_UPLOADED_DOCUMENT,
    )
    _expect_header(upload, "x-operation", "document-upload")

    invalid_upload_body = _multipart_body(
        category=_INVALID_CATEGORY,
        filename="rejected.txt",
        content=b"must not be stored",
    )
    invalid_upload = await _send_request(
        application.asgi,
        routes["upload"],
        method="POST",
        headers=_multipart_headers(invalid_upload_body),
        body=invalid_upload_body,
    )
    _expect_validation_rejection(invalid_upload)

    disk = application.make(StorageManager).disk()
    stored_content = await disk.get_bytes_async("guides/reference.txt")
    if stored_content != _EXPECTED_STORED_CONTENT:
        message = "The document was not stored with processed bytes."
        raise RuntimeError(message)
    if await disk.exists_async("guides/rejected.txt"):
        message = "Invalid document input reached application storage."
        raise RuntimeError(message)

    return {
        "health": health,
        "generated": generated,
        "upload": upload,
        "invalid_upload": invalid_upload,
        "middleware_verified": True,
    }


async def _exercise_native_http(
    application: Application,
    routes: _SmokeRoutes,
) -> _NativeHttpResults:
    """Exercise typed JSON, safe failures, and native response cookies.

    Args:
        application: Started application using production HTTP services.
        routes: Named paths from the canonical route catalog.

    Returns:
        Typed JSON and cookie integration observations.

    Raises:
        RuntimeError: If validation, middleware, or cookie behavior differs.
    """
    metadata_body = json.dumps({"category": "guides"}).encode("utf-8")
    metadata = await _send_request(
        application.asgi,
        routes["metadata"],
        method="POST",
        headers=_json_headers(metadata_body),
        body=metadata_body,
    )
    _expect_response(
        metadata,
        status=_HTTP_OK_STATUS,
        body=_EXPECTED_JSON_METADATA,
    )
    _expect_header(metadata, "x-operation", "metadata-json")

    invalid_body = json.dumps(
        {"category": _UNSUPPORTED_JSON_CATEGORY},
    ).encode("utf-8")
    invalid = await _send_request(
        application.asgi,
        routes["metadata"],
        method="POST",
        headers=_json_headers(invalid_body),
        body=invalid_body,
    )
    json_validation_safe = (
        invalid.status == _HTTP_UNPROCESSABLE_STATUS
        and _UNSUPPORTED_JSON_CATEGORY.encode("utf-8") not in invalid.raw_body
    )
    if not json_validation_safe:
        message = "JSON validation exposed rejected input."
        raise RuntimeError(message)

    cookie_response = await _send_request(
        application.asgi,
        routes["cookie"],
    )
    _expect_response(
        cookie_response,
        status=_HTTP_OK_STATUS,
        body=_EXPECTED_COOKIE_RESPONSE,
    )
    cookie_values = _header_values(cookie_response, "set-cookie")
    response_cookie_verified = _secure_cookies_are_preserved(cookie_values)
    if not response_cookie_verified:
        message = "Native response cookies lost values or attributes."
        raise RuntimeError(message)

    return {
        "json_metadata": metadata.body,
        "json_validation_safe": json_validation_safe,
        "response_cookie_verified": response_cookie_verified,
        "middleware_verified": True,
    }


def _secure_cookies_are_preserved(values: Sequence[str]) -> bool:
    """Check duplicate cookie values and default security attributes.

    Args:
        values: Set-Cookie field values from the ASGI response.

    Returns:
        Whether both distinct cookies preserve secure defaults.
    """
    return (
        len(values) == _EXPECTED_COOKIE_COUNT
        and all("secure" in value.lower() for value in values)
        and all("httponly" in value.lower() for value in values)
        and any("document_session=opaque" in value for value in values)
        and any("document_preference=compact" in value for value in values)
    )


async def _exercise_application_fakes(
    application: Application,
    upload_url: str,
) -> _ComponentFakeResults:
    """Substitute application services around real endpoint execution.

    Args:
        application: Started document application using installed services.
        upload_url: Relative URL generated from the application's route table.

    Returns:
        Results that prove fakes intercepted the normal service paths.

    Raises:
        RuntimeError: If a fake leaks into production storage or requests.
    """
    with (
        application.context(),
        Storage.fake() as storage_fake,
        Event.fake() as event_fake,
        Log.fake() as log_fake,
    ):
        fake_body = _multipart_body(
            category="guides",
            filename="fake-reference.txt",
            content=b"isolated fake workflow",
        )
        fake_upload = await _send_request(
            application.asgi,
            upload_url,
            method="POST",
            headers=_multipart_headers(fake_body),
            body=fake_body,
        )
        _expect_response(
            fake_upload,
            status=_HTTP_OK_STATUS,
            body={
                "path": _FAKE_DOCUMENT_PATH,
                "bytes": len(_FAKE_DOCUMENT_CONTENT),
                "event_count": 1,
            },
        )
        storage_fake.assert_stored(
            _FAKE_DOCUMENT_PATH,
            _FAKE_DOCUMENT_CONTENT,
        )
        event_fake.assert_dispatched(object, times=1)
        event_count = len(event_fake.dispatched())
        log_record = log_fake.assert_logged(
            message="Document stored",
            context={"path": _FAKE_DOCUMENT_PATH},
        )
        log_captured = log_record.message == "Document stored"

    production_disk = application.make(StorageManager).disk()
    storage_isolated = not await production_disk.exists_async(
        _FAKE_DOCUMENT_PATH,
    )
    if not storage_isolated:
        message = "The storage fake wrote to the local disk."
        raise RuntimeError(message)

    with application.context():
        async with Http.fake(
            {
                _FAKE_HTTP_URL: Http.fake_response(
                    {"status": "available"},
                ),
            },
        ) as http_fake:
            http_response = await Http.get_async(_FAKE_HTTP_URL)
            http_status = http_response.status_code
            if not http_response.successful():
                message = "The application HTTP fake returned an error."
                raise RuntimeError(message)
            http_fake.assert_sent(
                Http.request_pattern(
                    url=_FAKE_HTTP_URL,
                    method="GET",
                ),
            )

    return {
        "storage_isolated": storage_isolated,
        "event_count": event_count,
        "log_captured": log_captured,
        "http_status": http_status,
    }


async def _verify_application_hasher(application: Application) -> bool:
    """Verify generated password data through the application Hasher.

    Args:
        application: Started application with its default hashing provider.

    Returns:
        Whether the hasher accepts the exact text used to create the hash.
    """
    with application.context():
        password_hash = await Hash.make_async(_HASH_SAMPLE_TEXT)
        return await Hash.check_async(_HASH_SAMPLE_TEXT, password_hash)


async def _run_document_count_command(
    application: Application,
) -> int:
    """Run the example command with the active application's audit service.

    Args:
        application: Started application containing document audit records.

    Returns:
        Count read by the Console handler through native injection.

    Raises:
        RuntimeError: If command execution fails.
        TypeError: If the example does not expose its command registration.
    """
    module = sys.modules.get(_REFERENCE_APPLICATION_MODULE)
    register = (
        None
        if module is None
        else getattr(
            module,
            "register_console_commands",
            None,
        )
    )
    if not callable(register):
        message = "The reference application has no Console registration."
        raise TypeError(message)

    console = Console()
    register_console = cast(
        "Callable[[Console], None]",
        register,
    )
    register_console(console)
    with application.context(), Log.fake() as log_fake:
        status = await console.execute_async("documents count")
        log_fake.assert_logged_times(
            1,
            level="info",
            message="Document count inspected",
            context={"document_count": 1},
        )
        record = log_fake.assert_logged(
            level="info",
            message="Document count inspected",
            context={"document_count": 1},
        )
    if status != 0:
        message = "The injected document count command did not complete."
        raise RuntimeError(message)
    document_count = record.context["document_count"]
    if isinstance(document_count, bool) or not isinstance(document_count, int):
        message = "The injected command did not log an integer document count."
        raise TypeError(message)
    return document_count


async def _verify_application_testing() -> bool:
    """Exercise the public async testing context and production ASGI route.

    Returns:
        Whether the test context served the route with an injected service.

    Raises:
        RuntimeError: If application startup, injection, or request fails.
    """
    testing = AsyncApplicationTest()
    testing.application.router.get("/test-probe", _test_probe)
    async with testing as active:
        response = await active.client.get("/test-probe")
        if response.status_code != _HTTP_OK_STATUS:
            message = "The native application test route failed."
            raise RuntimeError(message)
        if response.json() != {"status": "ready"}:
            message = "The native test route returned an unexpected payload."
            raise RuntimeError(message)
    return True


class _RuntimeProbe:
    """Provide a zero-argument service for native test-client injection.

    Attributes:
        status: Safe test value returned through the actual application.
    """

    def __init__(self) -> None:
        """Create a deterministic value for the installed test context.

        The value makes dependency resolution observable in the test route.
        """
        self.status = "ready"

    status: str


async def _test_probe(probe: _RuntimeProbe) -> dict[str, str]:
    """Return a value from a Container-injected test service.

    Args:
        probe: Application service resolved for the test request.

    Returns:
        Small response proving native injection and ASGI execution.
    """
    return {"status": probe.status}


def _generate_document_controller(base_path: Path) -> Path:
    """Generate one controller through the installed Titanspan CLI.

    Args:
        base_path: Isolated application root used as the CLI working directory.

    Returns:
        The generated controller path inside ``base_path``.

    Raises:
        RuntimeError: If CLI execution or artifact creation fails.
    """
    # Fixed argv keeps this installed CLI check shell-free and trusted.
    result = run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "titanspan",
            "make:controller",
            "documents.DocumentController",
        ],
        cwd=base_path,
        capture_output=True,
        text=True,
        timeout=_GENERATOR_TIMEOUT_SECONDS,
        check=False,
    )
    generated_path = (
        base_path
        / "app"
        / "controllers"
        / "documents"
        / "document_controller.py"
    )
    if result.returncode != 0 or not generated_path.is_file():
        message = (
            "The installed Titanspan controller generator failed "
            f"(status {result.returncode})."
        )
        raise RuntimeError(message)
    return generated_path


def _load_document_action(generated_path: Path) -> ControllerAction:
    """Import one generated controller and select its native action.

    Args:
        generated_path: Controller file created by the installed CLI.

    Returns:
        A controller action for registration with the native Router.

    Raises:
        RuntimeError: If generated source cannot provide the expected class.
    """
    spec = spec_from_file_location(
        _GENERATED_CONTROLLER_MODULE,
        generated_path,
    )
    if spec is None or spec.loader is None:
        message = "The generated controller could not be imported."
        raise RuntimeError(message)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    controller = getattr(module, _DOCUMENT_CONTROLLER_NAME, None)
    if not isinstance(controller, type):
        message = "The generated controller class is missing."
        raise TypeError(message)
    # This narrow cast marks the generated module as the dynamic boundary.
    return cast("ControllerAction", (controller, _DOCUMENT_CONTROLLER_ACTION))


def _load_reference_application(base_path: Path) -> Application:
    """Import the example and create an application at the selected root.

    Args:
        base_path: Isolated project root shared with the installed CLI.

    Returns:
        The example's native Foundation application.

    Raises:
        RuntimeError: If the example does not expose its factory.
    """
    spec = spec_from_file_location(
        _REFERENCE_APPLICATION_MODULE,
        _REFERENCE_APPLICATION_PATH,
    )
    if spec is None or spec.loader is None:
        message = "The document processor example could not be imported."
        raise RuntimeError(message)
    module = module_from_spec(spec)
    sys.modules[_REFERENCE_APPLICATION_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[_REFERENCE_APPLICATION_MODULE]
        raise
    factory = getattr(module, "create_application", None)
    if not callable(factory):
        message = "The document processor example has no application factory."
        raise TypeError(message)
    typed_factory = cast("Callable[[Path], Application]", factory)
    return typed_factory(base_path)


def _multipart_headers(body: bytes) -> tuple[tuple[bytes, bytes], ...]:
    """Return headers for the fixed local multipart request boundary.

    Args:
        body: Complete multipart payload sent by the smoke client.

    Returns:
        Content type and byte length headers for the selected boundary.
    """
    return (
        (
            b"content-type",
            f"multipart/form-data; boundary={_MULTIPART_BOUNDARY}".encode(),
        ),
        (b"content-length", str(len(body)).encode()),
    )


def _json_headers(body: bytes) -> tuple[tuple[bytes, bytes], ...]:
    """Return content type and length for one local JSON request.

    Args:
        body: Complete JSON request body sent to the local ASGI application.

    Returns:
        Headers declaring the JSON media type and exact body length.
    """
    return (
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
    )


def _multipart_body(
    *,
    category: str,
    filename: str,
    content: bytes,
) -> bytes:
    """Encode one fixed multipart upload without an external client.

    Args:
        category: Form value validated by the native Validation service.
        filename: Client filename used to verify path sanitization.
        content: Upload content passed through the real ASGI parser.

    Returns:
        One complete multipart request body.
    """
    boundary = _MULTIPART_BOUNDARY.encode()
    return b"".join(
        (
            b"--",
            boundary,
            b'\r\nContent-Disposition: form-data; name="category"\r\n\r\n',
            category.encode(),
            b"\r\n--",
            boundary,
            b'\r\nContent-Disposition: form-data; name="document"; filename="',
            filename.encode(),
            b'"\r\nContent-Type: text/plain\r\n\r\n',
            content,
            b"\r\n--",
            boundary,
            b"--\r\n",
        ),
    )


async def _send_request(
    application: ASGIApp,
    path: str,
    *,
    method: str = "GET",
    headers: Sequence[tuple[bytes, bytes]] = (),
    body: bytes = b"",
) -> _AsgiResponse:
    """Send one request through the real ASGI host and capture its response.

    Args:
        application: Native host assembled by Foundation.
        path: Local path selected from the application's URL generator.
        method: HTTP method used for this request.
        headers: Request headers in ASGI byte form.
        body: Complete request body for bounded local smoke payloads.

    Returns:
        Status and decoded JSON body emitted by the ASGI application.

    Raises:
        RuntimeError: If ASGI emits a malformed or non-JSON response.
    """
    messages: list[Message] = []
    request_sent = False

    async def receive() -> Message:
        """Provide the request body once, then report disconnection.

        Returns:
            One ASGI request or disconnect message.
        """
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        """Capture response events for deterministic smoke assertions.

        Args:
            message: Response start or body event emitted by ASGI.
        """
        messages.append(message)

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "headers": list(headers),
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 80),
    }
    await application(scope, receive, send)
    return _decode_response(messages)


def _decode_response(messages: Sequence[Message]) -> _AsgiResponse:
    """Decode the captured ASGI message sequence as a JSON response.

    Args:
        messages: Response events emitted by the native application.

    Returns:
        One status and JSON body from the completed response.

    Raises:
        RuntimeError: If ASGI emits an invalid HTTP response.
        TypeError: If ASGI response fields have invalid types.
    """
    start_events = [
        message
        for message in messages
        if message.get("type") == "http.response.start"
    ]
    body_events = [
        message
        for message in messages
        if message.get("type") == "http.response.body"
    ]
    if len(start_events) != 1 or not body_events:
        observed = [message.get("type") for message in messages]
        reason = f"Malformed ASGI response events: {observed}"
        raise RuntimeError(reason)
    status = start_events[0].get("status")
    if not isinstance(status, int):
        message = "ASGI response start has an invalid status."
        raise TypeError(message)
    chunks = [event.get("body", b"") for event in body_events]
    if not all(isinstance(chunk, bytes) for chunk in chunks):
        message = "ASGI response body chunks must be bytes."
        raise RuntimeError(message)
    raw_body = b"".join(chunk for chunk in chunks if isinstance(chunk, bytes))
    header_value = start_events[0].get("headers", [])
    if not isinstance(header_value, list):
        message = "ASGI response start has invalid headers."
        raise TypeError(message)
    headers: list[tuple[bytes, bytes]] = []
    for header in cast("list[object]", header_value):
        if not isinstance(header, tuple):
            message = "ASGI response header entries must be tuples."
            raise TypeError(message)
        header_pair = cast("tuple[object, ...]", header)
        if (
            len(header_pair) != _HEADER_PAIR_LENGTH
            or not isinstance(header_pair[0], bytes)
            or not isinstance(header_pair[1], bytes)
        ):
            message = "ASGI response header entries must contain bytes."
            raise TypeError(message)
        headers.append((header_pair[0], header_pair[1]))
    try:
        body = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        message = "ASGI response body is not valid JSON."
        raise RuntimeError(message) from error
    return _AsgiResponse(status, body, raw_body, tuple(headers))


def _header_values(response: _AsgiResponse, name: str) -> tuple[str, ...]:
    """Return every response value for one case-insensitive header name.

    Args:
        response: ASGI response captured by the reference smoke.
        name: Header name to select.

    Returns:
        Decoded values in the order emitted by the ASGI application.
    """
    encoded_name = name.encode("ascii").lower()
    return tuple(
        value.decode("latin-1")
        for header_name, value in response.headers
        if header_name.lower() == encoded_name
    )


def _expect_header(
    response: _AsgiResponse,
    name: str,
    expected: str,
) -> None:
    """Require one exact value for a response header.

    Args:
        response: ASGI response captured by the reference smoke.
        name: Header name to select.
        expected: Exact value required by the smoke.

    Raises:
        RuntimeError: If the selected header differs from its expectation.
    """
    if _header_values(response, name) != (expected,):
        message = f"The reference response omitted the {name} header."
        raise RuntimeError(message)


def _expect_response(
    response: _AsgiResponse,
    *,
    status: int,
    body: object,
) -> None:
    """Fail the installed-package smoke when a response differs.

    Args:
        response: Actual response emitted by the reference application.
        status: Expected HTTP status code.
        body: Expected decoded JSON body.

    Raises:
        RuntimeError: If the status or body does not match.
    """
    if response.status != status or response.body != body:
        message = (
            "The reference application returned an unexpected response "
            f"(status {response.status})."
        )
        raise RuntimeError(message)


def _expect_validation_rejection(response: _AsgiResponse) -> None:
    """Verify safe validation output for a rejected secret-shaped value.

    Args:
        response: Response emitted for invalid multipart metadata.

    Raises:
        RuntimeError: If invalid input is accepted or echoed to the client.
    """
    if response.status != _HTTP_UNPROCESSABLE_STATUS:
        message = "Invalid document metadata did not return HTTP 422."
        raise RuntimeError(message)
    if _INVALID_CATEGORY.encode() in response.raw_body:
        message = "The validation response exposed submitted field content."
        raise RuntimeError(message)


def main() -> int:
    """Run the installed-package smoke and report its process status.

    Returns:
        Zero after the real application and installed CLI pass.
    """
    anyio.run(run_smoke)
    sys.stdout.write("Installed Titanspan reference application passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
