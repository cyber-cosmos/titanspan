"""End-to-end checks for the runnable Hello World example."""

from app import app
from fastapi.testclient import TestClient


def test_hello_world_endpoint_returns_a_greeting() -> None:
    """Serve the documented greeting through the ASGI application."""
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "framework": "Titanspan",
        "message": "Hello, world!",
    }
