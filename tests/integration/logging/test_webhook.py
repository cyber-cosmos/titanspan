"""Verify network logging drivers against an isolated local HTTP server.

The integration tests exercise real HTTP delivery and do not contact an
external service or include an application credential.
"""

import json
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from titanspan.logging import LogDeliveryError, LogManager
from titanspan.logging.exceptions import LogBackendError

pytestmark = pytest.mark.integration
RESPONSE_TIMEOUT_SECONDS = 2
REDIRECT_STATUS_MINIMUM = 300
CLIENT_ERROR_STATUS_MINIMUM = 400


@pytest.fixture
def webhook_server() -> Iterator[tuple[str, Queue[bytes]]]:
    """Start a bounded local receiver for structured log payloads.

    Yields:
        The local URL and a queue containing each received request body.
    """
    received: Queue[bytes] = Queue()

    class Receiver(BaseHTTPRequestHandler):
        """Record request bodies from the local integration test.

        The server is bound only to loopback and is shut down by its fixture.
        """

        def do_POST(self) -> None:
            """Capture the current JSON request body.

            The test server accepts only the POST requests created by the
            logging adapter.
            """
            length = int(self.headers.get("Content-Length", "0"))
            received.put(self.rfile.read(length))
            query = parse_qs(urlsplit(self.path).query)
            status = int(query.get("status", ["204"])[0])
            self.send_response(status)
            if REDIRECT_STATUS_MINIMUM <= status < CLIENT_ERROR_STATUS_MINIMUM:
                self.send_header("Location", "/redirect-target")
            self.end_headers()

        def log_message(
            self,
            format: str,
            *args: object,
        ) -> None:
            """Suppress server diagnostics unrelated to payload assertions.

            Args:
                format: The standard server message format.
                *args: Standard server message values.
            """
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/logs"
    try:
        yield url, received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_webhook_driver_sends_native_json_record(
    webhook_server: tuple[str, Queue[bytes]],
) -> None:
    """Send one structured record to a configured local destination.

    The payload uses the Titanspan schema rather than backend event fields.

    Args:
        webhook_server: Isolated server URL and its received-body queue.
    """
    url, received = webhook_server
    manager = LogManager(
        {
            "channels": {
                "default": {
                    "driver": "webhook",
                    "options": {"url": url, "allow_http": True},
                },
            },
        },
    )

    manager.info("workflow completed", run_id="run-7")
    manager.close()

    payload = json.loads(
        received.get(timeout=RESPONSE_TIMEOUT_SECONDS),
    )
    assert payload["message"] == "workflow completed"
    assert payload["channel"] == "default"
    assert payload["context"] == {"run_id": "run-7"}


def test_slack_driver_uses_native_text_payload(
    webhook_server: tuple[str, Queue[bytes]],
) -> None:
    """Deliver a human-readable Slack webhook body to the local receiver.

    Args:
        webhook_server: Isolated server URL and its received-body queue.
    """
    url, received = webhook_server
    manager = LogManager(
        {
            "channels": {
                "default": {
                    "driver": "slack",
                    "options": {"url": url, "allow_http": True},
                },
            },
        },
    )

    manager.warning("worker capacity reached", worker_id="worker-1")
    manager.close()

    payload = json.loads(
        received.get(timeout=RESPONSE_TIMEOUT_SECONDS),
    )
    assert "worker capacity reached" in payload["text"]
    assert "worker-1" in payload["text"]


@pytest.mark.parametrize("status", [302, 503])
def test_webhook_rejects_redirects_and_failed_responses(
    webhook_server: tuple[str, Queue[bytes]],
    status: int,
) -> None:
    """Surface non-success HTTP responses as native delivery failures.

    Redirects are rejected before a log payload can be sent to another URL.

    Args:
        webhook_server: Isolated server URL and received request bodies.
        status: Redirect or server failure returned by the local receiver.
    """
    url, _ = webhook_server
    manager = LogManager(
        {
            "channels": {
                "default": {
                    "driver": "webhook",
                    "options": {
                        "url": f"{url}?status={status}",
                        "allow_http": True,
                    },
                },
            },
        },
    )

    with pytest.raises(LogDeliveryError) as error:
        manager.info("private log payload")
    manager.close()

    assert isinstance(error.value.__cause__, LogBackendError)
