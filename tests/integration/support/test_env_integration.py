"""Verify Env interoperates with process-backed application settings.

The integration checks compare environment reads with Pydantic Settings.
"""

from __future__ import annotations

import importlib
import os
from contextvars import ContextVar

import pytest

from titanspan.config import Settings
from titanspan.support import Env


@pytest.fixture(autouse=True)
def isolate_environment_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset context-local adapters around integration checks.

    Returns:
        None after the previous context state has been restored.
    """
    module = importlib.import_module("titanspan.support.env")
    test_state: ContextVar[object | None] = ContextVar(
        "titanspan_environment_integration_test",
        default=None,
    )
    monkeypatch.setattr(module, "_ENV_STATE", test_state)


@pytest.mark.integration
def test_env_and_pydantic_settings_read_the_same_process_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the same process variable source as application settings.

    Args:
        monkeypatch: Fixture that restores process environment changes.

    Returns:
        None.
    """
    monkeypatch.setenv("TITANSPAN_DEBUG", "true")

    assert Env.get("TITANSPAN_DEBUG") is True
    assert Settings().debug is True


@pytest.mark.integration
def test_env_reads_do_not_mutate_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep normalized reads separate from process environment mutation.

    Args:
        monkeypatch: Fixture that restores process environment changes.

    Returns:
        None.
    """
    monkeypatch.setenv("TITANSPAN_READ_ONLY", "(false)")

    assert Env.get("TITANSPAN_READ_ONLY") is False
    assert os.environ["TITANSPAN_READ_ONLY"] == "(false)"
