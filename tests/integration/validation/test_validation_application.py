"""Verify Validation uses the application Container and HTTP request.

The test exercises the real Foundation, Routing, HTTP, Config, and Validation
services through one ASGI application.
"""

from http import HTTPStatus
from typing import Annotated, Self

import anyio
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.websockets import WebSocket

from titanspan.contracts.http import (
    HttpRequest,
    HttpResponse,
    RequestHandler,
    ResponseFactory,
)
from titanspan.contracts.validation import (
    AsyncValidationRule,
    ValidationRule,
    ValidationService,
)
from titanspan.facades import Validation
from titanspan.foundation import Application
from titanspan.routing import InvalidRouteError
from titanspan.validation import (
    ValidationException,
    ValidationServiceProvider,
)

pytestmark = [pytest.mark.integration, pytest.mark.architecture]
_SCHEMA_VALIDATION_CALLS: list[str] = []


class CreateAccountInput(BaseModel):
    """Define one request model for the Validation integration route.

    The model includes a field constraint for the real ASGI request.
    """

    username: Annotated[str, Field(min_length=3)]
    credits: int


class CountedInput(BaseModel):
    """Count Pydantic model validation across the routing boundary.

    The configured instance policy exposes any second schema-validation pass.
    """

    model_config = ConfigDict(revalidate_instances="always")

    value: str

    @model_validator(mode="after")
    def record_validation(self) -> Self:
        """Record one completed schema validation.

        Returns:
            This validated instance.
        """
        _SCHEMA_VALIDATION_CALLS.append(self.value)
        return self


class RejectInputMiddleware:
    """Short-circuit one route before its input rules run.

    The response factory comes from the application's canonical container.
    """

    def __init__(self, factory: ResponseFactory) -> None:
        """Retain the application-owned response factory.

        Args:
            factory: Canonical HTTP response construction service.
        """
        self._factory = factory

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Reject the request without calling downstream validation.

        Args:
            request: Current request in its native execution scope.
            next_handler: Downstream route continuation, intentionally unused.

        Returns:
            A forbidden response produced by the native factory.
        """
        del request, next_handler
        return self._factory.json({"detail": "Access denied."}, status=403)


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

        def same_account(value: object) -> bool:
            """Verify rules receive the already validated model instance.

            Args:
                value: Typed account model passed to the application rule.

            Returns:
                Whether the rule received the same model object.
            """
            return value is sync_value

        rule_value = await Validation.apply_rules_async(
            sync_value,
            rules=(
                ValidationRule(
                    field="username",
                    check=same_account,
                    message="The input identity changed.",
                ),
            ),
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
                and rule_value is sync_value
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


def test_route_applies_validation_rules_to_typed_request_body() -> None:
    """Apply native application rules after backend schema parsing.

    The endpoint schema remains visible in OpenAPI and both failure paths use
    Foundation's safe 422 response policy.
    """
    application = Application()
    rule_calls: list[str] = []
    credit_rule_calls: list[int] = []

    def credits_are_positive(value: object) -> bool:
        """Reject non-positive credits after typed schema validation.

        Args:
            value: Schema-validated account request.

        Returns:
            Whether the account has a positive credit balance.
        """
        assert isinstance(value, CreateAccountInput)
        credit_rule_calls.append(value.credits)
        return value.credits > 0

    async def username_is_available(value: object) -> bool:
        """Reject one reserved name after typed schema validation.

        Args:
            value: Schema-validated account request.

        Returns:
            Whether the account name can be used.
        """
        await anyio.lowlevel.checkpoint()
        assert isinstance(value, CreateAccountInput)
        rule_calls.append(value.username)
        return value.username != "reserved"

    async def create(
        payload: CreateAccountInput,
    ) -> dict[str, object]:
        """Return the typed request fields accepted by application rules.

        Args:
            payload: Pydantic model parsed from the JSON body.

        Returns:
            A JSON object containing the accepted account values.
        """
        return {
            "username": payload.username,
            "credits": payload.credits,
        }

    def optional_payload_is_valid(value: object) -> bool:
        """Accept the declared absent-value default.

        Args:
            value: Optional typed request body.

        Returns:
            Whether the request body is absent.
        """
        return value is None

    async def create_optional(
        payload: CreateAccountInput | None = None,
    ) -> dict[str, bool]:
        """Return whether an optional request body was omitted.

        Args:
            payload: Optional typed request body.

        Returns:
            Whether the endpoint received its declared absent default.
        """
        return {"missing": payload is None}

    validated_route = application.router.post(
        "/validated",
        create,
    ).validate_input(
        "payload",
        rules=(
            ValidationRule(
                field="credits",
                check=credits_are_positive,
                message="Credits must be positive.",
            ),
        ),
        async_rules=(
            AsyncValidationRule(
                field="username",
                check=username_is_available,
                message="This username is unavailable.",
            ),
        ),
    )
    with pytest.raises(InvalidRouteError):
        validated_route.validate_input("payload")
    with pytest.raises(InvalidRouteError):
        validated_route.validate_input("not a parameter")
    application.router.post("/short-circuit", create).middleware(
        RejectInputMiddleware,
    ).validate_input(
        "payload",
        async_rules=(
            AsyncValidationRule(
                field="username",
                check=username_is_available,
                message="This username is unavailable.",
            ),
        ),
    )
    application.router.post(
        "/optional",
        create_optional,
    ).validate_input(
        "payload",
        rules=(
            ValidationRule(
                field="payload",
                check=optional_payload_is_valid,
                message="The optional body is invalid.",
            ),
        ),
    )

    with TestClient(application.asgi) as client:
        schema = client.get("/openapi.json").json()
        accepted = client.post(
            "/validated",
            json={"username": "ada", "credits": 5},
        )
        rule_rejected = client.post(
            "/validated",
            json={"username": "reserved", "credits": 5},
        )
        sync_rule_rejected = client.post(
            "/validated",
            json={"username": "ada", "credits": 0},
        )
        schema_rejected = client.post(
            "/validated",
            json={"username": "credential-marker", "credits": "bad"},
        )
        short_circuited = client.post(
            "/short-circuit",
            json={"username": "reserved", "credits": 5},
        )
        optional = client.post("/optional")

    operation = schema["paths"]["/validated"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("CreateAccountInput")
    assert accepted.status_code == HTTPStatus.OK
    assert accepted.json() == {"username": "ada", "credits": 5}
    assert rule_rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert rule_rejected.json()["errors"] == {
        "username": ["This username is unavailable."],
    }
    assert sync_rule_rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert sync_rule_rejected.json()["errors"] == {
        "credits": ["Credits must be positive."],
    }
    assert schema_rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "credential-marker" not in schema_rejected.text
    assert short_circuited.status_code == HTTPStatus.FORBIDDEN
    assert optional.status_code == HTTPStatus.OK
    assert optional.json() == {"missing": True}
    assert rule_calls == ["ada", "reserved", "ada"]
    assert credit_rule_calls == [5, 5, 0]


def test_route_rejects_validation_on_injected_services_at_startup() -> None:
    """Reject invalid validation declarations before request handling.

    Service dependencies are not client input schemas and cannot receive
    application request rules.
    """
    application = Application()

    async def endpoint(request: HttpRequest) -> dict[str, str]:
        """Return a status for an intentionally invalid route declaration.

        Args:
            request: Native request service injected by Routing.

        Returns:
            A minimal response if the invalid route is ever dispatched.
        """
        return {"status": request.method}

    application.router.post("/invalid", endpoint).validate_input(
        "request",
    )

    with pytest.raises(InvalidRouteError), TestClient(application.asgi):
        pytest.fail("Invalid request validation passed startup.")


def test_route_rejects_unresolved_schema_and_websocket_input_rules() -> None:
    """Reject annotations Routing cannot expose as HTTP input schemas.

    Startup errors must identify invalid declarations before any request runs.
    """
    unresolved_application = Application()

    async def unresolved(payload: object) -> dict[str, str]:
        """Return a marker for an unresolved annotation declaration.

        Args:
            payload: Value with a deliberately unresolved runtime annotation.

        Returns:
            A response that should never be reached.
        """
        return {"status": str(payload)}

    unresolved.__annotations__["payload"] = "MissingInputSchema"
    unresolved_application.router.post(
        "/unresolved",
        unresolved,
    ).validate_input("payload")

    with (
        pytest.raises(InvalidRouteError),
        TestClient(
            unresolved_application.asgi,
        ),
    ):
        pytest.fail("Unresolved input schema passed startup.")

    websocket_application = Application()

    async def websocket_handler(websocket: WebSocket) -> None:
        """Accept a connection if unsupported HTTP rules are ignored.

        Args:
            websocket: Backend WebSocket used only by this startup test.
        """
        await websocket.accept()

    websocket_application.router.websocket(
        "/socket",
        websocket_handler,
    ).validate_input("payload")

    with (
        pytest.raises(InvalidRouteError),
        TestClient(
            websocket_application.asgi,
        ),
    ):
        pytest.fail("WebSocket input validation passed startup.")


def test_route_rules_do_not_repeat_pydantic_schema_validation() -> None:
    """Apply rules to FastAPI's typed value without parsing it again.

    Pydantic is configured to revalidate model instances so duplicate schema
    execution is observable.
    """
    _SCHEMA_VALIDATION_CALLS.clear()
    application = Application()

    async def submit(payload: CountedInput) -> dict[str, str]:
        """Return the value parsed by the HTTP request boundary.

        Args:
            payload: Pydantic model parsed from the JSON body.

        Returns:
            The accepted input value.
        """
        return {"value": payload.value}

    def is_counted_input(value: object) -> bool:
        """Require the Pydantic model selected by the endpoint annotation.

        Args:
            value: Input parsed by the native HTTP route.

        Returns:
            Whether the request value has the declared model type.
        """
        return isinstance(value, CountedInput)

    application.router.post("/counted", submit).validate_input(
        "payload",
        rules=(
            ValidationRule(
                field="value",
                check=is_counted_input,
                message="A typed value is required.",
            ),
        ),
    )

    with TestClient(application.asgi) as client:
        response = client.post("/counted", json={"value": "parsed-once"})

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"value": "parsed-once"}
    assert _SCHEMA_VALIDATION_CALLS == ["parsed-once"]
