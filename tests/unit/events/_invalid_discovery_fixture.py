"""Provide an unresolved event annotation for discovery error tests.

The module remains isolated from valid discovery fixtures.
"""

from __future__ import annotations


def unresolved_listener(event: object) -> None:
    """Provide a listener whose annotation name is unavailable.

    Discovery must report the unresolved reference during inspection.
    """
    _ = event


unresolved_listener.__annotations__["event"] = "MissingEventType"
