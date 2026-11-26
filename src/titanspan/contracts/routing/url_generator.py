"""Describe application URL construction backed by native route metadata.

The protocol keeps URI factories independent of concrete routing services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


@runtime_checkable
class UriUrlGenerator(Protocol):
    """Build application URLs without exposing a routing implementation.

    Implementations use their owning application's route catalog and trusted
    origin. Runtime protocol checks validate member presence only.
    """

    def to(self, path: str) -> str:
        """Resolve a local path against the configured application origin.

        Args:
            path: Local absolute path with optional query and fragment.

        Returns:
            Absolute URL containing the configured trusted origin.
        """
        ...

    def url(self, path: str, absolute: bool) -> str:
        """Build a local application URL through the owning generator.

        Args:
            path: Local absolute path with optional query and fragment.
            absolute: Whether to add the configured trusted application origin.

        Returns:
            A local path or trusted-origin absolute URL.
        """
        ...

    def route(
        self,
        name: str,
        parameters: Mapping[str, object],
        absolute: bool,
    ) -> str:
        """Build a URL from one registered named route.

        Args:
            name: Unique route name in the owning application's catalog.
            parameters: Path values and remaining query values.
            absolute: Whether to include the configured trusted origin.

        Returns:
            Encoded route URL with any remaining values in its query.
        """
        ...

    def signed_route(
        self,
        name: str,
        parameters: Mapping[str, object],
        expiration: object,
        absolute: bool,
    ) -> str:
        """Build a route whose query is authenticated and verifiable.

        Args:
            name: Unique route name in the owning application's catalog.
            parameters: Path values and signed query values.
            expiration: Signature expiration accepted by key management.
            absolute: Whether to include the configured trusted origin.

        Returns:
            A signed route URL.

        Implementations that lack key management must raise their native
        security error instead of returning an unsigned URL.
        """
        ...

    def action(
        self,
        action: str | Sequence[str],
        parameters: Mapping[str, object],
        absolute: bool,
    ) -> str:
        """Build a URL for an unambiguous registered callable action.

        Args:
            action: Dotted action identifier or ordered identifier parts.
            parameters: Path values and remaining query values.
            absolute: Whether to include the configured trusted origin.

        Returns:
            Encoded URL for the route associated with the action.
        """
        ...


__all__ = ["UriUrlGenerator"]
