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


@dataclass
class _UnregisteredValueJob(_ValueJob):
    """Represent a valid Job subclass absent from the trusted catalog.
    """  # fmt: skip


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
async def test_dispatch_many_executes_jobs_in_order() -> None:
    """Return ordered receipts from one native bulk dispatch operation.

    The sync connection still uses the manager's async execution path.
    """
    application = _application()

    async with application:
        dispatcher = application.container.make(QueueDispatcher)
        assert dispatcher is application.container.make(QueueManager)
        queue_receipts = await Queue.dispatch_many_async(
            [_ValueJob("queue")],
            connection="sync",
            queue="bulk",
        )
        bus_receipts = await Bus.dispatch_many_async(
            [_ValueJob("bus")],
            connection="sync",
            queue="bulk",
        )
        contract_receipts = await dispatcher.dispatch_many_async(
            [_ValueJob("contract")],
            connection="sync",
            queue="bulk",
        )

    receipts = queue_receipts + bus_receipts + contract_receipts
    assert [receipt.result for receipt in receipts] == [
        "queue",
        "bus",
        "contract",
    ]
    assert all(receipt.queue == "bulk" for receipt in receipts)


@pytest.mark.anyio
async def test_dispatch_many_prevalidates_fake_recording() -> None:
    """Reject an invalid later job before recording any earlier job.

    Preflight validation prevents avoidable partial publication when a job
    registration is invalid.
    """
    application = _application()

    async with application:
        manager = application.container.make(QueueManager)
        with (
            manager.fake() as fake,
            pytest.raises(QueueConfigurationError),
        ):
            await manager.dispatch_many_async(
                [_ValueJob("valid"), object()],
            )

    fake.assert_nothing_pushed()


@pytest.mark.anyio
async def test_dispatch_many_is_empty_safe_and_bounded() -> None:
    """Treat empty input as a no-op and reject oversized input early.

    The limit prevents one call from retaining unbounded dispatch builders.
    """
    application = _application()

    async with application:
        manager = application.container.make(QueueManager)
        with manager.fake() as fake:
            assert await manager.dispatch_many_async([]) == ()
            with pytest.raises(QueueConfigurationError):
                await manager.dispatch_many_async(
                    [_ValueJob("bounded")] * 1001,
                )

    fake.assert_nothing_pushed()


@pytest.mark.anyio
async def test_conditional_dispatch_skips_or_uses_the_shared_dispatcher() -> (
    None
):
    """Skip false conditions without validating or publishing jobs.

    Enabled operations still use the application's ordinary pending path.
    """
    application = _application()

    async with application:
        manager = application.container.make(QueueManager)
        dispatcher = application.container.make(QueueDispatcher)
        with manager.fake() as fake:
            assert (
                manager.dispatch_if(
                    False,
                    _UnregisteredValueJob("ignored"),
                )
                is None
            )
            assert (
                await Queue.dispatch_if_async(
                    False,
                    _UnregisteredValueJob("ignored"),
                    connection="missing",
                )
                is None
            )
            assert (
                Bus.dispatch_unless(
                    True,
                    _UnregisteredValueJob("ignored"),
                )
                is None
            )
            assert (
                await dispatcher.dispatch_unless_async(
                    True,
                    _UnregisteredValueJob("ignored"),
                )
                is None
            )
            assert (
                await manager.dispatch_if_async(
                    False,
                    _UnregisteredValueJob("ignored"),
                )
                is None
            )

            pending = Queue.dispatch_if(True, _ValueJob("pending"))
            assert pending is not None
            pending_receipt = await pending.dispatch_async()
            bus_pending = Bus.dispatch_unless(False, _ValueJob("bus-pending"))
            assert bus_pending is not None
            bus_pending_receipt = await bus_pending.dispatch_async()
            queue_receipt = await Queue.dispatch_if_async(
                True,
                _ValueJob("manager"),
            )
            bus_receipt = await Bus.dispatch_unless_async(
                False,
                _ValueJob("bus"),
            )

    assert pending_receipt.state == "queued"
    assert bus_pending_receipt.state == "queued"
    assert queue_receipt is not None
    assert queue_receipt.state == "queued"
    assert bus_receipt is not None
    assert bus_receipt.state == "queued"
    fake.assert_pushed_count(_ValueJob, 4)


@pytest.mark.anyio
async def test_pending_chain_and_batch_reject_reuse() -> None:
    """Keep chain and batch builders single-use after dispatch.

    Reusing a builder could repeat application side effects.
    """
    application = _application()

    async with application:
        manager = application.container.make(QueueManager)
        chain = (
            manager.chain([_ValueJob("middle")])
            .prepend(_ValueJob("first"))
            .append(_ValueJob("last"))
            .on_connection("sync")
            .on_queue("chain")
        )
        chain_receipt = await chain.dispatch_async()
        batch = (
            manager.batch([_ValueJob("batch")])
            .name("Unit batch")
            .on_connection("sync")
            .on_queue("batch")
            .allow_failures()
        )
        batch_handle = await batch.dispatch_async()

        with pytest.raises(QueueDispatchError):
            await chain.dispatch_async()
        with pytest.raises(QueueDispatchError):
            chain.append(_ValueJob("too-late"))
        with pytest.raises(QueueError):
            await batch.dispatch_async()
        with pytest.raises(QueueError):
            batch.allow_failures()
        with pytest.raises(QueueConfigurationError):
            manager.chain([])
        with pytest.raises(QueueConfigurationError):
            manager.batch([])
        with pytest.raises(QueueConfigurationError):
            manager.batch([_ValueJob("invalid")]).name(" \n")
        with pytest.raises(QueueConfigurationError):
            manager.chain([_ValueJob("invalid")]).prepend(object())
        with pytest.raises(QueueConfigurationError):
            manager.chain([_ValueJob("invalid")]).on_queue("../unsafe")
        with pytest.raises(QueueConfigurationError):
            manager.batch([_ValueJob("invalid")]).on_connection("missing")

    assert chain_receipt.state == "executed"
    assert chain_receipt.result == "first"
    assert batch_handle.name == "Unit batch"
    assert batch_handle.total_jobs == 1
    assert batch_handle.pending_jobs == 0
    assert batch_handle.processed_jobs == 1
    assert batch_handle.failed_jobs == 0
    assert batch_handle.id
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
