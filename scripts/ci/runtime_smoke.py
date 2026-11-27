"""Exercise an installed Titanspan application through an ASGI request.

The script runs from outside the source tree and uses only the package's
declared runtime dependencies. It invokes the ASGI lifespan and one real
in-process HTTP scope without test-only client packages.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Protocol

import anyio

from titanspan import Application

# Container evaluates these injected annotations during route dispatch.
from titanspan.contracts.config import ConfigRepository  # noqa: TC001
from titanspan.contracts.foundation import ServiceProvider
from titanspan.contracts.logging import LogWriter  # noqa: TC001
from titanspan.contracts.routing import UriUrlGenerator
from titanspan.http import Request  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Sequence

    from starlette.types import ASGIApp, Message, Scope

    from titanspan.contracts.container import ServiceRegistry

_APPLICATION_NAME = "Installed Titanspan"
EXPECTED_RESPONSE = {
    "status": "ok",
    "greeting": f"Hello from {_APPLICATION_NAME}.",
}
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


async def run_smoke() -> dict[str, str]:
    """Start, request, and shut down a minimal application instance.

    Raises:
        RuntimeError: If the ASGI application does not return the expected
            status or response payload.

    Returns:
        The JSON response produced through native route dispatch.
    """
    application = _create_application()
    generated_url = application.make(UriUrlGenerator).route(
        "runtime.health",
        {},
        absolute=False,
    )
    if generated_url != "/health":
        message = f"unexpected generated health URL: {generated_url}"
        raise RuntimeError(message)

    messages: list[Message] = []
    async with application.asgi.router.lifespan_context(application.asgi):
        await _send_health_request(application.asgi, messages)

    return _decode_response(messages)


def _create_application() -> Application:
    """Compose the smoke app through native Foundation and Routing.

    Returns:
        An application with a provider-backed route and injected services.
    """
    application = Application(
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
    return application


async def _send_health_request(
    application: ASGIApp,
    messages: list[Message],
) -> None:
    """Send one deterministic HTTP request through the ASGI application.

    Args:
        application: Native host assembled by Foundation.
        messages: Mutable response event buffer owned by this smoke run.
    """
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
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 80),
    }

    await application(scope, receive, send)


def _decode_response(messages: Sequence[Message]) -> dict[str, str]:
    """Validate one ASGI response and return its JSON object.

    Args:
        messages: ASGI response events emitted by the native application.

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
        EXPECTED_RESPONSE,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if body != expected_body:
        reason = "ASGI response body did not match the health payload"
        raise RuntimeError(reason)
    return EXPECTED_RESPONSE.copy()


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
