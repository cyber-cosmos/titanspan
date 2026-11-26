"""Test safe route URL generation from one canonical route catalog.

The generator is exercised without a server or request Host header.
"""

from collections.abc import Mapping

import pytest

from titanspan.routing import (
    Router,
    RouteUrlError,
    UrlGenerator,
)

_PRIVATE_BACKEND_DETAIL = "private backend detail"


def endpoint() -> dict[str, str]:
    """Return a JSON-compatible value for route registration.

    Returns:
        Empty mapping used only as an endpoint annotation.
    """
    return {}


def named_router() -> Router:
    """Create a Router containing one named typed route.

    Returns:
        Router with a route used by the URL generator tests.
    """
    router = Router()
    router.get("/documents/{document_id}", endpoint).name("documents.show")
    return router


def test_named_route_encodes_path_and_query_values() -> None:
    """Substitute path parameters and encode unused values as a query.

    Path slashes are encoded to avoid changing route structure.
    """
    generator = UrlGenerator(named_router().routes)

    generated = generator.route(
        "documents.show",
        {"document_id": "a/b", "tag": ["ai", "data"]},
        False,
    )

    assert generated == "/documents/a%2Fb?tag=ai&tag=data"


def test_absolute_route_uses_only_the_configured_origin() -> None:
    """Build absolute URLs without trusting a request Host header.

    Only the explicitly configured origin is used.
    """
    generator = UrlGenerator(
        named_router().routes,
        origin="https://app.example.test/",
    )

    generated = generator.route(
        "documents.show",
        {"document_id": 42},
        True,
    )

    assert generated == "https://app.example.test/documents/42"


def test_missing_path_value_is_rejected() -> None:
    """Require every non-defaulted path parameter.

    The generator reports omissions before returning a URL.
    """
    generator = UrlGenerator(named_router().routes)

    with pytest.raises(RouteUrlError, match="document_id"):
        generator.route("documents.show", {}, False)


def test_absolute_generation_requires_a_trusted_origin() -> None:
    """Do not derive absolute URL origins from untrusted request headers.

    Relative URLs remain available without application origin data.
    """
    generator = UrlGenerator(named_router().routes)

    with pytest.raises(RouteUrlError, match="trusted origin"):
        generator.to("/documents")


@pytest.mark.parametrize(
    "origin",
    [
        "javascript:alert(1)",
        "https://user:secret@example.test",
        "https://example.test/path",
        "https://example.test/?host=evil",
        "https://example.test:99999",
    ],
)
def test_untrusted_or_non_origin_configuration_is_rejected(
    origin: str,
) -> None:
    """Accept only origin-only HTTP and HTTPS values.

    Credentials, paths, queries, and fragments are rejected.
    """
    with pytest.raises(RouteUrlError):
        UrlGenerator(named_router().routes, origin=origin)


def test_signed_urls_are_explicitly_pending_and_action_lookup_is_native() -> (
    None
):
    """Fail safely without signing keys and resolve registered actions.

    Controller actions resolve only when their route path is unambiguous.
    """
    generator = UrlGenerator(named_router().routes)

    with pytest.raises(RouteUrlError, match="key-management"):
        generator.signed_route("documents.show", {}, None, False)

    with pytest.raises(RouteUrlError, match="No route"):
        generator.action("DocumentController.show", {}, False)


def test_controller_action_generates_the_same_registered_route() -> None:
    """Resolve a controller action without constructing the controller.

    URI action lookup and named route generation share the catalog entry.
    """

    class DocumentController:
        """Declare a route action without requiring controller construction.

        The generator inspects its qualified identity from route metadata.
        """

        def show(self, document_id: int) -> None:
            """Declare an endpoint signature without executing it.

            Args:
                document_id: Route identifier required by the path.

            Returns:
                None because URL generation does not invoke the endpoint.
            """

    router = Router()
    router.get(
        "/documents/{document_id}",
        (DocumentController, "show"),
    )
    generator = UrlGenerator(router.routes)

    assert (
        generator.action(
            "DocumentController.show",
            {"document_id": 42},
            False,
        )
        == "/documents/42"
    )


def test_action_lookup_rejects_multiple_route_paths() -> None:
    """Reject action lookup when one callable maps to distinct paths.

    Callers can select a specific route by its stable route name instead.
    """

    class DocumentController:
        """Declare a controller whose same method has multiple paths.

        The two registrations intentionally make action lookup ambiguous.
        """

        def show(self, document_id: int) -> None:
            """Declare the shared endpoint signature.

            Args:
                document_id: Value included in the route path.

            Returns:
                None because this test only inspects route identity.
            """

    router = Router()
    router.get(
        "/documents/{document_id}",
        (DocumentController, "show"),
    )
    router.get(
        "/articles/{document_id}",
        (DocumentController, "show"),
    )

    with pytest.raises(RouteUrlError, match="multiple route paths"):
        UrlGenerator(router.routes).action(
            "DocumentController.show",
            {"document_id": 42},
            False,
        )


def test_path_reverser_is_single_assignment_and_errors_are_native() -> None:
    """Translate backend reversal failures without leaking backend errors.

    A configured path reverser is immutable after route compilation.
    """
    generator = UrlGenerator(named_router().routes)

    def fail_reversal(name: str, values: Mapping[str, str]) -> str:
        """Raise as a backend would when a route cannot be reversed.

        Args:
            name: Native route name selected by the catalog.
            values: Encoded path values supplied by the caller.

        Raises:
            KeyError: The simulated backend has no compiled route.
        """
        _ = name, values
        raise KeyError(_PRIVATE_BACKEND_DETAIL)

    generator.configure_path_reverser(fail_reversal)
    with pytest.raises(RouteUrlError, match="could not be reversed"):
        generator.route("documents.show", {"document_id": 7}, False)

    with pytest.raises(RuntimeError, match="already configured"):
        generator.configure_path_reverser(
            lambda name, values: name + str(values)
        )


def test_custom_converter_uses_native_path_substitution() -> None:
    """Retain custom converter syntax when backend reversal is unavailable.

    Converter values use the canonical path substitution implementation.
    """
    router = Router()
    router.get("/documents/{document_id:int}", endpoint).name("documents.show")
    generator = UrlGenerator(router.routes)
    generator.configure_path_reverser(
        lambda name, values: f"/{name}/{values['document_id']}"
    )

    assert (
        generator.route(
            "documents.show",
            {"document_id": 42},
            False,
        )
        == "/documents/42"
    )


def test_path_helper_and_action_selector_validate_inputs() -> None:
    """Reject unsafe local paths and malformed action identifiers.

    Sequence selectors normalize to a stable dotted identity.
    """
    router = Router()
    router.get("/documents/{document_id}", endpoint).name("documents.show")
    generator = UrlGenerator(router.routes, origin="https://app.example.test")

    with pytest.raises(RouteUrlError, match="local absolute paths"):
        generator.to("//external.example.test/path")
    with pytest.raises(RouteUrlError, match="No route"):
        generator.action((), {}, False)
    with pytest.raises(RouteUrlError, match="No route"):
        generator.action(("documents", "show"), {}, False)


def test_action_selector_accepts_dotted_sequence_parts() -> None:
    """Resolve sequence-form selectors against the canonical route catalog.

    Action lookup never constructs or invokes a controller instance.
    """

    class DocumentController:
        """Declare a controller action for sequence lookup.

        The method is inspected only through route metadata.
        """

        def show(self, document_id: int) -> None:
            """Describe a path parameter without executing a response.

            Args:
                document_id: Identifier to substitute into the URL.

            Returns:
                None because the action is never invoked.
            """

    router = Router()
    router.get(
        "/documents/{document_id}",
        (DocumentController, "show"),
    )

    assert (
        UrlGenerator(router.routes).action(
            ("DocumentController", "show"),
            {"document_id": 9},
            False,
        )
        == "/documents/9"
    )
