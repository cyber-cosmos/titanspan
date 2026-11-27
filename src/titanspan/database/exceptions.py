"""Define safe errors for native database operations.

Backend exceptions remain available through exception chaining while native
messages avoid including SQL bindings and connection credentials.
"""

from collections.abc import Sequence

from titanspan.contracts.database.manager import TransactionOutcome


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


class ModelPersistenceCancelledError(DatabaseError):
    """Report a model operation rejected by a cancellable lifecycle event.

    High-level creation APIs raise this error when cancellation prevents them
    from returning the persisted model or collection promised by their type.
    """


class ModelSerializationLimitError(DatabaseError):
    """Report a model graph that exceeds safe serialization bounds.

    Serialization fails instead of returning a silently truncated graph.
    """


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


class DatabaseTransactionCallbackError(DatabaseTransactionError):
    """Report callback failures with the confirmed transaction outcome.
    """  # fmt: skip

    def __init__(
        self,
        outcome: TransactionOutcome,
        callback_errors: Sequence[Exception],
    ) -> None:
        """Preserve callback errors in registration order.

        Args:
            outcome: Confirmed transaction or savepoint outcome.
            callback_errors: Failures raised by selected callbacks.
        """
        self.outcome = outcome
        self.callback_errors = tuple(callback_errors)
        if outcome is TransactionOutcome.COMMITTED_WITH_CALLBACK_ERRORS:
            message = (
                "The database transaction committed, but one or more "
                "after-commit callbacks failed."
            )
        else:
            message = (
                "The database transaction rolled back, but one or more "
                "after-rollback callbacks failed."
            )
        super().__init__(message)

    @property
    def committed(self) -> bool:
        """Return whether persistence committed before callbacks failed.

        Returns:
            Whether the callback failure followed a confirmed commit.
        """
        return self.outcome is TransactionOutcome.COMMITTED_WITH_CALLBACK_ERRORS

    @property
    def rolled_back(self) -> bool:
        """Return whether rollback completed before callbacks failed.

        Returns:
            Whether the callback failure followed a confirmed rollback.
        """
        return self.outcome in {
            TransactionOutcome.ROLLED_BACK,
            TransactionOutcome.SAVEPOINT_ROLLED_BACK,
        }


class DatabaseCommitOutcomeUnknownError(DatabaseTransactionError):
    """Report a commit failure whose durable outcome cannot be confirmed.
    """  # fmt: skip

    def __init__(
        self,
        commit_error: BaseException,
        cleanup_error: BaseException | None = None,
    ) -> None:
        """Preserve commit and cleanup errors for caller diagnostics.

        Args:
            commit_error: Failure raised while issuing transaction commit.
            cleanup_error: Optional failure while invalidating the connection.
        """
        self.commit_error = commit_error
        self.cleanup_error = cleanup_error
        message = "The database commit failed; its outcome is unknown."
        super().__init__(message)


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
    "DatabaseCommitOutcomeUnknownError",
    "DatabaseConfigurationError",
    "DatabaseConnectionError",
    "DatabaseError",
    "DatabaseFactoryError",
    "DatabaseMigrationError",
    "DatabaseQueryError",
    "DatabaseSchemaError",
    "DatabaseSeederError",
    "DatabaseTransactionCallbackError",
    "DatabaseTransactionError",
    "DatabaseTransactionOwnershipError",
    "MassAssignmentError",
    "ModelNotFoundError",
    "ModelPersistenceCancelledError",
    "ModelSerializationLimitError",
    "MultipleModelsFoundError",
]
