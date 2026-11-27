"""Expose native application persistence APIs over SQLAlchemy.

Import this optional component after installing the ``database`` extra.
SQLAlchemy owns database infrastructure while Titanspan owns application
configuration, connection selection, sessions, and transaction conventions.
"""

from titanspan.contracts.database import (
    CursorPage,
    DatabaseConnectionService,
    DatabaseJoinClause,
    DatabaseQueryBuilder,
    DatabaseResult,
    DatabaseService,
    LengthAwarePage,
    SimplePage,
    TransactionOutcome,
    TransactionReceipt,
)
from titanspan.database.configuration import (
    ConnectionConfiguration,
    DatabaseConfiguration,
)
from titanspan.database.connection import Connection
from titanspan.database.events import (
    ModelCreated,
    ModelCreating,
    ModelDeleted,
    ModelDeleting,
    ModelEvent,
    ModelSaved,
    ModelSaving,
    ModelUpdated,
    ModelUpdating,
)
from titanspan.database.exceptions import (
    AsyncOperationRequiredError,
    DatabaseCommitOutcomeUnknownError,
    DatabaseConfigurationError,
    DatabaseConnectionError,
    DatabaseError,
    DatabaseFactoryError,
    DatabaseMigrationError,
    DatabaseQueryError,
    DatabaseSchemaError,
    DatabaseSeederError,
    DatabaseTransactionCallbackError,
    DatabaseTransactionError,
    DatabaseTransactionOwnershipError,
    MassAssignmentError,
    ModelNotFoundError,
    ModelPersistenceCancelledError,
    ModelSerializationLimitError,
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
from titanspan.database.pagination import (
    CursorPaginator,
    LengthAwarePaginator,
    Paginator,
)
from titanspan.database.query_builder import QueryBuilder
from titanspan.database.relationships import (
    belongs_to,
    belongs_to_many,
    has_many,
    has_one,
)
from titanspan.database.routing import bind_model
from titanspan.database.schema import Blueprint, ColumnDefinition, Schema
from titanspan.database.seeder import Seeder
from titanspan.database.service_provider import DatabaseServiceProvider
from titanspan.database.testing import (
    assert_database_count,
    assert_database_count_async,
    assert_database_empty,
    assert_database_empty_async,
    assert_database_has,
    assert_database_has_async,
    assert_database_missing,
    assert_database_missing_async,
    assert_model_exists,
    assert_model_exists_async,
    assert_model_missing,
    assert_model_missing_async,
    assert_not_soft_deleted,
    assert_not_soft_deleted_async,
    assert_soft_deleted,
    assert_soft_deleted_async,
)
from titanspan.database.validation import exists_rule, unique_rule

__all__ = [
    "AsyncOperationRequiredError",
    "Blueprint",
    "ColumnDefinition",
    "Connection",
    "ConnectionConfiguration",
    "CursorPage",
    "CursorPaginator",
    "DatabaseCommitOutcomeUnknownError",
    "DatabaseConfiguration",
    "DatabaseConfigurationError",
    "DatabaseConnectionError",
    "DatabaseConnectionService",
    "DatabaseError",
    "DatabaseFactoryError",
    "DatabaseJoinClause",
    "DatabaseManager",
    "DatabaseMigrationError",
    "DatabaseQueryBuilder",
    "DatabaseQueryError",
    "DatabaseResult",
    "DatabaseSchemaError",
    "DatabaseSeederError",
    "DatabaseService",
    "DatabaseServiceProvider",
    "DatabaseTransactionCallbackError",
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
    "ModelCreated",
    "ModelCreating",
    "ModelDeleted",
    "ModelDeleting",
    "ModelEvent",
    "ModelFactory",
    "ModelNotFoundError",
    "ModelPersistenceCancelledError",
    "ModelQueryBuilder",
    "ModelSaved",
    "ModelSaving",
    "ModelSerializationLimitError",
    "ModelUpdated",
    "ModelUpdating",
    "MultipleModelsFoundError",
    "Paginator",
    "QueryBuilder",
    "Schema",
    "Seeder",
    "SimplePage",
    "SoftDeletes",
    "TransactionOutcome",
    "TransactionReceipt",
    "assert_database_count",
    "assert_database_count_async",
    "assert_database_empty",
    "assert_database_empty_async",
    "assert_database_has",
    "assert_database_has_async",
    "assert_database_missing",
    "assert_database_missing_async",
    "assert_model_exists",
    "assert_model_exists_async",
    "assert_model_missing",
    "assert_model_missing_async",
    "assert_not_soft_deleted",
    "assert_not_soft_deleted_async",
    "assert_soft_deleted",
    "assert_soft_deleted_async",
    "belongs_to",
    "belongs_to_many",
    "bind_model",
    "exists_rule",
    "has_many",
    "has_one",
    "run_migration",
    "unique_rule",
]
