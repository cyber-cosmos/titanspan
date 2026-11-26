"""Re-export the canonical dependency scope values for container users.

The value type belongs to Contracts so registration providers need no
dependency on the concrete container implementation.
"""

from titanspan.contracts.container.scope import Scope

__all__ = ["Scope"]
