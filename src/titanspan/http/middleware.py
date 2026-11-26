"""Expose native ASGI middleware backed by supported Starlette behavior.

Global application middleware remains configured through the ASGI host.
"""

from titanspan.http._backends.middleware import (
    CorsMiddleware,
    HttpsRedirectMiddleware,
    TrustedHostMiddleware,
)

__all__ = [
    "CorsMiddleware",
    "HttpsRedirectMiddleware",
    "TrustedHostMiddleware",
]
