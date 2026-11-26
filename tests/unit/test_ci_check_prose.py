"""Verify the repository prose target's blocking rule selection.

The terminology target reports canonical language errors only.
"""

from __future__ import annotations

import pytest
from scripts.ci.check_prose import (
    Alert,
    _report,  # pyright: ignore[reportPrivateUsage]
)

pytestmark = pytest.mark.unit


def test_terminology_report_excludes_prohibited_expression_rule() -> None:
    """Keep prohibited language in prose checks, not terminology checks.

    Returns:
        None.
    """
    alerts = [
        Alert(
            path="docs/example.md",
            line=1,
            check="Titanspan.ProhibitedExpressions",
            severity="error",
            message="Avoid the prohibited expression.",
        )
    ]

    assert _report(alerts, terminology_only=True) is False
