"""Define safe errors for native database operations.

Backend exceptions remain available through exception chaining while native
messages avoid including SQL bindings and connection credentials.
"""


class DatabaseError(Exception):
    """Represent a failure at the Titanspan database boundary.
    """  # fmt: skip


class DatabaseConfigurationError(DatabaseError):
    """Report invalid or incomplete database configuration.
    """  # fmt: skip


class DatabaseConnectionError(DatabaseError):
    """Report a connection or driver failure without exposing credentials.
    """  # fmt: skip


class DatabaseQueryError(DatabaseError):
    """Report a failed statement without exposing bound parameters.
    """  # fmt: skip


class DatabaseSchemaError(DatabaseError):
    """Report an invalid or unsupported native schema operation.
    """  # fmt: skip


class DatabaseMigrationError(DatabaseError):
    """Report a migration failure without exposing database credentials.
    """  # fmt: skip


class DatabaseFactoryError(DatabaseError):
    """Report invalid model-factory configuration or batch values.
    """  # fmt: skip


class DatabaseSeederError(DatabaseError):
    """Report an invalid or unavailable application database seeder.
    """  # fmt: skip


class DatabaseTransactionError(DatabaseError):
    """Report an invalid transaction lifecycle operation.
    """  # fmt: skip


class DatabaseTransactionOwnershipError(DatabaseTransactionError):
    """Reject database work from an execution that does not own its session.
    """  # fmt: skip


class ModelNotFoundError(DatabaseError):
    """Report a model lookup that returned no database row.
    """  # fmt: skip


class MultipleModelsFoundError(DatabaseError):
    """Report a lookup that expected one row but matched several.
    """  # fmt: skip


class MassAssignmentError(DatabaseError):
    """Reject attributes excluded by the model's mass-assignment policy.
    """  # fmt: skip


class AsyncOperationRequiredError(DatabaseError):
    """Require the explicit async API when sync database I/O could block.
    """  # fmt: skip


__all__ = [
    "AsyncOperationRequiredError",
    "DatabaseConfigurationError",
    "DatabaseConnectionError",
    "DatabaseError",
    "DatabaseFactoryError",
    "DatabaseMigrationError",
    "DatabaseQueryError",
    "DatabaseSchemaError",
    "DatabaseSeederError",
    "DatabaseTransactionError",
    "DatabaseTransactionOwnershipError",
    "MassAssignmentError",
    "ModelNotFoundError",
    "MultipleModelsFoundError",
]
