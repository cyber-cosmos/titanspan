"""Define native logger customization for newly resolved channels.

Customizers receive Titanspan loggers before they are cached or returned.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from titanspan.logging.logger import Logger


class LogCustomizer(Protocol):
    """Customize one newly constructed native logger.

    Implementations can attach native listeners or apply application-owned
    setup while avoiding access to third-party backend logger objects.
    """

    def customize(self, logger: Logger) -> None:
        """Apply synchronous setup before the logger is published.

        Args:
            logger: Newly constructed Titanspan logger being initialized.

        Raises:
            Exception: A setup error aborts channel construction.
        """
        ...
