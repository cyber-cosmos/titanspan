"""Define backend-independent response-cookie options.

HTTP response adapters use the same immutable cookie policy values.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class CookieOptions:
    """Describe response-cookie attributes with secure defaults.

    Attributes:
        max_age: Optional lifetime in seconds.
        path: Cookie path scope.
        domain: Optional host scope.
        secure: Restrict transmission to HTTPS.
        http_only: Prevent ordinary browser script access.
        same_site: Cross-site request policy.
    """

    max_age: int | None = None
    path: str = "/"
    domain: str | None = None
    secure: bool = True
    http_only: bool = True
    same_site: Literal["lax", "strict", "none"] = "lax"


DEFAULT_COOKIE_OPTIONS = CookieOptions()


__all__ = ["DEFAULT_COOKIE_OPTIONS", "CookieOptions"]
