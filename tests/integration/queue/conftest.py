"""Provide disposable Redis infrastructure for Queue integration tests.

Mandatory CI uses its Redis service. Local runs start an isolated process.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import tempfile
from importlib import import_module
from os import environ
from time import monotonic, sleep
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

_REDIS_REQUIRED_ENV = "TITANSPAN_REQUIRE_REDIS"
_REDIS_PORT_ENV = "TITANSPAN_TEST_REDIS_PORT"


@pytest.fixture
def queue_redis_port() -> Iterator[int]:
    """Require the Redis adapter and use CI or local Redis for this test.

    Yields:
        The loopback port used by the Queue Redis integration.
    """
    required = environ.get(_REDIS_REQUIRED_ENV) == "1"
    try:
        import_module("taskiq_redis")
    except ImportError:
        message = "Install the queue-redis extra to run Queue Redis tests."
        if required:
            pytest.fail(message)
        pytest.skip(message)

    configured_port = environ.get(_REDIS_PORT_ENV)
    if configured_port is not None:
        try:
            port = int(configured_port)
        except ValueError:
            pytest.fail("The configured Redis test port must be an integer.")
        yield port
        return

    executable = shutil.which("redis-server")
    if executable is None:
        if required:
            pytest.fail("Mandatory Queue tests need a Redis service.")
        pytest.skip("redis-server is not installed")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="titanspan-queue-redis-") as data:
        process = subprocess.Popen(  # noqa: S603
            [
                executable,
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
                "--save",
                "",
                "--appendonly",
                "no",
                "--dir",
                data,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = monotonic() + 5
        while monotonic() < deadline and process.poll() is None:
            try:
                with socket.create_connection(
                    ("127.0.0.1", port),
                    timeout=0.1,
                ):
                    break
            except OSError:
                sleep(0.05)
        else:
            process.terminate()
            process.wait(timeout=3)
            pytest.fail("Local Queue Redis did not start within five seconds.")
        try:
            yield port
        finally:
            process.terminate()
            process.wait(timeout=3)
