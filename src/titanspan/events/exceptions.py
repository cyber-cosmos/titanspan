"""Define native event failures with actionable recovery guidance.

Callers can handle event failures without depending on Blinker.
"""


class EventError(RuntimeError):
    """Report an event registration, dispatch, or lifecycle failure.

    Framework event failures share one catchable base type.
    """


class EventRegistrationError(EventError):
    """Report an invalid listener or event registration.

    The error includes registration failures at the API boundary.
    """


class AsyncDispatchRequiredError(EventError):
    """Report that a dispatch contains asynchronous listener work.

    The message directs callers to explicit async dispatch.
    """


class EventDiscoveryError(EventError):
    """Report a trusted module discovery or manifest failure.

    The exception identifies trusted discovery or cache failures.
    """


class DeferredBufferOverflowError(EventError):
    """Report that execution-local deferred events reached their limit.

    The error reports bounded execution-local buffer overflow.
    """


__all__ = [
    "AsyncDispatchRequiredError",
    "DeferredBufferOverflowError",
    "EventDiscoveryError",
    "EventError",
    "EventRegistrationError",
]
