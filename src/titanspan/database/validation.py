"""Provide asynchronous database-backed Validation rules.

Validation owns issue aggregation while Database executes each rule as a
bound SQLAlchemy Core existence query.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import cast

from titanspan.contracts.validation import AsyncValidationRule
from titanspan.database.model import Model
from titanspan.facades.database import DB

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)
_MAX_IDENTIFIER_PARTS = 3
_INVALID_IDENTIFIER_ERROR = "Database validation identifiers must be safe."
_INVALID_FIELD_ERROR = "Database validation requires a field path."

type ModelTable = str | type[Model]
type _Filter = tuple[str, object]


def unique_rule(
    table: ModelTable,
    column: str,
    *,
    field: str,
    connection: str | None = None,
    constraints: Mapping[str, object] | None = None,
    ignore: tuple[str, object] | None = None,
) -> AsyncValidationRule:
    """Build an async rule that rejects an existing database value.

    ``ignore`` must contain a trusted column and value, such as the model
    being updated. Query values are always passed through SQLAlchemy binding.

    Args:
        table: Trusted table name or mapped model type.
        column: Trusted column containing the value being checked.
        field: Dotted path on the schema-validated input object.
        connection: Optional connection override for a table or model.
        constraints: Additional trusted column values in the query.
        ignore: Trusted column and identifier excluded from the query.

    Returns:
        A Validation rule that requires explicit asynchronous execution.

    Raises:
        ValueError: If a field path or SQL identifier is unsafe.
    """
    _validate_field(field)
    table_name, selected_connection = _resolve_table(table, connection)
    filters = _validate_filters(constraints)
    _validate_identifier(column)
    if ignore is not None:
        _validate_identifier(ignore[0])

    async def check(value: object) -> bool:
        """Check that no visible row contains the supplied field value.

        Args:
            value: Schema-validated object passed by Validation.

        Returns:
            Whether the value is unique within the selected constraints.
        """
        field_value = _field_value(value, field)
        if field_value is None:
            return True
        query = DB.table(
            table_name,
            connection=selected_connection,
        ).where(column, field_value)
        for filter_name, filter_value in filters:
            query.where(filter_name, filter_value)
        if ignore is not None:
            ignore_column, ignore_value = ignore
            query.where(ignore_column, "!=", ignore_value)
        return await query.doesnt_exist_async()

    return AsyncValidationRule(
        field=field,
        check=check,
        message="The value has already been taken.",
        code="unique",
    )


def exists_rule(
    table: ModelTable,
    column: str,
    *,
    field: str,
    message: str = "The selected value is invalid.",
    connection: str | None = None,
    constraints: Mapping[str, object] | None = None,
) -> AsyncValidationRule:
    """Build an async rule that requires a matching database record.

    Args:
        table: Trusted table name or mapped model type.
        column: Trusted column compared with the validated field value.
        field: Dotted path on the schema-validated input object.
        message: Safe message returned by Validation when no row exists.
        connection: Optional connection override for a table or model.
        constraints: Additional trusted column values in the query.

    Returns:
        A Validation rule that requires explicit asynchronous execution.

    Raises:
        ValueError: If a field path or SQL identifier is unsafe.
    """
    _validate_field(field)
    table_name, selected_connection = _resolve_table(table, connection)
    filters = _validate_filters(constraints)
    _validate_identifier(column)

    async def check(value: object) -> bool:
        """Check that one visible row contains the supplied field value.

        Args:
            value: Schema-validated object passed by Validation.

        Returns:
            Whether a matching record satisfies all extra constraints.
        """
        field_value = _field_value(value, field)
        if field_value is None:
            return True
        query = DB.table(
            table_name,
            connection=selected_connection,
        ).where(column, field_value)
        for filter_name, filter_value in filters:
            query.where(filter_name, filter_value)
        return await query.exists_async()

    return AsyncValidationRule(
        field=field,
        check=check,
        message=message,
        code="exists",
    )


def _resolve_table(
    table: ModelTable,
    connection: str | None,
) -> tuple[str, str | None]:
    """Resolve a safe table name and optional model connection.

    Args:
        table: Trusted table name or mapped model type.
        connection: Explicit connection override, when present.

    Returns:
        Table identity and the selected connection name.
    """
    if isinstance(table, str):
        table_name = table
        selected_connection = connection
    else:
        table_name = table.table or table.__tablename__
        selected_connection = (
            table.connection if connection is None else connection
        )
    _validate_identifier(table_name)
    return table_name, selected_connection


def _validate_filters(
    constraints: Mapping[str, object] | None,
) -> tuple[_Filter, ...]:
    """Snapshot and validate additional fixed query constraints.

    Args:
        constraints: Optional mapping from trusted columns to bound values.

    Returns:
        Validated constraints in their original iteration order.
    """
    if constraints is None:
        return ()
    filters = tuple(constraints.items())
    for column, _ in filters:
        _validate_identifier(column)
    return filters


def _validate_identifier(value: str) -> None:
    """Reject empty or executable SQL identifier fragments.

    Args:
        value: Trusted table or column identifier supplied by application code.

    Raises:
        ValueError: If any dotted identifier segment is invalid.
    """
    parts = value.split(".")
    if not 1 <= len(parts) <= _MAX_IDENTIFIER_PARTS or any(
        _IDENTIFIER.fullmatch(part) is None for part in parts
    ):
        raise ValueError(_INVALID_IDENTIFIER_ERROR)


def _validate_field(field: str) -> None:
    """Require a non-empty dotted value path.

    Args:
        field: Field path selected by trusted application code.

    Raises:
        ValueError: If the path is empty or contains an empty segment.
    """
    if not field or any(not segment for segment in field.split(".")):
        raise ValueError(_INVALID_FIELD_ERROR)


def _field_value(value: object, field: str) -> object | None:
    """Read a dotted field from a mapping or validated model.

    Args:
        value: Schema-validated mapping or object.
        field: Dotted field path declared by the rule.

    Returns:
        The field value, or ``None`` when an optional field is absent.
    """
    result: object | None = value
    for segment in field.split("."):
        if isinstance(result, Mapping):
            result = cast("Mapping[object, object]", result).get(segment)
        elif result is not None:
            result = cast("object | None", getattr(result, segment, None))
    return result


__all__ = ["exists_rule", "unique_rule"]
