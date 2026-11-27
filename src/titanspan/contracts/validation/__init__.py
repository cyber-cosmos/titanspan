"""Define backend-independent types for application data validation.

Pydantic schema execution remains behind the Validation component boundary.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from typing_extensions import TypeForm

if TYPE_CHECKING:
    from titanspan.contracts.http.request import HttpRequest

type ValidationRuleCheck = Callable[[object], bool]
type AsyncValidationRuleCheck = Callable[[object], Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """Describe one rejected field without retaining its input value.

    Attributes:
        location: Nested field segments from the schema or custom rule.
        message: Safe, application-facing diagnostic text.
        code: Stable Pydantic error type or application rule code.
        attribute: Optional display label selected for the field.
    """

    location: tuple[str | int, ...]
    message: str
    code: str
    attribute: str | None = None

    @property
    def field(self) -> str:
        """Return the dotted field path represented by this issue.

        Model-level errors use an empty path.
        """
        return ".".join(str(segment) for segment in self.location)


@dataclass(frozen=True, slots=True)
class ValidationResult[OutputT]:
    """Hold valid data or the field issues produced by a validation call.

    Attributes:
        data: Validated value, which may itself be ``None``.
        errors: Ordered, immutable field issues.
    """

    data: OutputT | None
    errors: tuple[ValidationIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        """Report whether validation produced no issues.

        A valid schema may return ``None`` as its data value.
        """
        return not self.errors


@dataclass(frozen=True, slots=True)
class ValidationRule:
    """Associate a synchronous application check with a field path.

    The callback receives the schema-validated value. Use Pydantic field or
    model validators for constraints intrinsic to a reusable schema.

    Attributes:
        field: Dotted field path associated with a failed check.
        check: Predicate receiving the complete validated data value.
        message: Safe message used when the predicate returns ``False``.
        code: Stable application code for message customization.
    """

    field: str
    check: ValidationRuleCheck
    message: str
    code: str = "custom"


@dataclass(frozen=True, slots=True)
class AsyncValidationRule:
    """Associate an asynchronous application check with a field path.

    Async rules run sequentially after the Pydantic schema has succeeded.
    They do not replace schema or cross-field validation.

    Attributes:
        field: Dotted field path associated with a failed check.
        check: Awaitable predicate receiving validated data.
        message: Safe message used when the predicate returns ``False``.
        code: Stable application code for message customization.
    """

    field: str
    check: AsyncValidationRuleCheck
    message: str
    code: str = "custom"


class ValidationService(Protocol):
    """Validate values through one application-owned service boundary.

    Implementations preserve output types while keeping schema backends
    private. Async request methods parse through the native HTTP contract.
    """

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
            ValidationException: If the schema or rules reject the value.
        """
        ...

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
        """Validate through the explicit async application-rule path.

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
            ValidationException: If the schema or rules reject the value.
        """
        ...

    async def apply_rules_async[DataT](
        self,
        value: DataT,
        *,
        rules: Sequence[ValidationRule] = (),
        async_rules: Sequence[AsyncValidationRule] = (),
        messages: Mapping[str, str] | None = None,
        attribute_labels: Mapping[str, str] | None = None,
        stop_on_first_error: bool = False,
    ) -> DataT:
        """Apply application rules to an already schema-validated value.

        Use this operation when another trusted boundary, such as FastAPI,
        has already produced typed data from the declared schema.

        Args:
            value: Typed value produced by its owning schema boundary.
            rules: Ordered synchronous application checks.
            async_rules: Ordered asynchronous application checks.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display labels keyed by dotted field path.
            stop_on_first_error: Stop after the first failed rule.

        Returns:
            The same typed value after all rules pass.

        Raises:
            ValidationException: If an application rule rejects the value.
        """
        ...

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
        ...

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
        ...

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
        """Validate merged input from a native incoming request.

        Args:
            request: HTTP request whose input remains owned by HTTP.
            schema: Python or Pydantic-supported schema declaration.
            strict: Optional override for configured coercion behavior.
            from_attributes: Optional object extraction override.
            context: Context passed to Pydantic validators.
            rules: Reusable synchronous checks after schema validation.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom rule evaluation after one issue.

        Returns:
            Typed schema output.

        Raises:
            ValidationException: If the schema or rules reject the input.
        """
        ...

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
        """Validate request input with explicit asynchronous rules.

        Args:
            request: HTTP request whose input remains owned by HTTP.
            schema: Python or Pydantic-supported schema declaration.
            strict: Optional override for configured coercion behavior.
            from_attributes: Optional object extraction override.
            context: Context passed to Pydantic validators.
            rules: Reusable synchronous checks after schema validation.
            async_rules: Explicit asynchronous application checks.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom rule evaluation after one issue.

        Returns:
            Typed schema output.

        Raises:
            ValidationException: If the schema or rules reject the input.
        """
        ...


__all__ = [
    "AsyncValidationRule",
    "AsyncValidationRuleCheck",
    "ValidationIssue",
    "ValidationResult",
    "ValidationRule",
    "ValidationRuleCheck",
    "ValidationService",
]
