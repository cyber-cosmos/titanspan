"""Validate application values through Pydantic's public TypeAdapter API.

Schema execution stays with Pydantic; this module adapts errors, rules, and
request input to stable Titanspan boundaries.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

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
    from collections.abc import Mapping, Sequence

    from titanspan.contracts.http import HttpRequest

_ASYNC_RULE_ERROR = "An asynchronous validation rule requires validate_async."


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
                for issue in _pydantic_issues(error)
            )
            raise ValidationException(issues) from None

    _configuration: ValidationConfiguration


def _pydantic_issues(error: ValidationError) -> tuple[ValidationIssue, ...]:
    """Extract safe locations, messages, and codes from Pydantic errors.

    Args:
        error: Validation failure from a Pydantic TypeAdapter.

    Returns:
        Ordered issues without input or context values.
    """
    details = error.errors(
        include_input=False,
        include_context=False,
        include_url=False,
    )
    return tuple(
        ValidationIssue(
            tuple(item["loc"]),
            item["msg"],
            item["type"],
        )
        for item in details
    )


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
