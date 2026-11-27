"""Provide query-backed assertions for native Database tests.

The helpers reuse the active application service and never own a test
application lifecycle or bypass SQLAlchemy's execution policy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.database.model import Model, SoftDeletes
from titanspan.facades.database import DB

if TYPE_CHECKING:
    from collections.abc import Mapping

    from titanspan.database.orm_builder import ModelQueryBuilder

_DATABASE_ROW_MISSING = (
    "Expected a row matching the supplied attributes in the selected table."
)
_DATABASE_ROW_PRESENT = (
    "Expected no row matching the supplied attributes in the selected table."
)
_MODEL_MISSING = "Expected the model's persisted row to exist."
_MODEL_PRESENT = "Expected the model's persisted row to be absent."
_SOFT_DELETED = "Expected the model's row to be soft deleted."
_NOT_SOFT_DELETED = (
    "Expected the model's row to be active and not soft deleted."
)
_SOFT_DELETE_TYPE_ERROR = "Soft-delete assertions require SoftDeletes models."


def assert_database_has(
    table_name: str,
    attributes: Mapping[str, object],
    *,
    connection: str | None = None,
) -> None:
    """Assert that one row matches the supplied column values.

    Args:
        table_name: Safe table identifier accepted by the Query Builder.
        attributes: Bound equality conditions used to find a row.
        connection: Optional configured connection name.
    """
    query = DB.table(table_name, connection=connection).where(attributes)
    if not query.exists():
        raise AssertionError(_DATABASE_ROW_MISSING)


async def assert_database_has_async(
    table_name: str,
    attributes: Mapping[str, object],
    *,
    connection: str | None = None,
) -> None:
    """Asynchronously assert that a matching row exists.

    Args:
        table_name: Safe table identifier accepted by the Query Builder.
        attributes: Bound equality conditions used to find a row.
        connection: Optional configured connection name.
    """
    query = DB.table(table_name, connection=connection).where(attributes)
    if not await query.exists_async():
        raise AssertionError(_DATABASE_ROW_MISSING)


def assert_database_missing(
    table_name: str,
    attributes: Mapping[str, object],
    *,
    connection: str | None = None,
) -> None:
    """Assert that no row matches the supplied column values.

    Args:
        table_name: Safe table identifier accepted by the Query Builder.
        attributes: Bound equality conditions used to search for a row.
        connection: Optional configured connection name.
    """
    if DB.table(table_name, connection=connection).where(attributes).exists():
        raise AssertionError(_DATABASE_ROW_PRESENT)


async def assert_database_missing_async(
    table_name: str,
    attributes: Mapping[str, object],
    *,
    connection: str | None = None,
) -> None:
    """Asynchronously assert that no matching row exists.

    Args:
        table_name: Safe table identifier accepted by the Query Builder.
        attributes: Bound equality conditions used to search for a row.
        connection: Optional configured connection name.
    """
    query = DB.table(table_name, connection=connection).where(attributes)
    if await query.exists_async():
        raise AssertionError(_DATABASE_ROW_PRESENT)


def assert_database_count(
    table_name: str,
    expected: int,
    *,
    connection: str | None = None,
) -> None:
    """Assert the exact row count for one table.

    Args:
        table_name: Safe table identifier accepted by the Query Builder.
        expected: Expected non-negative table row count.
        connection: Optional configured connection name.
    """
    actual = DB.table(table_name, connection=connection).count()
    if actual != expected:
        message = f"Expected {expected} rows but found {actual}."
        raise AssertionError(message)


async def assert_database_count_async(
    table_name: str,
    expected: int,
    *,
    connection: str | None = None,
) -> None:
    """Asynchronously assert the exact row count for one table.

    Args:
        table_name: Safe table identifier accepted by the Query Builder.
        expected: Expected non-negative table row count.
        connection: Optional configured connection name.
    """
    actual = await DB.table(table_name, connection=connection).count_async()
    if actual != expected:
        message = f"Expected {expected} rows but found {actual}."
        raise AssertionError(message)


def assert_database_empty(
    table_name: str,
    *,
    connection: str | None = None,
) -> None:
    """Assert that a table contains no rows.

    Args:
        table_name: Safe table identifier accepted by the Query Builder.
        connection: Optional configured connection name.
    """
    assert_database_count(table_name, 0, connection=connection)


async def assert_database_empty_async(
    table_name: str,
    *,
    connection: str | None = None,
) -> None:
    """Asynchronously assert that a table contains no rows.

    Args:
        table_name: Safe table identifier accepted by the Query Builder.
        connection: Optional configured connection name.
    """
    await assert_database_count_async(table_name, 0, connection=connection)


def assert_model_exists(model: Model) -> None:
    """Assert that the model's primary-key row remains in the database.

    Soft-deleted rows count as existing records for this assertion.

    Args:
        model: Mapped model instance whose database identity is checked.
    """
    if not _model_query(model).exists():
        raise AssertionError(_MODEL_MISSING)


async def assert_model_exists_async(model: Model) -> None:
    """Asynchronously assert that the model's row exists.

    Soft-deleted rows count as existing records for this assertion.

    Args:
        model: Mapped model instance whose database identity is checked.
    """
    if not await _model_query(model).exists_async():
        raise AssertionError(_MODEL_MISSING)


def assert_model_missing(model: Model) -> None:
    """Assert that the model's primary-key row is absent.

    Args:
        model: Mapped model instance whose database identity is checked.
    """
    if _model_query(model).exists():
        raise AssertionError(_MODEL_PRESENT)


async def assert_model_missing_async(model: Model) -> None:
    """Asynchronously assert that the model's row is absent.

    Args:
        model: Mapped model instance whose database identity is checked.
    """
    if await _model_query(model).exists_async():
        raise AssertionError(_MODEL_PRESENT)


def assert_soft_deleted(model: Model) -> None:
    """Assert that a persisted soft-deletable row has been deleted.

    Args:
        model: Instance mapped with the :class:`SoftDeletes` mixin.

    Raises:
        TypeError: If the model does not support soft deletion.
    """
    query = _soft_delete_query(model)
    if not query.only_trashed().exists():
        raise AssertionError(_SOFT_DELETED)


async def assert_soft_deleted_async(model: Model) -> None:
    """Asynchronously assert that a soft-deleted row is persisted.

    Args:
        model: Instance mapped with the :class:`SoftDeletes` mixin.

    Raises:
        TypeError: If the model does not support soft deletion.
    """
    query = _soft_delete_query(model)
    if not await query.only_trashed().exists_async():
        raise AssertionError(_SOFT_DELETED)


def assert_not_soft_deleted(model: Model) -> None:
    """Assert that a persisted soft-deletable row remains active.

    Args:
        model: Instance mapped with the :class:`SoftDeletes` mixin.

    Raises:
        TypeError: If the model does not support soft deletion.
    """
    query = _soft_delete_query(model)
    if not query.without_trashed().exists():
        raise AssertionError(_NOT_SOFT_DELETED)


async def assert_not_soft_deleted_async(model: Model) -> None:
    """Asynchronously assert that a soft-deletable row remains active.

    Args:
        model: Instance mapped with the :class:`SoftDeletes` mixin.

    Raises:
        TypeError: If the model does not support soft deletion.
    """
    query = _soft_delete_query(model)
    if not await query.without_trashed().exists_async():
        raise AssertionError(_NOT_SOFT_DELETED)


def _model_query[ModelT: Model](model: ModelT) -> ModelQueryBuilder[ModelT]:
    """Build a primary-key query that includes soft-deleted rows.

    Args:
        model: Mapped instance with a single-column primary key.

    Returns:
        A typed query limited to the model's primary-key identity.
    """
    model_type = type(model)
    key_name = model_type.primary_key_name()
    identifier = getattr(model, key_name)
    return model_type.query().with_trashed().where(key_name, identifier)


def _soft_delete_query(model: Model) -> ModelQueryBuilder[Model]:
    """Require a soft-delete model and return its identity query.

    Args:
        model: Mapped model checked through a database query.

    Returns:
        Its typed identity query with deleted rows included.

    Raises:
        TypeError: If the model does not support soft deletion.
    """
    if not isinstance(model, SoftDeletes):
        raise TypeError(_SOFT_DELETE_TYPE_ERROR)
    return _model_query(model)


__all__ = [
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
]
