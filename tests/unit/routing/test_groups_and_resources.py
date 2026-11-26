"""Test route-group state and REST resource declarations.

The tests use native Router definitions without compiling an ASGI app.
"""

import pytest

from titanspan.contracts.http import (
    HttpRequest,
    HttpResponse,
    RequestHandler,
)
from titanspan.routing import DuplicateRouteError, InvalidRouteError, Router

pytestmark = pytest.mark.unit

_REGISTRATION_FAILURE = "registration failed"
_THREE_ROUTES = 3
_TWO_ROUTES = 2
_FIVE_ROUTES = 5
_GROUP_DEFAULT_ID = 5


class FirstMiddleware:
    """Provide a middleware type for metadata expansion tests.

    The middleware is resolved only when an incoming request is dispatched.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Pass the request to the next registered handler.

        Args:
            request: Active request contract.
            next_handler: Remaining route dispatch chain.

        Returns:
            Downstream native HTTP response.
        """
        return await next_handler(request)


class SecondMiddleware:
    """Provide another middleware class used to verify ordering.

    Its body delegates to the next request handler.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Pass the request to the next registered handler.

        Args:
            request: Active request contract.
            next_handler: Remaining route dispatch chain.

        Returns:
            Downstream native HTTP response.
        """
        return await next_handler(request)


class ResourceController:
    """Declare the actions expanded by a resource registrar.

    Each method stands in for one conventional action.
    """

    def index(self) -> None:
        """Represent the collection action.

        The registrar maps this method to the collection path.
        """

    def create(self) -> None:
        """Represent the HTML create action.

        The registrar maps this method to the create path.
        """

    def store(self) -> None:
        """Represent the collection creation action.

        The registrar maps this method to the collection path.
        """

    def show(self, document: str) -> None:
        """Represent the item lookup action.

        The registrar maps this method to the item path.
        """

    def edit(self, document: str) -> None:
        """Represent the HTML edit action.

        The registrar maps this method to the edit path.
        """

    def update(self, document: str) -> None:
        """Represent the item update action.

        The registrar maps this method to PUT and PATCH.
        """

    def destroy(self, document: str) -> None:
        """Represent the item removal action.

        The registrar maps this method to DELETE.
        """


def endpoint() -> str:
    """Return a route body for group tests.

    Returns:
        Stable text for registered handler metadata.
    """
    return "ok"


def test_nested_groups_merge_prefix_names_and_middleware() -> None:
    """Compose nested group attributes deterministically.

    The assertions cover prefix, names, and middleware inheritance.
    """
    router = Router()
    router.middleware_group("api", ["auth"])
    router.alias_middleware("auth", FirstMiddleware)

    with (
        router.prefix("/api").name("api.").middleware("api").group(),
        router.prefix("/v1").name("v1.").group(),
    ):
        route = router.get("/documents", endpoint).name("documents.index")

    assert route.path == "/api/v1/documents"
    assert route.route_name == "api.v1.documents.index"
    assert router.resolve_middleware(route) == (FirstMiddleware,)


def test_group_inherits_constraints_defaults_and_domain() -> None:
    """Propagate route matching metadata through nested group builders.

    Builder updates are immutable snapshots and merge with child declarations.
    """
    router = Router()
    group = (
        router.prefix("")
        .name("api.")
        .middleware(FirstMiddleware)
        .where("document_id", "[0-9]+")
        .defaults({"document_id": 5})
        .domain("api.example.test")
    )

    with group.group(), router.prefix("/v1").group():
        route = router.get(
            "/documents/{document_id}",
            endpoint,
        ).name("documents.show")

    assert route.path == "/v1/documents/{document_id}"
    assert route.route_name == "api.documents.show"
    assert route.constraints["document_id"] == "[0-9]+"
    assert route.default_values["document_id"] == _GROUP_DEFAULT_ID
    assert route.domain_name == "api.example.test"
    assert group.middleware(SecondMiddleware) is group


@pytest.mark.parametrize("prefix", ["api", "/api//v1", "/api?x=1"])
def test_group_prefix_must_be_an_absolute_clean_path(prefix: str) -> None:
    """Reject relative or ambiguous route prefix syntax.

    Group paths are validated before any routes can inherit them.
    """
    with pytest.raises(ValueError, match="absolute"):
        Router().prefix(prefix)


def test_empty_nested_group_prefixes_do_not_add_path_separators() -> None:
    """Keep empty group path values neutral during nested composition.

    Neither an empty parent nor child creates duplicate separators.
    """
    router = Router()

    with router.prefix("").group(), router.prefix("").group():
        route = router.get("/health", endpoint)

    assert route.path == "/health"


def test_group_context_restores_after_exception() -> None:
    """Prevent nested registration attributes from leaking on failure.

    The Router must restore its context-local group stack.
    """
    router = Router()

    with pytest.raises(RuntimeError), router.prefix("/temporary").group():
        raise RuntimeError(_REGISTRATION_FAILURE)

    route = router.get("/health", endpoint)

    assert route.path == "/health"


def test_concurrent_registration_contexts_keep_prefixes_isolated() -> None:
    """Use separate Router contexts to avoid cross-application group state.

    Each Router owns an independent registration context.
    """
    first = Router()
    second = Router()

    with first.prefix("/first").group():
        first_route = first.get("/health", endpoint)

    with second.prefix("/second").group():
        second_route = second.get("/health", endpoint)

    assert first_route.path == "/first/health"
    assert second_route.path == "/second/health"


def test_middleware_groups_detect_cycles_and_missing_aliases() -> None:
    """Fail route compilation when middleware references are invalid.

    Cycles and missing aliases are reported before serving requests.
    """
    router = Router()
    router.middleware_group("one", ["two"])
    router.middleware_group("two", ["one"])
    cyclic = router.get("/cycle", endpoint).middleware("one")
    missing = router.get("/missing", endpoint).middleware("unknown")

    with pytest.raises(InvalidRouteError):
        router.resolve_middleware(cyclic)

    with pytest.raises(InvalidRouteError):
        router.resolve_middleware(missing)


def test_middleware_aliases_and_groups_reject_conflicts() -> None:
    """Reject empty and conflicting middleware registrations.

    Re-registering one alias to its existing class remains idempotent.
    """
    router = Router()

    with pytest.raises(InvalidRouteError):
        router.alias_middleware("", FirstMiddleware)
    router.alias_middleware("auth", FirstMiddleware)
    router.alias_middleware("auth", FirstMiddleware)
    with pytest.raises(DuplicateRouteError):
        router.alias_middleware("auth", SecondMiddleware)

    with pytest.raises(InvalidRouteError):
        router.middleware_group("", [FirstMiddleware])
    router.middleware_group("api", [FirstMiddleware])
    with pytest.raises(DuplicateRouteError):
        router.middleware_group("api", [SecondMiddleware])

    direct = router.get("/direct", endpoint).middleware(FirstMiddleware)
    assert router.resolve_middleware(direct) == (FirstMiddleware,)


def test_route_middleware_aliases_are_deduplicated_and_excludable() -> None:
    """Preserve middleware order while applying route-local exclusions.

    Expansion also removes duplicate middleware declarations.
    """
    router = Router()
    router.alias_middleware("first", FirstMiddleware)
    router.alias_middleware("second", SecondMiddleware)
    router.middleware_group("api", ["first", "second", "first"])
    route = (
        router.get("/health", endpoint)
        .middleware(["api", "first"])
        .without_middleware("first")
    )

    assert router.resolve_middleware(route) == (SecondMiddleware,)


def test_resource_action_filters_update_the_shared_route_collection() -> None:
    """Filter resource routes in the same collection used by dispatch.

    The URL catalog and backend observe the same remaining routes.
    """
    router = Router()
    registrar = router.resource("documents", ResourceController).only(
        ["index", "show", "store"],
    )

    routes = router.routes.all()

    assert len(routes) == _THREE_ROUTES
    assert {route.route_name for route in routes} == {
        "documents.index",
        "documents.show",
        "documents.store",
    }
    assert registrar.except_(["store"]) is registrar
    assert len(router.routes.all()) == _TWO_ROUTES


def test_api_resource_omits_html_actions_and_uses_singular_parameter() -> None:
    """Expand the API action set without create/edit pages.

    Item parameters use a predictable singular default.
    """
    router = Router()
    router.api_resource("documents", ResourceController)

    routes = router.routes.all()

    assert len(routes) == _FIVE_ROUTES
    assert all("/create" not in route.path for route in routes)
    assert all("/edit" not in route.path for route in routes)
    assert any(route.path == "/documents/{document}" for route in routes)


def test_resource_filter_rejects_unknown_actions() -> None:
    """Keep action filtering limited to the documented resource vocabulary.

    Unknown names fail before route collection mutation.
    """
    router = Router()
    registrar = router.api_resource("documents", ResourceController)

    with pytest.raises(InvalidRouteError):
        registrar.only(["unknown"])
    with pytest.raises(InvalidRouteError):
        registrar.except_(["unknown"])


def test_resource_registration_rejects_absolute_or_query_paths() -> None:
    """Prevent resource helpers from accepting malformed URI roots.

    Resource paths are relative to the Router root.
    """
    router = Router()

    with pytest.raises(InvalidRouteError):
        router.resource("/documents", ResourceController)
    with pytest.raises(InvalidRouteError):
        router.resource("documents?active=true", ResourceController)


@pytest.mark.parametrize(
    ("name", "expected_parameter"),
    [
        ("categories", "category"),
        ("classes", "class"),
        ("status", "statu"),
        ("news", "news"),
    ],
)
def test_resource_parameter_singularization_is_explicit_and_predictable(
    name: str,
    expected_parameter: str,
) -> None:
    """Apply the documented common suffix rules to item parameters.

    Unusual nouns remain available through the explicit parameter option.
    """
    router = Router()
    router.api_resource(name, ResourceController)

    assert f"/{name}/{{{expected_parameter}}}" in {
        route.path for route in router.routes.all()
    }
