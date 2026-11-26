"""Expose Titanspan-owned typed settings and validation conventions.

The private adapter initializes and exports validated values while translating
backend validation errors into native configuration exceptions.
"""

from pathlib import Path
from typing import Self

from titanspan.config._backends.settings import (
    _SettingsBackend,
    export_settings,
    initialize_settings,
)
from titanspan.config.repository import Repository


class Settings(_SettingsBackend):
    """Define validated, environment-aware application settings.

    Application-specific subclasses declare typed fields and inherit the
    ``TITANSPAN_`` environment prefix. Use :meth:`from_environment` to select
    an application dotenv file without changing process environment state.

    Attributes:
        app_name: Name shown by the FastAPI OpenAPI metadata.
        debug: Whether FastAPI debug behavior is enabled.
    """

    app_name: str = "Titanspan"
    debug: bool = False

    def __init__(self, **values: object) -> None:
        """Validate explicit values and environment sources safely.

        Args:
            **values: Native fields and explicit environment source options.

        Raises:
            SettingsValidationError: If any field fails validation.
        """
        initialize_settings(self, values)

    @classmethod
    def from_environment(
        cls,
        *,
        env_file: str | Path | None = None,
    ) -> Self:
        """Build settings from process values and one selected dotenv file.

        Process environment variables take precedence over the selected file.
        Passing ``None`` disables dotenv loading while retaining process values.

        Args:
            env_file: Explicit trusted dotenv path, if any.

        Returns:
            An instance of the receiving settings subclass.

        Raises:
            SettingsValidationError: If a resolved field is invalid.
        """
        return cls(_env_file=env_file)

    def redacted(self) -> dict[str, object]:
        """Return a secret-safe dictionary for diagnostics.

        Returns:
            A structurally copied settings mapping with common secret keys
            replaced by a fixed redaction marker.
        """
        return dict(Repository(self.to_dict()).redacted())

    def to_dict(self, *, include_defaults: bool = True) -> dict[str, object]:
        """Export validated values through a Titanspan-owned API.

        Args:
            include_defaults: Whether to include fields supplied only by
                their class declarations.

        Returns:
            A new mapping containing the settings values. Secret values are
            included for authorized application use; use :meth:`redacted`
            for diagnostics.
        """
        return export_settings(self, include_defaults=include_defaults)

    def __repr__(self) -> str:
        """Render settings without exposing secret-shaped fields.

        Returns:
            The class name and redacted field mapping.
        """
        return f"{type(self).__name__}({self.redacted()!r})"

    def __str__(self) -> str:
        """Use the same secret-safe representation as ``repr``.

        Returns:
            The class name and redacted field mapping.
        """
        return self.__repr__()


__all__ = ["Settings"]
