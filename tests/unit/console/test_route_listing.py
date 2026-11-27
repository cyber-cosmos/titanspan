"""Verify route metadata formatting through native routing definitions.

Tests use Router records and the Console command handler.
"""

from collections.abc import Iterable, Sequence

import pytest

from titanspan.console.cli import list_routes
from titanspan.console.output import TerminalOutput
from titanspan.contracts import HttpRequest, HttpResponse, RequestHandler
from titanspan.contracts.http import MiddlewareDeclaration
from titanspan.routing import Router

pytestmark = pytest.mark.unit


class _DocumentController:
    """Represent one named controller action for route inspection.

    The command must inspect this identity without construction.
    """

    def show(self) -> None:
        """Provide the registered action identity without side effects.

        Route inspection never invokes this method.
        """


class _ReadyController:
    """Represent a class-based endpoint for route inspection.

    The route command reports the class without constructing it.
    """

    def __call__(self) -> dict[str, str]:
        """Return a stable value if the endpoint is invoked.

        Returns:
            A ready status value for this route fixture.
        """
        return {"status": "ready"}


class _RouteMiddleware:
    """Represent a typed middleware entry in route metadata.

    Inspection reads its class name without invoking the middleware.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Delegate if a test dispatches the registered route.

        Args:
            request: Native request passed through the middleware chain.
            next_handler: Native continuation for the request.

        Returns:
            The response returned by the next middleware or endpoint.
        """
        return await next_handler(request)


def test_route_list_formats_controller_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Render domains, action pairs, names, and middleware from Router.

    Console reads only the route catalog and never constructs the action.
    """
    tables: list[tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]] = []

    def record_table(
        output: TerminalOutput,
        headers: Sequence[str],
        rows: Iterable[Sequence[str]],
    ) -> None:
        """Capture the table passed through the native output adapter.

        Args:
            output: Terminal output instance selected by Console.
            headers: Ordered headings supplied by the command.
            rows: Route rows supplied by the command.
        """
        _ = output
        tables.append(
            (
                tuple(headers),
                tuple(tuple(row) for row in rows),
            )
        )

    monkeypatch.setattr(TerminalOutput, "table", record_table)
    router = Router()
    definition = router.get(
        "/documents/{document_id}",
        (_DocumentController, "show"),
    )
    definition.name("documents.show")
    definition.domain("api.example.test")
    definition.middleware(
        [
            "auth",
            _RouteMiddleware,
            MiddlewareDeclaration("policy", ("synthetic-secret",)),
        ],
    )

    list_routes(router.routes, TerminalOutput())

    assert tables == [
        (
            ("METHOD", "DOMAIN", "URI", "NAME", "ACTION", "MIDDLEWARE"),
            (
                (
                    "GET",
                    "api.example.test",
                    "/documents/{document_id}",
                    "documents.show",
                    "_DocumentController.show",
                    "auth, _RouteMiddleware, policy [parameterized]",
                ),
            ),
        )
    ]


def test_route_list_formats_invokable_and_incomplete_definitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Format class actions and pending decorator definitions safely.

    Applications reject incomplete routes before serving requests.
    """
    tables: list[tuple[tuple[str, ...], ...]] = []

    def record_table(
        output: TerminalOutput,
        headers: Sequence[str],
        rows: Iterable[Sequence[str]],
    ) -> None:
        """Capture route rows emitted by the command.

        Args:
            output: Terminal output instance selected by Console.
            headers: Ordered headings supplied by the command.
            rows: Route rows supplied by the command.
        """
        _ = output, headers
        tables.append(tuple(tuple(row) for row in rows))

    monkeypatch.setattr(TerminalOutput, "table", record_table)
    router = Router()
    router.get("/ready", _ReadyController)
    router.get("/deferred")

    list_routes(router.routes, TerminalOutput())

    assert tables == [
        (
            ("GET", "-", "/ready", "-", "_ReadyController", "-"),
            ("GET", "-", "/deferred", "-", "-", "-"),
        )
    ]
