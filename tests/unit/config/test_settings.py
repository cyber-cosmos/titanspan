"""Verify the native typed settings abstraction and safe validation errors.

Pydantic Settings remains an internal validation engine while applications
inherit from the Titanspan-owned ``Settings`` base.
"""

import os
from pathlib import Path

import pytest

from titanspan.config import Settings, SettingsValidationError

pytestmark = pytest.mark.unit
_ENV_WORKER_COUNT = "5"
_PARSED_WORKER_COUNT = 5


class WorkerSettings(Settings):
    """Define typed worker configuration for settings source tests.

    Attributes:
        workers: Number of worker processes configured for the application.
    """

    workers: int = 2


def test_settings_load_typed_fields_from_an_explicit_environment_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parse a selected dotenv file without modifying process environment.

    Args:
        tmp_path: Temporary location for the source file.
        monkeypatch: Fixture that isolates the process environment.

    Returns:
        None.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TITANSPAN_APP_NAME=File application\n"
        "TITANSPAN_DEBUG=true\n"
        f"TITANSPAN_WORKERS={_ENV_WORKER_COUNT}\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TITANSPAN_APP_NAME", raising=False)
    monkeypatch.delenv("TITANSPAN_DEBUG", raising=False)
    monkeypatch.delenv("TITANSPAN_WORKERS", raising=False)

    settings = WorkerSettings.from_environment(env_file=env_file)

    assert settings.app_name == "File application"
    assert settings.debug is True
    assert settings.workers == _PARSED_WORKER_COUNT
    assert "TITANSPAN_APP_NAME" not in os.environ


def test_settings_validation_errors_do_not_include_rejected_values(
    tmp_path: Path,
) -> None:
    """Translate Pydantic validation details into a native safe exception.

    Args:
        tmp_path: Temporary location for the invalid environment file.

    Returns:
        None.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TITANSPAN_DEBUG=do-not-disclose-this-value\n",
        encoding="utf-8",
    )

    with pytest.raises(SettingsValidationError) as error:
        Settings.from_environment(env_file=env_file)

    assert "debug" in str(error.value)
    assert "do-not-disclose-this-value" not in str(error.value)


def test_settings_repr_redacts_secret_named_fields() -> None:
    """Keep secret-shaped typed fields out of representation output.

    Returns:
        None.
    """

    class CredentialSettings(Settings):
        """Describe credentials without exposing them in diagnostics.

        Attributes:
            api_key: Secret configured for a third-party API client.
        """

        api_key: str = "private-value"

    settings = CredentialSettings()

    assert "private-value" not in repr(settings)
    assert "private-value" not in str(settings)
    assert settings.redacted()["api_key"] == "[REDACTED]"
