"""Expose native application persistence APIs over SQLAlchemy.

Import this optional component after installing the ``database`` extra.
SQLAlchemy owns database infrastructure while Titanspan owns application
configuration, connection selection, sessions, and transaction conventions.
"""

from titanspan.contracts.database import (
    DatabaseConnectionService,
    DatabaseQueryBuilder,
    DatabaseResult,
    DatabaseService,
)
from titanspan.database.configuration import (
    ConnectionConfiguration,
    DatabaseConfiguration,
)
from titanspan.database.connection import Connection
from titanspan.database.exceptions import (
    AsyncOperationRequiredError,
    DatabaseConfigurationError,
    DatabaseConnectionError,
    DatabaseError,
    DatabaseQueryError,
    DatabaseSchemaError,
    DatabaseTransactionError,
    DatabaseTransactionOwnershipError,
    MassAssignmentError,
    ModelNotFoundError,
    MultipleModelsFoundError,
)
from titanspan.database.manager import DatabaseManager
from titanspan.database.model import Model
from titanspan.database.orm_builder import ModelQueryBuilder
from titanspan.database.query_builder import QueryBuilder
from titanspan.database.relationships import (
    belongs_to,
    belongs_to_many,
    has_many,
    has_one,
)
from titanspan.database.schema import Blueprint, ColumnDefinition, Schema
from titanspan.database.service_provider import DatabaseServiceProvider

__all__ = [
    "AsyncOperationRequiredError",
    "Blueprint",
    "ColumnDefinition",
    "Connection",
    "ConnectionConfiguration",
    "DatabaseConfiguration",
    "DatabaseConfigurationError",
    "DatabaseConnectionError",
    "DatabaseConnectionService",
    "DatabaseError",
    "DatabaseManager",
    "DatabaseQueryBuilder",
    "DatabaseQueryError",
    "DatabaseResult",
    "DatabaseSchemaError",
    "DatabaseService",
    "DatabaseServiceProvider",
    "DatabaseTransactionError",
    "DatabaseTransactionOwnershipError",
    "MassAssignmentError",
    "Model",
    "ModelNotFoundError",
    "ModelQueryBuilder",
    "MultipleModelsFoundError",
    "QueryBuilder",
    "Schema",
    "belongs_to",
    "belongs_to_many",
    "has_many",
    "has_one",
]
