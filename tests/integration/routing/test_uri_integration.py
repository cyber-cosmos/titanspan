"""Verify URI factories and routing share application services.

The tests use the production Application, Container, Router, and response
factory rather than a separate URL registry.
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus

import pytest

from titanspan import redirect, route, url
from titanspan.container import Scope
from titanspan.contracts.http import ResponseFactory
from titanspan.contracts.routing import UriUrlGenerator
from titanspan.foundation import Application
from titanspan.http import RedirectResponse
from titanspan.routing import RouteNotFoundError, RouteUrlError, UrlGenerator
from titanspan.support import Uri, UriContextError

pytestmark = pytest.mark.integration


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
            "https://first.example.test/articles/a%20b"
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
            == "https://first.example.test/articles/8"
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
        named_redirect = redirect().route(
            "articles.show",
            {"article_id": 9},
        )
        assert named_redirect.headers["location"] == "/articles/9"


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
        assert Uri.route("articles.show", {"article_id": 1}).host() == (
            "first.example.test"
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
                    ).host()
                    == "second.example.test"
                )
                raise LookupError

        with pytest.raises(LookupError):
            enter_second_then_fail()
        assert Uri.route("articles.show", {"article_id": 3}).host() == (
            "first.example.test"
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

    async def generate(application: Application, article_id: int) -> str:
        """Generate one URL while yielding inside an app binding.

        Args:
            application: Application whose URI services are active.
            article_id: Distinct path parameter for the generated URL.

        Returns:
            Absolute article URL generated in that task's context.
        """
        async with application.execution_scope(Scope.REQUEST):
            await asyncio.sleep(0)
            return Uri.route(
                "articles.show",
                {"article_id": article_id},
            ).value()

    first_url, second_url = await asyncio.gather(
        generate(first, 1),
        generate(second, 2),
    )

    assert first_url == "https://first.example.test/articles/1"
    assert second_url == "https://second.example.test/articles/2"


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
