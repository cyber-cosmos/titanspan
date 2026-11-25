"""Adapt Pydantic Settings validation behind a native Titanspan boundary.

The adapter owns the settings source configuration and translates validation
failures before they reach application code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from titanspan.config.exceptions import SettingsValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping


class _SettingsBackend(BaseSettings):
    """Provide the private Pydantic Settings model base.

    Application code should inherit from ``titanspan.config.Settings`` so the
    framework can define source behavior and expose native error semantics.
    """

    model_config = SettingsConfigDict(
        env_file=None,
        env_prefix="TITANSPAN_",
        extra="ignore",
        validate_default=True,
    )


def _validation_fields(error: ValidationError) -> tuple[str, ...]:
    """Extract field paths without retaining rejected values or messages.

    Args:
        error: Pydantic validation error from the private backend.

    Returns:
        Ordered unique field paths suitable for a safe native diagnostic.
    """
    fields: list[str] = []
    for detail in error.errors(include_input=False):
        # Pydantic's error details already expose a typed location tuple.
        parts = tuple(str(part) for part in detail["loc"])
        if parts:
            fields.append(".".join(parts))
    return tuple(dict.fromkeys(fields))


def initialize_settings(
    instance: _SettingsBackend,
    values: Mapping[str, object],
) -> None:
    """Initialize one native Settings instance through Pydantic sources.

    Args:
        instance: Titanspan settings model being constructed.
        values: Constructor and explicit source options.

    Raises:
        SettingsValidationError: If the settings values fail validation.
    """
    # Pydantic's BaseSettings constructor uses dynamic source-specific keyword
    # options. Keep that dynamic typing isolated at this adapter boundary.
    backend_values = cast("dict[str, Any]", dict(values))
    try:
        BaseSettings.__init__(instance, **backend_values)
    except ValidationError as error:
        raise SettingsValidationError(_validation_fields(error)) from None


__all__ = ["_SettingsBackend", "initialize_settings"]
