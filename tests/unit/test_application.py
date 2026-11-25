"""Test typed settings behavior used during application construction.

Environment parsing is isolated here; ASGI and dependency lifecycle behavior
is covered by the integration suite.
"""

from pathlib import Path

import pytest

from titanspan.config import Settings, SettingsValidationError
from titanspan.foundation import Application

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

    with pytest.raises(SettingsValidationError):
        Settings()


def test_application_exposes_its_typed_settings_lazily(
    tmp_path: Path,
) -> None:
    """Expose the exact Settings instance used during bootstrap.

    Args:
        tmp_path: Isolated temporary directory for application sources.
    """
    settings = Settings(app_name="Configured")
    application = Application(base_path=tmp_path, settings=settings)

    assert application.settings is settings
