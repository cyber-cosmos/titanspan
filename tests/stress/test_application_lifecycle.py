"""Exercise repeated application startup and shutdown behavior.

The stress test checks deterministic lifecycle cleanup without relying on
wall-clock thresholds.
"""

import pytest
from fastapi.testclient import TestClient

from titanspan import Application


@pytest.mark.stress
@pytest.mark.concurrency
def test_application_can_start_and_stop_repeatedly() -> None:
    """Start and stop native applications without an unused route graph.

    An external provider graph is composed only when the application supplies
    explicit providers; ordinary ASGI apps use the native service container.
    """
    for _ in range(20):
        application = Application().asgi

        with TestClient(application):
            assert not hasattr(application.state, "dishka_container")
