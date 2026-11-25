"""Verify application-scoped logging and request context integration.

The test runs real FastAPI requests through the application middleware and
observes native records retained by the in-memory driver.
"""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi import Request  # noqa: TC002 - FastAPI resolves route annotations.
from fastapi.testclient import TestClient

from titanspan import Application
from titanspan.facades import Log
from titanspan.logging import (
    LogCustomizer,
    Logger,
    LogLifecycleError,
    MemoryLogDriver,
    MessageLogged,
)

pytestmark = pytest.mark.integration
EXPECTED_REQUEST_EVENTS = 2


def test_application_binds_request_context_and_closes_logging() -> None:
    """Bind request IDs and close logging at ASGI lifespan exit.

    Multiple real requests verify that context values do not bleed between
    executions handled by the same application instance.
    """
    messages: list[MessageLogged] = []

    class CaptureMessages:
        """Observe events from the application-owned default channel.

        This hook uses only the native logger lifecycle interface.
        """

        def customize(self, logger: Logger) -> None:
            """Attach an observer before the application serves requests.

            Args:
                logger: Logger constructed by the application manager.
            """
            logger.listen(messages.append)

    customizer: LogCustomizer = CaptureMessages()
    application = Application(
        logging={
            "channels": {
                "default": {
                    "driver": "memory",
                    "tap": ["capture"],
                },
            },
        },
        logging_customizers={"capture": customizer},
    )
    driver = application.logging.channel().channel.driver
    assert isinstance(driver, MemoryLogDriver)

    @application.asgi.get("/logging-context")
    async def read_logging_context(request: Request) -> dict[str, object]:
        """Log once and return the execution-local request metadata.

        Args:
            request: The active FastAPI request.

        Returns:
            Request context observed by the active logging facade.
        """
        Log.info("request received", path=request.url.path)
        return Log.get_context()

    with TestClient(application.asgi) as client:
        first = client.get(
            "/logging-context",
            headers={"x-request-id": "request-1"},
        )
        second = client.get(
            "/logging-context",
            headers={"x-request-id": "request-2"},
        )

    assert first.status_code == HTTPStatus.OK
    assert second.status_code == HTTPStatus.OK
    assert first.json() == {
        "application": "Titanspan",
        "request_id": "request-1",
    }
    assert second.json() == {
        "application": "Titanspan",
        "request_id": "request-2",
    }
    assert [record.context["request_id"] for record in driver.records] == [
        "request-1",
        "request-2",
    ]
    assert all(
        record.context["application"] == "Titanspan"
        for record in driver.records
    )
    assert len(messages) == EXPECTED_REQUEST_EVENTS
    assert all(event.record.channel == "default" for event in messages)
    with pytest.raises(LogLifecycleError):
        application.logging.channel()
