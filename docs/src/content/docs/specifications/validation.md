---
title: "Validation behavioral specification"
---

# Validation behavioral specification

This specification records verified behavior in `titanspan.validation`.
Pydantic owns schema validation. Titanspan supplies configuration,
application-rule sequencing, request integration, and safe native errors.

## Capability inventory

| Capability | Public API | Evidence |
| --- | --- | --- |
| Python and Pydantic schemas | `Validator.validate`, `TypeForm` | `tests/unit/validation/test_validator.py` |
| Strict and coercive input | `strict`, `validation.strict` | Validator and application integration tests |
| Nested values and constraints | Pydantic models, `Annotated`, `Field` | Validator unit tests |
| Email and URL schema types | `EmailStr`, `HttpUrl` | Validator unit tests; `email-validator` dependency |
| Python object attributes | `from_attributes` | Validator unit tests |
| Safe field issues | `ValidationException`, `ValidationIssue` | Validator unit tests |
| Sync application rules | `ValidationRule` | Validator unit tests |
| Async application rules | `AsyncValidationRule`, `validate_async` | Validator unit tests |
| Non-raising test results | `make`, `make_async` | Validator unit tests |
| Default Container and Config integration | Foundation's `ValidationServiceProvider` | `tests/integration/validation/test_validation_application.py`, `tests/integration/test_framework_cohesion.py` |
| Safe HTTP 422 rendering | Foundation's default `ValidationException` handler | `tests/integration/test_validation_exception_rendering.py` |
| HTTP request input | `validate_request`, `validate_request_async` | Real ASGI application integration test |

## Schemas and errors

`Validator` constructs Pydantic's public `TypeAdapter` for the supplied
`TypeForm`. It supports schemas accepted by the installed Pydantic release,
including models, Python types, typed mapping declarations, and
`Annotated` metadata. `strict` and `from_attributes` default to the immutable
`ValidationConfiguration`; per-call values take precedence. Pydantic receives
the supplied validation context.

Pydantic owns required and optional values, nullability, scalar conversion,
collection and mapping checks, nested fields, item constraints, lengths,
ranges, patterns, enumerations, dates, datetimes, URLs, emails, and custom
field or model validators. Cross-field and conditional rules belong in those
schema validators when the constraint is reusable. Pydantic controls schema
error aggregation; `Field(fail_fast=True)` applies where supported.

`ValidationIssue.location` retains nested path segments and `field` renders
them as dotted text. Pydantic error values and backend messages are not
returned. Titanspan maps known error codes to fixed messages and uses a
generic message for unknown codes. Declared schema fields remain in locations;
dynamic mapping keys become `"<key>"`. This prevents input values embedded in
keys from appearing in diagnostics.

`ValidationException` groups safe messages into an immutable mapping.
Caller-provided field messages and `ValidationRule` messages remain visible.
Treat those messages as application-authored public text. Attribute labels
affect the exception summary but do not alter field keys.

`make` and `make_async` return `ValidationResult`. A valid schema whose output
is `None` remains valid; `is_valid` follows the error tuple.

## Application rules

`ValidationRule` callbacks receive the complete schema-validated value and
return a boolean. `AsyncValidationRule` callbacks return an awaitable boolean.
The service runs rules sequentially. A sync call that receives an awaitable
closes a coroutine and raises `AsyncValidationRequiredError`; it does not
create an event loop. Rule exceptions and cancellation propagate unchanged.
`stop_on_first_error` affects application-rule execution only.

Rules are application-level checks, not a second schema language. Database
uniqueness and existence require a future Database-owned implementation with
transaction and session guarantees. Authorization, session, and storage
checks remain with their respective owners.

## HTTP and framework integration

Foundation registers `ValidationServiceProvider` by default. The provider
registers a singleton under the canonical `ValidationService` protocol. Its
factory receives the active `ConfigRepository` through the application
Container. An explicit provider replaces the default. The standalone
`Validator` remains independently usable.

Request validation calls `HttpRequest.all()` before schema execution. This
reuses HTTP's authoritative JSON, form, multipart, and query input behavior
and does not add a request parser. HTTP owns upload temporary files and
request-scoped cleanup.

Foundation maps native `ValidationException` and FastAPI
`RequestValidationError` values to status 422 through the canonical HTTP
response factory. Native issues retain fixed safe messages and declared field
paths. Backend request failures use a generic detail and issue. Foundation
does not expose Pydantic error dictionaries, custom backend messages, input,
context, exception text, or dynamic mapping keys. Internal diagnostic detail
requires the application's explicit exception-reporting policy.

Custom rule messages and explicit `messages` overrides are application-owned
public text. Do not include rejected values, credentials, tokens, or other
secrets in them. Routing uses FastAPI request parsing and applies the same
safe 422 rendering policy.

## Verification

Focused validation behavior and application integration tests are under
`tests/unit/validation/` and `tests/integration/validation/`. The integration
test uses a real Foundation application, its Container and Config repository,
native Routing dispatch, Starlette's ASGI request implementation, and the HTTP
request contract.
