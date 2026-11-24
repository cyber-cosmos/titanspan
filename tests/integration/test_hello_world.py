"""Exercise the runnable Hello World app across the HTTP boundary.

This test validates the composed FastAPI application without mocking the
framework or HTTP client integration.
"""

from http import HTTPStatus

import pytest
from app import app
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.feature, pytest.mark.integration]


def test_hello_world_endpoint_returns_a_greeting() -> None:
    """Return the documented greeting through the ASGI application.

    The request travels through Starlette's test client and FastAPI routing.
    """
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "framework": "Titanspan",
        "message": "Hello, world!",
    }
