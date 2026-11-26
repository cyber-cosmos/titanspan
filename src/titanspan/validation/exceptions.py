"""Define native errors raised by the Validation component.

Error objects retain field paths and messages, not rejected input values.
"""

from collections.abc import Mapping
from types import MappingProxyType

from titanspan.contracts.validation import ValidationIssue

_EMPTY_ISSUES_ERROR = "A validation failure requires at least one issue."
_GENERIC_ATTRIBUTE = "value"


class ValidationException(ValueError):
    """Report schema or application-rule failures with safe field details.

    Attributes:
        issues: Ordered native issues without original input values.
        field_errors: Read-only field paths mapped to error message tuples.
    """

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        """Create a native error with an immutable field-error snapshot.

        Args:
            issues: Ordered, safe details for rejected fields.

        Raises:
            ValueError: If no issue was supplied.
        """
        if not issues:
            raise ValueError(_EMPTY_ISSUES_ERROR)
        self.issues = tuple(issues)
        grouped: dict[str, list[str]] = {}
        for issue in self.issues:
            grouped.setdefault(issue.field, []).append(issue.message)
        self.field_errors = MappingProxyType(
            {field: tuple(messages) for field, messages in grouped.items()}
        )
        summary = "; ".join(
            f"{issue.attribute or issue.field or _GENERIC_ATTRIBUTE}: "
            f"{issue.message}"
            for issue in self.issues
        )
        super().__init__(f"Validation failed: {summary}")

    issues: tuple[ValidationIssue, ...]
    field_errors: Mapping[str, tuple[str, ...]]


class ValidationConfigurationError(ValueError):
    """Report invalid Validation settings without retaining their values.

    Callers can correct the ``validation`` namespace in their configuration.
    """


class AsyncValidationRequiredError(RuntimeError):
    """Require explicit async execution for an asynchronous validation rule.

    Sync validation does not create an event loop or discard async work.
    """


__all__ = [
    "AsyncValidationRequiredError",
    "ValidationConfigurationError",
    "ValidationException",
]
