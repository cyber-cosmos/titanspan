"""Expose canonical database contracts without backend imports.
"""  # fmt: skip

from titanspan.contracts.database.connection import (
    DatabaseConnectionService,
)
from titanspan.contracts.database.manager import DatabaseService
from titanspan.contracts.database.query import DatabaseQueryBuilder
from titanspan.contracts.database.result import DatabaseResult

__all__ = [
    "DatabaseConnectionService",
    "DatabaseQueryBuilder",
    "DatabaseResult",
    "DatabaseService",
]
