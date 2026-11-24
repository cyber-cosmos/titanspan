"""Pydantic Settings models used by the initial application foundation."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated settings for a Titanspan application."""

    model_config = SettingsConfigDict(env_prefix="TITANSPAN_", extra="ignore")

    app_name: str = "Titanspan"
    debug: bool = False
