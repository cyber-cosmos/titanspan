"""Test route-definition validation and the authoritative route catalog.

These tests isolate registration behavior from the ASGI matching backend.
"""

import pytest

from titanspan.routing import (
    DuplicateRouteError,
    InvalidRouteError,
    Router,
    RouterFrozenError,
)
from titanspan.routing.route import RouteDefinition, RouteMetadata
from titanspan.routing.route_collection import RouteCollection

pytestmark = pytest.mark.unit

_TWO_ROUTES = 2
_SIX_ROUTES = 6


def endpoint() -> str:
    """Return a simple response for route registration tests.

    Returns:
        Stable text for a registered handler.
    """
    return "ok"


def test_route_collection_resolves_unique_names_and_snapshots() -> None:
    """Expose stable named lookup and immutable ordered route snapshots.

    The same collection supports inspection and URL generation.
    """
    router = Router()
    first = router.get("/health", endpoint).name("health")
    second = router.post("/documents", endpoint).name("documents.store")

    assert router.routes.all() == (first, second)
    assert router.routes.named("health") is first
    assert router.named("documents.store") is second
    assert router.has("documents.store")
    assert not router.has("missing")


def test_duplicate_method_and_path_registration_fails() -> None:
    """Reject duplicate endpoint ownership for one method and path.

    Different methods may still share a path template.
    """
    router = Router()
    router.get("/health", endpoint)

    with pytest.raises(DuplicateRouteError):
        router.get("/health", endpoint)


def test_different_methods_can_share_a_path() -> None:
    """Allow the normal REST methods to share one path template.

    Only overlapping method declarations conflict.
    """
    router = Router()
    router.get("/documents", endpoint)
    router.post("/documents", endpoint)

    assert len(router.routes.all()) == _TWO_ROUTES


def test_router_method_shortcuts_and_explicit_route_name() -> None:
    """Route shortcuts delegate to the same registrar and collection.

    Each declaration has a unique path and a stable ordered method tuple.
    """
    router = Router()
    named = router.route("/named", endpoint, name="named")
    put_route = router.put("/put", endpoint)
    patch_route = router.patch("/patch", endpoint)
    delete_route = router.delete("/delete", endpoint)
    head_route = router.head("/head", endpoint)
    options_route = router.options("/options", endpoint)

    assert named.route_name == "named"
    assert put_route.methods == ("PUT",)
    assert patch_route.methods == ("PATCH",)
    assert delete_route.methods == ("DELETE",)
    assert head_route.methods == ("HEAD",)
    assert options_route.methods == ("OPTIONS",)
    assert len(router.routes.all()) == _SIX_ROUTES


def test_duplicate_route_names_fail_before_mutation() -> None:
    """Keep named URL generation unambiguous across one route catalog.

    The second route remains unnamed after rejection.
    """
    router = Router()
    router.get("/first", endpoint).name("shared")
    second = router.get("/second", endpoint)

    with pytest.raises(DuplicateRouteError):
        second.name("shared")

    assert second.route_name is None


@pytest.mark.parametrize(
    ("path", "pattern"),
    [
        ("/documents/{document_id}", "[0-9]+"),
        ("/documents/{document_id}", "("),
    ],
)
def test_path_constraints_validate_target_and_expression(
    path: str,
    pattern: str,
) -> None:
    """Reject malformed regular expressions without changing route metadata.

    Valid expressions are retained for backend matching.
    """
    router = Router()
    route = router.get(path, endpoint)

    if pattern == "(":
        with pytest.raises(InvalidRouteError):
            route.where("document_id", pattern)
    else:
        route.where("document_id", pattern)
        assert route.constraints["document_id"] == pattern


def test_route_definition_rejects_unknown_constraint_parameter() -> None:
    """Avoid attaching route matching metadata to absent path names.

    The invalid constraint leaves the definition unchanged.
    """
    router = Router()
    route = router.get("/documents/{document_id}", endpoint)

    with pytest.raises(InvalidRouteError):
        route.where_number("other_id")


@pytest.mark.parametrize(
    "path",
    ["/search?query=value", "/documents#fragment"],
)
def test_route_paths_reject_query_and_fragment_components(
    path: str,
) -> None:
    """Keep query and fragment data outside route path declarations.

    These values belong to request URLs and must not become matcher syntax.
    """
    router = Router()

    with pytest.raises(InvalidRouteError):
        router.get(path, endpoint)


def test_registration_freezes_after_route_compilation() -> None:
    """Prevent route metadata changes after the backend composes routes.

    The frozen route catalog rejects later registration.
    """
    router = Router()
    route = router.get("/health", endpoint)
    router.freeze()

    with pytest.raises(RouterFrozenError):
        router.get("/later", endpoint)

    with pytest.raises(RouterFrozenError):
        route.name("health")


def test_decorator_registration_preserves_callable_identity() -> None:
    """Return the original endpoint object from decorator registration.

    The router stores the callable without a wrapper layer.
    """
    router = Router()
    decorator = router.get("/health")
    decorated = decorator(endpoint)

    assert decorated is endpoint
    assert router.routes.all()[0].action is endpoint


def test_freeze_rejects_an_unapplied_route_decorator() -> None:
    """Fail startup if a decorator registration has no endpoint.

    An incomplete definition cannot enter the compiled route set.
    """
    router = Router()
    router.get("/missing")

    with pytest.raises(InvalidRouteError):
        router.freeze()


def test_any_uses_explicit_common_methods() -> None:
    """Exclude unsafe and uncommon methods from the convenience any route.

    Applications use explicit registration for CONNECT and TRACE.
    """
    router = Router()
    route = router.any("/resource", endpoint)

    assert route.methods == (
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
        "HEAD",
    )


def test_collection_rejects_duplicate_pre_named_routes() -> None:
    """Protect name uniqueness even for externally assembled definitions.

    The collection remains authoritative if a named definition is added
    directly rather than through the Router convenience methods.
    """
    collection = RouteCollection()

    def definition(path: str) -> RouteDefinition:
        """Build a route with a permissive local metadata validator.

        Args:
            path: Distinct path used to isolate the duplicate-name rule.

        Returns:
            A standalone route definition suitable for collection insertion.
        """
        route = RouteDefinition(
            path,
            ("GET",),
            endpoint,
            RouteMetadata(),
            ensure_mutable=lambda: None,
            validate_name=lambda _name, _candidate: None,
        )
        route.name("shared")
        return route

    collection.add(definition("/first"))
    with pytest.raises(DuplicateRouteError, match="Route name"):
        collection.add(definition("/second"))


def test_collection_reports_absent_removal_and_frozen_state() -> None:
    """Keep collection lifecycle checks explicit and observable.

    Removing an unknown route is an error and freezing is irreversible.
    """
    collection = RouteCollection()
    route = RouteDefinition(
        "/health",
        ("GET",),
        endpoint,
        RouteMetadata(),
        ensure_mutable=lambda: None,
        validate_name=lambda _name, _candidate: None,
    )

    with pytest.raises(InvalidRouteError, match="not in this collection"):
        collection.remove(route)

    collection.add(route)
    collection.freeze()
    assert collection.frozen

    with pytest.raises(RouterFrozenError):
        collection.add(
            RouteDefinition(
                "/later",
                ("GET",),
                endpoint,
                RouteMetadata(),
                ensure_mutable=lambda: None,
                validate_name=lambda _name, _candidate: None,
            )
        )
