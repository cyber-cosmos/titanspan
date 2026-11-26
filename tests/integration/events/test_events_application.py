"""Verify that Events uses the canonical application service graph.

The enclosing test observes this target through the framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from tests.unit.events._discovery_fixture import FixtureEvent

from titanspan import Application
from titanspan._application_context import active_application_context
from titanspan.container import Scope
from titanspan.contracts.events import EventDispatcher

# Container resolves this annotation from module globals at runtime.
from titanspan.contracts.logging import LoggingManager  # noqa: TC001
from titanspan.events import (
    DeferredBufferOverflowError,
    Dispatchable,
    EventsConfiguration,
    EventsConfigurationError,
    NativeEventDispatcher,
    event,
    event_async,
)
from titanspan.facades import Event

pytestmark = [pytest.mark.integration, pytest.mark.architecture]
_MISSING_CONTEXT_ERROR = "The application context was not active."

if TYPE_CHECKING:
    from pathlib import Path

    from titanspan.contracts.container import ServiceRegistry


class RecordingService:
    """Retain event identifiers and active application identity.

    The enclosing test observes this target through the framework.
    """

    def __init__(self) -> None:
        """Create an empty app-owned record list.

        The enclosing test observes this target through the framework.
        """
        self.records: list[tuple[str, object]] = []

    def add(self, event_id: str, application: object) -> None:
        """Retain one event and its application context.

        Args:
            event_id: Domain identifier carried by the event object.
            application: Active Titanspan application.
        """
        self.records.append((event_id, application))


class RecordingProvider:
    """Register the integration test's application-owned recording service.

    The enclosing test observes this target through the framework.
    """

    def __init__(self, service: RecordingService) -> None:
        """Retain the service instance provided by the test.

        Args:
            service: Object whose identity should survive resolution.
        """
        self._service = service

    def register(self, container: ServiceRegistry) -> None:
        """Contribute the recording service to native application bindings.

        Args:
            container: Application's canonical service registry.
        """
        container.instance(RecordingService, self._service)


@dataclass(frozen=True, slots=True)
class DocumentProcessed(Dispatchable):
    """Identify one processed document for integration coverage.

    The enclosing test observes this target through the framework.
    """

    document_id: str


class RecordDocument:
    """Resolve a real service and record one event through injection.

    The enclosing test observes this target through the framework.
    """

    def __init__(self, service: RecordingService) -> None:
        """Retain the service resolved from the application's container.

        Args:
            service: Recording service injected by the native container.
        """
        self._service = service

    def handle(self, event: DocumentProcessed) -> str:
        """Record the payload and return its stable event identifier.

        Args:
            event: Event object passed explicitly before dependency injection.

        Returns:
            The document identifier recorded by the injected service.
        """
        context = active_application_context()
        if context is None:
            raise RuntimeError(_MISSING_CONTEXT_ERROR)
        self._service.add(event.document_id, context.application)
        return event.document_id


class AsyncRecordDocument:
    """Resolve an application service for an asynchronous listener.

    The enclosing test observes this target through the framework.
    """

    def __init__(self, service: RecordingService) -> None:
        """Retain the dependency constructed by the active Container.

        Args:
            service: Recording service provided by the application.
        """
        self._service = service

    async def handle(self, event: DocumentProcessed) -> str:
        """Record the event through the explicit async listener path.

        Args:
            event: Event value supplied before dependency resolution.

        Returns:
            The recorded event identifier.
        """
        context = active_application_context()
        if context is None:
            raise RuntimeError(_MISSING_CONTEXT_ERROR)
        self._service.add(
            f"async-class:{event.document_id}",
            context.application,
        )
        return event.document_id


class ReadLoggingContext:
    """Read execution-local logging metadata inside a listener.

    The enclosing test observes this target through the framework.
    """

    def __init__(self, logging: LoggingManager) -> None:
        """Retain the application-owned logging manager.

        Args:
            logging: Manager resolved by the native application container.
        """
        self._logging = logging

    def handle(self, event: DocumentProcessed) -> dict[str, object]:
        """Return the active logging context to the dispatch caller.

        Args:
            event: Event value supplied by the dispatcher.

        Returns:
            A detached snapshot of task-local logging metadata.
        """
        _ = event
        return self._logging.get_context()


@dataclass(frozen=True, slots=True)
class WorkflowContext:
    """Carry one execution-local workflow identifier.

    The enclosing test observes this target through the framework.
    """

    workflow_id: str


class ReadWorkflowContext:
    """Resolve a value provided only by the current workflow scope.

    The enclosing test observes this target through the framework.
    """

    def __init__(self, context: WorkflowContext) -> None:
        """Retain the scope-owned workflow context.

        Args:
            context: Value provided by the active container scope.
        """
        self._context = context

    def handle(self, event: DocumentProcessed) -> str:
        """Return the event and active workflow identifiers.

        Args:
            event: Event dispatched from the active workflow scope.

        Returns:
            A stable pair encoded for the integration assertion.
        """
        return f"{event.document_id}:{self._context.workflow_id}"


async def record_document_async(
    event: DocumentProcessed,
    service: RecordingService,
) -> str:
    """Resolve a callable dependency and retain an async event result.

    Args:
        event: Event object supplied explicitly to the listener.
        service: Service resolved from the active application container.

    Returns:
        The document identifier recorded by the injected service.
    """
    context = active_application_context()
    if context is None:
        raise RuntimeError(_MISSING_CONTEXT_ERROR)
    service.add(f"async-call:{event.document_id}", context.application)
    return event.document_id


@pytest.mark.anyio
async def test_facade_helpers_and_injection_share_one_dispatcher() -> None:
    """Resolve the same application dispatcher through all entry points.

    The scenario exercises this behavior through the real application graph.
    """
    service = RecordingService()
    application = Application(
        service_providers=[RecordingProvider(service)],
    )

    async with application:
        contract = application.make(EventDispatcher)
        concrete = application.make(NativeEventDispatcher)
        Event.listen(DocumentProcessed, RecordDocument)

        assert contract is concrete
        assert Event.dispatch(DocumentProcessed("sync")) == ["sync"]
        assert await event_async(DocumentProcessed("async")) == ["async"]
        assert event(DocumentProcessed("helper")) == ["helper"]
        assert DocumentProcessed.dispatch(
            document_id="dispatchable",
        ) == ["dispatchable"]
        assert DocumentProcessed.dispatch_if(
            True,
            document_id="conditional",
        ) == ["conditional"]
        Event.listen(DocumentProcessed, record_document_async)
        Event.listen(DocumentProcessed, AsyncRecordDocument)
        assert await Event.dispatch_async(
            DocumentProcessed("injected-async"),
        ) == [
            "injected-async",
            "injected-async",
            "injected-async",
        ]
        assert service.records == [
            ("sync", application),
            ("async", application),
            ("helper", application),
            ("dispatchable", application),
            ("conditional", application),
            ("injected-async", application),
            ("async-call:injected-async", application),
            ("async-class:injected-async", application),
        ]


@pytest.mark.anyio
async def test_fake_intercepts_facade_helper_and_injected_dispatcher() -> None:
    """Record selected dispatches without running real listeners.

    The scenario exercises this behavior through the real application graph.
    """
    service = RecordingService()
    application = Application(
        service_providers=[RecordingProvider(service)],
    )

    async with application:
        dispatcher = application.make(EventDispatcher)
        Event.listen(DocumentProcessed, RecordDocument)

        with Event.fake([DocumentProcessed]) as fake:
            Event.dispatch(DocumentProcessed("facade"))
            await event_async(DocumentProcessed("helper"))
            dispatcher.dispatch(DocumentProcessed("injected"))
            fake.assert_dispatched(DocumentProcessed, times=3)

        assert service.records == []
        Event.dispatch(DocumentProcessed("real"))
        assert service.records == [("real", application)]


def test_invalid_event_configuration_fails_application_composition() -> None:
    """Reject invalid event settings through the established Config model.

    The scenario exercises this behavior through the real application graph.
    """
    with pytest.raises(EventsConfigurationError, match="configuration"):
        Application(config={"events": {"unknown": True}})


@pytest.mark.anyio
async def test_logging_context_is_available_inside_injected_listeners() -> None:
    """Preserve application logging metadata through event resolution.

    The scenario exercises this behavior through the real application graph.
    """
    application = Application()

    async with application:
        dispatcher = application.make(EventDispatcher)
        Event.listen(DocumentProcessed, ReadLoggingContext)

        with application.logging.context(correlation_id="run-1"):
            responses = dispatcher.dispatch(DocumentProcessed("logged"))

    assert responses == [{"correlation_id": "run-1"}]


@pytest.mark.anyio
async def test_listener_resolution_uses_the_active_workflow_scope() -> None:
    """Resolve a listener's scoped dependency from active execution state.

    The scenario exercises this behavior through the real application graph.
    """
    application = Application()

    async with (
        application,
        application.execution_scope(
            Scope.WORKFLOW,
        ) as scope,
    ):
        scope.provide_instance(
            WorkflowContext,
            WorkflowContext("workflow-1"),
        )
        Event.listen(DocumentProcessed, ReadWorkflowContext)

        result = Event.dispatch(DocumentProcessed("doc-1"))

    assert result == ["doc-1:workflow-1"]


@pytest.mark.anyio
async def test_application_boot_discovers_and_caches_trusted_listeners(
    tmp_path: Path,
) -> None:
    """Discover configured listeners through real provider startup.

    The scenario exercises this behavior through the real application graph.
    """
    manifest_path = tmp_path / "events.json"
    configuration = {
        "events": {
            "discovery_modules": [
                "tests.unit.events._discovery_fixture",
            ],
            "manifest_path": str(manifest_path),
        },
    }

    first = Application(config=configuration)
    async with first:
        assert Event.dispatch(FixtureEvent("first")) == [
            "annotated:first",
            "class:first",
            "declared:first",
            "subscriber:first",
            "union:first",
            "function:first",
        ]

    assert manifest_path.is_file()

    second = Application(config=configuration)
    async with second:
        assert Event.dispatch(FixtureEvent("cached")) == [
            "annotated:cached",
            "class:cached",
            "declared:cached",
            "subscriber:cached",
            "union:cached",
            "function:cached",
        ]


@pytest.mark.anyio
async def test_applications_own_independent_dispatcher_registries() -> None:
    """Keep event listeners isolated when application contexts nest.

    The scenario exercises this behavior through the real application graph.
    """
    first = Application()
    second = Application()

    def record_first(event: DocumentProcessed) -> str:
        """Return the first application's event identifier.

        The enclosing test observes this target through the framework.
        """
        return event.document_id

    async with first:
        Event.listen(DocumentProcessed, record_first)
        first_dispatcher = first.make(EventDispatcher)

        async with second:
            second_dispatcher = second.make(EventDispatcher)

            assert second_dispatcher is not first_dispatcher
            assert Event.dispatch(DocumentProcessed("second")) == []

        assert Event.dispatch(DocumentProcessed("first")) == ["first"]


def test_missing_event_configuration_uses_established_defaults() -> None:
    """Read absent settings through the canonical validated repository.

    The scenario exercises this behavior through the real application graph.
    """
    application = Application()

    configuration = EventsConfiguration.from_repository(application.config)

    assert configuration == EventsConfiguration()


def test_invalid_event_configuration_shape_fails_with_native_error() -> None:
    """Reject a non-mapping namespace through the shared configuration model.

    The scenario exercises this behavior through the real application graph.
    """
    with pytest.raises(EventsConfigurationError, match="configuration"):
        Application(config={"events": []})


@pytest.mark.anyio
async def test_configuration_bounds_deferred_event_buffers() -> None:
    """Apply configured buffer limits to real application dispatch.

    The scenario exercises this behavior through the real application graph.
    """
    service = RecordingService()
    application = Application(
        config={"events": {"deferred_buffer_limit": 1}},
        service_providers=[RecordingProvider(service)],
    )

    async with application:
        dispatcher = application.make(NativeEventDispatcher)

        def exceed_buffer() -> None:
            """Fill the configured event buffer beyond its limit.

            The enclosing test observes this target through the framework.
            """
            with dispatcher.defer():
                dispatcher.dispatch(DocumentProcessed("first"))
                dispatcher.dispatch(DocumentProcessed("overflow"))

        with pytest.raises(DeferredBufferOverflowError):
            exceed_buffer()

    assert service.records == []


@pytest.mark.anyio
async def test_facade_exposes_dispatcher_query_and_removal_operations() -> None:
    """Exercise query, halting, and removal methods through the facade.

    The application owns the dispatcher used by each public entry point.
    """
    application = Application()
    observed: list[str] = []

    def respond(payload: object) -> str:
        """Record a named payload and return its string value.

        Args:
            payload: Explicit payload supplied by named dispatch.

        Returns:
            The payload converted to a stable response.
        """
        value = str(payload)
        observed.append(value)
        return value

    def observe_wildcard(name: str, payload: object) -> None:
        """Record canonical name and payload for wildcard matching.

        Args:
            name: Canonical named event selected by the pattern.
            payload: Optional payload represented by named dispatch.
        """
        observed.append(f"{name}:{payload}")

    async def respond_async(payload: object) -> str:
        """Record one payload through an asynchronous listener.

        Args:
            payload: Explicit payload supplied by named dispatch.

        Returns:
            The payload converted to a stable response.
        """
        value = str(payload)
        observed.append(f"async:{value}")
        return value

    async with application:
        handle = Event.listen("query.ready", respond)
        wildcard = Event.listen("query.*", observe_wildcard)

        assert Event.has_listeners("query.ready")
        assert Event.has_wildcard_listeners()
        assert Event.has_wildcard_listeners("query.ready")
        assert not Event.has_wildcard_listeners("other.ready")
        assert Event.get_listeners("query.ready") == (
            respond,
            observe_wildcard,
        )
        assert Event.until("query.ready", "sync") == "sync"
        assert observed == ["sync"]

        handle.close()
        wildcard.close()
        assert not Event.has_listeners("query.ready")
        Event.listen("query.ready", respond_async)
        assert await Event.until_async("query.ready", "async") == "async"

        Event.forget("query.ready", respond_async)
        assert Event.get_listeners("query.ready") == ()
        assert observed == ["sync", "async:async"]


@pytest.mark.anyio
async def test_dispatchable_async_and_conditional_variants() -> None:
    """Exercise explicit async and unless dispatch conveniences.

    Conditions are evaluated before the event class is constructed.
    """
    application = Application()
    observed: list[str] = []

    def record(event: DocumentProcessed) -> str:
        """Return and retain one dispatched document identifier.

        Args:
            event: Class-based payload provided by Dispatchable.

        Returns:
            The dispatched document identifier.
        """
        observed.append(event.document_id)
        return event.document_id

    def condition_true() -> bool:
        """Return a sync predicate value for an async API.

        The async convenience accepts ordinary synchronous callbacks.
        """
        return True

    async def condition_false() -> bool:
        """Return an awaited false predicate for async dispatch.

        A skipped event does not invoke a listener.
        """
        return False

    async with application:
        Event.listen(DocumentProcessed, record)

        assert await DocumentProcessed.dispatch_async(
            document_id="async",
        ) == ["async"]
        assert DocumentProcessed.dispatch_unless(
            False,
            document_id="unless-sync",
        ) == ["unless-sync"]
        assert (
            DocumentProcessed.dispatch_unless(
                True,
                document_id="skipped-sync",
            )
            is None
        )
        assert await DocumentProcessed.dispatch_if_async(
            condition_true,
            document_id="if-async-sync-condition",
        ) == ["if-async-sync-condition"]
        assert (
            await DocumentProcessed.dispatch_if_async(
                condition_false,
                document_id="skipped-if-async",
            )
            is None
        )
        assert await DocumentProcessed.dispatch_unless_async(
            condition_false,
            document_id="unless-async",
        ) == ["unless-async"]
        assert (
            await DocumentProcessed.dispatch_unless_async(
                True,
                document_id="skipped-unless-async",
            )
            is None
        )

    assert observed == [
        "async",
        "unless-sync",
        "if-async-sync-condition",
        "unless-async",
    ]


@pytest.mark.anyio
async def test_facade_subscribers_push_and_deferred_dispatch() -> None:
    """Use facade lifecycle methods with synchronous and async subscribers.

    All operations reach the same application-owned dispatcher.
    """
    application = Application()
    observed: list[str] = []

    def respond_sync(payload: object) -> str:
        """Record one synchronous named event payload.

        Args:
            payload: Explicit payload passed by the dispatcher.

        Returns:
            The payload converted to a stable string.
        """
        value = str(payload)
        observed.append(value)
        return value

    async def respond_async(payload: object) -> str:
        """Record one asynchronous named event payload.

        Args:
            payload: Explicit payload passed by the dispatcher.

        Returns:
            The payload converted to a stable string.
        """
        value = str(payload)
        observed.append(value)
        return value

    class SyncSubscriber:
        """Register one named event through the facade subscriber API.

        Its listener is resolved from the subscriber mapping.
        """

        def subscribe(self, dispatcher: EventDispatcher) -> dict[str, str]:
            """Return the synchronous listener declaration.

            Args:
                dispatcher: Canonical application dispatcher.

            Returns:
                Mapping for the subscriber's handler method.
            """
            _ = dispatcher
            return {"subscribed.sync": "handle"}

        def handle(self, payload: object) -> str:
            """Record the payload selected by subscription metadata.

            Args:
                payload: Explicit event value.

            Returns:
                A stable response.
            """
            return respond_sync(payload)

    class AsyncSubscriber:
        """Register one named event through async subscriber setup.

        The facade waits for registration before returning.
        """

        async def subscribe(self, dispatcher: EventDispatcher) -> None:
            """Register the asynchronous payload listener directly.

            Args:
                dispatcher: Canonical application dispatcher.
            """
            dispatcher.listen("subscribed.async", respond_async)

    async with application:
        Event.subscribe(SyncSubscriber())
        await Event.subscribe_async(AsyncSubscriber())
        assert Event.dispatch("subscribed.sync", "subscriber") == [
            "subscriber",
        ]
        assert await Event.dispatch_async(
            "subscribed.async",
            "async-subscriber",
        ) == ["async-subscriber"]

        Event.listen("push.sync", respond_sync)
        Event.push("push.sync", "pushed")
        assert Event.flush("push.sync") == ["pushed"]
        assert Event.flush("push.sync") == ["pushed"]
        Event.forget_pushed()
        assert Event.flush("push.sync") == []

        Event.listen("push.async", respond_async)
        Event.push("push.async", "pushed-async")
        assert await Event.flush_async("push.async") == ["pushed-async"]
        Event.forget_pushed()

        with Event.defer():
            Event.dispatch("push.sync", "deferred")
            assert observed[-1] == "pushed-async"
        assert observed[-1] == "deferred"

        async with Event.defer_async():
            await Event.dispatch_async("push.async", "deferred-async")
            assert observed[-1] == "deferred"
        assert observed[-1] == "deferred-async"

        with Event.fake_except(["push.sync"]) as fake:
            Event.dispatch("push.async", "fake")
            Event.dispatch("push.sync", "real")
            fake.assert_dispatched("push.async", times=1)

        assert observed[-1] == "real"
