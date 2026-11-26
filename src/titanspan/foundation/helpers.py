"""Provide context-aware helpers for the active application lifecycle.

The helpers read Foundation's existing execution context and do not create an
application or maintain a second service registry.
"""

from titanspan._application_context import (
    ApplicationContextError,
    active_application_context,
)
from titanspan.foundation.application import Application

_MISSING_APPLICATION_ERROR = (
    "No active application context is available. Enter an Application "
    "context before calling app()."
)


def app() -> Application:
    """Return the application bound to the current execution context.

    Returns:
        The active Titanspan application and its canonical service container.

    Raises:
        ApplicationContextError: If there is no valid active application.

    Notes:
        The helper never constructs an application and does not provide a
        process-global fallback.
    """
    active = active_application_context()
    if (
        active is None
        or not isinstance(active.application, Application)
        or active.container is not active.application.container
    ):
        raise ApplicationContextError(_MISSING_APPLICATION_ERROR)
    return active.application


__all__ = ["app"]
