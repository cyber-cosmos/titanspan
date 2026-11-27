"""Verify Queue manager behavior through real application composition.

These tests exercise the native Container, dispatcher contracts, and facades.
"""

from dataclasses import dataclass

import pytest
from taskiq import InMemoryBroker
from taskiq.abc.broker import AsyncBroker

from titanspan.contracts.queue import (
    BusDispatcher,
    DispatchReceipt,
    QueueDispatcher,
)
from titanspan.facades.bus import Bus
from titanspan.facades.queue import Queue
from titanspan.foundation import Application
from titanspan.queue import (
    Job,
    QueueCapabilityError,
    QueueConfigurationError,
    QueueDispatchError,
    QueueError,
    QueueManager,
    QueueServiceProvider,
)
from titanspan.queue.configuration import QueueConnectionConfiguration

pytestmark = pytest.mark.unit
_FAKED_DISPATCH_COUNT = 2


@dataclass
class _ValueJob(Job):
    """Return one value through the application's Queue manager.
    """  # fmt: skip

    value: str

    def handle(self) -> str:
        """Return the job payload for synchronous dispatch assertions.

        Returns:
            The value supplied when the job was created.
        """
        return self.value


def _application() -> Application:
    """Create an application with real sync and null Queue drivers.

    Returns:
        An unstarted application with the trusted test job registered.
    """
    return Application(
        config={
            "app": {"name": "queue-manager-unit"},
            "queue": {
                "connections": {
                    "sync": {"driver": "sync"},
                    "null": {"driver": "null"},
                },
            },
        },
        service_providers=(QueueServiceProvider(jobs=(_ValueJob,)),),
    )


def _in_memory_broker(
    configuration: QueueConnectionConfiguration,
    connection_name: str,
    physical_queue: str,
) -> AsyncBroker:
    """Construct a Taskiq broker for custom-driver result tests.

    Args:
        configuration: Trusted custom connection settings.
        connection_name: Selected connection name.
        physical_queue: Application-owned queue identifier.

    Returns:
        A Taskiq in-memory broker without a result backend.
    """
    _ = configuration, connection_name, physical_queue
    return InMemoryBroker()


def _custom_driver_application() -> Application:
    """Create an application with a custom broker without results.

    Returns:
        An unstarted application using one Taskiq in-memory broker.
    """
    return Application(
        config={
            "app": {"name": "queue-custom-broker-unit"},
            "queue": {
                "default_connection": "memory",
                "connections": {"memory": {"driver": "memory"}},
            },
        },
        service_providers=(
            QueueServiceProvider(
                jobs=(_ValueJob,),
                drivers={"memory": _in_memory_broker},
            ),
        ),
    )


@pytest.mark.anyio
async def test_sync_and_null_drivers_have_distinct_public_outcomes() -> None:
    """Execute sync jobs and discard null-driver jobs predictably.

    Both connections use the same registered application job catalog.
    """
    application = _application()

    async with application:
        manager = application.container.make(QueueManager)
        executed = await manager.dispatch_async(
            _ValueJob("executed"),
            connection="sync",
        )
        discarded = await manager.dispatch_async(
            _ValueJob("discarded"),
            connection="null",
        )

    assert executed.state == "executed"
    assert executed.result == "executed"
    assert discarded.state == "discarded"
    assert discarded.result is None


@pytest.mark.anyio
async def test_facades_and_contracts_resolve_one_manager_and_fake() -> None:
    """Share the application manager across injected and facade access.

    The manager fake records direct and facade dispatch without execution.
    """
    application = _application()

    async with application:
        manager = application.container.make(QueueManager)
        queue_dispatcher = application.container.make(QueueDispatcher)
        bus_dispatcher = application.container.make(BusDispatcher)

        assert queue_dispatcher is manager
        assert bus_dispatcher is manager
        assert Queue.manager() is manager
        assert Queue.resolve_service() is queue_dispatcher
        assert Bus.resolve_service() is bus_dispatcher

        with manager.fake() as fake:
            facade_receipt = await Queue.dispatch_async(_ValueJob("facade"))
            injected_receipt = await queue_dispatcher.dispatch_async(
                _ValueJob("injected")
            )

    assert facade_receipt.state == "queued"
    assert injected_receipt.state == "queued"
    fake.assert_pushed_count(_ValueJob, _FAKED_DISPATCH_COUNT)
    assert fake.pushed(_ValueJob)


@pytest.mark.anyio
async def test_pending_dispatch_rejects_second_publication() -> None:
    """Prevent a reused dispatch builder from publishing twice.

    The first explicit operation still executes through the sync driver.
    """
    application = _application()

    async with application:
        manager = application.container.make(QueueManager)
        pending = manager.dispatch(_ValueJob("once"))
        first_receipt = await pending.dispatch_async()

        with pytest.raises(QueueDispatchError):
            await pending.dispatch_async()

    assert first_receipt.state == "executed"
    assert first_receipt.result == "once"


@pytest.mark.anyio
async def test_pending_chain_and_batch_reject_reuse() -> None:
    """Keep chain and batch builders single-use after dispatch.

    Reusing a builder could repeat application side effects.
    """
    application = _application()

    async with application:
        manager = application.container.make(QueueManager)
        chain = manager.chain([_ValueJob("chain")])
        chain_receipt = await chain.dispatch_async()
        batch = manager.batch([_ValueJob("batch")])
        batch_handle = await batch.dispatch_async()

        with pytest.raises(QueueDispatchError):
            await chain.dispatch_async()
        with pytest.raises(QueueError):
            await batch.dispatch_async()

    assert chain_receipt.state == "executed"
    assert batch_handle.processed_jobs == 1
    assert batch_handle.state == "completed"


@pytest.mark.anyio
async def test_unsupported_operations_fail_before_backend_work() -> None:
    """Reject result and worker operations unsupported by sync drivers.

    Invalid queue names fail during builder creation before dispatch.
    """
    application = _application()

    async with application:
        manager = application.container.make(QueueManager)
        receipt = await manager.dispatch_async(_ValueJob("sync"))

        with pytest.raises(QueueCapabilityError):
            manager.result_for(receipt)
        queued_sync_receipt = DispatchReceipt(
            job_id="unsupported-result",
            connection="sync",
            queue="default",
            state="queued",
        )
        with pytest.raises(QueueCapabilityError):
            manager.result_for(queued_sync_receipt)
        with pytest.raises(QueueCapabilityError):
            await manager.work_async(connection="sync")
        with pytest.raises(QueueCapabilityError):
            manager.dispatch_sync(_ValueJob("unsafe"))
        with pytest.raises(QueueConfigurationError):
            manager.dispatch(_ValueJob("invalid"), queue="../invalid")


@pytest.mark.anyio
async def test_custom_driver_without_result_storage_fails_explicitly() -> None:
    """Reject result polling before starting a custom broker without storage.

    Queue does not infer result support from a Taskiq broker alone.
    """
    application = _custom_driver_application()
    receipt = DispatchReceipt(
        job_id="custom-job",
        connection="memory",
        queue="default",
        state="queued",
    )

    async with application:
        manager = application.container.make(QueueManager)

        with pytest.raises(QueueCapabilityError):
            await manager.result_is_ready(receipt)
