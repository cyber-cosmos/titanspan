"""Verify Validation contracts and services use canonical export identities.

Convenience imports must re-export the same boundary objects.
"""

import pytest

from titanspan.contracts import (
    AsyncValidationRule,
    ValidationIssue,
    ValidationResult,
    ValidationRule,
    ValidationService,
)
from titanspan.contracts.validation import (
    AsyncValidationRule as DomainAsyncValidationRule,
)
from titanspan.contracts.validation import (
    ValidationIssue as DomainValidationIssue,
)
from titanspan.contracts.validation import (
    ValidationResult as DomainValidationResult,
)
from titanspan.contracts.validation import (
    ValidationRule as DomainValidationRule,
)
from titanspan.contracts.validation import (
    ValidationService as DomainValidationService,
)
from titanspan.facades import Validation
from titanspan.validation import (
    AsyncValidationRule as ComponentAsyncValidationRule,
)
from titanspan.validation import (
    ValidationIssue as ComponentValidationIssue,
)
from titanspan.validation import (
    ValidationResult as ComponentValidationResult,
)
from titanspan.validation import (
    ValidationRule as ComponentValidationRule,
)
from titanspan.validation import (
    ValidationService as ComponentValidationService,
)

pytestmark = pytest.mark.unit


def test_contract_and_component_exports_preserve_canonical_objects() -> None:
    """Expose each contract through the root and owning component.

    The facade names only the service contract and adds no competing API.
    """
    assert AsyncValidationRule is DomainAsyncValidationRule
    assert AsyncValidationRule is ComponentAsyncValidationRule
    assert ValidationIssue is DomainValidationIssue
    assert ValidationIssue is ComponentValidationIssue
    assert ValidationResult is DomainValidationResult
    assert ValidationResult is ComponentValidationResult
    assert ValidationRule is DomainValidationRule
    assert ValidationRule is ComponentValidationRule
    assert ValidationService is DomainValidationService
    assert ValidationService is ComponentValidationService
    assert Validation.service_contract is ValidationService
