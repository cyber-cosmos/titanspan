"""Validate application values through Pydantic's public TypeAdapter API.

Schema execution stays with Pydantic; this module adapts errors, rules, and
request input to stable Titanspan boundaries.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from pydantic import TypeAdapter, ValidationError
from typing_extensions import TypeForm

from titanspan.contracts.validation import (
    AsyncValidationRule,
    ValidationIssue,
    ValidationResult,
    ValidationRule,
)
from titanspan.validation.configuration import ValidationConfiguration
from titanspan.validation.exceptions import (
    AsyncValidationRequiredError,
    ValidationException,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from titanspan.contracts.http import HttpRequest

_ASYNC_RULE_ERROR = "An asynchronous validation rule requires validate_async."
_SAFE_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z", re.ASCII)
_SAFE_ERROR_MESSAGES = {
    "bool_parsing": "Input should be a valid boolean",
    "bool_type": "Input should be a valid boolean",
    "float_parsing": "Input should be a valid number",
    "float_type": "Input should be a valid number",
    "int_parsing": "Input should be a valid integer",
    "int_type": "Input should be a valid integer",
    "list_type": "Input should be a valid list",
    "missing": "Field is required.",
    "string_type": "Input should be a valid string",
    "string_too_long": "Input is too long.",
    "string_too_short": "Input is too short.",
    "value_error": "Input is invalid.",
    "assertion_error": "Input is invalid.",
}
_SAFE_LOCATION_SEGMENTS = frozenset(
    {"body", "cookie", "header", "path", "query"},
)
_REDACTED_MAPPING_KEY = "<key>"
_GENERIC_INVALID_INPUT = "Input is invalid."


class Validator:
    """Validate Python and Pydantic schemas with safe native errors.

    Pydantic owns schema parsing and validation. Application rules run only
    after a schema succeeds; async rules use explicit async methods.
    """

    __slots__ = ("_configuration",)

    def __init__(
        self,
        configuration: ValidationConfiguration | None = None,
    ) -> None:
        """Create a stateless validator with optional application defaults.

        Args:
            configuration: Immutable defaults supplied by the service
                provider or a standalone caller.
        """
        self._configuration = (
            ValidationConfiguration()
            if configuration is None
            else configuration
        )

    def validate[OutputT](  # noqa: PLR0913
        self,
        value: object,
        schema: TypeForm[OutputT],
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: Mapping[str, object] | None = None,
        rules: Sequence[ValidationRule] = (),
        messages: Mapping[str, str] | None = None,
        attribute_labels: Mapping[str, str] | None = None,
        stop_on_first_error: bool = False,
    ) -> OutputT:
        """Validate one value synchronously and raise native issues.

        Args:
            value: Mapping or Python object supplied for validation.
            schema: Python or Pydantic-supported schema declaration.
            strict: Optional override for configured coercion behavior.
            from_attributes: Optional object-attribute extraction policy.
            context: Context passed to Pydantic validators.
            rules: Reusable synchronous checks after schema validation.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom rule evaluation after one issue.

        Returns:
            Typed schema output.

        Raises:
            ValidationException: If the schema or a rule rejects the value.
            AsyncValidationRequiredError: If a rule returns an awaitable.
        """
        validated = self._validate_schema(
            value,
            schema,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            messages=messages,
            attribute_labels=attribute_labels,
        )
        issues = _sync_rule_issues(
            validated,
            rules,
            messages=messages,
            attribute_labels=attribute_labels,
            stop_on_first_error=stop_on_first_error,
        )
        if issues:
            raise ValidationException(issues)
        return validated

    async def validate_async[OutputT](  # noqa: PLR0913
        self,
        value: object,
        schema: TypeForm[OutputT],
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: Mapping[str, object] | None = None,
        rules: Sequence[ValidationRule] = (),
        async_rules: Sequence[AsyncValidationRule] = (),
        messages: Mapping[str, str] | None = None,
        attribute_labels: Mapping[str, str] | None = None,
        stop_on_first_error: bool = False,
    ) -> OutputT:
        """Validate through explicit async application-rule execution.

        Pydantic validates the schema before sequential custom checks run.
        Cancellation from an async rule propagates to its caller.

        Args:
            value: Mapping or Python object supplied for validation.
            schema: Python or Pydantic-supported schema declaration.
            strict: Optional override for configured coercion behavior.
            from_attributes: Optional object-attribute extraction policy.
            context: Context passed to Pydantic validators.
            rules: Reusable synchronous checks after schema validation.
            async_rules: Explicit asynchronous application checks.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom rule evaluation after one issue.

        Returns:
            Typed schema output.

        Raises:
            ValidationException: If the schema or a rule rejects the value.
        """
        validated = self._validate_schema(
            value,
            schema,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            messages=messages,
            attribute_labels=attribute_labels,
        )
        issues = _sync_rule_issues(
            validated,
            rules,
            messages=messages,
            attribute_labels=attribute_labels,
            stop_on_first_error=stop_on_first_error,
        )
        if stop_on_first_error and issues:
            raise ValidationException(issues)
        for rule in async_rules:
            if await rule.check(validated):
                continue
            issues = (
                *issues,
                _rule_issue(
                    rule.field,
                    rule.message,
                    rule.code,
                    messages=messages,
                    attribute_labels=attribute_labels,
                ),
            )
            if stop_on_first_error:
                break
        if issues:
            raise ValidationException(issues)
        return validated

    def make[OutputT](  # noqa: PLR0913
        self,
        value: object,
        schema: TypeForm[OutputT],
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: Mapping[str, object] | None = None,
        rules: Sequence[ValidationRule] = (),
        messages: Mapping[str, str] | None = None,
        attribute_labels: Mapping[str, str] | None = None,
        stop_on_first_error: bool = False,
    ) -> ValidationResult[OutputT]:
        """Return schema output or aggregated issues without raising.

        Args:
            value: Mapping or Python object supplied for validation.
            schema: Python or Pydantic-supported schema declaration.
            strict: Optional override for configured coercion behavior.
            from_attributes: Optional object-attribute extraction policy.
            context: Context passed to Pydantic validators.
            rules: Reusable synchronous checks after schema validation.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom rule evaluation after one issue.

        Returns:
            An immutable success or failure result.
        """
        try:
            data = self.validate(
                value,
                schema,
                strict=strict,
                from_attributes=from_attributes,
                context=context,
                rules=rules,
                messages=messages,
                attribute_labels=attribute_labels,
                stop_on_first_error=stop_on_first_error,
            )
        except ValidationException as error:
            return ValidationResult(None, error.issues)
        return ValidationResult(data)

    async def make_async[OutputT](  # noqa: PLR0913
        self,
        value: object,
        schema: TypeForm[OutputT],
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: Mapping[str, object] | None = None,
        rules: Sequence[ValidationRule] = (),
        async_rules: Sequence[AsyncValidationRule] = (),
        messages: Mapping[str, str] | None = None,
        attribute_labels: Mapping[str, str] | None = None,
        stop_on_first_error: bool = False,
    ) -> ValidationResult[OutputT]:
        """Return async rule results without raising validation issues.

        Args:
            value: Mapping or Python object supplied for validation.
            schema: Python or Pydantic-supported schema declaration.
            strict: Optional override for configured coercion behavior.
            from_attributes: Optional object-attribute extraction policy.
            context: Context passed to Pydantic validators.
            rules: Reusable synchronous checks after schema validation.
            async_rules: Explicit asynchronous application checks.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom rule evaluation after one issue.

        Returns:
            An immutable success or failure result.
        """
        try:
            data = await self.validate_async(
                value,
                schema,
                strict=strict,
                from_attributes=from_attributes,
                context=context,
                rules=rules,
                async_rules=async_rules,
                messages=messages,
                attribute_labels=attribute_labels,
                stop_on_first_error=stop_on_first_error,
            )
        except ValidationException as error:
            return ValidationResult(None, error.issues)
        return ValidationResult(data)

    async def validate_request[OutputT](  # noqa: PLR0913
        self,
        request: HttpRequest,
        schema: TypeForm[OutputT],
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: Mapping[str, object] | None = None,
        rules: Sequence[ValidationRule] = (),
        messages: Mapping[str, str] | None = None,
        attribute_labels: Mapping[str, str] | None = None,
        stop_on_first_error: bool = False,
    ) -> OutputT:
        """Validate merged values from the authoritative native request.

        HTTP parses and owns the request body. This method reads through the
        request contract and does not add a competing request parser.

        Args:
            request: HTTP request whose input remains owned by HTTP.
            schema: Python or Pydantic-supported schema declaration.
            strict: Optional override for configured coercion behavior.
            from_attributes: Optional object extraction policy.
            context: Context passed to Pydantic validators.
            rules: Reusable synchronous checks after schema validation.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom rule evaluation after one issue.

        Returns:
            Typed schema output.

        Raises:
            ValidationException: If the schema or a rule rejects the input.
        """
        value = await request.all()
        return self.validate(
            value,
            schema,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            rules=rules,
            messages=messages,
            attribute_labels=attribute_labels,
            stop_on_first_error=stop_on_first_error,
        )

    async def validate_request_async[OutputT](  # noqa: PLR0913
        self,
        request: HttpRequest,
        schema: TypeForm[OutputT],
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: Mapping[str, object] | None = None,
        rules: Sequence[ValidationRule] = (),
        async_rules: Sequence[AsyncValidationRule] = (),
        messages: Mapping[str, str] | None = None,
        attribute_labels: Mapping[str, str] | None = None,
        stop_on_first_error: bool = False,
    ) -> OutputT:
        """Validate native request input with async application checks.

        Args:
            request: HTTP request whose input remains owned by HTTP.
            schema: Python or Pydantic-supported schema declaration.
            strict: Optional override for configured coercion behavior.
            from_attributes: Optional object extraction policy.
            context: Context passed to Pydantic validators.
            rules: Reusable synchronous checks after schema validation.
            async_rules: Explicit asynchronous application checks.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom rule evaluation after one issue.

        Returns:
            Typed schema output.

        Raises:
            ValidationException: If the schema or a rule rejects the input.
        """
        value = await request.all()
        return await self.validate_async(
            value,
            schema,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            rules=rules,
            async_rules=async_rules,
            messages=messages,
            attribute_labels=attribute_labels,
            stop_on_first_error=stop_on_first_error,
        )

    def _validate_schema[OutputT](  # noqa: PLR0913
        self,
        value: object,
        schema: TypeForm[OutputT],
        *,
        strict: bool | None,
        from_attributes: bool | None,
        context: Mapping[str, object] | None,
        messages: Mapping[str, str] | None,
        attribute_labels: Mapping[str, str] | None,
    ) -> OutputT:
        """Apply a Pydantic adapter and translate only backend errors.

        Args:
            value: Untrusted Python input.
            schema: Supported Pydantic schema declaration.
            strict: Optional policy override.
            from_attributes: Optional object extraction override.
            context: Caller-provided validator context.
            messages: Optional safe message overrides.
            attribute_labels: Optional display labels.

        Returns:
            The value returned by Pydantic's public adapter.

        Raises:
            ValidationException: If Pydantic rejects the input.
        """
        adapter: TypeAdapter[OutputT] = TypeAdapter(schema)
        try:
            return adapter.validate_python(
                value,
                strict=(
                    self._configuration.strict if strict is None else strict
                ),
                from_attributes=(
                    self._configuration.from_attributes
                    if from_attributes is None
                    else from_attributes
                ),
                context=context,
            )
        except ValidationError as error:
            issues = tuple(
                _with_error_options(
                    issue,
                    messages=messages,
                    attribute_labels=attribute_labels,
                )
                for issue in _pydantic_issues(error, adapter)
            )
            raise ValidationException(issues) from None

    _configuration: ValidationConfiguration


def _pydantic_issues[OutputT](
    error: ValidationError,
    adapter: TypeAdapter[OutputT],
) -> tuple[ValidationIssue, ...]:
    """Extract safe locations, messages, and codes from Pydantic errors.

    Args:
        error: Validation failure from a Pydantic TypeAdapter.
        adapter: Adapter used for the failed schema validation.

    Returns:
        Ordered issues without input or context values.
    """
    details = error.errors(
        include_input=False,
        include_context=False,
        include_url=False,
    )
    schema_fields = _schema_field_names(adapter)
    return tuple(
        ValidationIssue(
            _safe_location(item["loc"], schema_fields),
            _SAFE_ERROR_MESSAGES.get(
                _safe_error_code(item["type"]),
                _GENERIC_INVALID_INPUT,
            ),
            _safe_error_code(item["type"]),
        )
        for item in details
    )


def _safe_error_code(value: object) -> str:
    """Keep a bounded stable code and reject arbitrary backend text.

    Args:
        value: Pydantic error type supplied by the backend.

    Returns:
        A safe lowercase code or a generic code.
    """
    if isinstance(value, str) and _SAFE_ERROR_CODE.fullmatch(value):
        return value
    return "invalid_input"


def _schema_field_names[OutputT](
    adapter: TypeAdapter[OutputT],
) -> frozenset[str]:
    """Collect declared JSON Schema field names for safe error locations.

    Args:
        adapter: Adapter used by the failed validation.

    Returns:
        Declared property names, or an empty set if schema export fails.
    """
    try:
        schema = adapter.json_schema(mode="validation")
    except Exception:
        # Custom schema hooks must not replace the original validation error.
        return frozenset()
    fields: set[str] = set()
    pending: list[object] = [schema]
    while pending:
        current = pending.pop()
        if isinstance(current, Mapping):
            current_mapping = cast("Mapping[object, object]", current)
            properties = current_mapping.get("properties")
            if isinstance(properties, Mapping):
                property_mapping = cast(
                    "Mapping[object, object]",
                    properties,
                )
                fields.update(
                    key for key in property_mapping if isinstance(key, str)
                )
            pending.extend(current_mapping.values())
        elif isinstance(current, list):
            pending.extend(cast("list[object]", current))
    return frozenset(fields)


def _safe_location(
    value: object,
    schema_fields: frozenset[str],
) -> tuple[str | int, ...]:
    """Retain declared fields and redact untrusted dynamic mapping keys.

    Args:
        value: Location tuple returned by Pydantic.
        schema_fields: Names declared by the validated JSON Schema.

    Returns:
        A bounded path without arbitrary input-derived string segments.
    """
    if not isinstance(value, tuple):
        return ()
    segments: list[str | int] = []
    for segment in cast("tuple[object, ...]", value):
        if isinstance(segment, int):
            segments.append(segment)
        elif isinstance(segment, str):
            if segment in schema_fields or segment in _SAFE_LOCATION_SEGMENTS:
                segments.append(segment)
            else:
                segments.append(_REDACTED_MAPPING_KEY)
        else:
            segments.append(_REDACTED_MAPPING_KEY)
    return tuple(segments)


def _sync_rule_issues(
    value: object,
    rules: Sequence[ValidationRule],
    *,
    messages: Mapping[str, str] | None,
    attribute_labels: Mapping[str, str] | None,
    stop_on_first_error: bool,
) -> tuple[ValidationIssue, ...]:
    """Run synchronous checks against schema-validated data in order.

    Args:
        value: Typed data returned by the schema adapter.
        rules: Ordered application checks.
        messages: Optional safe message overrides.
        attribute_labels: Optional display labels.
        stop_on_first_error: Whether to stop after one rejected check.

    Returns:
        Ordered issues produced by failed rules.

    Raises:
        AsyncValidationRequiredError: If a sync rule returns an awaitable.
    """
    issues: list[ValidationIssue] = []
    for rule in rules:
        accepted = rule.check(value)
        if inspect.isawaitable(accepted):
            if inspect.iscoroutine(accepted):
                accepted.close()
            raise AsyncValidationRequiredError(_ASYNC_RULE_ERROR)
        if accepted:
            continue
        issues.append(
            _rule_issue(
                rule.field,
                rule.message,
                rule.code,
                messages=messages,
                attribute_labels=attribute_labels,
            )
        )
        if stop_on_first_error:
            break
    return tuple(issues)


def _rule_issue(
    field: str,
    message: str,
    code: str,
    *,
    messages: Mapping[str, str] | None,
    attribute_labels: Mapping[str, str] | None,
) -> ValidationIssue:
    """Build a field issue for one failed application rule.

    Args:
        field: Dotted application field path.
        message: Rule's default user-facing message.
        code: Stable application rule code.
        messages: Optional safe message overrides.
        attribute_labels: Optional display labels.

    Returns:
        A native issue with no rejected input value.
    """
    location = tuple(segment for segment in field.split(".") if segment)
    return _with_error_options(
        ValidationIssue(location, message, code),
        messages=messages,
        attribute_labels=attribute_labels,
    )


def _with_error_options(
    issue: ValidationIssue,
    *,
    messages: Mapping[str, str] | None,
    attribute_labels: Mapping[str, str] | None,
) -> ValidationIssue:
    """Apply safe field-path messages and optional human-readable labels.

    Args:
        issue: Pydantic or application-rule validation issue.
        messages: Message overrides keyed by field path or error code.
        attribute_labels: Labels keyed by field path.

    Returns:
        A replacement issue with its selected message and label.
    """
    field = issue.field
    message = issue.message
    if messages is not None:
        message = messages.get(field, messages.get(issue.code, message))
    label = None if attribute_labels is None else attribute_labels.get(field)
    return ValidationIssue(issue.location, message, issue.code, label)


__all__ = ["Validator"]
