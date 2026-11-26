"""Verify native validation failures use the application response factory.

The test exercises Validation through the real ASGI request lifecycle.
"""

from http import HTTPStatus
from typing import Annotated

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from titanspan.contracts.http import HttpRequest
from titanspan.contracts.validation import ValidationService
from titanspan.foundation import Application
from titanspan.validation import ValidationServiceProvider

pytestmark = [pytest.mark.architecture, pytest.mark.integration]


class _CreateTask(BaseModel):
    """Define request data for one create operation.

    The model rejects non-positive task counts.
    """

    count: Annotated[int, Field(gt=0)]


def test_uncaught_validation_errors_render_safe_http_422() -> None:
    """Render safe field errors without returning rejected input values.

    Validation, request parsing, routing, and response creation use the
    application-owned services.
    """
    application = Application(
        service_providers=(ValidationServiceProvider(),),
    )

    async def create_task(
        request: HttpRequest,
        validator: ValidationService,
    ) -> object:
        """Validate request data and let native errors reach Foundation.

        Args:
            request: Request-scoped Titanspan request contract.
            validator: Application-owned validation service.

        Returns:
            Validated model data for an accepted request.
        """
        return await validator.validate_request_async(
            request,
            _CreateTask,
        )

    application.router.post("/tasks", create_task)

    with TestClient(application.asgi) as client:
        response = client.post("/tasks", json={"count": -1})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    body = response.json()
    assert body["detail"] == "Request validation failed."
    assert body["errors"]["count"]
    assert "input" not in body
