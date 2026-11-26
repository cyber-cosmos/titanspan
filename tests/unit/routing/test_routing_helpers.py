"""Exercise URL, route, and redirect helpers at context boundaries.

Helpers resolve application services without creating global registries.
"""

import pytest

from titanspan import redirect, route, url
from titanspan._application_context import bind_application_context
from titanspan.container import BindingResolutionError, Container
from titanspan.foundation import Application
from titanspan.routing import (
    RouteUrlError,
    RoutingContextError,
)
from titanspan.routing.helpers import current_route, current_route_name

pytestmark = pytest.mark.unit


def endpoint() -> str:
    """Provide an endpoint for named redirect generation.

    Returns:
        Stable response text that is not invoked by these tests.
    """
    return "ok"


def test_url_and_route_helpers_require_an_active_application_when_needed() -> (
    None
):
    """Resolve local and absolute paths through the app-owned URL service.

    Both URL modes require the application's replaceable generator contract.
    """
    application = Application()
    with (
        application.context(),
        pytest.raises(RouteUrlError, match="local absolute paths"),
    ):
        url("//external.example.test")
    with pytest.raises(RoutingContextError, match="active application"):
        url("/local")
    with pytest.raises(RoutingContextError, match="active application"):
        url("/local", absolute=False)
    with pytest.raises(RoutingContextError, match="active application"):
        url("/local", absolute=True)
    with pytest.raises(RoutingContextError, match="active application"):
        route("missing")
    with pytest.raises(RoutingContextError, match="active application"):
        redirect()
    with pytest.raises(RoutingContextError, match="active matched"):
        current_route()
    with pytest.raises(RoutingContextError, match="active matched"):
        current_route_name()


def test_helpers_translate_missing_application_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translate absent routing bindings into native context errors.

    The helper reports its application requirement without exposing container
    internals.
    """
    container = Container()

    def fail_resolution(service: type[object]) -> object:
        """Simulate a missing service in an active application registry.

        Args:
            service: Requested service key from a route helper.

        Raises:
            BindingResolutionError: No service exists in this fixture.
        """
        _ = service
        raise BindingResolutionError

    monkeypatch.setattr(container, "make", fail_resolution)

    with bind_application_context(object(), container):
        with pytest.raises(RoutingContextError, match="active application"):
            url("/local", absolute=True)
        with pytest.raises(RoutingContextError, match="active application"):
            url("/local")
        with pytest.raises(RoutingContextError, match="active application"):
            redirect()
        with pytest.raises(RoutingContextError, match="active matched"):
            current_route()


def test_redirect_builder_uses_the_native_response_factory() -> None:
    """Validate local and named redirects through the app response service.

    The helper returns the canonical native HTTP response type.
    """
    application = Application()
    application.router.get("/documents/{document_id}", endpoint).name(
        "documents.show"
    )

    with application.context():
        redirector = redirect()
        local = redirector.to("/local")
        named = redirector.route(
            "documents.show",
            {"document_id": 12},
        )

    assert local.headers["location"] == "/local"
    assert named.headers["location"] == "/documents/12"
