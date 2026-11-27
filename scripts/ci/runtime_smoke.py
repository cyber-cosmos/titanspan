"""Exercise installed Titanspan commands and routes through ASGI.

The script runs outside the source tree and uses declared runtime
dependencies. It invokes the installed artifact generator and ASGI lifespan.
"""

from __future__ import annotations

import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Protocol, cast

import anyio

from titanspan import Application

# Container evaluates these injected annotations during route dispatch.
from titanspan.contracts.config import ConfigRepository  # noqa: TC001
from titanspan.contracts.foundation import ServiceProvider
from titanspan.contracts.logging import LogWriter  # noqa: TC001
from titanspan.contracts.routing import ControllerAction, UriUrlGenerator
from titanspan.http import Request  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Sequence

    from starlette.types import ASGIApp, Message, Scope

    from titanspan.contracts.container import ServiceRegistry

_APPLICATION_NAME = "Installed Titanspan"
_DOCUMENT_CONTROLLER_NAME = "DocumentController"
_DOCUMENT_CONTROLLER_ACTION = "index"
_DOCUMENT_ROUTE_NAME = "documents.index"
_GENERATOR_TIMEOUT_SECONDS = 30
_GENERATED_CONTROLLER_MODULE = "_titanspan_installed_document_controller"
EXPECTED_RESPONSE = {
    "status": "ok",
    "greeting": f"Hello from {_APPLICATION_NAME}.",
}
EXPECTED_DOCUMENT_RESPONSE = {"resource": "Document"}
HTTP_OK_STATUS = 200
_REQUEST_ID_ERROR = "The request identifier was not registered."


class _GreetingService(Protocol):
    """Describe the application service used by the smoke endpoint.

    The provider binds this interface in Foundation's canonical Container.
    """

    def message(self) -> str:
        """Return the configured application greeting.

        Returns:
            One greeting generated from application configuration.
        """
        ...


class _ConfiguredGreeting:
    """Build a greeting through injected configuration and logging.

    The example resolves both services from the native application graph.
    """

    def __init__(
        self,
        configuration: ConfigRepository,
        logger: LogWriter,
    ) -> None:
        """Retain application-owned services for the smoke request.

        Args:
            configuration: Canonical application configuration repository.
            logger: Application logger resolved through its contract.
        """
        self._configuration = configuration
        self._logger = logger

    def message(self) -> str:
        """Create and log one configured greeting.

        Returns:
            A greeting containing the configured application name.

        Raises:
            TypeError: If the configured application name is not text.
        """
        application_name = self._configuration.get(
            "app.name",
            _APPLICATION_NAME,
        )
        if not isinstance(application_name, str):
            message = "The configured application name must be text."
            raise TypeError(message)
        self._logger.info(
            "Installed application smoke request handled",
            application=application_name,
        )
        return f"Hello from {application_name}."


class _RuntimeSmokeProvider(ServiceProvider):
    """Register the smoke service through the native provider contract.

    Foundation owns provider order and Container composition.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Bind the greeting implementation under its service contract.

        Args:
            container: Canonical service registry owned by Foundation.
        """
        container.singleton(_GreetingService, _ConfiguredGreeting)


async def run_smoke() -> dict[str, dict[str, str]]:
    """Generate, start, exercise, and shut down a reference application.

    Raises:
        RuntimeError: If the ASGI application does not return the expected
            status or response payload, or the installed CLI cannot generate
            an executable controller.

    Returns:
        Health and generated-controller responses from native route dispatch.
    """
    with TemporaryDirectory(prefix="titanspan-reference-") as directory:
        base_path = Path(directory)
        (base_path / "routes").mkdir()
        generated_path = await anyio.to_thread.run_sync(
            _generate_document_controller,
            base_path,
            abandon_on_cancel=False,
        )
        controller_action = _load_document_action(generated_path)
        application = _create_application(base_path, controller_action)
        health_url = application.make(UriUrlGenerator).route(
            "runtime.health",
            {},
            absolute=False,
        )
        document_url = application.make(UriUrlGenerator).route(
            _DOCUMENT_ROUTE_NAME,
            {},
            absolute=False,
        )
        if health_url != "/health" or document_url != "/documents":
            message = "The reference application's named routes are invalid."
            raise RuntimeError(message)

        async with application.asgi.router.lifespan_context(application.asgi):
            health = await _send_request(
                application.asgi,
                health_url,
                EXPECTED_RESPONSE,
            )
            documents = await _send_request(
                application.asgi,
                document_url,
                EXPECTED_DOCUMENT_RESPONSE,
            )

    return {"health": health, "documents": documents}


def _generate_document_controller(base_path: Path) -> Path:
    """Generate one controller through the installed Titanspan CLI.

    Args:
        base_path: Isolated application root used as the CLI working directory.

    Returns:
        The generated controller path inside ``base_path``.

    Raises:
        RuntimeError: If CLI execution or artifact creation fails.
    """
    # A fixed argv keeps this installed CLI check shell-free and trusted.
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
    # Dynamic module attributes are the only untyped boundary in this smoke.
    return cast("ControllerAction", (controller, _DOCUMENT_CONTROLLER_ACTION))


def _create_application(
    base_path: Path,
    document_action: ControllerAction,
) -> Application:
    """Compose the reference app through native Foundation and Routing.

    Args:
        base_path: Isolated project root shared with the CLI generator.
        document_action: Imported controller action generated by the CLI.

    Returns:
        An application with provider-backed and generated routes.
    """
    application = Application(
        base_path=base_path,
        config={
            "app": {
                "name": _APPLICATION_NAME,
                "debug": False,
            },
        },
        service_providers=(_RuntimeSmokeProvider(),),
    )

    async def health(
        greeting: _GreetingService,
        request: Request,
    ) -> dict[str, str]:
        """Return configured data through native dependency injection.

        Args:
            greeting: Application service selected by the native Container.
            request: Request scoped to this ASGI execution.

        Returns:
            A small response proving route and service integration.
        """
        if not request.request_id:
            raise RuntimeError(_REQUEST_ID_ERROR)
        return {"status": "ok", "greeting": greeting.message()}

    application.router.get("/health", health).name("runtime.health")
    application.router.get("/documents", document_action).name(
        _DOCUMENT_ROUTE_NAME,
    )
    return application


async def _send_request(
    application: ASGIApp,
    path: str,
    expected_response: dict[str, str],
) -> dict[str, str]:
    """Send and verify one request through the ASGI application.

    Args:
        application: Native host assembled by Foundation.
        path: Local path selected from the application's URL generator.
        expected_response: JSON object expected from the selected route.

    Returns:
        The verified JSON object from the ASGI response.

    Raises:
        RuntimeError: If ASGI emits a malformed response.
    """
    messages: list[Message] = []
    request_sent = False

    async def receive() -> Message:
        """Provide one empty HTTP request body to the ASGI application.

        Returns:
            The request event consumed by the route handler.
        """
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {
            "type": "http.request",
            "body": b"",
            "more_body": False,
        }

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
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 80),
    }

    await application(scope, receive, send)
    return _decode_response(messages, expected_response)


def _decode_response(
    messages: Sequence[Message],
    expected_response: dict[str, str],
) -> dict[str, str]:
    """Validate one ASGI response and return its JSON object.

    Args:
        messages: ASGI response events emitted by the native application.
        expected_response: JSON object expected from the selected route.

    Returns:
        Response object with string keys and values.

    Raises:
        RuntimeError: If the application emits an invalid HTTP response.
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
        reason = (
            "ASGI response did not contain one start and body event: "
            f"{observed}"
        )
        raise RuntimeError(reason)
    if start_events[0].get("status") != HTTP_OK_STATUS:
        reason = f"unexpected HTTP status: {start_events[0].get('status')}"
        raise RuntimeError(reason)
    body_chunks = [event.get("body", b"") for event in body_events]
    if not all(isinstance(chunk, bytes) for chunk in body_chunks):
        reason = "ASGI response body must be bytes"
        raise RuntimeError(reason)
    body = b"".join(chunk for chunk in body_chunks if isinstance(chunk, bytes))
    expected_body = json.dumps(
        expected_response,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if body != expected_body:
        reason = "ASGI response body did not match the health payload"
        raise RuntimeError(reason)
    return expected_response.copy()


def main() -> int:
    """Run the application smoke and report its process status.

    Let application failures propagate so the runtime verification job fails
    rather than recording a false success.
    """
    anyio.run(run_smoke)
    sys.stdout.write("Installed Titanspan application smoke passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
