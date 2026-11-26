"""Expose the native Pydantic-backed application Validation component.

Pydantic owns schema validation; Titanspan adds service integration, rules,
and safe field-oriented errors.
"""

from titanspan.contracts.validation import (
    AsyncValidationRule,
    AsyncValidationRuleCheck,
    ValidationIssue,
    ValidationResult,
    ValidationRule,
    ValidationRuleCheck,
    ValidationService,
)
from titanspan.validation.configuration import ValidationConfiguration
from titanspan.validation.exceptions import (
    AsyncValidationRequiredError,
    ValidationConfigurationError,
    ValidationException,
)
from titanspan.validation.service_provider import ValidationServiceProvider
from titanspan.validation.validator import Validator

__all__ = [
    "AsyncValidationRequiredError",
    "AsyncValidationRule",
    "AsyncValidationRuleCheck",
    "ValidationConfiguration",
    "ValidationConfigurationError",
    "ValidationException",
    "ValidationIssue",
    "ValidationResult",
    "ValidationRule",
    "ValidationRuleCheck",
    "ValidationService",
    "ValidationServiceProvider",
    "Validator",
]
