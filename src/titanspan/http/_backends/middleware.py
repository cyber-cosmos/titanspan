"""Wrap Starlette's supported HTTP security middleware.

Starlette owns CORS, Host validation, and HTTPS redirect mechanics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, Unpack

from starlette.middleware.cors import CORSMiddleware as StarletteCorsMiddleware
from starlette.middleware.httpsredirect import (
    HTTPSRedirectMiddleware as StarletteHttpsRedirectMiddleware,
)
from starlette.middleware.trustedhost import (
    TrustedHostMiddleware as StarletteTrustedHostMiddleware,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from starlette.types import ASGIApp, Receive, Scope, Send


class CorsMiddleware:
    """Apply Starlette CORS handling to an ASGI application.

    Configure explicit origins and methods for browser-facing endpoints.
    """

    def __init__(self, app: ASGIApp, **options: Unpack[_CorsOptions]) -> None:
        """Build a CORS policy through Starlette's public middleware API.

        Args:
            app: Downstream ASGI application.
            options: Public Starlette CORS options for origins, methods,
                headers, credentials, exposed values, and preflight caching.
        """
        self._app = StarletteCorsMiddleware(app, **options)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Delegate one ASGI message flow to Starlette's CORS middleware.

        Starlette retains ownership of preflight handling and response headers.
        """
        await self._app(scope, receive, send)

    _app: ASGIApp


class HttpsRedirectMiddleware:
    """Redirect HTTP and WS requests to their secure schemes.

    Starlette owns the ASGI redirect response and scheme handling.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap an ASGI application with Starlette's HTTPS redirect.

        Args:
            app: Downstream ASGI application.
        """
        self._app = StarletteHttpsRedirectMiddleware(app)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Delegate redirect decisions to Starlette.

        The downstream app receives only secure HTTP or WebSocket requests.
        """
        await self._app(scope, receive, send)

    _app: ASGIApp


class TrustedHostMiddleware:
    """Reject requests whose Host header is outside an allowlist.

    The configured allowlist remains an application-owned security policy.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_hosts: Sequence[str],
        www_redirect: bool = False,
    ) -> None:
        """Wrap an application with Starlette Host validation.

        Args:
            app: Downstream ASGI application.
            allowed_hosts: Hostnames or wildcard suffixes accepted by policy.
            www_redirect: Whether to redirect allowed bare hosts to ``www``.
        """
        self._app = StarletteTrustedHostMiddleware(
            app,
            allowed_hosts=allowed_hosts,
            www_redirect=www_redirect,
        )

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Delegate Host validation and rejection responses to Starlette.

        The host allowlist remains the application security policy.
        """
        await self._app(scope, receive, send)

    _app: ASGIApp


class _CorsOptions(TypedDict, total=False):
    """Type Starlette's supported keyword-only CORS configuration.

    Starlette remains responsible for validating and enforcing these values.
    """

    allow_origins: Sequence[str]
    allow_methods: Sequence[str]
    allow_headers: Sequence[str]
    allow_credentials: bool
    allow_origin_regex: str | None
    expose_headers: Sequence[str]
    max_age: int


__all__ = [
    "CorsMiddleware",
    "HttpsRedirectMiddleware",
    "TrustedHostMiddleware",
]
