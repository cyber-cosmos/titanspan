"""Verify Pydantic-backed validation and native application errors.

The tests use real Pydantic schemas and validation primitives.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, NoReturn, Self, cast

import anyio
import pytest
from pydantic import (
    AfterValidator,
    BaseModel,
    EmailStr,
    Field,
    GetCoreSchemaHandler,
    HttpUrl,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import CoreSchema, PydanticCustomError, core_schema

from titanspan.config import Repository
from titanspan.contracts.validation import (
    AsyncValidationRule,
    ValidationResult,
    ValidationRule,
    ValidationRuleCheck,
)
from titanspan.validation import (
    AsyncValidationRequiredError,
    ValidationConfiguration,
    ValidationConfigurationError,
    ValidationException,
    Validator,
)

pytestmark = pytest.mark.unit
_REJECTED_MARKER = "private-marker-not-in-error"
_EXPECTED_AGE = 32
_EXPECTED_OBJECT_COUNT = 3
_CONTEXT_AMOUNT = 8
_EXPECTED_RULE_ISSUES = 2
_CONTEXT_LIMIT_ERROR = "The value exceeds its limit."
_CONFIRMATION_ERROR = "The amount requires confirmation."
_RULE_SERVICE_ERROR = "Rule service unavailable."
_PRIVATE_VALIDATION_VALUE = "secret=untrusted-input"
_CUSTOM_VALIDATION_CODE = "invalid value with secrets"
_CUSTOM_VALIDATION_MESSAGE = "Rejected value: {value}"


class AccessLevel(StrEnum):
    """Represent the access level accepted by the schema tests.

    The values verify native Python enumeration support.
    """

    READER = "reader"
    EDITOR = "editor"


class AddressInput(BaseModel):
    """Validate one nested postal address.

    The fields exercise nested string constraints.
    """

    city: Annotated[str, Field(min_length=2)]
    postal_code: Annotated[str, Field(pattern=r"^[0-9]{5}$")]


class SignupInput(BaseModel):
    """Validate common typed, nested, and constrained user fields.

    The schema exercises Python and Pydantic validation primitives.
    """

    name: Annotated[str, Field(min_length=3, max_length=40)]
    age: Annotated[int, Field(ge=13, le=120)]
    active: bool
    email: EmailStr
    homepage: HttpUrl
    role: AccessLevel
    birthday: date
    created_at: datetime
    labels: list[Annotated[str, Field(min_length=1)]]
    address: AddressInput
    nickname: str | None = None


class ObjectInput(BaseModel):
    """Describe attributes copied from a regular Python object.

    Pydantic reads attributes when the caller explicitly allows it.
    """

    name: str
    count: int


class RequiredNullableInput(BaseModel):
    """Distinguish nullable required fields from optional fields.

    The schema keeps requiredness independent of nullable types.
    """

    required_value: str | None
    optional_value: str | None = None


class _InvalidJsonSchemaInput:
    """Reject values with a custom code and no JSON Schema representation.

    The type exercises safe diagnostics when a Pydantic schema export fails.
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: object,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        """Return a validator that raises a deliberately unsafe message.

        Args:
            source_type: Type Pydantic is adapting.
            handler: Pydantic's schema handler, unused by this fixture.

        Returns:
            A plain validator schema without JSON Schema support.
        """
        _ = source_type
        _ = handler
        return core_schema.no_info_plain_validator_function(cls._reject)

    @staticmethod
    def _reject(value: object) -> NoReturn:
        """Raise a custom error that contains the rejected value.

        Args:
            value: Untrusted input that must not appear in public errors.

        Raises:
            PydanticCustomError: Always, for the validation safety test.
        """
        raise PydanticCustomError(
            _CUSTOM_VALIDATION_CODE,
            _CUSTOM_VALIDATION_MESSAGE,
            {"value": value},
        )


class SecretRejectedInput(BaseModel):
    """Reject one value with a backend message containing that value.

    Validation must replace backend-generated text before exposing it.
    """

    credential: str

    @field_validator("credential")
    @classmethod
    def reject_credential(cls, value: str) -> str:
        """Reject the supplied credential using an unsafe backend message.

        Args:
            value: Untrusted credential supplied to the schema.

        Returns:
            A value accepted by the schema.

        Raises:
            ValueError: Always, with the rejected credential in the detail.
        """
        message = f"Credential rejected: {value}"
        raise ValueError(message)


def test_validator_coerces_values_and_validates_nested_models() -> None:
    """Use Pydantic's native conversion and nested schema validation.

    Validated values are ordinary Pydantic models with typed fields.
    """
    validator = Validator()
    user = validator.validate(
        _signup_values(),
        SignupInput,
    )

    assert isinstance(user, SignupInput)
    assert user.age == _EXPECTED_AGE
    assert user.active is True
    assert user.role is AccessLevel.READER
    assert user.birthday == date(1994, 5, 17)
    assert user.address.city == "Colombo"
    assert user.nickname is None


def test_validator_supports_strict_and_coercive_modes() -> None:
    """Allow call-level policy to select Pydantic strictness explicitly.

    Coercion remains enabled by default and can be disabled per call.
    """
    schema = dict[str, int]
    validator = Validator()

    assert validator.validate({"count": "4"}, schema) == {"count": 4}
    with pytest.raises(ValidationException):
        validator.validate({"count": "4"}, schema, strict=True)


def test_required_nullable_field_still_requires_an_input_value() -> None:
    """Keep Pydantic's distinction between nullable and optional fields.

    Defaults and nullability come from schema declarations, not framework
    heuristics.
    """
    validator = Validator()
    accepted = validator.validate(
        {"required_value": None},
        RequiredNullableInput,
    )
    assert accepted.required_value is None
    assert accepted.optional_value is None

    with pytest.raises(ValidationException) as captured:
        validator.validate({}, RequiredNullableInput)
    assert "required_value" in captured.value.field_errors


def test_validator_reads_strictness_from_validation_configuration() -> None:
    """Use explicit per-call settings to override application defaults.

    A call can opt into coercion even when its configured default is strict.
    """
    validator = Validator(ValidationConfiguration(strict=True))

    with pytest.raises(ValidationException):
        validator.validate({"count": "4"}, dict[str, int])
    assert validator.validate(
        {"count": "4"},
        dict[str, int],
        strict=False,
    ) == {"count": 4}


def test_validator_accepts_python_objects_and_mapping_schemas() -> None:
    """Validate attributes and ordinary typed mapping schemas.

    ``from_attributes`` delegates model extraction to Pydantic.
    """

    class Source:
        """Expose values as ordinary attributes.

        The source is not a Pydantic model.
        """

        name: str
        count: int

        def __init__(self) -> None:
            """Populate values inspected by the type adapter.

            The adapter reads these attributes when configured to do so.
            """
            self.name = "report"
            self.count = 3

    result = Validator().validate(
        Source(),
        ObjectInput,
        from_attributes=True,
    )

    assert isinstance(result, ObjectInput)
    assert result.name == "report"
    assert result.count == _EXPECTED_OBJECT_COUNT
    mapped = Validator().validate({"count": "3"}, dict[str, int])
    assert mapped == {"count": 3}


def test_validation_context_and_pydantic_cross_field_rules() -> None:
    """Pass Pydantic context and preserve schema-owned model validation.

    Application-level orchestration does not replace schema validators.
    """

    def maximum_from_context(
        value: int,
        info: ValidationInfo,
    ) -> int:
        """Enforce a context-selected numeric maximum.

        Args:
            value: Integer already parsed by Pydantic.
            info: Validation context supplied by the caller.

        Returns:
            The value when it remains below the contextual limit.

        Raises:
            ValueError: If the value exceeds the supplied maximum.
        """
        context = info.context
        maximum = 10 if context is None else context["maximum"]
        if value > maximum:
            raise ValueError(_CONTEXT_LIMIT_ERROR)
        return value

    class AmountInput(BaseModel):
        """Use a context-aware field and a cross-field invariant.

        The fields exercise Pydantic validators before rule execution.
        """

        amount: Annotated[int, AfterValidator(maximum_from_context)]
        confirmed: bool

        @model_validator(mode="after")
        def require_confirmation(self) -> Self:
            """Reject unconfirmed amounts after field validation.

            Returns:
                This model when the amount is confirmed.

            Raises:
                ValueError: If the confirmation field is false.
            """
            if not self.confirmed:
                raise ValueError(_CONFIRMATION_ERROR)
            return self

    validator = Validator()
    assert (
        validator.validate(
            {"amount": 8, "confirmed": True},
            AmountInput,
            context={"maximum": _CONTEXT_AMOUNT},
        ).amount
        == _CONTEXT_AMOUNT
    )

    with pytest.raises(ValidationException) as too_large:
        validator.validate(
            {"amount": _CONTEXT_AMOUNT + 1, "confirmed": True},
            AmountInput,
            context={"maximum": _CONTEXT_AMOUNT},
        )
    assert "amount" in too_large.value.field_errors

    with pytest.raises(ValidationException) as unconfirmed:
        validator.validate(
            {"amount": _CONTEXT_AMOUNT, "confirmed": False},
            AmountInput,
            context={"maximum": _CONTEXT_AMOUNT},
        )
    assert "" in unconfirmed.value.field_errors


def test_validator_aggregates_field_errors_and_omits_rejected_values() -> None:
    """Return safe field paths, custom labels, and custom messages.

    Validation errors do not retain raw rejected input values.
    """
    validator = Validator()
    invalid = _signup_values()
    invalid.update(
        {
            "name": _REJECTED_MARKER * 2,
            "email": _REJECTED_MARKER,
            "age": 8,
            "labels": [""],
            "address": {"city": "X", "postal_code": "bad"},
        },
    )

    with pytest.raises(ValidationException) as captured:
        validator.validate(
            invalid,
            SignupInput,
            messages={"name": "Choose a display name."},
            attribute_labels={"name": "Display name"},
        )

    error = captured.value
    fields = {issue.field for issue in error.issues}
    assert {"age", "name", "labels.0", "address.city"} <= fields
    assert "address.postal_code" in error.field_errors
    assert error.field_errors["name"] == ("Choose a display name.",)
    assert "Display name" in str(error)
    assert _REJECTED_MARKER not in str(error)
    assert _REJECTED_MARKER not in repr(error.issues)

    with pytest.raises(ValidationException) as code_message:
        validator.validate(
            {"count": -1},
            dict[str, Annotated[int, Field(ge=0)]],
            messages={"greater_than_equal": "Choose a nonnegative value."},
        )
    assert code_message.value.field_errors["<key>"] == (
        "Choose a nonnegative value.",
    )


def test_backend_error_messages_do_not_expose_rejected_values() -> None:
    """Replace Pydantic validator text with a stable safe message.

    Custom application messages remain available through explicit overrides.
    """
    validator = Validator()
    sensitive_value = "credential-marker"

    with pytest.raises(ValidationException) as captured:
        validator.validate(
            {"credential": sensitive_value},
            SecretRejectedInput,
        )

    issue = captured.value.issues[0]
    assert issue.field == "credential"
    assert issue.code == "value_error"
    assert issue.message == "Input is invalid."
    assert sensitive_value not in str(captured.value)

    with pytest.raises(ValidationException) as overridden:
        validator.validate(
            {"credential": sensitive_value},
            SecretRejectedInput,
            messages={"credential": "Enter a valid credential."},
        )
    assert overridden.value.field_errors["credential"] == (
        "Enter a valid credential.",
    )
    assert sensitive_value not in str(overridden.value)


def test_dynamic_mapping_keys_are_not_exposed_as_field_locations() -> None:
    """Redact arbitrary mapping keys from public validation locations.

    Integer collection indices and declared schema field names remain useful.
    """
    dynamic_key = "token-marker"

    with pytest.raises(ValidationException) as captured:
        Validator().validate(
            {dynamic_key: "not-an-integer"},
            dict[str, int],
        )

    issue = captured.value.issues[0]
    assert issue.field == "<key>"
    assert dynamic_key not in str(captured.value)
    assert "not-an-integer" not in str(captured.value)


def test_malformed_backend_error_metadata_uses_safe_defaults() -> None:
    """Reject malformed backend codes, locations, and schema metadata.

    The public validation boundary keeps only bounded native diagnostics.
    """
    with pytest.raises(ValidationException) as captured:
        Validator().validate(
            _PRIVATE_VALIDATION_VALUE,
            _InvalidJsonSchemaInput,
        )

    issue = captured.value.issues[0]
    assert issue.code == "invalid_input"
    assert issue.message == "Input is invalid."
    assert _PRIVATE_VALIDATION_VALUE not in str(captured.value)


def test_non_string_mapping_keys_are_redacted_in_locations() -> None:
    """Redact mapping keys whose object representations are untrusted.

    Public issue locations must not call or expose arbitrary key values.
    """
    key = object()
    with pytest.raises(ValidationException) as captured:
        Validator().validate({key: "bad"}, dict[str, int])

    assert all("<key>" in issue.location for issue in captured.value.issues)
    assert repr(key) not in str(captured.value)


def test_validation_exception_requires_at_least_one_issue() -> None:
    """Prevent construction of an error with no rejected field.

    Native exceptions always have at least one safe issue to report.
    """
    with pytest.raises(ValueError, match="requires at least one issue"):
        ValidationException(())


def test_make_returns_success_and_failure_results() -> None:
    """Return a result object for validation flows that should not raise.

    Successful results retain data; failed results retain only issues.
    """
    validator = Validator()
    successful = validator.make({"count": 4}, dict[str, int])
    failed = validator.make({"count": "bad"}, dict[str, int])

    assert isinstance(successful, ValidationResult)
    assert successful.is_valid
    assert successful.data == {"count": 4}
    valid_none = validator.make(None, type(None))
    assert valid_none.is_valid
    assert valid_none.data is None
    assert not failed.is_valid
    assert failed.data is None
    assert failed.errors


def test_pydantic_field_fail_fast_stops_list_item_error_collection() -> None:
    """Use Pydantic's field-level fail-fast metadata for list validation.

    The framework does not implement a parallel schema validation engine.
    """

    class Numbers(BaseModel):
        """Validate a sequence with the schema's fail-fast policy.

        List item collection stops at the first invalid element.
        """

        values: Annotated[list[int], Field(fail_fast=True)]

    with pytest.raises(ValidationException) as captured:
        Validator().validate({"values": ["bad", "also-bad"]}, Numbers)

    assert len(captured.value.issues) == 1


def test_sync_reusable_rules_aggregate_or_stop_after_first_failure() -> None:
    """Apply reusable checks to validated data with explicit stop behavior.

    Rule failures retain application messages and field association.
    """
    checked: list[object] = []

    def blocked_name(value: object) -> bool:
        """Reject one reserved name in the validated model.

        Args:
            value: Validated mapping supplied to the reusable rule.

        Returns:
            Whether the name is permitted.
        """
        checked.append(value)
        return value != {"name": "blocked"}

    def reject_all(value: object) -> bool:
        """Always fail to make rule aggregation observable.

        Args:
            value: Validated mapping passed to this rule.

        Returns:
            Whether the value is accepted.
        """
        checked.append(value)
        return False

    rules = (
        ValidationRule("name", blocked_name, "This name is reserved."),
        ValidationRule("name", reject_all, "This name is unavailable."),
    )
    validator = Validator()

    accepted = validator.validate(
        {"name": "available"},
        dict[str, str],
        rules=(rules[0],),
    )
    assert accepted == {"name": "available"}

    with pytest.raises(ValidationException) as aggregated:
        validator.validate({"name": "blocked"}, dict[str, str], rules=rules)
    assert len(aggregated.value.issues) == _EXPECTED_RULE_ISSUES
    assert aggregated.value.field_errors["name"] == (
        "This name is reserved.",
        "This name is unavailable.",
    )

    checked.clear()
    with pytest.raises(ValidationException) as first_only:
        validator.validate(
            {"name": "blocked"},
            dict[str, str],
            rules=rules,
            stop_on_first_error=True,
        )
    assert len(first_only.value.issues) == 1
    assert len(checked) == 1


@pytest.mark.anyio
async def test_async_rules_run_explicitly_after_schema_validation() -> None:
    """Run asynchronous application checks through the async API only.

    Cancellation and exceptions from an async rule propagate unchanged.
    """

    async def account_is_available(value: object) -> bool:
        """Check a username after yielding to the async runtime.

        Args:
            value: Validated mapping supplied to the reusable rule.

        Returns:
            Whether the account name is available.
        """
        await anyio.lowlevel.checkpoint()
        return value != {"username": "taken"}

    rule = AsyncValidationRule(
        "username",
        account_is_available,
        "This username is already in use.",
    )
    result = await Validator().validate_async(
        {"username": "new"},
        dict[str, str],
        async_rules=[rule],
    )
    assert result == {"username": "new"}

    with pytest.raises(ValidationException) as captured:
        await Validator().validate_async(
            {"username": "taken"},
            dict[str, str],
            async_rules=[rule],
        )
    assert captured.value.field_errors["username"] == (
        "This username is already in use.",
    )
    failed_result = await Validator().make_async(
        {"username": "taken"},
        dict[str, str],
        async_rules=(rule,),
    )
    assert not failed_result.is_valid
    assert failed_result.errors[0].field == "username"

    calls: list[str] = []

    async def reject_and_record(value: object) -> bool:
        """Reject one value and retain execution order for assertions.

        Args:
            value: Schema-validated input supplied to the rule.

        Returns:
            Whether the value is accepted.
        """
        calls.append(
            "first" if value == {"username": "taken"} else "unexpected",
        )
        return False

    async def accept_and_record(value: object) -> bool:
        """Record a later rule that should be skipped in fail-fast mode.

        Args:
            value: Schema-validated input supplied to the rule.

        Returns:
            Whether the value is accepted.
        """
        calls.append(
            "second" if value == {"username": "taken"} else "unexpected",
        )
        return True

    with pytest.raises(ValidationException):
        await Validator().validate_async(
            {"username": "taken"},
            dict[str, str],
            async_rules=(
                AsyncValidationRule(
                    "username",
                    reject_and_record,
                    "The first rule rejected the username.",
                ),
                AsyncValidationRule(
                    "username",
                    accept_and_record,
                    "The second rule accepts the username.",
                ),
            ),
            stop_on_first_error=True,
        )
    assert calls == ["first"]

    def reject_sync(value: object) -> bool:
        """Reject a value before async rules are considered.

        Args:
            value: Complete schema-validated input.

        Returns:
            Whether the value passes the synchronous rule.
        """
        return value != {"username": "taken"}

    with pytest.raises(ValidationException):
        await Validator().validate_async(
            {"username": "taken"},
            dict[str, str],
            rules=(
                ValidationRule(
                    "username",
                    reject_sync,
                    "The sync rule rejected the username.",
                ),
            ),
            async_rules=(
                AsyncValidationRule(
                    "username",
                    reject_and_record,
                    "The async rule rejected the username.",
                ),
            ),
            stop_on_first_error=True,
        )
    assert calls == ["first"]


@pytest.mark.anyio
async def test_async_rule_cancellation_propagates_to_the_caller() -> None:
    """Propagate an enclosing AnyIO timeout through asynchronous rules.

    Validation creates no detached tasks and keeps cancellation structured.
    """

    async def wait_for_external_work(value: object) -> bool:
        """Wait until the caller cancels the validation operation.

        Args:
            value: Complete schema-validated data.

        Returns:
            Whether external work accepts the input.
        """
        _ = value
        await anyio.sleep_forever()
        return False

    with pytest.raises(TimeoutError):
        with anyio.fail_after(0.01):
            await Validator().validate_async(
                {"name": "Ada"},
                dict[str, str],
                async_rules=(
                    AsyncValidationRule(
                        "name",
                        wait_for_external_work,
                        "The name check did not finish.",
                    ),
                ),
            )


def test_application_rule_exceptions_propagate_unchanged() -> None:
    """Preserve failures raised by application-owned rule callbacks.

    Validation translates schema issues only, not application exceptions.
    """

    def unavailable(value: object) -> bool:
        """Raise a transport-shaped error from an external rule service.

        Args:
            value: Complete schema-validated input.

        Returns:
            Whether the input is available.

        Raises:
            RuntimeError: The external rule service is unavailable.
        """
        _ = value
        raise RuntimeError(_RULE_SERVICE_ERROR)

    with pytest.raises(RuntimeError, match="Rule service unavailable"):
        Validator().validate(
            {"name": "Ada"},
            dict[str, str],
            rules=(
                ValidationRule(
                    "name",
                    unavailable,
                    "The name could not be checked.",
                ),
            ),
        )


def test_sync_validation_requires_explicit_async_rule_execution() -> None:
    """Close a returned coroutine and require an explicit async API.

    Sync validation never starts or leaks application rule coroutines.
    """

    async def asynchronous_check(value: object) -> bool:
        """Return one result using an explicitly asynchronous signature.

        Args:
            value: Complete schema-validated value.

        Returns:
            Whether the value is accepted.
        """
        return bool(value)

    # This cast intentionally violates the sync callback type to verify that
    # runtime protection closes an accidental coroutine.
    with pytest.raises(AsyncValidationRequiredError):
        Validator().validate(
            {"name": "Ada"},
            dict[str, str],
            rules=(
                ValidationRule(
                    "name",
                    cast("ValidationRuleCheck", asynchronous_check),
                    "The name is unavailable.",
                ),
            ),
        )


def test_validation_configuration_rejects_malformed_defaults() -> None:
    """Reject invalid application defaults without exposing their values.

    Configuration shape and boolean types remain strict.
    """
    malformed = (
        Repository({"validation": []}),
        Repository({"validation": {"strict": "enabled"}}),
        Repository({"validation": {"unknown": True}}),
    )
    for repository in malformed:
        with pytest.raises(ValidationConfigurationError):
            ValidationConfiguration.from_repository(repository)


def _signup_values() -> dict[str, object]:
    """Return one representative valid signup mapping.

    Each call creates an independent shallow input mapping for mutation.
    """
    return {
        "name": "Ada Lovelace",
        "age": "32",
        "active": "true",
        "email": "ada@example.com",
        "homepage": "https://example.com/profile",
        "role": "reader",
        "birthday": "1994-05-17",
        "created_at": "2025-11-24T12:30:00Z",
        "labels": ["analysis", "science"],
        "address": {"city": "Colombo", "postal_code": "00100"},
    }
