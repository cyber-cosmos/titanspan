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

from titanspan.contracts.filesystem import StorageManager
from titanspan.contracts.routing import ControllerAction, UriUrlGenerator
from titanspan.facades import Event, Hash, Http, Log, Storage

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
        component_fakes: Results from application-scoped fake services.
        password_hash_verified: Whether native hashing verifies its result.
    """

    health: object
    documents: object
    uploaded_document: object
    invalid_upload: _ValidationRejection
    component_fakes: _ComponentFakeResults
    password_hash_verified: bool


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
    """

    status: int
    body: object
    raw_body: bytes


async def run_smoke() -> _SmokeResult:
    """Run CLI generation and a local document workflow through ASGI.

    Raises:
        RuntimeError: If installed command generation, route reversal,
            response behavior, validation safety, or storage verification
            fails.

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

        health_url = application.make(UriUrlGenerator).route(
            "runtime.health",
            {},
            absolute=False,
        )
        generated_url = application.make(UriUrlGenerator).route(
            "generated.documents.index",
            {},
            absolute=False,
        )
        upload_url = application.make(UriUrlGenerator).route(
            "documents.store",
            {},
            absolute=False,
        )
        if (
            health_url != "/health"
            or generated_url != "/generated-documents"
            or upload_url != "/documents"
        ):
            message = "The reference application's named routes are invalid."
            raise RuntimeError(message)

        async with application.asgi.router.lifespan_context(application.asgi):
            health = await _send_request(application.asgi, health_url)
            _expect_response(
                health,
                status=_HTTP_OK_STATUS,
                body=_EXPECTED_HEALTH,
            )
            generated = await _send_request(application.asgi, generated_url)
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
                upload_url,
                method="POST",
                headers=_multipart_headers(upload_body),
                body=upload_body,
            )
            _expect_response(
                upload,
                status=_HTTP_OK_STATUS,
                body=_EXPECTED_UPLOADED_DOCUMENT,
            )
            invalid_upload_body = _multipart_body(
                category=_INVALID_CATEGORY,
                filename="rejected.txt",
                content=b"must not be stored",
            )
            invalid_upload = await _send_request(
                application.asgi,
                upload_url,
                method="POST",
                headers=_multipart_headers(invalid_upload_body),
                body=invalid_upload_body,
            )
            _expect_validation_rejection(invalid_upload)

            disk = application.make(StorageManager).disk()
            stored_content = await disk.get_bytes_async(
                "guides/reference.txt",
            )
            if stored_content != _EXPECTED_STORED_CONTENT:
                message = "The document was not stored with processed bytes."
                raise RuntimeError(message)
            if await disk.exists_async("guides/rejected.txt"):
                message = "Invalid document input reached application storage."
                raise RuntimeError(message)

            fake_results = await _exercise_application_fakes(
                application,
                upload_url,
            )
            password_hash_verified = await _verify_application_hasher(
                application,
            )

    return {
        "health": health.body,
        "documents": generated.body,
        "uploaded_document": upload.body,
        "invalid_upload": {
            "status": invalid_upload.status,
            "body": invalid_upload.body,
        },
        "component_fakes": fake_results,
        "password_hash_verified": password_hash_verified,
    }


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
    try:
        body = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        message = "ASGI response body is not valid JSON."
        raise RuntimeError(message) from error
    return _AsgiResponse(status, body, raw_body)


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
