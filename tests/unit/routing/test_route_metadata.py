"""Verify validation and mutation of native route metadata.

Route definitions remain editable only before their Router is frozen.
"""

import pytest

from titanspan.routing import InvalidRouteError, Router, RouterFrozenError

_CREATED_STATUS = 201


def endpoint() -> str:
    """Return a stable value for metadata tests.

    Returns:
        Text accepted by the native response normalizer.
    """
    return "ok"


def test_route_metadata_methods_preserve_validated_values() -> None:
    """Apply constraints, defaults, documentation and response metadata.

    The fluent methods update one mutable definition and return that object.
    """
    router = Router()
    route = router.get("/documents/{document_id}", endpoint)

    assert route.where_number("document_id") is route
    assert route.where_alpha("document_id") is route
    assert route.where_alpha_numeric("document_id") is route
    assert route.where_uuid("document_id") is route
    assert route.where_in("document_id", ["one", "two"]) is route
    assert route.defaults({"document_id": "one"}) is route
    assert route.domain("APP.EXAMPLE.TEST.") is route
    assert route.tags(["documents", "documents"]) is route
    assert route.summary("Find a document") is route
    assert route.description("Resolve a document by identifier.") is route
    assert route.deprecated() is route
    assert route.deprecated(False) is route
    assert route.status_code(_CREATED_STATUS) is route

    assert route.constraints["document_id"] == "(?:one|two)"
    assert route.default_values["document_id"] == "one"
    assert route.domain_name == "app.example.test"
    assert route.tag_values == ("documents",)
    assert route.summary_text == "Find a document"
    assert route.description_text == "Resolve a document by identifier."
    assert not route.is_deprecated
    assert route.response_status == _CREATED_STATUS


@pytest.mark.parametrize("methods", [(), ("GET/POST",)])
def test_route_rejects_empty_or_malformed_method_sets(
    methods: tuple[str, ...],
) -> None:
    """Reject an empty set and method tokens containing separators.

    Method validation occurs before a definition enters the route catalog.
    """
    with pytest.raises(InvalidRouteError, match="HTTP method"):
        Router().match(methods, "/items", endpoint)


@pytest.mark.parametrize(
    "path",
    [
        "items",
        "/items//new",
        "/items?query=value",
        "/items#fragment",
        "/items/{item",
        "/items/{1item}",
        "/items/{item}}",
    ],
)
def test_route_rejects_malformed_path_templates(path: str) -> None:
    """Reject path strings that cannot be represented as safe templates.

    Invalid route syntax is reported at registration time.
    """
    with pytest.raises(InvalidRouteError):
        Router().get(path, endpoint)


def test_route_rejects_invalid_metadata_values() -> None:
    """Validate names, constraints, defaults, domains and HTTP statuses.

    Rejected updates do not replace existing valid route metadata.
    """
    route = Router().get("/items/{item_id}", endpoint)

    with pytest.raises(InvalidRouteError):
        route.name("contains whitespace")
    with pytest.raises(InvalidRouteError):
        route.where_in("item_id", [])
    with pytest.raises(InvalidRouteError):
        route.where("item_id", "(")
    with pytest.raises(InvalidRouteError):
        route.where("item_id", "x" * 257)
    with pytest.raises(InvalidRouteError):
        route.defaults({"other": 1})
    with pytest.raises(InvalidRouteError):
        route.domain("https://example.test")
    with pytest.raises(InvalidRouteError):
        route.status_code(99)


def test_route_mutations_fail_after_router_freeze() -> None:
    """Keep compiled route metadata stable during request handling.

    Every fluent mutation shares the owning Router's registration guard.
    """
    router = Router()
    route = router.get("/items/{item_id}", endpoint)
    router.freeze()

    with pytest.raises(RouterFrozenError):
        route.where_number("item_id")
    with pytest.raises(RouterFrozenError):
        route.defaults({"item_id": 1})
    with pytest.raises(RouterFrozenError):
        route.domain("example.test")
    with pytest.raises(RouterFrozenError):
        route.tags(["items"])
    with pytest.raises(RouterFrozenError):
        route.description("Description")
    with pytest.raises(RouterFrozenError):
        route.deprecated()
    with pytest.raises(RouterFrozenError):
        route.status_code(200)
    with pytest.raises(RouterFrozenError):
        route.set_action(endpoint)
