"""Verify Validation uses the application Container and HTTP request.

The test exercises the real Foundation, Routing, HTTP, Config, and Validation
services through one ASGI application.
"""

from http import HTTPStatus
from typing import Annotated

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from titanspan.contracts.http import HttpRequest
from titanspan.contracts.validation import ValidationService
from titanspan.facades import Validation
from titanspan.foundation import Application
from titanspan.validation import (
    ValidationException,
    ValidationServiceProvider,
)

pytestmark = [pytest.mark.integration, pytest.mark.architecture]


class CreateAccountInput(BaseModel):
    """Define one request model for the Validation integration route.

    The model includes a field constraint for the real ASGI request.
    """

    username: Annotated[str, Field(min_length=3)]
    credits: int


def test_validation_uses_application_configuration_and_http_input() -> None:
    """Resolve one configured service through injection and its facade.

    The route validates JSON parsed by the HTTP request and uses the
    application repository's strict validation setting.
    """
    application = Application(
        config={"validation": {"strict": True}},
        service_providers=(ValidationServiceProvider(),),
    )

    async def create_account(
        request: HttpRequest,
        validator: ValidationService,
    ) -> dict[str, object]:
        """Validate native request input and expose service identity.

        Args:
            request: Request-scoped native HTTP service.
            validator: Application-owned Validation protocol.

        Returns:
            Validated account fields and a service identity check.
        """
        assert Validation.resolve_service() is validator
        sample = {"username": "ada", "credits": 5}
        sync_value = Validation.validate(sample, CreateAccountInput)
        async_value = await Validation.validate_async(
            sample,
            CreateAccountInput,
        )
        sync_result = Validation.make(sample, CreateAccountInput)
        async_result = await Validation.make_async(
            sample,
            CreateAccountInput,
        )
        try:
            account = await Validation.validate_request_async(
                request,
                CreateAccountInput,
            )
            account_from_request = await Validation.validate_request(
                request,
                CreateAccountInput,
            )
        except ValidationException as error:
            return {
                "errors": {
                    field: list(messages)
                    for field, messages in error.field_errors.items()
                },
            }
        return {
            "username": account.username,
            "credits": account.credits,
            "facade_calls": (
                sync_value == async_value
                and sync_result.is_valid
                and async_result.is_valid
                and account == account_from_request
            ),
        }

    application.router.post("/accounts", create_account)

    with TestClient(application.asgi) as client:
        accepted = client.post(
            "/accounts",
            json={"username": "ada", "credits": 5},
        )
        rejected = client.post(
            "/accounts",
            json={"username": "ada", "credits": "5"},
        )

    assert accepted.status_code == HTTPStatus.OK
    assert accepted.json() == {
        "username": "ada",
        "credits": 5,
        "facade_calls": True,
    }
    assert rejected.status_code == HTTPStatus.OK
    assert rejected.json() == {
        "errors": {"credits": ["Input should be a valid integer"]},
    }
