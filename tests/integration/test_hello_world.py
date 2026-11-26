"""Exercise the runnable example through its real ASGI lifecycle.

The test verifies application configuration, native provider registration,
contract-based constructor injection, facade access, and request isolation.
"""

from http import HTTPStatus

import pytest
from app import Greeter, app, application
from fastapi.testclient import TestClient

pytestmark = [
    pytest.mark.architecture,
    pytest.mark.feature,
    pytest.mark.integration,
]


def test_example_composes_native_services_and_request_context() -> None:
    """Serve configured greetings with independently scoped request IDs.

    The route uses the application-owned service container and facades while
    FastAPI remains the explicitly documented ASGI integration boundary.
    """
    greeter = application.make(Greeter)
    assert greeter is application.make(Greeter)

    with TestClient(app) as client:
        first = client.get(
            "/",
            headers={"x-request-id": "example-request-1"},
        )
        second = client.get(
            "/",
            headers={"x-request-id": "example-request-2"},
        )

    assert first.status_code == HTTPStatus.OK
    assert second.status_code == HTTPStatus.OK
    assert first.json() == {
        "application": "Titanspan Example",
        "message": "Hello from Titanspan Example, world!",
        "request_id": "example-request-1",
    }
    assert second.json() == {
        "application": "Titanspan Example",
        "message": "Hello from Titanspan Example, world!",
        "request_id": "example-request-2",
    }
