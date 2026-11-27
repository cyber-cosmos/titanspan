"""Define the application-relative path resolution contract.

Providers use this shared boundary to anchor relative resources to the
composition root without reading the process working directory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path


@runtime_checkable
class ApplicationPaths(Protocol):
    """Expose the trusted root and conventional path joining operation.

    Application-owned providers depend on this contract instead of keeping
    independent working-directory defaults.
    """

    @property
    def base_path(self) -> Path:
        """Return the resolved root selected by the Application.

        Returns:
            The trusted application root.
        """
        ...

    def path(self, *parts: str) -> Path:
        """Join path segments beneath the application root.

        Args:
            *parts: Trusted path segments to append.

        Returns:
            A path rooted at ``base_path``.
        """
        ...


__all__ = ["ApplicationPaths"]
