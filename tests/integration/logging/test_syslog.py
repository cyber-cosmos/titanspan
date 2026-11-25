"""Verify RFC severity priorities cross the real syslog handler boundary.

An isolated UDP socket receives local datagrams without contacting an
external logging service or modifying standard-library global state.
"""

from __future__ import annotations

import socket

import pytest

from titanspan.logging import LogLevel, LogManager

pytestmark = pytest.mark.integration
SYSLOG_USER_FACILITY = 8
DATAGRAM_TIMEOUT_SECONDS = 2.0


@pytest.mark.parametrize("level", tuple(LogLevel))
def test_syslog_driver_preserves_rfc_severity_priority(
    level: LogLevel,
) -> None:
    """Encode each native severity as the matching syslog priority.

    Args:
        level: A Titanspan RFC 5424 severity level.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(DATAGRAM_TIMEOUT_SECONDS)
        host, port = receiver.getsockname()
        manager = LogManager(
            {
                "channels": {
                    "default": {
                        "driver": "syslog",
                        "formatter": "json",
                        "options": {"address": (host, port)},
                    },
                },
            },
        )

        try:
            manager.channel().log(level, "priority check")
            payload, _ = receiver.recvfrom(4096)
        finally:
            manager.close()

    priority_text = payload.split(b">", maxsplit=1)[0].removeprefix(b"<")
    assert int(priority_text) == SYSLOG_USER_FACILITY + level.severity
