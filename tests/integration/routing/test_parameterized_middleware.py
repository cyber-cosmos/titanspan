"""Verify route middleware receives immutable declaration parameters.

The test exercises alias expansion, Container construction, and real ASGI
dispatch through one native application.
"""

from http import HTTPStatus

import anyio
import pytest
from fastapi.testclient import TestClient

from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.http import (
    HttpRequest,
    HttpResponse,
    MiddlewareDeclaration,
    ParameterizedHttpMiddleware,
    RequestHandler,
)
from titanspan.foundation import Application
from titanspan.routing import InvalidRouteError
from titanspan.testing import AsyncApplicationTest

pytestmark = [pytest.mark.integration, pytest.mark.architecture]


class _PolicyMiddleware:
    """Implement route policy behavior through structural typing.

    The request-specific values arrive as method arguments, so the same
    application-owned instance can serve concurrent declarations safely.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Continue requests that do not declare parameters.

        Args:
            request: Current native request.
            next_handler: Downstream request handler.

        Returns:
            The downstream response for this request.
        """
        return await next_handler(request)

    async def handle_with_parameters(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
        parameters: tuple[str, ...],
    ) -> HttpResponse:
        """Continue one request with its immutable declaration values.

        Args:
            request: Current native request.
            next_handler: Downstream request handler.
            parameters: Values declared on this route.

        Returns:
            The downstream response for this request.
        """
        await anyio.lowlevel.checkpoint()
        response = await next_handler(request)
        return response.with_header(
            "X-Policy", ",".join(parameters)
        ).with_header("X-Policy-Instance", str(id(self)))


_PARAMETERIZED_POLICY: type[ParameterizedHttpMiddleware] = _PolicyMiddleware


class _PolicyProvider:
    """Register the middleware as an application-owned singleton.

    The provider uses the canonical application container.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Bind the middleware in the canonical application graph.

        Args:
            container: Shared application service registry.
        """
        container.singleton(_PolicyMiddleware)


def test_route_middleware_receives_declaration_parameters() -> None:
    """Pass alias parameters without writing request data onto the service.

    The real route and Container resolve the aliased middleware.
    """
    application = Application(
        service_providers=(_PolicyProvider(),),
    )
    application.router.alias_middleware("policy", _PolicyMiddleware)
    application.router.middleware_group(
        "download",
        (
            MiddlewareDeclaration(
                "policy",
                ("staff", "download"),
            ),
        ),
    )
    application.router.get(
        "/staff-document",
        _document_payload,
    ).middleware("download")
    application.router.get(
        "/public-document",
        _document_payload,
    ).middleware(
        MiddlewareDeclaration(
            _PARAMETERIZED_POLICY,
            ("public", "download"),
        ),
    )

    with TestClient(application.asgi) as client:
        staff_response = client.get("/staff-document")
        public_response = client.get("/public-document")

    assert staff_response.status_code == HTTPStatus.OK
    assert staff_response.json() == {"status": "ok"}
    assert staff_response.headers["x-policy"] == "staff,download"
    assert public_response.headers["x-policy"] == "public,download"


@pytest.mark.anyio
async def test_concurrent_routes_keep_parameters_on_their_declarations() -> (
    None
):
    """Keep parameter values separate across concurrent singleton requests.

    Both route declarations resolve the same middleware class from the
    application Container.
    """
    test_application = AsyncApplicationTest(
        service_providers=(_PolicyProvider(),),
    )
    application = test_application.application
    application.router.get(
        "/first",
        _document_payload,
    ).middleware(
        MiddlewareDeclaration(_PARAMETERIZED_POLICY, ("first",)),
    )
    application.router.get(
        "/second",
        _document_payload,
    ).middleware(
        MiddlewareDeclaration(_PARAMETERIZED_POLICY, ("second",)),
    )

    results: list[tuple[int, str, str]] = []
    async with test_application as active:

        async def request_first() -> None:
            """Record the first route's middleware result.

            The test compares its policy with the concurrent route.
            """
            response = await active.client.get("/first")
            results.append(
                (
                    response.status_code,
                    response.headers["x-policy"],
                    response.headers["x-policy-instance"],
                ),
            )

        async def request_second() -> None:
            """Record the second route's middleware result.

            The test compares its policy with the concurrent route.
            """
            response = await active.client.get("/second")
            results.append(
                (
                    response.status_code,
                    response.headers["x-policy"],
                    response.headers["x-policy-instance"],
                ),
            )

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(request_first)
            tasks.start_soon(request_second)

    assert {(status, policy) for status, policy, _ in results} == {
        (HTTPStatus.OK, "first"),
        (HTTPStatus.OK, "second"),
    }
    assert len({instance for _, _, instance in results}) == 1


def test_plain_middleware_rejects_parameter_declaration_at_startup() -> None:
    """Reject invalid parameter declarations before request dispatch.

    Startup validates the middleware capability without constructing it.
    """
    application = Application()
    application.router.alias_middleware("plain", _PlainMiddleware)
    application.router.get(
        "/document",
        _document_payload,
    ).middleware(
        MiddlewareDeclaration("plain", ("admin",)),
    )

    with (
        pytest.raises(
            InvalidRouteError,
            match="handle_with_parameters",
        ),
        TestClient(application.asgi),
    ):
        pass


class _PlainMiddleware:
    """Provide ordinary middleware without parameter support.

    Startup must reject route parameters for this implementation.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Continue a request without route-specific values.

        Args:
            request: Current native request.
            next_handler: Downstream request handler.

        Returns:
            The downstream response.
        """
        return await next_handler(request)


def _document_payload() -> dict[str, str]:
    """Return a fixed response body for middleware integration tests.

    Returns:
        A JSON object with a stable status field.
    """
    return {"status": "ok"}
