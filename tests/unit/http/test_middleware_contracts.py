"""Verify HTTP middleware contracts have one public identity.

The HTTP component re-exports the canonical shared contract objects.
"""

import pytest

from titanspan.contracts import (
    MiddlewareDeclaration as RootDeclaration,
)
from titanspan.contracts import (
    MiddlewareItem as RootMiddlewareItem,
)
from titanspan.contracts import (
    ParameterizedHttpMiddleware as RootParameterizedMiddleware,
)
from titanspan.contracts.http import (
    MiddlewareDeclaration as ContractDeclaration,
)
from titanspan.contracts.http import (
    MiddlewareItem as ContractMiddlewareItem,
)
from titanspan.contracts.http import (
    ParameterizedHttpMiddleware as ContractParameterizedMiddleware,
)
from titanspan.http import (
    MiddlewareDeclaration,
    MiddlewareItem,
    ParameterizedHttpMiddleware,
)

pytestmark = pytest.mark.unit


def test_http_component_reexports_canonical_middleware_contracts() -> None:
    """Keep component imports identical to shared contract definitions.

    Container keys and structural checks must use the same objects.
    """
    assert MiddlewareDeclaration is ContractDeclaration
    assert MiddlewareItem is ContractMiddlewareItem
    assert ParameterizedHttpMiddleware is ContractParameterizedMiddleware
    assert MiddlewareDeclaration is RootDeclaration
    assert MiddlewareItem is RootMiddlewareItem
    assert ParameterizedHttpMiddleware is RootParameterizedMiddleware
