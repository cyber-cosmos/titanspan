"""Verify Foundation renders failures from native global middleware.

The tests exercise real application scopes, exception handlers, and ASGI.
"""

from http import HTTPStatus
from threading import get_ident
from uuid import uuid4

import anyio
import httpx2
import pytest
from starlette.requests import Request as StarletteRequest
from starlette.responses import PlainTextResponse
from starlette.responses import Response as StarletteResponse

from titanspan.container import Scope
from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.http import (
    HttpRequest,
    HttpResponse,
    RequestHandler,
    ResponseFactory,
)
from titanspan.contracts.validation import ValidationIssue
from titanspan.facades import Log
from titanspan.foundation import Application
from titanspan.validation import ValidationException

pytestmark = [pytest.mark.architecture, pytest.mark.integration]

_PRIVATE_FAILURE = "middleware-private-marker"
_EXPECTED_REQUEST_COUNT = 2


class _PublicFailureError(Exception):
    """Represent a safe error selected by a custom exception handler.
    """  # fmt: skip


class _RequestMarker:
    """Identify the request-owned scope used by an exception renderer.

    UUID values prevent object-address reuse from hiding scope leakage.
    """

    def __init__(self) -> None:
        """Create one stable marker for the current request scope.

        The token lets the test compare independent requests.
        """
        self.token = uuid4().hex

    token: str


class _RequestMarkerProvider:
    """Register a fresh dependency for every incoming request.

    The Container creates each marker inside the request scope.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Bind request-scoped state in the application container.

        Args:
            container: Canonical service registry owned by the application.
        """
        container.scoped(_RequestMarker, scope=Scope.REQUEST)


class _PublicFailureMiddleware:
    """Raise one public error outside route-level exception middleware.

    The test compares this path with a routed endpoint.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Raise on one path and continue all other requests.

        Args:
            request: Active native request supplied by Foundation.
            next_handler: Remaining application request pipeline.

        Returns:
            The downstream response for paths without a middleware failure.

        Raises:
            _PublicFailureError: If the request targets the public failure path.
        """
        if request.path == "/global":
            raise _PublicFailureError(_PRIVATE_FAILURE)
        return await next_handler(request)


class _ValidationFailureMiddleware:
    """Raise a native validation failure before route dispatch.

    Foundation must apply the same safe response policy as for routes.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Raise one safe issue for the configured integration request.

        Args:
            request: Active native request supplied by Foundation.
            next_handler: Remaining application request pipeline.

        Returns:
            The downstream response when no failure is configured.

        Raises:
            ValidationException: Always for the test path.
        """
        _ = request, next_handler
        raise ValidationException(
            (
                ValidationIssue(
                    location=("profile", "email"),
                    message="The address is invalid.",
                    code="email",
                ),
            )
        )


class _UnexpectedFailureMiddleware:
    """Raise an unexpected failure for safe logging verification.

    The private message must not appear in the response or log record.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Raise a private detail before route dispatch.

        Args:
            request: Active native request supplied by Foundation.
            next_handler: Remaining application request pipeline.

        Returns:
            The downstream response when no failure is configured.

        Raises:
            RuntimeError: Always for the test path.
        """
        _ = request, next_handler
        raise RuntimeError(_PRIVATE_FAILURE)


class _WaitingMiddleware:
    """Pause request processing until the test cancels the owner task.

    The events expose request entry and deterministic cleanup.
    """

    def __init__(self) -> None:
        """Create deterministic entry and finalization events.

        The test waits for these signals instead of sleeping.
        """
        self.entered = anyio.Event()
        self.finished = anyio.Event()

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Wait for cancellation and expose cleanup completion.

        Args:
            request: Active native request supplied by Foundation.
            next_handler: Remaining application request pipeline.

        Returns:
            The downstream response if the test releases the wait normally.
        """
        self.entered.set()
        try:
            await anyio.sleep_forever()
        finally:
            self.finished.set()
        return await next_handler(request)


class _WaitingMiddlewareProvider:
    """Bind a preconfigured middleware instance through the native graph.

    The provider does not create a competing middleware registry.
    """

    def __init__(self, middleware: _WaitingMiddleware) -> None:
        """Retain the test-owned synchronization middleware.

        Args:
            middleware: Middleware whose events coordinate cancellation.
        """
        self.middleware = middleware

    def register(self, container: ServiceRegistry) -> None:
        """Register that instance without adding another middleware registry.

        Args:
            container: Canonical service registry owned by the application.
        """
        container.instance(_WaitingMiddleware, self.middleware)

    middleware: _WaitingMiddleware


@pytest.mark.anyio
async def test_global_middleware_uses_custom_handler_and_request_scope() -> (
    None
):
    """Render middleware errors like routed errors with injected services.

    Each request receives a distinct scoped marker and exits its scope.
    """
    application = Application(
        http_middleware=(_PublicFailureMiddleware,),
        service_providers=(_RequestMarkerProvider(),),
    )
    observed: list[str] = []

    async def fail_from_route() -> None:
        """Raise the same public error from a routed endpoint.

        Raises:
            _PublicFailureError: The error rendered by the shared handler.
        """
        raise _PublicFailureError(_PRIVATE_FAILURE)

    application.router.get("/route", fail_from_route)

    async def render_public_failure(
        request: HttpRequest,
        exception: _PublicFailureError,
        marker: _RequestMarker,
        factory: ResponseFactory,
    ) -> HttpResponse:
        """Return a safe response using request-scoped injection.

        Args:
            request: Request associated with the public failure.
            exception: Classified error selected by Foundation.
            marker: Request-owned service resolved by the Container.
            factory: Canonical application response factory.

        Returns:
            A public response that excludes internal error text.
        """
        _ = exception
        observed.append(marker.token)
        return factory.json(
            {"path": request.path, "marker": marker.token},
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        )

    application.add_exception_handler(
        _PublicFailureError,
        render_public_failure,
    )

    async with application:
        transport = httpx2.ASGITransport(
            app=application.asgi,
            raise_app_exceptions=False,
        )
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            global_result = await client.get("/global")
            route_result = await client.get("/route")

    assert global_result.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert route_result.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert global_result.json()["path"] == "/global"
    assert route_result.json()["path"] == "/route"
    assert _PRIVATE_FAILURE not in global_result.text
    assert _PRIVATE_FAILURE not in route_result.text
    assert len(observed) == _EXPECTED_REQUEST_COUNT
    assert observed[0] != observed[1]
    assert application.container.active_scope_count == 0


@pytest.mark.anyio
async def test_global_middleware_uses_native_validation_renderer() -> None:
    """Render middleware validation failures with the native 422 policy.

    The error includes safe field details without backend diagnostics.
    """
    application = Application(
        http_middleware=(_ValidationFailureMiddleware,),
    )

    async with application:
        transport = httpx2.ASGITransport(
            app=application.asgi,
            raise_app_exceptions=False,
        )
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/invalid")

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json() == {
        "detail": "Request validation failed.",
        "errors": {"profile.email": ["The address is invalid."]},
    }
    assert application.container.active_scope_count == 0


@pytest.mark.anyio
async def test_global_unexpected_failure_is_safe_and_logged() -> None:
    """Return a generic 500 while the active logger records classification.

    Exception text remains absent from the response and ordinary log record.
    """
    application = Application(
        config={"app": {"debug": False}},
        http_middleware=(_UnexpectedFailureMiddleware,),
    )

    async with application:
        with Log.fake() as fake:
            transport = httpx2.ASGITransport(
                app=application.asgi,
                raise_app_exceptions=False,
            )
            async with httpx2.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                response = await client.get("/unexpected")

            record = fake.assert_logged(
                "error",
                "Application operation failed",
            )

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json() == {"detail": "Internal server error."}
    assert _PRIVATE_FAILURE not in response.text
    assert record.context["exception_type"] == "RuntimeError"
    assert record.exception is None
    assert application.container.active_scope_count == 0


@pytest.mark.anyio
async def test_global_middleware_uses_fallback_without_handler() -> None:
    """Use Foundation's safe renderer when the ASGI map has no match.
    """  # fmt: skip
    application = Application(
        config={"app": {"debug": False}},
        http_middleware=(_UnexpectedFailureMiddleware,),
    )
    application.asgi.exception_handlers.pop(Exception)

    async with application:
        transport = httpx2.ASGITransport(
            app=application.asgi,
            raise_app_exceptions=False,
        )
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/unexpected")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json() == {"detail": "Internal server error."}
    assert _PRIVATE_FAILURE not in response.text
    assert application.container.active_scope_count == 0


@pytest.mark.anyio
async def test_global_middleware_runs_sync_backend_handler_in_worker() -> None:
    """Use AnyIO's worker boundary for synchronous ASGI error handlers.
    """  # fmt: skip
    application = Application(
        http_middleware=(_PublicFailureMiddleware,),
    )
    handler_threads: list[int] = []

    def render_failure(
        request: StarletteRequest,
        error: Exception,
    ) -> StarletteResponse:
        """Return a safe response and record the execution thread.

        Args:
            request: Backend request associated with the middleware error.
            error: Public exception selected by the handler registry.

        Returns:
            A response accepted by the ASGI application.
        """
        _ = request, error
        handler_threads.append(get_ident())
        return PlainTextResponse("safe")

    application.asgi.exception_handlers[_PublicFailureError] = render_failure
    event_loop_thread = get_ident()

    async with application:
        transport = httpx2.ASGITransport(app=application.asgi)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/global")

    assert response.status_code == HTTPStatus.OK
    assert response.text == "safe"
    assert len(handler_threads) == 1
    assert handler_threads[0] != event_loop_thread


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_global_middleware_cancellation_is_not_rendered_as_failure() -> (
    None
):
    """Propagate cancellation and finalize the request scope promptly.

    The synchronization event proves cancellation starts after middleware
    entry, without timing-based sleeps.
    """
    middleware = _WaitingMiddleware()
    application = Application(
        http_middleware=(_WaitingMiddleware,),
        service_providers=(_WaitingMiddlewareProvider(middleware),),
    )
    handler_calls = 0

    async def render_failure(
        request: HttpRequest,
        exception: Exception,
    ) -> HttpResponse:
        """Count any exception incorrectly produced by cancellation.

        Args:
            request: Request that entered the middleware stack.
            exception: Failure selected by Foundation.

        Returns:
            A response that must not be reached by cancellation.
        """
        nonlocal handler_calls
        _ = request, exception
        handler_calls += 1
        return application.make(ResponseFactory).json(
            {"detail": "unexpected"},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    application.add_exception_handler(Exception, render_failure)

    async with application:
        transport = httpx2.ASGITransport(app=application.asgi)
        async with (
            httpx2.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client,
            anyio.create_task_group() as tasks,
        ):
            tasks.start_soon(client.get, "/cancel")
            await middleware.entered.wait()
            tasks.cancel_scope.cancel()

    assert middleware.finished.is_set()
    assert handler_calls == 0
    assert application.container.active_scope_count == 0
