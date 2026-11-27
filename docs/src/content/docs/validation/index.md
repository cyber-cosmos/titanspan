---
title: "Validation"
---

# Validation

Validation adapts Pydantic's schema validation to native Titanspan services,
field errors, reusable application rules, and HTTP request input. Pydantic
owns schema parsing and constraint execution.

## Declare a schema

Use Python types, `Annotated` metadata, and Pydantic models to describe input.
Pydantic handles required and nullable fields, coercion, nested models,
collections, constraints, custom validators, and error aggregation.

```python
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, HttpUrl

from titanspan.validation import Validator


class CreateAccountInput(BaseModel):
    """Describe one account creation request.

    The model has scalar, nullable, and email fields.
    """

    name: Annotated[str, Field(min_length=2, max_length=80)]
    age: Annotated[int, Field(ge=13)]
    email: EmailStr
    homepage: HttpUrl | None = None


account = Validator().validate(
    {
        "name": "Ada Lovelace",
        "age": "32",
        "email": "ada@example.com",
    },
    CreateAccountInput,
)
```

The default mode accepts conversions supported by the declared schema. Pass
`strict=True` to reject coercion, or configure the application's
`validation.strict` value. A per-call option overrides that default.

`EmailStr` uses Pydantic's supported `email-validator` integration. The
framework installs `email-validator` as a runtime dependency so this schema
works in the standard environment.

## Use the application service

Foundation registers `ValidationServiceProvider` by default. The standalone
`Validator` has no application or lifecycle requirement.

```python
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field

from titanspan.facades import Validation
from titanspan.foundation import Application


class CreateAccountInput(BaseModel):
    """Describe one account creation request.

    The model has scalar, nullable, and email fields.
    """

    name: Annotated[str, Field(min_length=2, max_length=80)]
    age: Annotated[int, Field(ge=13)]
    email: EmailStr


application = Application(
    config={"validation": {"strict": True}},
)

async with application:
    account = Validation.validate(
        {"name": "Ada", "age": 32, "email": "ada@example.com"},
        CreateAccountInput,
    )
```

The facade resolves the same `ValidationService` available through
dependency injection. The provider reads defaults from the active
`ConfigRepository` and has no resources to close.

## Add application rules

Use Pydantic field and model validators for conditions that belong to a
reusable schema. Use `ValidationRule` for sync checks tied to one application
operation, or `AsyncValidationRule` when that check performs asynchronous I/O.
Rules receive the complete schema-validated value and run in order.

```python
from collections.abc import Mapping

import anyio

from titanspan.contracts.validation import (
    AsyncValidationRule,
    ValidationRule,
)
from titanspan.validation import Validator


def name_is_available(value: object) -> bool:
    """Reject the reserved name in one validated mapping.

    Args:
        value: Complete value returned by the schema.

    Returns:
        Whether the name may be used.
    """
    return isinstance(value, Mapping) and value.get("name") != "admin"


async def email_is_available(value: object) -> bool:
    """Check account availability through an application-owned service.

    Args:
        value: Complete value returned by the schema.

    Returns:
        Whether the email may be used.
    """
    await anyio.lowlevel.checkpoint()
    return isinstance(value, Mapping) and (
        value.get("email") != "taken@example.com"
    )


rules = (
    ValidationRule(
        "name",
        name_is_available,
        "This name is unavailable.",
    ),
)
async_rules = (
    AsyncValidationRule(
        "email",
        email_is_available,
        "This email is already registered.",
    ),
)
result = await Validator().validate_async(
    {"name": "ada", "email": "ada@example.com"},
    dict[str, str],
    rules=rules,
    async_rules=async_rules,
)
```

The example's asynchronous rule is deliberately local. A production rule
should call the owning application service. Async rules execute sequentially;
Validation does not create tasks, a database connection, or an event loop.
Use `stop_on_first_error=True` to stop application-rule evaluation after the
first failure. Pydantic field aggregation follows the schema's own policy,
including `Field(fail_fast=True)` for supported collections.

Use `apply_rules_async()` when a trusted framework boundary has already
validated a typed value. This applies application rules without running its
schema a second time.

## Validate HTTP input

Validation reads request input through the canonical `HttpRequest.all()`
method. HTTP retains ownership of body parsing, upload identity, and request
cleanup.

```python
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field

from titanspan.contracts.http import HttpRequest
from titanspan.facades import Validation
from titanspan.foundation import Application


class CreateAccountInput(BaseModel):
    """Describe one account creation request.

    The model has scalar and email fields.
    """

    name: Annotated[str, Field(min_length=2, max_length=80)]
    age: Annotated[int, Field(ge=13)]
    email: EmailStr


async def create_account(request: HttpRequest) -> dict[str, object]:
    """Validate one parsed JSON request body.

    Args:
        request: Request-scoped native HTTP interface.

    Returns:
        Public account fields from the validated model.
    """
    account = await Validation.validate_request(
        request,
        CreateAccountInput,
    )
    return {"name": account.name, "email": str(account.email)}


application = Application()
application.router.post("/accounts", create_account)
```

`validate_request_async` additionally runs async application rules. Both
operations consume HTTP's existing authoritative body parser. Routing does
not infer request schemas from calls made inside a handler. Typed Pydantic
endpoint parameters provide a declarative schema and can apply application
rules through the same Validation service:

```python
from titanspan.contracts.validation import ValidationRule


def name_is_available(value: object) -> bool:
    """Reject one reserved account name.

    Args:
        value: Typed account request produced by Pydantic.

    Returns:
        Whether the requested name is available.
    """
    return isinstance(value, CreateAccountInput) and value.name != "reserved"


async def create_typed_account(
    payload: CreateAccountInput,
) -> dict[str, str]:
    """Return fields from a validated account request.

    Args:
        payload: Pydantic model parsed from the JSON body.

    Returns:
        Public account fields.
    """
    return {"name": payload.name, "email": str(payload.email)}


application.router.post(
    "/typed-accounts",
    create_typed_account,
).validate_input(
    "payload",
    rules=(
        ValidationRule(
            field="name",
            check=name_is_available,
            message="This name is unavailable.",
        ),
    ),
)
```

The endpoint annotation supplies the OpenAPI request schema. FastAPI parses
the body once, then the application-owned `ValidationService` runs configured
rules before the endpoint. Route middleware can reject a request before
these rules run. Use `async_rules` for asynchronous application checks.

## Handle errors and test results

`ValidationException` exposes ordered `issues` and immutable
`field_errors`. Issues include nested field paths, safe messages, stable
error codes, and optional attribute labels. Rejected input values are not
retained. Pydantic backend messages are replaced with fixed Titanspan
messages. Unknown error codes use a generic message. Declared schema fields
remain in error paths; dynamic mapping keys become `"<key>"`.

Application-authored custom rule messages and explicit message overrides are
returned to clients. Keep them safe for public output. Never include rejected
values or secrets. Native validation exceptions and FastAPI request validation
failures use the same generic 422 response policy.

Use `make` or `make_async` when a validation result is data rather than a
raised exception:

```python
result = Validator().make({"age": "bad"}, dict[str, int])
if not result.is_valid:
    for issue in result.errors:
        print(issue.field, issue.message)
```

The same result methods work through the `Validation` facade inside an active
application context. Foundation automatically renders an uncaught
`ValidationException` as a 422 JSON response through the native response
factory. The response includes safe field messages and excludes rejected
input values. Native typed routes and FastAPI interoperability routes document
the same `ValidationErrorBody` schema for their default 422 response.
Applications can register a more specific handler before startup.

## Integration boundaries

Validation does not implement database uniqueness or existence checks. The
Database component must provide those rules with explicit transaction and
session ownership before they can make database guarantees. Authentication
and authorization rules belong to their owning components. Storage-aware file
constraints belong to Filesystem. Application rules may inspect HTTP upload
metadata while the request scope is active; HTTP owns upload parsing and
temporary-file cleanup.
