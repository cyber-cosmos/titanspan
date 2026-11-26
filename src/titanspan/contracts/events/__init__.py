"""Define the dependency-independent event dispatch contract.

The contract does not expose Blinker or Container implementation types.
"""

from titanspan.contracts.events.dispatcher import (
    EventDispatcher,
    EventSelector,
)

__all__ = ["EventDispatcher", "EventSelector"]
