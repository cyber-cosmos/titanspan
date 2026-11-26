"""Expose application Validation through the active typed facade context.

The facade delegates every operation to the canonical ValidationService.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import TypeForm

from titanspan.contracts.validation import ValidationService
from titanspan.facades.base import Facade

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from titanspan.contracts.container import ServiceContainer
    from titanspan.contracts.http import HttpRequest
    from titanspan.contracts.validation import (
        AsyncValidationRule,
        ValidationResult,
        ValidationRule,
    )


class Validation(Facade[ValidationService]):
    """Resolve validation operations from the active application service graph.

    Explicit class methods keep the public API discoverable by Python tools.
    """

    service_contract = ValidationService

    @classmethod
    def resolve_from_container(
        cls,
        container: ServiceContainer,
    ) -> ValidationService:
        """Resolve the canonical application Validation service.

        Args:
            container: Active application service registry.

        Returns:
            The same service available through dependency injection.
        """
        _ = cls
        return container.make(ValidationService)

    @classmethod
    def validate[OutputT](  # noqa: PLR0913
        cls,
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
        """Validate one value synchronously through the active service.

        Args:
            value: Untrusted mapping or Python object.
            schema: Native Python or Pydantic-supported schema.
            strict: Optional per-call coercion policy.
            from_attributes: Optional object-attribute extraction policy.
            context: Context passed to schema validators.
            rules: Ordered reusable synchronous application rules.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom checks after the first failure.

        Returns:
            Typed schema output.
        """
        return cls.resolve_service().validate(
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

    @classmethod
    async def validate_async[OutputT](  # noqa: PLR0913
        cls,
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
        """Validate schema data with explicit asynchronous application rules.

        Args:
            value: Untrusted mapping or Python object.
            schema: Native Python or Pydantic-supported schema.
            strict: Optional per-call coercion policy.
            from_attributes: Optional object-attribute extraction policy.
            context: Context passed to schema validators.
            rules: Ordered reusable synchronous application rules.
            async_rules: Ordered asynchronous application rules.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom checks after the first failure.

        Returns:
            Typed schema output.
        """
        return await cls.resolve_service().validate_async(
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

    @classmethod
    def make[OutputT](  # noqa: PLR0913
        cls,
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
        """Return validated data or field issues without raising.

        Args:
            value: Untrusted mapping or Python object.
            schema: Native Python or Pydantic-supported schema.
            strict: Optional per-call coercion policy.
            from_attributes: Optional object-attribute extraction policy.
            context: Context passed to schema validators.
            rules: Ordered reusable synchronous application rules.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom checks after the first failure.

        Returns:
            An immutable result containing data or validation issues.
        """
        return cls.resolve_service().make(
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

    @classmethod
    async def make_async[OutputT](  # noqa: PLR0913
        cls,
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
        """Return schema and async-rule results without raising issues.

        Args:
            value: Untrusted mapping or Python object.
            schema: Native Python or Pydantic-supported schema.
            strict: Optional per-call coercion policy.
            from_attributes: Optional object-attribute extraction policy.
            context: Context passed to schema validators.
            rules: Ordered reusable synchronous application rules.
            async_rules: Ordered asynchronous application rules.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom checks after the first failure.

        Returns:
            An immutable result containing data or validation issues.
        """
        return await cls.resolve_service().make_async(
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

    @classmethod
    async def validate_request[OutputT](  # noqa: PLR0913
        cls,
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
        """Validate merged input from the native HTTP request.

        Args:
            request: Incoming request whose body remains HTTP-owned.
            schema: Native Python or Pydantic-supported schema.
            strict: Optional per-call coercion policy.
            from_attributes: Optional object-attribute extraction policy.
            context: Context passed to schema validators.
            rules: Ordered reusable synchronous application rules.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom checks after the first failure.

        Returns:
            Typed schema output.
        """
        return await cls.resolve_service().validate_request(
            request,
            schema,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            rules=rules,
            messages=messages,
            attribute_labels=attribute_labels,
            stop_on_first_error=stop_on_first_error,
        )

    @classmethod
    async def validate_request_async[OutputT](  # noqa: PLR0913
        cls,
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
        """Validate native HTTP input with asynchronous application rules.

        Args:
            request: Incoming request whose body remains HTTP-owned.
            schema: Native Python or Pydantic-supported schema.
            strict: Optional per-call coercion policy.
            from_attributes: Optional object-attribute extraction policy.
            context: Context passed to schema validators.
            rules: Ordered reusable synchronous application rules.
            async_rules: Ordered asynchronous application rules.
            messages: Error-code or field-path message overrides.
            attribute_labels: Display names keyed by dotted field path.
            stop_on_first_error: Stop custom checks after the first failure.

        Returns:
            Typed schema output.
        """
        return await cls.resolve_service().validate_request_async(
            request,
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


__all__ = ["Validation"]
