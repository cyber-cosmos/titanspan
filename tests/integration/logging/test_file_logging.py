"""Verify structured records cross the native backend and file boundary.

The tests use Python's actual delayed file handlers and isolated temporary
destinations; no global logging configuration is modified.
"""

import asyncio
import calendar
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from titanspan import Application
from titanspan.container import BindingResolutionError
from titanspan.logging import (
    ChannelConfiguration,
    LogManager,
    LogRecord,
    MemoryLogDriver,
)
from titanspan.logging.drivers.standard import (
    next_monthly_rollover_timestamp,
)
from titanspan.logging.exceptions import LogConfigurationError

pytestmark = pytest.mark.integration
MAX_ROTATED_FILES = 3


class PrefixFormatter:
    """Provide a small application-defined native formatter.

    The implementation uses only Titanspan's formatter contract.
    """

    def format(self, record: LogRecord) -> str:
        """Prefix a native log message for an application destination.

        Args:
            record: The sanitized record selected for file delivery.

        Returns:
            One formatted line without a trailing record terminator.
        """
        return f"application::{record.message}"


def test_single_file_json_channel_writes_structured_record(
    tmp_path: Path,
) -> None:
    """Write a Titanspan record through the private structured adapter.

    The standard file handler owns output while the application uses only
    native channel, record, and formatter settings.
    """
    log_path = tmp_path / "logs" / "application.jsonl"
    manager = LogManager(
        {
            "channels": {
                "default": {
                    "driver": "single",
                    "path": log_path,
                    "level": "debug",
                    "formatter": "json",
                },
            },
        },
    )

    manager.channel().info("workflow completed", run_id="run-1")
    manager.close()

    record = json.loads(log_path.read_text(encoding="utf-8"))
    assert record["message"] == "workflow completed"
    assert record["context"] == {"run_id": "run-1"}
    assert record["channel"] == "default"


def test_application_file_logs_follow_the_configured_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve relative logging destinations under the application root.

    Changing the process working directory after construction must not
    redirect file output to another project.
    """
    application_root = tmp_path / "application"
    application_root.mkdir()
    ambient_root = tmp_path / "ambient"
    ambient_root.mkdir()
    application = Application(
        base_path=application_root,
        logging={
            "channels": {
                "default": {
                    "driver": "single",
                    "path": "storage/logs/application.log",
                    "formatter": "text",
                },
            },
        },
    )
    monkeypatch.chdir(ambient_root)

    async def write_log() -> None:
        """Write one record through the app-owned manager.

        The application closes its logging resources after this callback.
        """
        application.logging.channel().info("rooted log record")

    asyncio.run(application.run(write_log))

    expected = application_root / "storage/logs/application.log"
    assert "rooted log record" in expected.read_text(encoding="utf-8")
    assert not (ambient_root / "storage/logs").exists()


def test_application_file_logs_preserve_absolute_destinations(
    tmp_path: Path,
) -> None:
    """Keep explicit absolute log paths independent of application roots.

    Only relative destinations use Foundation's trusted application path.
    """
    application_root = tmp_path / "application"
    application_root.mkdir()
    explicit_path = tmp_path / "external" / "application.log"
    application = Application(
        base_path=application_root,
        logging={
            "channels": {
                "default": {
                    "driver": "single",
                    "path": explicit_path,
                    "formatter": "text",
                },
            },
        },
    )

    async def write_log() -> None:
        """Write one record to the explicitly selected destination.

        The call runs within the application's native lifecycle.
        """
        application.logging.channel().info("absolute destination")

    asyncio.run(application.run(write_log))

    assert "absolute destination" in explicit_path.read_text(
        encoding="utf-8",
    )


def test_application_rejects_relative_log_paths_outside_root(
    tmp_path: Path,
) -> None:
    """Reject relative file log destinations outside the application root.

    Validation occurs before any logging handler opens an output file.
    """
    with pytest.raises(BindingResolutionError) as error:
        Application(
            base_path=tmp_path / "application",
            logging={
                "channels": {
                    "default": {
                        "driver": "single",
                        "path": "../outside.log",
                        "formatter": "text",
                    },
                },
            },
        )
    assert isinstance(error.value.__cause__, LogConfigurationError)


def test_rotating_file_driver_delegates_rotation_to_stdlib(
    tmp_path: Path,
) -> None:
    """Use the standard rotating handler and retain bounded output files.

    A small configured size triggers rotation without a wall-clock assertion.
    """
    log_path = tmp_path / "logs" / "rotating.log"
    manager = LogManager(
        {
            "channels": {
                "default": {
                    "driver": "rotating",
                    "path": log_path,
                    "level": "debug",
                    "max_bytes": 100,
                    "backup_count": 2,
                    "formatter": "text",
                },
            },
        },
    )

    logger = manager.channel()
    for index in range(8):
        logger.info("record", index=index, payload="x" * 50)
    manager.close()

    files = tuple(log_path.parent.glob("rotating.log*"))
    assert len(files) > 1
    assert len(files) <= MAX_ROTATED_FILES


def test_monthly_file_driver_writes_to_managed_log_path(
    tmp_path: Path,
) -> None:
    """Write through a native monthly file channel configuration.

    Calendar rollover remains owned by the standard logging handler.
    """
    log_path = tmp_path / "logs" / "monthly.log"
    manager = LogManager(
        {
            "channels": {
                "default": {
                    "driver": "monthly",
                    "path": log_path,
                    "max_files": 3,
                    "formatter": "text",
                },
            },
        },
    )

    manager.info("monthly record", month="current")
    manager.close()

    assert "monthly record" in log_path.read_text(encoding="utf-8")


def test_monthly_handler_uses_calendar_boundaries() -> None:
    """Compute boundaries at month ends, year changes, and leap years.

    Calendar arithmetic must not approximate a month as a fixed duration.
    """
    rollover_cases = (
        (
            datetime(2026, 11, 30, 23, 59, tzinfo=UTC),
            datetime(2026, 12, 1, tzinfo=UTC),
        ),
        (
            datetime(2026, 12, 31, 23, 59, tzinfo=UTC),
            datetime(2027, 1, 1, tzinfo=UTC),
        ),
        (
            datetime(2024, 2, 29, 23, 59, tzinfo=UTC),
            datetime(2024, 3, 1, tzinfo=UTC),
        ),
    )
    for current, expected in rollover_cases:
        current_timestamp = calendar.timegm(current.utctimetuple())
        expected_timestamp = calendar.timegm(expected.utctimetuple())
        assert next_monthly_rollover_timestamp(current_timestamp) == (
            expected_timestamp
        )


def test_channel_stack_routes_to_children_in_order() -> None:
    """Fan each record out to configured child channels.

    Child filters and formatters remain independent from the stack itself.
    """
    drivers: list[MemoryLogDriver] = []

    def create_memory_driver(
        _: ChannelConfiguration,
    ) -> MemoryLogDriver:
        """Create one independently owned memory destination.

        Returns:
            A fresh in-memory driver for one configured child channel.
        """
        driver = MemoryLogDriver()
        drivers.append(driver)
        return driver

    manager = LogManager(
        {
            "default": "stack",
            "channels": {
                "first": {"driver": "memory"},
                "second": {"driver": "memory"},
                "stack": {
                    "driver": "stack",
                    "channels": ["first", "second"],
                },
            },
        },
        drivers={"memory": create_memory_driver},
    )

    manager.channel().info("distributed")

    assert [
        record.channel for driver in drivers for record in driver.records
    ] == ["first", "second"]
    manager.close()


def test_custom_formatter_uses_the_native_formatter_contract(
    tmp_path: Path,
) -> None:
    """Resolve a configured formatter through the manager registry.

    A real file handler verifies that output uses the custom formatter.
    """
    log_path = tmp_path / "logs" / "custom.log"
    manager = LogManager(
        {
            "channels": {
                "default": {
                    "driver": "single",
                    "path": log_path,
                    "formatter": "application",
                },
            },
        },
        formatters={"application": lambda _: PrefixFormatter()},
    )

    manager.channel().info("document stored")
    manager.close()

    assert log_path.read_text(encoding="utf-8").strip() == (
        "application::document stored"
    )
