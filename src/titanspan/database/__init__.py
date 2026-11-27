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
    LengthAwarePage,
    SimplePage,
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
    DatabaseFactoryError,
    DatabaseMigrationError,
    DatabaseQueryError,
    DatabaseSchemaError,
    DatabaseSeederError,
    DatabaseTransactionError,
    DatabaseTransactionOwnershipError,
    MassAssignmentError,
    ModelNotFoundError,
    MultipleModelsFoundError,
)
from titanspan.database.factory import FactoryBatch, ModelFactory
from titanspan.database.manager import DatabaseManager
from titanspan.database.migration_manager import (
    MigrationManager,
    MigrationStatus,
)
from titanspan.database.migrations import Migration, run_migration
from titanspan.database.model import Model, SoftDeletes
from titanspan.database.model_collection import ModelCollection
from titanspan.database.orm_builder import ModelQueryBuilder
from titanspan.database.pagination import LengthAwarePaginator, Paginator
from titanspan.database.query_builder import QueryBuilder
from titanspan.database.relationships import (
    belongs_to,
    belongs_to_many,
    has_many,
    has_one,
)
from titanspan.database.schema import Blueprint, ColumnDefinition, Schema
from titanspan.database.seeder import Seeder
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
    "DatabaseFactoryError",
    "DatabaseManager",
    "DatabaseMigrationError",
    "DatabaseQueryBuilder",
    "DatabaseQueryError",
    "DatabaseResult",
    "DatabaseSchemaError",
    "DatabaseSeederError",
    "DatabaseService",
    "DatabaseServiceProvider",
    "DatabaseTransactionError",
    "DatabaseTransactionOwnershipError",
    "FactoryBatch",
    "LengthAwarePage",
    "LengthAwarePaginator",
    "MassAssignmentError",
    "Migration",
    "MigrationManager",
    "MigrationStatus",
    "Model",
    "ModelCollection",
    "ModelFactory",
    "ModelNotFoundError",
    "ModelQueryBuilder",
    "MultipleModelsFoundError",
    "Paginator",
    "QueryBuilder",
    "Schema",
    "Seeder",
    "SimplePage",
    "SoftDeletes",
    "belongs_to",
    "belongs_to_many",
    "has_many",
    "has_one",
    "run_migration",
]
