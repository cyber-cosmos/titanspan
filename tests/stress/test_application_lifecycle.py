"""Repeated lifecycle checks for the initial application foundation."""

import pytest
from fastapi.testclient import TestClient

from titanspan import Application


@pytest.mark.stress
def test_application_can_start_and_stop_repeatedly() -> None:
    """Start and stop independent ASGI applications without leaked scopes."""
    for _ in range(20):
        application = Application().asgi

        with TestClient(application):
            assert application.state.dishka_container is not None
