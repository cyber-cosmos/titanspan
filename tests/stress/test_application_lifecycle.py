"""Exercise repeated application startup and shutdown behavior.

The stress test checks deterministic lifecycle cleanup without relying on
wall-clock thresholds.
"""

import pytest
from fastapi.testclient import TestClient

from titanspan import Application


@pytest.mark.stress
def test_application_can_start_and_stop_repeatedly() -> None:
    """Start and stop independent ASGI applications repeatedly.

    Each context exit closes its own Dishka application scope.
    """
    for _ in range(20):
        application = Application().asgi

        with TestClient(application):
            assert application.state.dishka_container is not None
