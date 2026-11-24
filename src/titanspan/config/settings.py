"""Define typed environment-backed application settings.

Pydantic Settings owns parsing and validation; Titanspan supplies the
framework-specific prefix and initial application defaults.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validate the settings consumed by the initial application foundation.

    Values are loaded from ``TITANSPAN_``-prefixed environment variables and
    validated by Pydantic Settings before application construction.

    Attributes:
        app_name: Name shown by the FastAPI OpenAPI metadata.
        debug: Whether FastAPI debug behavior is enabled.
    """

    model_config = SettingsConfigDict(env_prefix="TITANSPAN_", extra="ignore")

    app_name: str = "Titanspan"
    debug: bool = False
