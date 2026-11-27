"""Verify native validation failures use the application response factory.

The test exercises Validation through the real ASGI request lifecycle.
"""

from http import HTTPStatus
from typing import Annotated

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, field_validator

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


class _ExternalRequest(BaseModel):
    """Represent an explicitly registered FastAPI request schema.

    The validator deliberately includes untrusted input in its backend error.
    """

    credential: str
    attributes: dict[str, int]

    @field_validator("credential")
    @classmethod
    def reject_credential(cls, value: str) -> str:
        """Reject credentials with a message that must remain private.

        Args:
            value: Untrusted credential from the incoming request.

        Returns:
            A credential accepted by this test schema.

        Raises:
            ValueError: Always, with the input included by Pydantic.
        """
        message = f"Rejected credential: {value}"
        raise ValueError(message)


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


def test_fastapi_validation_errors_use_the_safe_native_response() -> None:
    """Hide backend messages and untrusted keys in FastAPI failures.

    Explicit FastAPI interoperability uses the same public 422 policy.
    """
    application = Application()

    @application.asgi.post("/external")
    async def external(payload: _ExternalRequest) -> dict[str, str]:
        """Return a marker only when FastAPI accepts the request.

        Args:
            payload: Typed body supplied by FastAPI's request validator.

        Returns:
            A stable response for accepted test input.
        """
        return {"credential": payload.credential}

    sensitive_value = "request-credential-marker"
    dynamic_key = "mapping-key-marker"
    with TestClient(application.asgi) as client:
        rejected_value = client.post(
            "/external",
            json={"credential": sensitive_value, "attributes": {}},
        )
        rejected_key = client.post(
            "/external",
            json={
                "credential": "safe-value",
                "attributes": {dynamic_key: "not-an-integer"},
            },
        )

    for response in (rejected_value, rejected_key):
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json() == {
            "detail": "Request validation failed.",
            "errors": {"request": ["Input is invalid."]},
        }
        assert sensitive_value not in response.text
        assert dynamic_key not in response.text


def test_malformed_native_json_is_a_safe_client_error() -> None:
    """Render malformed body input as 400 without reflecting its contents.

    Native request parsing errors are distinct from schema validation errors.
    """
    application = Application()

    async def parse_request(request: HttpRequest) -> object:
        """Read JSON through the native request contract.

        Args:
            request: Request-scoped HTTP interface.

        Returns:
            Parsed JSON when the payload is valid.
        """
        return await request.json()

    application.router.post("/parse", parse_request)
    secret_marker = b"body-secret-marker"

    with TestClient(
        application.asgi,
        raise_server_exceptions=False,
    ) as client:
        response = client.post(
            "/parse",
            content=b'{"secret":"' + secret_marker,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {"detail": "Invalid request input."}
    assert secret_marker.decode("ascii") not in response.text
