"""Share small event naming and matching operations inside the component.

Backend adapters and public APIs share these framework-owned rules.
"""

from fnmatch import fnmatchcase

from titanspan.contracts.events import EventSelector
from titanspan.events.exceptions import EventRegistrationError

MISSING_EVENT_PAYLOAD = object()


def canonical_event_name(event: object | str) -> str:
    """Return a stable name for diagnostics and named-event matching.

    Args:
        event: A named event or ordinary Python event object.

    Returns:
        The exact string name or fully qualified event class name.
    """
    if isinstance(event, str):
        return event
    event_type = type(event)
    return f"{event_type.__module__}.{event_type.__qualname__}"


def selector_matches(
    selector: EventSelector,
    event: object | str,
) -> bool:
    """Check a named glob or Python class selector against an event.

    Args:
        selector: Exact name, glob pattern, or event class.
        event: Named event or event object being matched.

    Returns:
        Whether the selector matches the event.

    Raises:
        EventRegistrationError: If a class selector cannot be used for
            runtime matching.
    """
    if isinstance(selector, str):
        return fnmatchcase(canonical_event_name(event), selector)
    if isinstance(event, str):
        return False
    try:
        return isinstance(event, selector)
    except TypeError as error:
        message = (
            "Event class selectors must support Python runtime instance checks."
        )
        raise EventRegistrationError(message) from error


def selector_is_wildcard(selector: EventSelector) -> bool:
    """Identify named glob selectors without matching a concrete event.

    Args:
        selector: Event class or named-event selector.

    Returns:
        Whether the selector contains a glob metacharacter.
    """
    return isinstance(selector, str) and any(
        character in selector for character in "*?["
    )


__all__ = [
    "canonical_event_name",
    "selector_is_wildcard",
    "selector_matches",
]
