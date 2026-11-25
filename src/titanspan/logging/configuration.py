"""Validate native channel and logging configuration.

The public configuration model expresses Titanspan concepts and deliberately
does not accept backend logger factories or processor paths.
"""

from __future__ import annotations

from pathlib import (
    Path,  # noqa: TC003 - Pydantic resolves this field at runtime.
)
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from titanspan.logging.exceptions import LogConfigurationError
from titanspan.logging.level import LogLevel

if TYPE_CHECKING:
    from collections.abc import Mapping

OverflowPolicy = Literal[
    "drop_newest",
    "drop_oldest",
    "raise",
    "emergency",
    "await",
]


class ChannelConfiguration(BaseModel):
    """Describe one named destination using Titanspan-owned options.

    Attributes:
        driver: Registered driver name such as ``console`` or ``single``.
        level: Lowest RFC severity to accept, with lower values more severe.
        formatter: Registered native output format selected for destination.
        path: Destination path for file-based drivers.
        days: Retained daily files for time-based rotation.
        max_files: Retained archives for calendar-month rotation.
        max_bytes: Maximum current file size for size-based rotation.
        backup_count: Retained rotated files.
        channels: Child channels for a stack driver.
        tap: Registered customizers run once when a channel is created.
        ignore_exceptions: Whether a stack continues after one child fails.
        options: Driver-specific native options passed to custom factories.
        color: Whether the console formatter emits ANSI color sequences.
        sensitive_fields: Additional key fragments to redact.
        background: Dispatch blocking destination writes on one worker.
        queue_capacity: Maximum pending records for background delivery.
        overflow_policy: Explicit behavior when the bounded queue is full.
        queue_wait_timeout: Maximum async queue-capacity wait in seconds.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    driver: str
    name: str | None = None
    level: LogLevel = LogLevel.DEBUG
    formatter: str = "console"
    path: Path | None = None
    days: int = Field(default=14, ge=1)
    max_files: int = Field(default=3, ge=0)
    max_bytes: int = Field(default=10_485_760, ge=1)
    backup_count: int = Field(default=5, ge=0)
    channels: tuple[str, ...] = ()
    tap: tuple[str, ...] = ()
    ignore_exceptions: bool = False
    options: dict[str, object] = Field(default_factory=dict)
    color: bool | None = None
    sensitive_fields: tuple[str, ...] = ()
    background: bool = False
    queue_capacity: int = Field(default=1000, ge=1)
    overflow_policy: OverflowPolicy = "drop_newest"
    queue_wait_timeout: float = Field(default=5.0, gt=0, le=60)

    @field_validator("driver")
    @classmethod
    def validate_driver_name(cls, value: str) -> str:
        """Reject blank or whitespace-padded driver identifiers.

        Args:
            value: The configured driver name.

        Returns:
            The unchanged valid driver identifier.

        Raises:
            ValueError: If the driver name is empty or padded.
        """
        if not value or value != value.strip():
            msg = "A driver name must be non-empty and trimmed"
            raise LogConfigurationError(
                msg,
            )
        return value

    @field_validator("name")
    @classmethod
    def validate_channel_name(cls, value: str | None) -> str | None:
        """Reject empty or whitespace-padded explicit channel names.

        Args:
            value: The optional display name for an on-demand channel.

        Returns:
            The unchanged name, or ``None`` when the manager generates one.

        Raises:
            LogConfigurationError: If the supplied name is invalid.
        """
        if value is not None and (not value or value != value.strip()):
            message = "A channel name must be non-empty and trimmed"
            raise LogConfigurationError(message)
        return value

    @field_validator("formatter")
    @classmethod
    def validate_formatter_name(cls, value: str) -> str:
        """Reject blank or whitespace-padded formatter identifiers.

        Args:
            value: A built-in or application-registered formatter name.

        Returns:
            The unchanged valid formatter identifier.

        Raises:
            LogConfigurationError: If the formatter identifier is invalid.
        """
        if not value or value != value.strip():
            message = "A formatter name must be non-empty and trimmed"
            raise LogConfigurationError(message)
        return value

    @field_validator("level", mode="before")
    @classmethod
    def parse_level(cls, value: object) -> LogLevel:
        """Normalize configured log level names and severity numbers.

        Args:
            value: A level name, native enum, or RFC severity number.

        Returns:
            A native log level.
        """
        if isinstance(value, (LogLevel, str)):
            return LogLevel.parse(value)
        if isinstance(value, int) and not isinstance(value, bool):
            return LogLevel.parse(value)
        msg = "A log level must be a name or RFC severity number"
        raise LogConfigurationError(
            msg,
        )

    @field_validator("channels")
    @classmethod
    def validate_child_channels(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Reject duplicate or blank stack destinations.

        Args:
            value: Names of child channels.

        Returns:
            The unchanged tuple when all names are unique and non-empty.

        Raises:
            ValueError: If a child list contains an invalid name.
        """
        if any(not channel for channel in value):
            msg = "Stack channel names must be non-empty"
            raise LogConfigurationError(
                msg,
            )
        if len(value) != len(set(value)):
            msg = "Stack channel names must be unique"
            raise LogConfigurationError(msg)
        return value

    @field_validator("tap")
    @classmethod
    def validate_tap_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Reject ambiguous or duplicate channel customizer names.

        Args:
            value: Ordered registered customizer names.

        Returns:
            The unchanged tuple when all names are valid.

        Raises:
            LogConfigurationError: If a tap name is empty, padded, or repeated.
        """
        if any(not name or name != name.strip() for name in value):
            message = "Channel customizer names must be non-empty and trimmed"
            raise LogConfigurationError(message)
        if len(value) != len(set(value)):
            message = "Channel customizer names must be unique"
            raise LogConfigurationError(message)
        return value


class LoggingConfiguration(BaseModel):
    """Define the default log channel and all named channel settings.

    The default configuration is a console channel suitable for local use.
    Applications can replace it with explicit production destinations.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    default: str = "default"
    channels: dict[str, ChannelConfiguration] = Field(
        default_factory=lambda: {
            "default": ChannelConfiguration(driver="console"),
        },
    )

    @field_validator("default")
    @classmethod
    def validate_default_name(cls, value: str) -> str:
        """Reject an empty default channel name.

        Args:
            value: The default channel identifier.

        Returns:
            The unchanged non-empty identifier.

        Raises:
            ValueError: If the default name is empty.
        """
        if not value:
            msg = "The default channel name must be non-empty"
            raise LogConfigurationError(
                msg,
            )
        return value

    @classmethod
    def from_value(
        cls,
        value: LoggingConfiguration | Mapping[str, object] | None,
    ) -> LoggingConfiguration:
        """Validate a native configuration model or mapping.

        Args:
            value: A model, mapping, or ``None`` for default configuration.

        Returns:
            A validated independent configuration model.
        """
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        return cls.model_validate(value)
