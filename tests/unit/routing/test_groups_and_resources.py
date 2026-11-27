"""Test route-group state and REST resource declarations.

The tests use native Router definitions without compiling an ASGI app.
"""

import pytest

from titanspan.contracts.http import (
    HttpRequest,
    HttpResponse,
    MiddlewareDeclaration,
    RequestHandler,
)
from titanspan.routing import (
    DuplicateRouteError,
    InvalidRouteError,
    RouteFilter,
    Router,
)

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


class ParameterizedFirstMiddleware(FirstMiddleware):
    """Provide one policy-aware extension of ordinary test middleware.

    The method receives immutable values for each route declaration.
    """

    async def handle_with_parameters(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
        parameters: tuple[str, ...],
    ) -> HttpResponse:
        """Continue one request with its declared parameter values.

        Args:
            request: Current native request.
            next_handler: Remaining route middleware chain.
            parameters: Immutable values declared on the route.

        Returns:
            The downstream response.
        """
        response = await next_handler(request)
        return response.with_header(
            "X-Policy",
            ",".join(parameters),
        )


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


class ControllerWithMiddleware(ResourceController):
    """Declare controller middleware through native class metadata.

    The router appends these values after inherited group middleware.
    """

    route_middleware = ("auth", SecondMiddleware)


class ControllerWithParameterizedMiddleware(ResourceController):
    """Declare immutable controller middleware parameters.

    The router combines these values with inherited group declarations.
    """

    route_middleware = MiddlewareDeclaration(
        ParameterizedFirstMiddleware,
        ("staff", "read"),
    )


class SingleMiddlewareController(ResourceController):
    """Declare one controller middleware alias without a sequence.

    The Router normalizes a single declaration into its ordered metadata.
    """

    route_middleware = "auth"


class InvalidControllerMiddleware(ResourceController):
    """Declare malformed controller middleware for validation coverage.

    Invalid declarations are rejected before route metadata is stored.
    """

    route_middleware = 7


class InvalidSequenceMiddleware(ResourceController):
    """Declare a sequence containing an unsupported middleware value.

    The Router validates every member of controller middleware sequences.
    """

    route_middleware = ("auth", 7)


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


def test_parameterized_middleware_keeps_distinct_declarations() -> None:
    """Deduplicate identical parameters and retain distinct route policies.

    Inspection uses the declaration target while dispatch retains parameters.
    """
    router = Router()
    router.alias_middleware("policy", ParameterizedFirstMiddleware)
    route = router.get("/policy", endpoint).middleware(
        (
            MiddlewareDeclaration("policy", ("staff",)),
            MiddlewareDeclaration("policy", ("visitor",)),
            MiddlewareDeclaration("policy", ("staff",)),
        ),
    )

    assert router.resolve_middleware_declarations(route) == (
        MiddlewareDeclaration(ParameterizedFirstMiddleware, ("staff",)),
        MiddlewareDeclaration(ParameterizedFirstMiddleware, ("visitor",)),
    )
    assert router.resolve_middleware(route) == (ParameterizedFirstMiddleware,)
    assert router.inspect(RouteFilter(middleware="policy")) == (route,)


def test_middleware_declaration_rejects_empty_alias_and_parameters() -> None:
    """Reject empty declaration values before route registration.

    Empty values cannot represent useful middleware policy arguments.
    """
    with pytest.raises(ValueError, match="aliases must not be empty"):
        MiddlewareDeclaration("", ())
    with pytest.raises(ValueError, match="parameters must be non-empty"):
        MiddlewareDeclaration("policy", ("",))
    with pytest.raises(ValueError, match="parameters must be non-empty"):
        MiddlewareDeclaration("policy", ("   ",))


def test_parameterized_middleware_requires_a_registered_alias() -> None:
    """Reject parameterized middleware aliases absent from the Router.

    Alias validation runs before route compilation.
    """
    router = Router()
    route = router.get("/missing", endpoint).middleware(
        MiddlewareDeclaration("missing", ("read",)),
    )

    with pytest.raises(InvalidRouteError, match="middleware alias"):
        router.resolve_middleware_declarations(route)


def test_parameterized_middleware_exclusions_match_alias_and_class() -> None:
    """Exclude all parameter variants by their declared target.

    The Router accepts both native aliases and middleware classes as selectors.
    """
    router = Router()
    router.alias_middleware("policy", ParameterizedFirstMiddleware)
    alias_route = (
        router.get("/alias", endpoint)
        .middleware(MiddlewareDeclaration("policy", ("staff",)))
        .without_middleware("policy")
    )
    class_route = (
        router.get("/class", endpoint)
        .middleware(
            MiddlewareDeclaration(
                ParameterizedFirstMiddleware,
                ("visitor",),
            ),
        )
        .without_middleware(ParameterizedFirstMiddleware)
    )
    aliased_class_route = (
        router.get("/aliased-class", endpoint)
        .middleware(MiddlewareDeclaration("policy", ("staff",)))
        .without_middleware(ParameterizedFirstMiddleware)
    )

    assert router.resolve_middleware_declarations(alias_route) == ()
    assert router.resolve_middleware_declarations(class_route) == ()
    assert router.resolve_middleware_declarations(aliased_class_route) == ()


def test_controller_middleware_accepts_parameterized_declarations() -> None:
    """Retain controller-level parameters in native route metadata.

    Dispatch resolves the same declaration as route and group middleware.
    """
    router = Router()
    route = router.get(
        "/controller",
        (ControllerWithParameterizedMiddleware, "index"),
    )

    assert route.middleware_types == (
        MiddlewareDeclaration(
            ParameterizedFirstMiddleware,
            ("staff", "read"),
        ),
    )
    assert router.resolve_middleware_declarations(route) == (
        MiddlewareDeclaration(
            ParameterizedFirstMiddleware,
            ("staff", "read"),
        ),
    )


def test_resource_routes_preserve_parameterized_middleware() -> None:
    """Apply one immutable declaration to each generated resource route.

    Resource registration delegates to the ordinary route definitions.
    """
    router = Router()
    declaration = MiddlewareDeclaration(
        ParameterizedFirstMiddleware,
        ("staff", "read"),
    )

    router.api_resource("documents", ResourceController).middleware(
        declaration,
    )

    assert all(
        route.middleware_types == (declaration,)
        for route in router.routes.all()
    )


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


def test_resource_configuration_validates_metadata() -> None:
    """Validate custom metadata and middleware on generated resource routes.

    Empty shallow updates remain neutral and valid declarations are inherited.
    """
    router = Router()

    with pytest.raises(InvalidRouteError):
        router.resource("widgets", ResourceController, parameter="widget-id")

    registrar = router.resource("documents", ResourceController)
    assert registrar.shallow(False) is registrar
    with pytest.raises(InvalidRouteError):
        registrar.parameters({"missing": "identifier"})
    with pytest.raises(InvalidRouteError):
        registrar.names({"show": "   "})
    with pytest.raises(InvalidRouteError):
        registrar.creatable()
    with pytest.raises(InvalidRouteError):
        registrar.destroyable()

    configured = router.api_resource("labels", ResourceController).middleware(
        [FirstMiddleware, "auth"],
    )
    assert configured is not None
    assert all(
        route.middleware_types == (FirstMiddleware, "auth")
        for route in router.routes.all()
        if route.path.startswith("/labels")
    )


def test_resource_reparameterization_keeps_constraints() -> None:
    """Remap constrained route parameters without replacing catalog entries.

    The old definition remains the exact route object after parameter changes.
    """
    router = Router()
    registrar = router.resource("documents", ResourceController).only(["show"])
    route = router.routes.named("documents.show")
    route.where("document", "[0-9]+")

    registrar.parameters({"documents": "document_id"})

    assert router.routes.named("documents.show") is route
    assert route.path == "/documents/{document_id}"
    assert route.constraints == {"document_id": "[0-9]+"}


def test_nested_resource_routes_support_shallow_paths_and_custom_names() -> (
    None
):
    """Build nested REST paths while shortening item routes when requested.

    Collection operations keep the parent key; item operations use shallow
    paths and configurable route names.
    """
    router = Router()
    router.resource(
        "photos.comments",
        ResourceController,
    ).shallow().names({"show": "comments.view"}).parameters(
        {"photos": "photo_key", "comments": "comment_key"},
    )

    routes = {route.route_name: route.path for route in router.routes.all()}

    assert routes["photos.comments.index"] == ("/photos/{photo_key}/comments")
    assert routes["photos.comments.store"] == ("/photos/{photo_key}/comments")
    assert routes["comments.view"] == "/comments/{comment_key}"
    assert routes["comments.update"] == "/comments/{comment_key}"


def test_singleton_resources_register_only_existing_instance_actions() -> None:
    """Register singleton action paths without item parameters.

    API singleton and creatable singleton routes retain native metadata.
    """
    router = Router()
    router.singleton("profile", ResourceController)
    router.api_singleton("preferences", ResourceController)

    profile = {
        route.route_name: (route.methods, route.path)
        for route in router.routes.all()
        if route.route_name is not None
    }

    assert profile["profile.show"] == (("GET",), "/profile")
    assert profile["profile.edit"] == (("GET",), "/profile/edit")
    assert profile["profile.update"] == (
        ("PUT", "PATCH"),
        "/profile",
    )
    assert "profile.create" not in profile
    assert "preferences.edit" not in profile
    assert "preferences.update" in profile

    router.singleton("avatar", ResourceController).creatable()
    assert router.has("avatar.store")
    assert router.has("avatar.create")
    assert not router.has("avatar.destroy")

    router.singleton("badge", ResourceController).destroyable()
    assert router.has("badge.destroy")
    assert not router.has("badge.create")


def test_nested_middleware_groups_flatten_in_registration_order() -> None:
    """Expand groups that reference other groups without reordering items.

    Duplicate classes keep their first position in the effective chain.
    """
    router = Router()
    router.alias_middleware("first", FirstMiddleware)
    router.alias_middleware("second", SecondMiddleware)
    router.middleware_group("inner", ["first", "second"])
    router.middleware_group("outer", ["inner", "first"])
    route = router.get("/health", endpoint).middleware("outer")

    assert router.resolve_middleware(route) == (
        FirstMiddleware,
        SecondMiddleware,
    )


def test_route_inspection_filters_stably_and_preserves_identity() -> None:
    """Filter the authoritative catalog in declaration order.

    Every inspection result is the exact route object used for dispatch.
    """
    router = Router()
    router.alias_middleware("auth", FirstMiddleware)
    with router.prefix("/api").name("api.").domain("api.example.test").group():
        first = (
            router.get("/documents", endpoint)
            .name(
                "documents.index",
            )
            .middleware("auth")
        )
        router.post("/documents", endpoint).name("documents.create")
    router.websocket("/events", _websocket_endpoint).name("events")

    matches = router.inspect(
        RouteFilter(
            method="GET",
            path="/api/documents",
            name="api.documents.index",
            domain="api.example.test",
            middleware="auth",
        )
    )

    assert matches == (first,)
    assert router.inspect(RouteFilter(protocol="websocket")) == (
        router.routes.named("events"),
    )


def test_controller_middleware_is_inherited_into_route_metadata() -> None:
    """Append controller middleware after group middleware declarations.

    Aliases remain route metadata until the Router expands the execution list.
    """
    router = Router()
    router.alias_middleware("auth", FirstMiddleware)
    route = router.get(
        "/documents/{document}",
        (ControllerWithMiddleware, "show"),
    )

    assert route.middleware_types == ("auth", SecondMiddleware)
    assert router.resolve_middleware(route) == (
        FirstMiddleware,
        SecondMiddleware,
    )


def test_controller_middleware_rejects_bad_values() -> None:
    """Normalize one middleware value and reject malformed declarations.

    Both direct classes and aliases use the existing HTTP middleware contract.
    """
    router = Router()
    router.alias_middleware("auth", FirstMiddleware)
    single = router.get("/single", (SingleMiddlewareController, "show"))

    assert single.middleware_types == ("auth",)

    with pytest.raises(InvalidRouteError):
        router.get("/invalid", (InvalidControllerMiddleware, "show"))
    with pytest.raises(InvalidRouteError):
        router.get("/invalid-sequence", (InvalidSequenceMiddleware, "show"))


async def _websocket_endpoint(websocket: object) -> None:
    """Provide an async endpoint declaration for protocol inspection.

    Args:
        websocket: Untouched connection value; inspection does not dispatch it.
    """
    _ = websocket


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
