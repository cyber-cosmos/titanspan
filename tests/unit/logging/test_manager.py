"""Verify channel resolution, record creation, and manager lifecycle.

The tests use real Titanspan memory drivers and exercise logging through the
public manager and logger APIs.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from titanspan.logging import (
    ChannelConfiguration,
    LogChannelNotFoundError,
    LogConfigurationError,
    LogLevel,
    LogManager,
    LogRecord,
    MemoryLogDriver,
)

pytestmark = pytest.mark.unit
EXPECTED_CHANNEL_INSTANCES = 2
EXPECTED_WORKER_COUNT = 9
DEFAULT_MONTHLY_ARCHIVES = 3


def test_manager_caches_named_channels_and_filters_by_level() -> None:
    """Cache channels and apply the configured severity threshold.

    A channel is constructed once and logs only messages at or above its
    configured RFC severity threshold.
    """
    driver = MemoryLogDriver()
    manager = LogManager(
        {
            "default": "application",
            "channels": {
                "application": {
                    "driver": "memory",
                    "level": "info",
                },
            },
        },
        drivers={"memory": lambda _: driver},
    )

    logger = manager.channel("application")

    assert logger is manager.channel("application")
    logger.debug("filtered")
    logger.info("accepted", context={"job_id": "job-1"})

    assert [record.message for record in driver.records] == ["accepted"]
    assert driver.records[0].context == {"job_id": "job-1"}
    assert isinstance(driver.records[0], LogRecord)


@pytest.mark.parametrize(
    ("threshold", "candidate"),
    [
        (threshold, candidate)
        for threshold in LogLevel
        for candidate in LogLevel
    ],
)
def test_every_threshold_combination_matches_rfc_severity(
    threshold: LogLevel,
    candidate: LogLevel,
) -> None:
    """Apply RFC severity ordering for every threshold and candidate pair.

    More severe messages have a lower RFC number and pass higher-numbered
    thresholds. This exhaustive pair test prevents backend ordering drift.

    Args:
        threshold: The configured least-severe accepted level.
        candidate: The level submitted to the channel.
    """
    driver = MemoryLogDriver()
    manager = LogManager(
        {
            "channels": {
                "default": {
                    "driver": "memory",
                    "level": threshold.value,
                },
            },
        },
        drivers={"memory": lambda _: driver},
    )

    manager.channel().log(candidate, "candidate")

    assert bool(driver.records) is (candidate.severity <= threshold.severity)


def test_manager_exposes_resolved_channels_and_forgets_one() -> None:
    """Expose cached channels and safely release one channel by name.

    The manager returns only channels it has resolved and allows a later
    lookup to construct a fresh logger after the old one is closed.
    """
    created: list[MemoryLogDriver] = []

    def create_driver(_: ChannelConfiguration) -> MemoryLogDriver:
        """Create a fresh driver for each channel resolution.

        Returns:
            An independently owned in-memory driver.
        """
        driver = MemoryLogDriver()
        created.append(driver)
        return driver

    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": create_driver},
    )
    first = manager.channel()

    assert manager.get_channels() == {"default": first}
    manager.forget_channel("default")
    second = manager.channel()

    assert first is not second
    assert first.channel.closed is True
    assert len(created) == EXPECTED_CHANNEL_INSTANCES


def test_manager_exposes_laravel_compatible_channel_and_context_methods() -> (
    None
):
    """Keep camel-case manager methods explicit and statically discoverable.

    The aliases share the same manager-owned cache and execution context as
    their Python snake-case counterparts.
    """
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: MemoryLogDriver()},
    )
    logger = manager.channel()
    manager.shareContext(tenant_id="tenant-a")

    assert manager.getDefaultDriver() == "default"
    assert manager.sharedContext() == {"tenant_id": "tenant-a"}
    assert manager.getChannels()["default"] is logger


def test_manager_methods_write_using_the_default_channel() -> None:
    """Delegate direct manager log calls to the active default channel.

    Convenience methods retain the same record formatting and structured
    context path as calls made through the resolved logger.
    """
    driver = MemoryLogDriver()
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: driver},
    )

    manager.warning(
        "capacity is high",
        context={"workers": EXPECTED_WORKER_COUNT},
    )

    assert driver.records[0].level is LogLevel.WARNING
    assert driver.records[0].context["workers"] == EXPECTED_WORKER_COUNT


def test_empty_channel_name_does_not_silently_select_default() -> None:
    """Reject a blank requested channel instead of using the default.

    A typo must remain visible as an unresolved channel error.
    """
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: MemoryLogDriver()},
    )

    with pytest.raises(LogChannelNotFoundError):
        manager.channel("")


def test_log_call_keyword_values_override_context_mapping() -> None:
    """Merge structured values with deterministic keyword precedence.

    Keyword arguments override keys from the positional context mapping.
    """
    driver = MemoryLogDriver()
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: driver},
    )

    manager.channel().info(
        "completed",
        {"status": "pending", "count": 4},
        status="complete",
    )

    assert driver.records[0].context == {
        "status": "complete",
        "count": 4,
    }


def test_unknown_channel_and_driver_fail_explicitly() -> None:
    """Report invalid channel references and driver names.

    Configuration mistakes must be visible instead of falling back to a
    different channel or silently dropping records.
    """
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: MemoryLogDriver()},
    )

    with pytest.raises(LogChannelNotFoundError):
        manager.channel("missing")

    with pytest.raises(LogConfigurationError):
        LogManager({"channels": {"default": {"driver": "unknown"}}})


def test_channel_close_is_idempotent_and_releases_driver() -> None:
    """Close a channel's owned driver exactly once.

    Repeated manager shutdown must not duplicate resource finalization.
    """
    driver = MemoryLogDriver()
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: driver},
    )
    manager.channel().info("before close")

    manager.close()
    manager.close()

    assert driver.closed is True


def test_custom_driver_factory_receives_typed_channel_configuration() -> None:
    """Pass validated native configuration to custom drivers.

    Custom driver registration uses Titanspan types and does not expose
    backend-specific configuration objects.
    """
    driver = MemoryLogDriver()
    received: list[ChannelConfiguration] = []

    def factory(configuration: ChannelConfiguration) -> MemoryLogDriver:
        """Capture the validated configuration and return a driver.

        Args:
            configuration: The channel's validated Titanspan settings.

        Returns:
            The driver that will receive channel records.
        """
        received.append(configuration)
        return driver

    manager = LogManager(
        {
            "channels": {
                "default": {
                    "driver": "custom",
                    "level": "notice",
                    "options": {"destination": "local"},
                },
            },
        },
        drivers={"custom": factory},
    )

    manager.channel().notice("started")

    assert received[0].options == {"destination": "local"}
    assert driver.records[0].level is LogLevel.NOTICE


def test_logging_context_is_redacted_before_driver_delivery() -> None:
    """Redact sensitive nested fields before records reach a driver.

    The message remains available while configured sensitive context is
    replaced recursively before delivery.
    """
    driver = MemoryLogDriver()
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: driver},
    )

    manager.channel().info(
        "authentication complete",
        {
            "user": {"access_token": "do-not-store"},
            "count": 2,
        },
    )

    assert driver.records[0].context == {
        "user": {"access_token": "[REDACTED]"},
        "count": 2,
    }
    assert "do-not-store" not in repr(driver.records[0])


def test_custom_options_preserve_nested_mapping_values() -> None:
    """Retain valid nested settings through model validation.

    The mapping is copied into immutable validated configuration so later
    caller mutations cannot change an active channel.
    """
    options: dict[str, object] = {"nested": {"enabled": True}}
    manager = LogManager(
        {
            "channels": {
                "default": {
                    "driver": "memory",
                    "options": options,
                },
            },
        },
        drivers={"memory": lambda _: MemoryLogDriver()},
    )
    options["nested"] = "changed"

    assert manager.configuration.channels["default"].options == {
        "nested": {"enabled": True},
    }


def test_record_context_has_no_mutable_alias_to_callers() -> None:
    """Keep the delivered record detached from mutable input mappings.

    Mutating a caller-owned context after logging cannot rewrite history.
    """
    driver = MemoryLogDriver()
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: driver},
    )
    values = ["a"]
    context: dict[str, object] = {"items": values}

    manager.channel().info("copied", context)
    values.append("b")

    assert driver.records[0].context == {"items": ["a"]}


def test_channel_rejects_empty_or_malformed_configuration() -> None:
    """Reject invalid channel configuration before resolving channels.

    A stack with a missing target and invalid threshold are configuration
    errors rather than runtime logging failures.
    """
    with pytest.raises(LogConfigurationError):
        LogManager({"channels": {"default": {"driver": "missing"}}})

    with pytest.raises(ValidationError):
        LogManager(
            {
                "channels": {
                    "default": {
                        "driver": "memory",
                        "level": "trace",
                    },
                },
            },
        )


def test_monthly_archive_configuration_validates_retention() -> None:
    """Validate monthly archive retention in the native channel model.

    Zero disables archive deletion while negative counts are rejected.
    """
    configuration = ChannelConfiguration(
        driver="monthly",
        path=Path("storage/logs/application.log"),
    )
    assert configuration.max_files == DEFAULT_MONTHLY_ARCHIVES
    assert (
        ChannelConfiguration(
            driver="monthly",
            path=Path("storage/logs/application.log"),
            max_files=0,
        ).max_files
        == 0
    )

    with pytest.raises(ValidationError):
        ChannelConfiguration(
            driver="monthly",
            path=Path("storage/logs/application.log"),
            max_files=-1,
        )


def test_log_record_supports_json_safe_context_types() -> None:
    """Normalize supported Python values into portable record context.

    Datetime and UUID values are represented using stable string forms.
    """
    driver = MemoryLogDriver()
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: driver},
    )

    manager.channel().info(
        "normalized",
        {
            "at": datetime(2026, 1, 1, tzinfo=UTC),
            "id": UUID("00000000-0000-0000-0000-000000000001"),
        },
    )

    assert driver.records[0].context == {
        "at": "2026-01-01T00:00:00+00:00",
        "id": "00000000-0000-0000-0000-000000000001",
    }


def test_manager_flushes_and_closes_custom_drivers() -> None:
    """Flush every instantiated custom driver before closing it.

    Manager cleanup owns each built channel and is deterministic on shutdown.
    """
    driver = MemoryLogDriver()
    manager = LogManager(
        {"channels": {"default": {"driver": "memory"}}},
        drivers={"memory": lambda _: driver},
    )

    manager.channel().flush()
    manager.close()

    assert driver.closed is True
