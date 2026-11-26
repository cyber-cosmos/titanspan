"""Provide trusted module members for event discovery tests.

Discovery reads these declarations from the explicitly trusted module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

# Container.call_async resolves this annotation during subscriber startup.
from titanspan.contracts.events import EventDispatcher  # noqa: TC001
from titanspan.events import listener, subscriber


@dataclass(frozen=True, slots=True)
class FixtureEvent:
    """Identify one event declared inside the trusted fixture module.

    Discovery reads these declarations from the explicitly trusted module.
    """

    value: str


@dataclass(frozen=True, slots=True)
class FixtureUpdated:
    """Identify a second event in a union annotation.

    Discovery reads these declarations from the explicitly trusted module.
    """

    value: str


@listener(FixtureEvent)
def function_listener(event: FixtureEvent) -> str:
    """Return the event value as a discovery registration marker.

    Discovery reads these declarations from the explicitly trusted module.
    """
    return f"function:{event.value}"


class ClassListener:
    """Declare a listener through its annotated handle method.

    Discovery reads these declarations from the explicitly trusted module.
    """

    def handle(self, event: FixtureEvent) -> str:
        """Return a class-listener registration marker.

        Args:
            event: Event value discovered from this parameter annotation.

        Returns:
            A stable marker for the discovery integration assertion.
        """
        return f"class:{event.value}"


@listener(FixtureEvent)
class DeclaredClassListener:
    """Declare an event class directly on its listener type.

    Discovery uses the decorator instead of inferring a method annotation.
    """

    def handle(self, event: FixtureEvent) -> str:
        """Return a marker for class-level listener metadata.

        Args:
            event: Class event selected by the decorator metadata.

        Returns:
            Stable marker for the decorated listener class.
        """
        return f"declared:{event.value}"


class MethodShapeListener:
    """Exercise static and class method discovery rules.

    Discovery accepts static functions and ignores classmethod descriptors.
    """

    @staticmethod
    def handle_static(event: FixtureUpdated) -> str:
        """Return a marker for a static listener method.

        Args:
            event: Event selected from the static method annotation.

        Returns:
            Stable marker for the discovered static listener.
        """
        return f"static:{event.value}"

    @classmethod
    def handle_class(
        cls,
        event: FixtureEvent,
    ) -> str:
        """Mark a method form excluded from automatic discovery.

        Args:
            cls: Listener type supplied by Python's classmethod descriptor.
            event: Event value that discovery must not register here.

        Returns:
            Stable marker if an explicit caller invokes this method.
        """
        return f"class-method:{cls.__name__}:{event.value}"


class AnnotatedListener:
    """Declare event matching through an annotated payload parameter.

    Discovery unwraps the metadata while preserving the event class.
    """

    def handle_annotated(
        self,
        event: Annotated[FixtureEvent, "domain event"],
    ) -> str:
        """Return a marker for an annotated listener parameter.

        Args:
            event: Event class wrapped with non-binding metadata.

        Returns:
            Stable marker for the annotated event listener.
        """
        return f"annotated:{event.value}"


def listener_without_payload() -> None:
    """Declare no listener payload for signature discovery.

    Discovery ignores unannotated functions with no positional payload.
    """


@listener("workflow.*")
def named_listener(event_name: str, payload: object) -> str:
    """Declare a named wildcard through explicit decorator metadata.

    Args:
        event_name: Canonical name supplied by wildcard dispatch.
        payload: Named-event payload delivered by the wildcard.

    Returns:
        Stable marker for the named listener.
    """
    return f"{event_name}:{payload}"


class UnionListener:
    """Declare one handler for two event classes through a union.

    Discovery reads these declarations from the explicitly trusted module.
    """

    def handle_union(self, event: FixtureEvent | FixtureUpdated) -> str:
        """Return a marker for either union member.

        Args:
            event: Event selected from the union parameter annotation.

        Returns:
            A stable marker proving each union member was discovered.
        """
        return f"union:{event.value}"


@subscriber
class FixtureSubscriber:
    """Declare several related handlers through a mapping.

    Discovery reads these declarations from the explicitly trusted module.
    """

    def subscribe(
        self,
        dispatcher: EventDispatcher,
    ) -> dict[type[FixtureEvent], str]:
        """Return an event-to-method declaration for the dispatcher.

        Args:
            dispatcher: Canonical dispatcher available for imperative use.

        Returns:
            Mapping from event class to this subscriber's handler method.
        """
        _ = dispatcher
        return {FixtureEvent: "handle"}

    def handle(self, event: FixtureEvent) -> str:
        """Return a subscriber registration marker.

        Args:
            event: Event passed explicitly before dependency injection.

        Returns:
            A stable marker for subscriber registration coverage.
        """
        return f"subscriber:{event.value}"
