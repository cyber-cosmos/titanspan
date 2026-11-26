"""Define callable types used by the native application lifecycle.

These aliases keep lifecycle hooks independent of the application
implementation and its ASGI adapter.
"""

from collections.abc import Awaitable, Callable

from titanspan.contracts.http import HttpResponse

ApplicationLifecycleCallback = Callable[[], object | Awaitable[object]]
ApplicationExceptionHandler = Callable[
    ...,
    HttpResponse | Awaitable[HttpResponse],
]

__all__ = [
    "ApplicationExceptionHandler",
    "ApplicationLifecycleCallback",
]
