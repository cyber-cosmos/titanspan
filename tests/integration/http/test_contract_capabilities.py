"""Exercise upload and response operations through native HTTP contracts.

The cases run through the application ASGI host and dependency injection.
"""

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from titanspan.contracts.http import (
    HttpRequest,
    HttpResponse,
    RequestHandler,
    ResponseFactory,
)
from titanspan.foundation import Application

pytestmark = [pytest.mark.architecture, pytest.mark.integration]
_EXPECTED_COOKIE_COUNT = 3


class CookieMiddleware:
    """Mutate response cookies through the native response contract.

    The integration test verifies repeated Set-Cookie headers.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Add cookies after the endpoint returns its native response.

        Args:
            request: Request contract forwarded through the route.
            next_handler: Native endpoint invocation.

        Returns:
            The response with two cookies and one expired cookie.
        """
        response = await next_handler(request)
        response.with_cookie("first", "one")
        response.with_cookie("second", "two")
        response.without_cookie("expired")
        return response


def test_injected_request_contract_exposes_upload_access() -> None:
    """Read upload metadata and chunks through the shared request contract.

    The request owns temporary file cleanup through response transmission.
    """
    application = Application()

    async def inspect_uploads(request: HttpRequest) -> dict[str, object]:
        """Read one file and repeated files without backend imports.

        Args:
            request: Request-scoped canonical HTTP contract.

        Returns:
            Safe metadata and bytes read from all submitted files.
        """
        single = await request.file("single")
        repeated = await request.files("repeated")
        if single is None:
            return {"single": None, "repeated": []}
        return {
            "single": {
                "filename": single.safe_filename,
                "content_type": single.content_type,
                "size": single.size,
                "chunks": [
                    chunk.decode("utf-8")
                    async for chunk in single.iter_chunks(2)
                ],
            },
            "repeated": [
                {
                    "filename": item.safe_filename,
                    "content": (await item.read()).decode("utf-8"),
                }
                for item in repeated
            ],
        }

    application.router.post("/uploads", inspect_uploads)

    with TestClient(application.asgi) as client:
        result = client.post(
            "/uploads",
            files=[
                ("single", ("../report.txt", b"abc", "text/plain")),
                ("repeated", ("one.txt", b"one", "text/plain")),
                ("repeated", ("two.txt", b"two", "text/plain")),
            ],
        )

    assert result.status_code == HTTPStatus.OK
    assert result.json() == {
        "single": {
            "filename": "report.txt",
            "content_type": "text/plain",
            "size": 3,
            "chunks": ["ab", "c"],
        },
        "repeated": [
            {"filename": "one.txt", "content": "one"},
            {"filename": "two.txt", "content": "two"},
        ],
    }


def test_route_middleware_mutates_multiple_response_cookies() -> None:
    """Preserve repeated Set-Cookie headers through Foundation adaptation.

    Middleware receives the same native response contract as an endpoint.
    """
    application = Application()

    def endpoint(factory: ResponseFactory) -> HttpResponse:
        """Create one JSON response through the native factory.

        Args:
            factory: Application-owned response factory contract.

        Returns:
            A response for cookie middleware to update.
        """
        return factory.json({"ready": True})

    application.router.get("/cookies", endpoint).middleware(
        CookieMiddleware,
    )

    with TestClient(application.asgi) as client:
        result = client.get("/cookies")

    assert result.status_code == HTTPStatus.OK
    assert result.json() == {"ready": True}
    cookies = result.headers.get_list("set-cookie")
    assert len(cookies) == _EXPECTED_COOKIE_COUNT
    assert any(cookie.startswith("first=one") for cookie in cookies)
    assert any(cookie.startswith("second=two") for cookie in cookies)
    assert any(cookie.startswith("expired=") for cookie in cookies)
