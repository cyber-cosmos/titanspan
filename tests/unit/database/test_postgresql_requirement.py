"""Verify PostgreSQL integration cannot silently skip in mandatory CI.

The test distinguishes local opt-in from required CI execution.
"""

from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url
from tests.integration.database.postgresql_support import (
    configured_postgres_url,
)

pytestmark = pytest.mark.unit
_POSTGRES_TEST_PORT = 5432
_SYNTHETIC_CREDENTIAL = "p@ss/word"  # pragma: allowlist secret


def test_missing_postgres_url_fails_in_ci(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject missing PostgreSQL service configuration in CI.

    Args:
        monkeypatch: Pytest environment adapter for this test.
    """
    monkeypatch.setenv("TITANSPAN_REQUIRE_POSTGRES", "1")
    monkeypatch.delenv("TITANSPAN_TEST_POSTGRES_URL", raising=False)
    monkeypatch.delenv("TITANSPAN_TEST_POSTGRES_USER", raising=False)
    monkeypatch.delenv("TITANSPAN_TEST_POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("TITANSPAN_TEST_POSTGRES_HOST", raising=False)
    monkeypatch.delenv("TITANSPAN_TEST_POSTGRES_PORT", raising=False)
    monkeypatch.delenv("TITANSPAN_TEST_POSTGRES_DATABASE", raising=False)

    with pytest.raises(pytest.fail.Exception):
        configured_postgres_url()


def test_postgres_url_uses_safe_structured_connection_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Build a URL with safely encoded credentials when CI provides parts.

    Args:
        monkeypatch: Pytest environment adapter for this test.
    """
    monkeypatch.setenv("TITANSPAN_REQUIRE_POSTGRES", "1")
    monkeypatch.delenv("TITANSPAN_TEST_POSTGRES_URL", raising=False)
    monkeypatch.setenv("TITANSPAN_TEST_POSTGRES_USER", "postgres")
    monkeypatch.setenv(
        "TITANSPAN_TEST_POSTGRES_PASSWORD",
        _SYNTHETIC_CREDENTIAL,
    )
    monkeypatch.setenv("TITANSPAN_TEST_POSTGRES_HOST", "localhost")
    monkeypatch.setenv(
        "TITANSPAN_TEST_POSTGRES_PORT",
        str(_POSTGRES_TEST_PORT),
    )
    monkeypatch.setenv(
        "TITANSPAN_TEST_POSTGRES_DATABASE",
        "titanspan_codex_test_ci",
    )

    url = make_url(configured_postgres_url())

    assert url.drivername == "postgresql+psycopg"
    assert url.username == "postgres"
    assert url.password == _SYNTHETIC_CREDENTIAL
    assert url.host == "localhost"
    assert url.port == _POSTGRES_TEST_PORT
    assert url.database == "titanspan_codex_test_ci"
