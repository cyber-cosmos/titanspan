"""Expose the native event API and its application integration boundary.

Backend adapters remain private to the component package.
"""

from titanspan.contracts.events import (
    EventDispatcher,
    EventSelector,
)
from titanspan.events.configuration import (
    EventsConfiguration,
    EventsConfigurationError,
)
from titanspan.events.discovery import (
    DiscoveryEntry,
    cache_events,
    clear_event_cache,
    discover_events,
    inspect_events,
)
from titanspan.events.dispatchable import Dispatchable
from titanspan.events.dispatcher import (
    ListenerRegistration,
    NativeEventDispatcher,
)
from titanspan.events.exceptions import (
    AsyncDispatchRequiredError,
    DeferredBufferOverflowError,
    EventDiscoveryError,
    EventError,
    EventRegistrationError,
)
from titanspan.events.helpers import event, event_async
from titanspan.events.listener import (
    ListenerReference,
    listener,
    subscriber,
)
from titanspan.events.service_provider import EventServiceProvider
from titanspan.events.testing import EventFake, EventRecord

__all__ = [
    "AsyncDispatchRequiredError",
    "DeferredBufferOverflowError",
    "DiscoveryEntry",
    "Dispatchable",
    "EventDiscoveryError",
    "EventDispatcher",
    "EventError",
    "EventFake",
    "EventRecord",
    "EventRegistrationError",
    "EventSelector",
    "EventServiceProvider",
    "EventsConfiguration",
    "EventsConfigurationError",
    "ListenerReference",
    "ListenerRegistration",
    "NativeEventDispatcher",
    "cache_events",
    "clear_event_cache",
    "discover_events",
    "event",
    "event_async",
    "inspect_events",
    "listener",
    "subscriber",
]
