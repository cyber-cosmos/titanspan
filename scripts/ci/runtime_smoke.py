"""Exercise an installed Titanspan application through an ASGI request.

The script runs from outside the source tree and uses only the package's
declared runtime dependencies. It invokes the ASGI lifespan and one real
in-process HTTP scope without test-only client packages.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import anyio

from titanspan import Application

if TYPE_CHECKING:
    from starlette.types import Message, Scope

EXPECTED_RESPONSE = {"status": "ok"}
HTTP_OK_STATUS = 200


async def _run_smoke() -> None:
    """Start, request, and shut down a minimal application instance.

    Raises:
        RuntimeError: If the ASGI application does not return the expected
            status or response payload.
    """
    application = Application()

    @application.asgi.get("/health")
    async def health() -> dict[str, str]:
        """Return the deterministic health response for the smoke request.

        Returns:
            A small JSON response that proves route execution.
        """
        return EXPECTED_RESPONSE

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
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 80),
    }

    # Lifespan context exercises the framework's actual startup and shutdown
    # hooks while keeping this smoke check independent of HTTP test extras.
    async with application.asgi.router.lifespan_context(application.asgi):
        await application.asgi(scope, receive, send)

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
    decoded_body: object = json.loads(body)
    if decoded_body != EXPECTED_RESPONSE:
        reason = "ASGI response body did not match the health payload"
        raise RuntimeError(reason)


def main() -> int:
    """Run the application smoke and report its process status.

    Let application failures propagate so the runtime verification job fails
    rather than recording a false success.
    """
    anyio.run(_run_smoke)
    sys.stdout.write("Installed Titanspan application smoke passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
