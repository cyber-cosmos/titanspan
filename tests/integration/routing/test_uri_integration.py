"""Verify URI factories and routing share application services.

The tests use the production Application, Container, Router, and response
factory rather than a separate URL registry.
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from titanspan import redirect, route, url
from titanspan.container import Scope
from titanspan.contracts.http import ResponseFactory
from titanspan.contracts.routing import UriUrlGenerator
from titanspan.foundation import Application
from titanspan.http import RedirectResponse
from titanspan.routing import RouteNotFoundError, RouteUrlError, UrlGenerator
from titanspan.support import (
    Uri,
    UriContextError,
)
from titanspan.support import (
    UriUrlGenerator as SupportUriUrlGenerator,
)

pytestmark = pytest.mark.integration

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class ArticleController:
    """Identify a registered action used by URI action generation.

    This controller has no dependencies because these cases exercise URL
    resolution rather than endpoint dispatch.
    """

    def show(self) -> None:
        """Provide an action target for route metadata.

        Returns:
            None because URL generation never invokes this method.
        """


class _AlternativeUrlGenerator(UriUrlGenerator):
    """Provide a substitutable generator for all native URL entry points.

    The fixed URLs make accidental concrete-class resolution observable.
    """

    def to(self, path: str) -> str:
        """Return an absolute URL from the replacement service.

        Args:
            path: Local application path.

        Returns:
            Absolute replacement URL.
        """
        return f"https://replacement.example.test{path}"

    def url(self, path: str, absolute: bool) -> str:
        """Build a URL through the substituted application contract.

        Args:
            path: Local path supplied by the top-level ``url`` helper.
            absolute: Whether the replacement origin should be included.

        Returns:
            A replacement URL that identifies this contract call.
        """
        if absolute:
            return self.to(path)
        return f"/replacement/url/{path.lstrip('/')}"

    def route(
        self,
        name: str,
        parameters: Mapping[str, object],
        absolute: bool,
    ) -> str:
        """Return a named URL from the replacement service.

        Args:
            name: Requested route name.
            parameters: Route values supplied by the caller.
            absolute: Whether to include the replacement origin.

        Returns:
            Absolute or relative replacement URL.
        """
        _ = parameters
        prefix = "https://replacement.example.test" if absolute else ""
        return f"{prefix}/replacement/{name}"

    def signed_route(
        self,
        name: str,
        parameters: Mapping[str, object],
        expiration: object,
        absolute: bool,
    ) -> str:
        """Return a replacement result for the signed URL capability.

        Args:
            name: Requested route name.
            parameters: Route values supplied by the caller.
            expiration: Requested expiration value.
            absolute: Whether to include the replacement origin.

        Returns:
            Absolute or relative replacement URL.
        """
        _ = parameters, expiration
        prefix = "https://replacement.example.test" if absolute else ""
        return f"{prefix}/replacement/signed/{name}"

    def action(
        self,
        action: str | Sequence[str],
        parameters: Mapping[str, object],
        absolute: bool,
    ) -> str:
        """Return an action URL from the replacement service.

        Args:
            action: Requested callable identity.
            parameters: Route values supplied by the caller.
            absolute: Whether to include the replacement origin.

        Returns:
            Absolute or relative replacement URL.
        """
        _ = action, parameters
        prefix = "https://replacement.example.test" if absolute else ""
        return f"{prefix}/replacement/action"


def _numeric_article(article_id: int) -> dict[str, int]:
    """Return the integer converted from a typed route parameter.

    Args:
        article_id: Integer path value supplied by Starlette's converter.

    Returns:
        A JSON-compatible mapping containing the converted identifier.
    """
    return {"article_id": article_id}


def _unicode_article(slug: str) -> dict[str, str]:
    """Return the value decoded by the compiled route matcher.

    Args:
        slug: Percent-decoded path parameter supplied by the ASGI router.

    Returns:
        The matched value for the end-to-end URL reversal assertion.
    """
    return {"slug": slug}


def _application(origin: str) -> Application:
    """Create an application with one named controller route.

    Args:
        origin: Trusted application origin selected for URL generation.

    Returns:
        An application whose helpers share one route catalog.
    """
    application = Application(config={"app": {"url": origin}})
    application.router.get(
        "/articles/{article_id}",
        (ArticleController, "show"),
    ).name("articles.show")
    return application


def test_uri_factories_helpers_and_facades_share_url_generator() -> None:
    """Resolve route and path URLs from the active application's registry.

    Controller action lookup and trusted-origin generation use the same
    canonical Router registered in the application container.
    """
    application = _application("https://first.example.test")

    assert SupportUriUrlGenerator is UriUrlGenerator

    with application.context():
        generator = application.make(UriUrlGenerator)
        assert generator is application.container.make(UrlGenerator)

        def injected_generator(
            value: UriUrlGenerator,
        ) -> UriUrlGenerator:
            """Return the route generator injected from the app container.

            Args:
                value: Canonical URL generator contract resolved by injection.

            Returns:
                The same application-owned generator instance.
            """
            return value

        assert application.container.call(injected_generator) is generator
        assert Uri.route("articles.show", {"article_id": "a b"}).value() == (
            "/articles/a%20b"
        )
        assert (
            Uri.route(
                "articles.show",
                {"article_id": 7},
                absolute=False,
            ).value()
            == "/articles/7"
        )
        assert Uri.to("/docs?lang=en#start").value() == (
            "https://first.example.test/docs?lang=en#start"
        )
        assert (
            Uri.action(
                "ArticleController.show",
                {"article_id": 8},
            ).value()
            == "/articles/8"
        )
        assert (
            route(
                "articles.show",
                {"article_id": 9},
                absolute=True,
            )
            == "https://first.example.test/articles/9"
        )
        assert url("/docs", absolute=True) == (
            "https://first.example.test/docs"
        )
        assert url("/docs?tag=a&tag=b#card", absolute=True) == (
            "https://first.example.test/docs?tag=a&tag=b#card"
        )
        named_redirect = redirect().route(
            "articles.show",
            {"article_id": 9},
        )
        assert named_redirect.headers["location"] == "/articles/9"


def test_url_entry_points_resolve_the_substituted_contract() -> None:
    """Use one substituted contract for URI, helper, and redirect access.

    The concrete generator remains registered, but public URL consumers use
    the canonical application contract.
    """
    application = _application("https://first.example.test")
    replacement = _AlternativeUrlGenerator()

    with application.context():
        with application.container.override({UriUrlGenerator: replacement}):
            assert application.make(UriUrlGenerator) is replacement
            assert Uri.route("articles.show").value() == (
                "/replacement/articles.show"
            )
            assert route("articles.show") == ("/replacement/articles.show")
            assert url("/docs", absolute=True) == (
                "https://replacement.example.test/docs"
            )
            assert url("/docs") == "/replacement/url/docs"
            assert Uri.to("/docs").value() == (
                "https://replacement.example.test/docs"
            )
            assert Uri.action("ArticleController.show").value() == (
                "/replacement/action"
            )
            assert Uri.signed_route("articles.show").value() == (
                "/replacement/signed/articles.show"
            )
            assert (
                Uri.temporary_signed_route(
                    "articles.show",
                    60,
                ).value()
                == "/replacement/signed/articles.show"
            )
            assert (
                route(
                    "articles.show",
                    absolute=True,
                )
                == "https://replacement.example.test/replacement/articles.show"
            )
            assert redirect().route("articles.show").headers["location"] == (
                "/replacement/articles.show"
            )
        assert Uri.route("articles.show", {"article_id": 1}).value() == (
            "/articles/1"
        )


def test_named_url_factories_share_relative_default_policy() -> None:
    """Return relative URLs by default from every named-route entry point.

    Callers can request an absolute URL with ``absolute=True``.
    """
    application = _application("https://first.example.test")

    with application.context():
        expected = "/articles/5"

        assert route("articles.show", {"article_id": 5}) == expected
        assert Uri.route("articles.show", {"article_id": 5}).value() == (
            expected
        )
        assert (
            Uri.action(
                "ArticleController.show",
                {"article_id": 5},
            ).value()
            == expected
        )

        assert (
            Uri.route(
                "articles.show",
                {"article_id": 5},
                absolute=True,
            ).value()
            == "https://first.example.test/articles/5"
        )


def test_contract_generated_url_uses_canonical_query_encoding() -> None:
    """Match Support query encoding for nested, repeated, and spaced values.

    Routing uses the shared RFC 3986 encoder instead of a second policy.
    """
    application = _application("https://first.example.test")

    with application.context():
        generated = route(
            "articles.show",
            {
                "article_id": 5,
                "search": "two words",
                "tags": ["ai", "data"],
            },
        )

    assert generated == (
        "/articles/5?search=two%20words&tags%5B0%5D=ai&tags%5B1%5D=data"
    )


def test_typed_route_urls_match_and_reject_invalid_converter_values() -> None:
    """Keep named URL reversal consistent with integer route matching.

    Validate both pre-start fallback generation and compiled backend reversal.
    """
    application = Application(
        config={"app": {"url": "https://api.example.test"}},
    )
    application.router.get(
        "/articles/{article_id:int}",
        _numeric_article,
    ).domain("api.example.test").name("articles.numeric")

    with application.context():
        assert (
            Uri.route(
                "articles.numeric",
                {"article_id": 17},
                absolute=False,
            ).value()
            == "/articles/17"
        )
        with pytest.raises(RouteUrlError):
            Uri.route(
                "articles.numeric",
                {"article_id": "not-an-integer"},
                absolute=False,
            )

    with TestClient(
        application.asgi,
        base_url="https://api.example.test",
    ) as client:
        with application.context():
            generated = Uri.route(
                "articles.numeric",
                {"article_id": 23},
                absolute=True,
            ).value()
            with pytest.raises(RouteUrlError):
                Uri.route(
                    "articles.numeric",
                    {"article_id": "not-an-integer"},
                    absolute=True,
                )

        response = client.get(generated)

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"article_id": 23}


def test_uri_redirect_uses_native_response_factory_and_blocks_external() -> (
    None
):
    """Route URI redirects through native response validation.

    A relative named URL is accepted while an external target remains
    rejected by the framework's response policy.
    """
    application = _application("https://first.example.test")

    with application.context():
        response_factory = application.make(ResponseFactory)
        response = Uri.route(
            "articles.show",
            {"article_id": 3},
            absolute=False,
        ).redirect(status=HTTPStatus.TEMPORARY_REDIRECT)

        assert isinstance(response, RedirectResponse)
        assert response.status_code == HTTPStatus.TEMPORARY_REDIRECT
        assert response.headers["location"] == "/articles/3"
        assert (
            response_factory.redirect("/articles/3").headers["location"]
            == response.headers["location"]
        )
        with pytest.raises(ValueError, match="External redirects"):
            Uri.of("https://evil.example.test/steal").redirect()
        with pytest.raises(ValueError, match="Protocol-relative"):
            Uri.of("//evil.example.test/steal").redirect()
        with pytest.raises(ValueError, match="replace the validated Location"):
            Uri.of("/safe").redirect(
                headers={"lOcAtIoN": "https://evil.example.test"},
            )


def test_uri_application_contexts_restore_after_nesting_and_failure() -> None:
    """Restore the correct URL service after nested and exceptional contexts.

    URI factories must not retain a resolver after its app context exits.
    """
    first = _application("https://first.example.test")
    second = _application("https://second.example.test")

    with first.context():
        assert (
            Uri.route(
                "articles.show",
                {"article_id": 1},
                absolute=True,
            ).host()
            == "first.example.test"
        )

        def enter_second_then_fail() -> None:
            """Raise inside a nested app context for restoration testing.

            The helper keeps the expected exception separate from assertions.
            """
            with second.context():
                assert (
                    Uri.route(
                        "articles.show",
                        {"article_id": 2},
                        absolute=True,
                    ).host()
                    == "second.example.test"
                )
                raise LookupError

        with pytest.raises(LookupError):
            enter_second_then_fail()
        assert (
            Uri.route(
                "articles.show",
                {"article_id": 3},
                absolute=True,
            ).host()
            == "first.example.test"
        )

    with pytest.raises(UriContextError, match="active application"):
        Uri.route("articles.show", {"article_id": 4})
    with pytest.raises(UriContextError, match="active application context"):
        Uri.of("/safe").redirect()


@pytest.mark.anyio
async def test_uri_resolution_isolated_between_concurrent_applications() -> (
    None
):
    """Keep URI generation bound to each concurrent task's application.

    ContextVar tokens restore each task independently after suspension.
    """
    first = _application("https://first.example.test")
    second = _application("https://second.example.test")

    async def generate(
        application: Application,
        article_id: int,
    ) -> tuple[str, str, str]:
        """Generate three URL forms inside one app binding.

        Args:
            application: Application whose URI services are active.
            article_id: Distinct path parameter for the generated URL.

        Returns:
            URI, route-helper, and absolute-path URLs for that application.
        """
        async with application.execution_scope(Scope.REQUEST):
            await asyncio.sleep(0)
            return (
                Uri.route(
                    "articles.show",
                    {"article_id": article_id},
                    absolute=True,
                ).value(),
                route("articles.show", {"article_id": article_id}),
                url("/docs", absolute=True),
            )

    first_url, second_url = await asyncio.gather(
        generate(first, 1),
        generate(second, 2),
    )

    assert first_url == (
        "https://first.example.test/articles/1",
        "/articles/1",
        "https://first.example.test/docs",
    )
    assert second_url == (
        "https://second.example.test/articles/2",
        "/articles/2",
        "https://second.example.test/docs",
    )


def test_uri_route_factory_reports_missing_routes_and_parameters() -> None:
    """Propagate precise native failures from the canonical route catalog.

    A missing name or required placeholder never produces a malformed URL.
    """
    application = _application("https://first.example.test")

    with application.context():
        with pytest.raises(RouteNotFoundError):
            Uri.route("missing.route")
        with pytest.raises(RouteUrlError, match="article_id"):
            Uri.route("articles.show")


def test_uri_signed_route_fails_without_key_management() -> None:
    """Reject signed URLs while no verification key lifecycle exists.

    URI factories must not imply that an unsigned URL is protected.
    """
    application = _application("https://first.example.test")

    with application.context():
        with pytest.raises(RouteUrlError, match="key-management"):
            Uri.signed_route("articles.show", {"article_id": 1})
        with pytest.raises(RouteUrlError, match="key-management"):
            Uri.temporary_signed_route(
                "articles.show",
                60,
                {"article_id": 1},
            )


@pytest.mark.anyio
async def test_compiled_named_route_reversal_uses_starlette_router() -> None:
    """Use backend route reversal after native route compilation.

    Path substitution and escaping are delegated to the installed ASGI router
    once it has compiled the canonical route definitions.
    """
    application = _application("https://first.example.test")
    await application.startup()
    try:
        with application.context():
            generated = Uri.route(
                "articles.show",
                {"article_id": "a b"},
                absolute=False,
            )
        assert generated.value() == "/articles/a%20b"
    finally:
        await application.shutdown()


def test_generated_encoded_url_dispatches_to_its_registered_route() -> None:
    """Dispatch the exact encoded URL produced from the canonical catalog.

    This verifies percent encoding against real route matching and confirms
    that absolute generation uses the configured domain and origin.
    """
    application = Application(
        config={"app": {"url": "https://api.example.test"}},
    )
    application.router.get(
        "/articles/{slug}",
        _unicode_article,
    ).domain("api.example.test").name("articles.unicode")

    with TestClient(
        application.asgi,
        base_url="https://api.example.test",
    ) as client:
        with application.context():
            generated = route(
                "articles.unicode",
                {"slug": "Résumé 17"},
                absolute=True,
            )

        response = client.get(generated)

    assert generated == (
        "https://api.example.test/articles/R%C3%A9sum%C3%A9%2017"
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"slug": "Résumé 17"}
