"""Test typed settings behavior used during application construction.

Environment parsing is isolated here; ASGI and dependency lifecycle behavior
is covered by the integration suite.
"""

import pytest
from pydantic import ValidationError

from titanspan.config import Settings

pytestmark = pytest.mark.unit


def test_settings_read_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read typed values from the configured environment variable prefix.

    Args:
        monkeypatch: Pytest fixture that restores process environment changes.
    """
    monkeypatch.setenv("TITANSPAN_DEBUG", "true")

    assert Settings().debug is True


def test_settings_reject_invalid_boolean_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject malformed booleans rather than silently accepting them.

    Args:
        monkeypatch: Pytest fixture that restores process environment changes.
    """
    monkeypatch.setenv("TITANSPAN_DEBUG", "sometimes")

    with pytest.raises(ValidationError):
        Settings()
