"""Define the framework's native asynchronous HTTP middleware boundary.

Callers rely on native contracts, not concrete backend types.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from titanspan.contracts.http.request import HttpRequest
from titanspan.contracts.http.response import HttpResponse

type RequestHandler = Callable[[HttpRequest], Awaitable[HttpResponse]]

_EMPTY_MIDDLEWARE_ALIAS_ERROR = "Middleware aliases must not be empty."
_EMPTY_MIDDLEWARE_PARAMETER_ERROR = (
    "Middleware parameters must be non-empty strings."
)


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


@runtime_checkable
class ParameterizedHttpMiddleware(HttpMiddleware, Protocol):
    """Describe middleware that accepts immutable route parameters.

    Implementations receive parameters for each declaration. They must not
    store request-specific values on an application-owned instance.
    """

    async def handle_with_parameters(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
        parameters: tuple[str, ...],
    ) -> HttpResponse:
        """Process one request using its route declaration parameters.

        Args:
            request: Native request scoped to one ASGI invocation.
            next_handler: Ordered continuation through the middleware chain.
            parameters: Immutable values from one route declaration.

        Returns:
            The response that should be transmitted for this request.
        """
        ...


@dataclass(frozen=True, slots=True)
class MiddlewareDeclaration:
    """Bind one middleware alias or class to immutable string parameters.

    Use this value in route, group, or resource middleware declarations.
    """

    target: str | type[HttpMiddleware]
    parameters: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate and freeze the declaration values.

        Raises:
            ValueError: If an alias or parameter is empty.
        """
        if isinstance(self.target, str) and not self.target.strip():
            raise ValueError(_EMPTY_MIDDLEWARE_ALIAS_ERROR)

        parameters = tuple(self.parameters)
        if any(not parameter.strip() for parameter in parameters):
            raise ValueError(_EMPTY_MIDDLEWARE_PARAMETER_ERROR)
        object.__setattr__(self, "parameters", parameters)


type MiddlewareItem = str | type[HttpMiddleware] | MiddlewareDeclaration


__all__ = [
    "HttpMiddleware",
    "MiddlewareDeclaration",
    "MiddlewareItem",
    "ParameterizedHttpMiddleware",
    "RequestHandler",
]
