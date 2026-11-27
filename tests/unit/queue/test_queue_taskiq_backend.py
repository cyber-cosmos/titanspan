"""Verify optional Taskiq broker integration without network access.
"""  # fmt: skip

from __future__ import annotations

from types import ModuleType
from typing import TYPE_CHECKING

import pytest
from taskiq import InMemoryBroker

from titanspan.queue._backends import taskiq as taskiq_backend
from titanspan.queue.configuration import QueueConnectionConfiguration

if TYPE_CHECKING:
    from taskiq.abc.broker import AsyncBroker

pytestmark = pytest.mark.unit


def test_rabbitmq_transport_has_no_result_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep unsupported RabbitMQ result handles explicitly unavailable.

    The selected optional broker package remains outside the core dependency.
    """
    module = ModuleType("taskiq_aio_pika")
    declarations: list[dict[str, object]] = []

    def broker_factory(**kwargs: object) -> AsyncBroker:
        """Build a Taskiq broker without opening a connection.

        Args:
            kwargs: Adapter options supplied by Titanspan.

        Returns:
            A real Taskiq broker for construction-only verification.
        """
        _ = kwargs
        return InMemoryBroker()

    def queue_factory(**kwargs: object) -> object:
        """Record one durable queue declaration from the adapter.

        Args:
            kwargs: Queue declaration options.

        Returns:
            An inert declaration accepted by the real broker constructor.
        """
        declarations.append(dict(kwargs))
        return object()

    module.__dict__["AioPikaBroker"] = broker_factory
    module.__dict__["Queue"] = queue_factory

    def load_module(name: str) -> ModuleType:
        """Return the test module for the optional import.

        Args:
            name: Requested module name.

        Returns:
            The test broker module or an empty module.
        """
        return module if name == "taskiq_aio_pika" else ModuleType(name)

    monkeypatch.setattr(taskiq_backend, "import_module", load_module)
    configuration = QueueConnectionConfiguration(
        "rabbitmq",
        {"url": "amqp://localhost"},
    )

    broker, source, result_backend = taskiq_backend.create_taskiq_transport(
        configuration,
        namespace="unit-tests",
        connection_name="rabbitmq",
        queue="default",
    )

    assert isinstance(broker, InMemoryBroker)
    assert source is None
    assert result_backend is None
    expected = [{"name": "unit-tests:rabbitmq:default", "durable": True}]
    assert declarations == expected
