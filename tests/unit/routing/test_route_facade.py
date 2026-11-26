"""Exercise the typed Route facade through an active application.

The facade delegates registrations to the Router that Foundation later
compiles for incoming requests.
"""

from titanspan.contracts.http import HttpRequest, HttpResponse, RequestHandler
from titanspan.facades import Route
from titanspan.foundation import Application
from titanspan.routing import RouteDefinition


class Middleware:
    """Provide a native middleware class for facade registration tests.

    The route declarations only inspect middleware registration metadata.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Delegate to the next handler without changing its result.

        Args:
            request: Request object accepted by the middleware contract.
            next_handler: Handler that produces the downstream response.

        Returns:
            The downstream response.
        """
        return await next_handler(request)


class ItemController:
    """Declare all actions used by resource facade registrations.

    Controller construction is deferred until an actual request arrives.
    """

    def index(self) -> None:
        """Provide the collection action signature.

        Returns:
            None because this test only inspects registration.
        """

    def create(self) -> None:
        """Provide the create action signature.

        Returns:
            None because this test only inspects registration.
        """

    def store(self) -> None:
        """Provide the store action signature.

        Returns:
            None because this test only inspects registration.
        """

    def show(self, item: str) -> None:
        """Provide the show action signature.

        Args:
            item: Item identifier from the route.

        Returns:
            None because this test only inspects registration.
        """

    def edit(self, item: str) -> None:
        """Provide the edit action signature.

        Args:
            item: Item identifier from the route.

        Returns:
            None because this test only inspects registration.
        """

    def update(self, item: str) -> None:
        """Provide the update action signature.

        Args:
            item: Item identifier from the route.

        Returns:
            None because this test only inspects registration.
        """

    def destroy(self, item: str) -> None:
        """Provide the destroy action signature.

        Args:
            item: Item identifier from the route.

        Returns:
            None because this test only inspects registration.
        """


def endpoint() -> str:
    """Return a stable value for route registration.

    Returns:
        A short string accepted by the route definition.
    """
    return "ok"


def test_route_facade_delegates_registration_to_active_router() -> None:
    """Exercise direct, fluent, decorator, and resource facade APIs.

    All entries remain in the same Router-owned route catalog.
    """
    application = Application()

    with application.context():
        route = Route.route("/route", endpoint, name="route")
        get_route = Route.get("/get", endpoint)
        post_route = Route.post("/post", endpoint)
        put_route = Route.put("/put", endpoint)
        patch_route = Route.patch("/patch", endpoint)
        delete_route = Route.delete("/delete", endpoint)
        head_route = Route.head("/head", endpoint)
        options_route = Route.options("/options", endpoint)
        matched_route = Route.match(("GET", "POST"), "/match", endpoint)
        any_route = Route.any("/any", endpoint)
        redirect_route = Route.redirect("/old", "/new")
        fallback_route = Route.fallback(endpoint)
        decorator = Route.route("/decorated")

        @decorator
        def decorated() -> str:
            """Return a value for decorator registration.

            Returns:
                Stable response data for the registered route.
            """
            return "decorated"

        assert isinstance(route, RouteDefinition)
        assert isinstance(get_route, RouteDefinition)
        assert isinstance(post_route, RouteDefinition)
        assert isinstance(put_route, RouteDefinition)
        assert isinstance(patch_route, RouteDefinition)
        assert isinstance(delete_route, RouteDefinition)
        assert isinstance(head_route, RouteDefinition)
        assert isinstance(options_route, RouteDefinition)

        with Route.prefix("/api").name("api.").group():
            grouped_route = Route.get("/health", endpoint).name("health")

        Route.alias_middleware("test", Middleware)
        Route.middleware_group("api", ["test"])
        api_resource = Route.api_resource("widgets", ItemController)
        api_resource.only(["index", "show"])
        resource = Route.resource("gadgets", ItemController)
        resource.except_(["destroy"])

        assert Route.router() is application.router
        assert Route.has("route")
        assert route.route_name == "route"
        assert [
            get_route.methods,
            post_route.methods,
            put_route.methods,
            patch_route.methods,
            delete_route.methods,
            head_route.methods,
            options_route.methods,
            matched_route.methods,
        ] == [
            ("GET",),
            ("POST",),
            ("PUT",),
            ("PATCH",),
            ("DELETE",),
            ("HEAD",),
            ("OPTIONS",),
            ("GET", "POST"),
        ]
        assert "CONNECT" not in any_route.methods
        assert redirect_route.action is not None
        assert fallback_route.path == "/{path:path}"
        assert decorated is not None
        assert grouped_route.route_name == "api.health"
        assert application.router.routes.all()


def test_route_facade_reuses_registered_router_instance() -> None:
    """Expose one application-owned route registry through the facade.

    Facade resolution does not create an independent Router.
    """
    application = Application()

    with application.context():
        first = Route.router()
        second = Route.router()

    assert first is second is application.router
