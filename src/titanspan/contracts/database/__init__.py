"""Expose canonical database contracts without backend imports.
"""  # fmt: skip

from titanspan.contracts.database.connection import (
    DatabaseConnectionService,
)
from titanspan.contracts.database.manager import (
    DatabaseService,
    TransactionOutcome,
    TransactionReceipt,
)
from titanspan.contracts.database.pagination import (
    LengthAwarePage,
    SimplePage,
)
from titanspan.contracts.database.query import DatabaseQueryBuilder
from titanspan.contracts.database.result import DatabaseResult

__all__ = [
    "DatabaseConnectionService",
    "DatabaseQueryBuilder",
    "DatabaseResult",
    "DatabaseService",
    "LengthAwarePage",
    "SimplePage",
    "TransactionOutcome",
    "TransactionReceipt",
]
