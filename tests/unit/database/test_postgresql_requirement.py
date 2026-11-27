"""Verify PostgreSQL integration cannot silently skip in mandatory CI.

The test distinguishes local opt-in from required CI execution.
"""

from __future__ import annotations

import pytest
from tests.integration.database.test_postgresql import (
    configured_postgres_url,
)

pytestmark = pytest.mark.unit


def test_missing_postgres_url_fails_in_ci(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject missing PostgreSQL service configuration in CI.

    Args:
        monkeypatch: Pytest environment adapter for this test.
    """
    monkeypatch.setenv("TITANSPAN_REQUIRE_POSTGRES", "1")
    monkeypatch.delenv("TITANSPAN_TEST_POSTGRES_URL", raising=False)

    with pytest.raises(pytest.fail.Exception):
        configured_postgres_url()
