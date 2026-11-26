"""Resolve the active request and response factory through the app container.

Both helpers resolve services from the active application.
"""

from typing import overload

from titanspan._application_context import (
    active_application_context,
)
from titanspan.container import BindingResolutionError
from titanspan.contracts.http import HttpResponse, ResponseFactory
from titanspan.http.exceptions import HttpContextError
from titanspan.http.request import Request

_REQUEST_CONTEXT_ERROR = (
    "The request helper is available only during an active HTTP request."
)
_RESPONSE_CONTEXT_ERROR = (
    "Bind an application context before creating an HTTP response."
)
_INVALID_RESPONSE_CONTENT_ERROR = (
    "Plain response content must be text, bytes, or None."
)
_NO_RESPONSE_ARGUMENT = object()


def request() -> Request:
    """Return the request seeded in the current execution scope.

    Returns:
        The exact request object used by dependency injection and middleware.

    Raises:
        HttpContextError: If there is no active request scope.
    """
    active = active_application_context()
    if active is None:
        raise HttpContextError(_REQUEST_CONTEXT_ERROR)
    try:
        return active.container.make(Request)
    except BindingResolutionError as error:
        raise HttpContextError(_REQUEST_CONTEXT_ERROR) from error


@overload
def response() -> ResponseFactory:
    """Return the active application's response factory.

    Both helpers resolve services from the active application.
    """


@overload
def response(
    content: str | bytes | None,
    *,
    status: int = 200,
) -> HttpResponse:
    """Create a plain response through the active factory.

    Both helpers resolve services from the active application.
    """


def response(
    content: str | bytes | None | object = _NO_RESPONSE_ARGUMENT,
    *,
    status: int = 200,
) -> ResponseFactory | HttpResponse:
    """Resolve the app factory or create a simple response immediately.

    Args:
        content: Optional plain text or byte body.
        status: HTTP response status when content is provided.

    Returns:
        The response factory when called without content, otherwise a response.

    Raises:
        HttpContextError: If no Titanspan application is active.
    """
    active = active_application_context()
    if active is None:
        raise HttpContextError(_RESPONSE_CONTEXT_ERROR)
    try:
        factory = active.container.make(ResponseFactory)
    except BindingResolutionError as error:
        raise HttpContextError(_RESPONSE_CONTEXT_ERROR) from error
    if content is _NO_RESPONSE_ARGUMENT:
        return factory
    if content is not None and not isinstance(content, (str, bytes)):
        raise TypeError(_INVALID_RESPONSE_CONTENT_ERROR)
    return factory(content, status=status)


__all__ = ["request", "response"]
