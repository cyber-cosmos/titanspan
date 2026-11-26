"""Define the framework's native asynchronous HTTP middleware boundary.

Callers rely on native contracts, not concrete backend types.
"""

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from titanspan.contracts.http.request import HttpRequest
from titanspan.contracts.http.response import HttpResponse

type RequestHandler = Callable[[HttpRequest], Awaitable[HttpResponse]]


@runtime_checkable
class HttpMiddleware(Protocol):
    """Transform one request or response around downstream handling.

    Callers rely on native contracts, not concrete backend types.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Process a request and optionally transform its response.

        Args:
            request: Native request value scoped to one ASGI invocation.
            next_handler: Ordered continuation for downstream middleware or
                the configured application routes.

        Returns:
            The response that should be transmitted for this request.
        """
        ...


__all__ = ["HttpMiddleware", "RequestHandler"]
