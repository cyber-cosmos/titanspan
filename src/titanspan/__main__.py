"""Dispatch ``python -m titanspan`` to the supported command-line entry.

The console module owns option parsing so module and installed entry points
share the same behavior.
"""

from titanspan.console.cli import main

main()
