"""Validate event behavior through the established Pydantic settings base.

The settings model reuses the shared Pydantic configuration base.
"""

from __future__ import annotations

# Pydantic resolves this field annotation while building the model class.
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from titanspan.events.exceptions import EventError

if TYPE_CHECKING:
    from titanspan.contracts.config import ConfigRepository


class EventsConfigurationError(EventError):
    """Report invalid event settings without exposing unrelated values.

    The exception identifies invalid event settings to callers.
    """


class EventsConfiguration(BaseModel):
    """Hold validated listener discovery and dispatch bounds.

    Attributes:
        discovery_modules: Trusted application module names to inspect.
        manifest_path: Optional JSON path for a validated discovery manifest.
        deferred_buffer_limit: Maximum pending events in one execution frame.
        max_dispatch_depth: Maximum nested dispatch depth per execution.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    discovery_modules: tuple[str, ...] = ()
    manifest_path: Path | None = None
    deferred_buffer_limit: int = Field(default=10_000, gt=0)
    max_dispatch_depth: int = Field(default=32, gt=0)

    @classmethod
    def from_repository(
        cls,
        repository: ConfigRepository,
    ) -> EventsConfiguration:
        """Read the event namespace from the canonical configuration source.

        Args:
            repository: Application-owned hierarchical repository.

        Returns:
            Validated settings with documented defaults for absent keys.

        Raises:
            EventsConfigurationError: If the namespace has an invalid shape.
        """
        values = repository.get("events", {})
        try:
            return cls.model_validate(values)
        except (TypeError, ValueError) as error:
            message = "The events configuration is invalid."
            raise EventsConfigurationError(message) from error


__all__ = ["EventsConfiguration", "EventsConfigurationError"]
