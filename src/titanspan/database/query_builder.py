"""Build safe fluent queries with SQLAlchemy Core expressions.

Mutable builders are intended to belong to one request or operation. Clone a
builder before branching it into independent query variations.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Callable,
    Generator,
    Iterator,
    Mapping,
    Sequence,
)
from contextlib import asynccontextmanager, contextmanager
from copy import copy
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from itertools import islice
from typing import TYPE_CHECKING, Literal, Protocol, cast
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    Integer,
    Numeric,
    String,
    Time,
    and_,
    column,
    delete,
    extract,
    func,
    insert,
    literal,
    literal_column,
    not_,
    or_,
    select,
    table,
    text,
    true,
    tuple_,
    update,
)
from sqlalchemy import (
    cast as sql_cast,
)
from sqlalchemy import (
    exists as sql_exists,
)
from sqlalchemy import (
    union as sql_union,
)
from sqlalchemy import (
    union_all as sql_union_all,
)
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.mysql import match as mysql_match
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import array as postgresql_array
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import ColumnElement, TextClause
from sqlalchemy.sql.selectable import TableClause

from titanspan.contracts.database import (
    DatabaseJoinClause,
    DatabaseQueryBuilder,
)
from titanspan.database.exceptions import (
    DatabaseQueryError,
    DatabaseTransactionError,
    ModelNotFoundError,
    MultipleModelsFoundError,
)
from titanspan.database.pagination import (
    CursorPaginator,
    LengthAwarePaginator,
    Paginator,
)

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager, AbstractContextManager
    from typing import NoReturn

    from sqlalchemy.sql import Executable
    from sqlalchemy.sql.schema import Table
    from sqlalchemy.sql.selectable import (
        CTE,
        FromClause,
        Select,
        SelectBase,
    )

    from titanspan.contracts.database.connection import (
        DatabaseConnectionService,
    )

type _Condition = ColumnElement[bool]
type _Projection = ColumnElement[object] | TextClause
type _Boolean = Literal["and", "or"]
type _LockMode = Literal["update", "share"]
type _JoinType = Literal["inner", "left", "right", "full"]
type _ColumnResolver = Callable[[str], ColumnElement[object]]
type _ColumnComparator = Callable[
    [ColumnElement[object], str, object],
    _Condition,
]
type _CursorDirection = Literal["after", "before"]
type _CursorOrder = tuple[str, bool]
type _CursorScalar = (
    bool | int | float | str | Decimal | datetime | date | time | UUID
)


class _ColumnCollectionSource(Protocol):
    """Narrow SQLAlchemy FROM objects to their public column collection.
    """  # fmt: skip

    @property
    def c(self) -> Mapping[str, ColumnElement[object]]:
        """Expose named columns for safe identifier resolution.

        Returns:
            The selectable's named SQLAlchemy column expressions.
        """
        ...


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_JSON_PATH_PART = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MISSING = object()
_SCHEMA_PART_COUNT = 2
_SCHEMA_COLUMN_PART_COUNT = 3
_COMPARISON_OPERATORS = {
    "=": operators.eq,
    "==": operators.eq,
    "!=": operators.ne,
    "<>": operators.ne,
    ">": operators.gt,
    ">=": operators.ge,
    "<": operators.lt,
    "<=": operators.le,
    "like": operators.like_op,
    "not like": operators.not_like_op,
    "ilike": operators.ilike_op,
}
_FIRST_PAGE = 1
_MINIMUM_PAGE_SIZE = 1
_NO_ROWS_FOUND = "The database query returned no rows."
_MULTIPLE_ROWS_FOUND = "The database query returned multiple rows."
_MAXIMUM_CURSOR_LENGTH = 4096
_MAXIMUM_JSON_PATH_LENGTH = 512
_REDACTED_QUERY_BINDING = "<redacted>"
_CURSOR_PAIR_LENGTH = 2
_EXPLAIN_PREFIXES = {
    "mariadb": "EXPLAIN",
    "mysql": "EXPLAIN",
    "postgresql": "EXPLAIN",
    "sqlite": "EXPLAIN QUERY PLAN",
}


class QueryBuilder(DatabaseQueryBuilder):
    """Compose retrieval and mutation statements for one table.

    SQL identifiers are validated before SQLAlchemy constructs expression
    objects. User values are always bound by SQLAlchemy and the dialect.
    """

    def __init__(
        self,
        connection: DatabaseConnectionService,
        table_name: str,
        *,
        table_clause: TableClause | Table | None = None,
        entity: type[object] | None = None,
    ) -> None:
        """Create a mutable query tied to one application connection.

        Args:
            connection: Application-owned logical connection and executor.
            table_name: Safe table name, optionally qualified by a schema.
            table_clause: Existing SQLAlchemy table used by mapped models.
            entity: Optional ORM entity selected by an Active Record query.
        """
        self._connection = connection
        self._connection_name = connection.name
        if table_clause is None:
            self._table, table_key = _make_table(table_name)
            self._allow_unknown_columns = True
        else:
            self._table = cast("TableClause", table_clause)
            table_key = table_name
            self._allow_unknown_columns = False
        self._entity = entity
        self._tables: dict[str, FromClause] = {table_key: self._table}
        self._ctes: list[CTE] = []
        self._from: FromClause = self._table
        self._default_source: FromClause = self._table
        self._is_derived = False
        self._selection: list[_Projection] | None = None
        self._where_groups: list[list[_Condition]] = []
        self._scope_condition: _Condition | None = None
        self._group_columns: list[ColumnElement[object]] = []
        self._having_groups: list[list[_Condition]] = []
        self._orders: list[ColumnElement[object]] = []
        self._order_specs: list[_CursorOrder] = []
        self._limit: int | None = None
        self._offset: int | None = None
        self._is_distinct = False
        self._lock_mode: _LockMode | None = None
        self._lock_nowait = False
        self._lock_skip_locked = False

    def select(self, *columns: str) -> QueryBuilder:
        """Replace the selected projection.

        Args:
            columns: Safe names or qualified column references.

        Returns:
            This builder for further query composition.
        """
        self._selection = (
            [self._projection(column_name) for column_name in columns]
            if columns
            else None
        )
        return self

    def add_select(self, *columns: str) -> QueryBuilder:
        """Append expressions to the current projection.

        Args:
            columns: Safe names or qualified column references.

        Returns:
            This builder for further query composition.
        """
        if not columns:
            return self
        if self._selection is None:
            self._selection = []
        self._selection.extend(
            self._projection(column_name) for column_name in columns
        )
        return self

    def select_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
    ) -> QueryBuilder:
        """Replace the projection with one scalar query expression.

        Args:
            query: Query that returns exactly one column and at most one row.
            alias: Safe output column name for the scalar result.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the alias is not a single identifier.
        """
        self._selection = [self._subquery_projection(query, alias)]
        return self

    def add_select_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
    ) -> QueryBuilder:
        """Append a scalar query expression to the current projection.

        Args:
            query: Query that returns exactly one column and at most one row.
            alias: Safe output column name for the scalar result.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the alias is not a single identifier.
        """
        if self._selection is None:
            self._selection = []
        self._selection.append(self._subquery_projection(query, alias))
        return self

    def select_raw(
        self,
        expression: str,
        bindings: Mapping[str, object] | None = None,
    ) -> QueryBuilder:
        """Append a trusted SQL projection with separately bound values.

        Args:
            expression: Application-authored SQL expression and aliases.
            bindings: Values bound to named placeholders in the expression.

        Returns:
            This builder for further query composition.
        """
        projection = _raw_clause(expression, bindings)
        if self._selection is None:
            self._selection = []
        self._selection.append(projection)
        return self

    def with_cte(
        self,
        name: str,
        query: DatabaseQueryBuilder,
        *,
        recursive: bool = False,
    ) -> QueryBuilder:
        """Attach a SQLAlchemy common table expression to this query.

        Args:
            name: Safe CTE identifier referenced by the query's FROM clause.
            query: Fluent query whose statement defines the CTE.
            recursive: Whether SQLAlchemy should render a recursive CTE.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the CTE name is unsafe or duplicated.
        """
        parts = _identifier_parts(name)
        if len(parts) != 1 or any(cte.name == name for cte in self._ctes):
            msg = "A common table expression requires a unique safe name."
            raise DatabaseQueryError(msg)
        self._ctes.append(
            query.to_statement().cte(name, recursive=recursive),
        )
        return self

    def distinct(self, enabled: bool = True) -> QueryBuilder:
        """Select distinct rows when enabled.

        Args:
            enabled: Whether duplicate result rows should be removed.

        Returns:
            This builder for further query composition.
        """
        self._is_distinct = enabled
        return self

    def where(
        self,
        column_name: str | Mapping[str, object] | Callable[..., object],
        operator_or_value: object = _MISSING,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Add equality, comparison, mapping, or grouped conditions.

        Two arguments mean equality. Three arguments select a comparison
        operator from a fixed allowlist. Callable conditions are parenthesized.

        Args:
            column_name: Column, equality mapping, or grouping callback.
            operator_or_value: Equality value or comparison operator.
            value: Value used with the explicit comparison operator.

        Returns:
            This builder for further query composition.
        """
        if isinstance(column_name, Mapping):
            if operator_or_value is not _MISSING or value is not _MISSING:
                _raise_invalid_condition()
            conditions_mapping = cast("Mapping[str, object]", column_name)
            conditions = [
                self._compare(self._column(key), "=", item)
                for key, item in conditions_mapping.items()
            ]
            if not conditions:
                return self
            return self._add_where(_conjunction(conditions), "and")

        if callable(column_name):
            if operator_or_value is not _MISSING or value is not _MISSING:
                _raise_invalid_condition()
            nested = self.clone()
            nested._where_groups = []  # noqa: SLF001  # Clear clone filters.
            column_name(nested)
            condition = nested._where_expression()  # noqa: SLF001  # Group.
            return (
                self if condition is None else self._add_where(condition, "and")
            )

        if value is _MISSING:
            if operator_or_value is _MISSING:
                _raise_invalid_condition()
            operator = "="
            right = operator_or_value
        else:
            if not isinstance(operator_or_value, str):
                _raise_invalid_condition()
            operator = operator_or_value
            right = value
        condition = self._compare(
            self._column(column_name),
            operator,
            right,
        )
        return self._add_where(condition, "and")

    def where_predicate(
        self,
        predicate: _Condition,
        *,
        boolean: _Boolean = "and",
    ) -> QueryBuilder:
        """Add a prebuilt SQLAlchemy condition to the fluent expression.

        Args:
            predicate: SQLAlchemy boolean expression authored by trusted code.
            boolean: Whether to join this condition with AND or OR.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(predicate, boolean)

    def where_raw(
        self,
        expression: str,
        bindings: Mapping[str, object] | None = None,
    ) -> QueryBuilder:
        """Add an application-authored SQL predicate with bound values.

        Args:
            expression: Trusted SQL predicate containing named placeholders.
            bindings: Values bound independently by SQLAlchemy.

        Returns:
            This builder for further query composition.
        """
        predicate = cast("_Condition", _raw_clause(expression, bindings))
        return self.where_predicate(predicate)

    def or_where_raw(
        self,
        expression: str,
        bindings: Mapping[str, object] | None = None,
    ) -> QueryBuilder:
        """Add a raw predicate joined by SQL OR with bound values.

        Args:
            expression: Trusted SQL predicate containing named placeholders.
            bindings: Values bound independently by SQLAlchemy.

        Returns:
            This builder for further query composition.
        """
        predicate = cast("_Condition", _raw_clause(expression, bindings))
        return self.where_predicate(predicate, boolean="or")

    def where_exists(
        self,
        subquery: (
            str | TextClause | DatabaseQueryBuilder | Select[tuple[object, ...]]
        ),
    ) -> QueryBuilder:
        """Require an EXISTS subquery authored through a trusted SQL API.

        Args:
            subquery: Trusted SQL text, a Core Select, or another builder.

        Returns:
            This builder for further query composition.
        """
        return self.where_predicate(
            _exists_predicate(subquery),
        )

    def where_not_exists(
        self,
        subquery: (
            str | TextClause | DatabaseQueryBuilder | Select[tuple[object, ...]]
        ),
    ) -> QueryBuilder:
        """Require an EXISTS subquery to return no rows.

        Args:
            subquery: Trusted SQL text, a Core Select, or another builder.

        Returns:
            This builder for further query composition.
        """
        return self.where_predicate(
            not_(_exists_predicate(subquery)),
        )

    def or_where_exists(
        self,
        subquery: (
            str | TextClause | DatabaseQueryBuilder | Select[tuple[object, ...]]
        ),
    ) -> QueryBuilder:
        """Add an OR condition for a subquery that returns any rows.

        Args:
            subquery: Trusted SQL text, a Core Select, or another builder.

        Returns:
            This builder for further query composition.
        """
        return self.where_predicate(
            _exists_predicate(subquery),
            boolean="or",
        )

    def or_where_not_exists(
        self,
        subquery: (
            str | TextClause | DatabaseQueryBuilder | Select[tuple[object, ...]]
        ),
    ) -> QueryBuilder:
        """Add an OR condition for a subquery that returns no rows.

        Args:
            subquery: Trusted SQL text, a Core Select, or another builder.

        Returns:
            This builder for further query composition.
        """
        return self.where_predicate(
            not_(_exists_predicate(subquery)),
            boolean="or",
        )

    def or_where(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Add a comparison joined by SQL OR.

        Args:
            column_name: Safe column name or qualified name.
            operator_or_value: Equality value or explicit operator.
            value: Value used with an explicit comparison operator.

        Returns:
            This builder for further query composition.
        """
        operator, right = _comparison_arguments(operator_or_value, value)
        return self._add_where(
            self._compare(self._column(column_name), operator, right),
            "or",
        )

    def where_not(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Add a negated comparison condition.

        Args:
            column_name: Safe column name or qualified name.
            operator_or_value: Equality value or explicit operator.
            value: Value used with an explicit comparison operator.

        Returns:
            This builder for further query composition.
        """
        operator, right = _comparison_arguments(operator_or_value, value)
        condition = self._compare(
            self._column(column_name),
            operator,
            right,
        )
        return self._add_where(not_(condition), "and")

    def or_where_not(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Add a negated comparison joined by SQL OR.

        Args:
            column_name: Safe column name or qualified name.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        operator, right = _comparison_arguments(operator_or_value, value)
        condition = self._compare(
            self._column(column_name),
            operator,
            right,
        )
        return self._add_where(not_(condition), "or")

    def where_null(self, column_name: str) -> QueryBuilder:
        """Require a column to contain SQL NULL.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(self._column(column_name).is_(None), "and")

    def where_not_null(self, column_name: str) -> QueryBuilder:
        """Require a column not to contain SQL NULL.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(self._column(column_name).is_not(None), "and")

    def where_date(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Compare the date portion of a date or timestamp column.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or supported comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        expression = self._date_expression(column_name)
        return self._where_temporal(
            expression,
            operator_or_value,
            value,
            "and",
        )

    def or_where_date(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Compare a date portion as an SQL OR predicate.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or supported comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        return self._where_temporal(
            self._date_expression(column_name),
            operator_or_value,
            value,
            "or",
        )

    def where_time(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Compare the time portion using a supported dialect expression.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or supported comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        source = self._column(column_name)
        if self._connection.dialect_name == "postgresql":
            expression = cast(
                "ColumnElement[object]",
                sql_cast(source, Time()),
            )
        elif self._connection.dialect_name in {"sqlite", "mysql"}:
            expression = cast("ColumnElement[object]", func.time(source))
        else:
            msg = "Time-part predicates are unsupported by this dialect."
            raise DatabaseQueryError(msg)
        return self._where_temporal(
            expression,
            operator_or_value,
            value,
            "and",
        )

    def or_where_time(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Compare a time portion as an SQL OR predicate.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or supported comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        source = self._column(column_name)
        if self._connection.dialect_name == "postgresql":
            expression = cast(
                "ColumnElement[object]",
                sql_cast(source, Time()),
            )
        elif self._connection.dialect_name in {"sqlite", "mysql"}:
            expression = cast("ColumnElement[object]", func.time(source))
        else:
            msg = "Time-part predicates are unsupported by this dialect."
            raise DatabaseQueryError(msg)
        return self._where_temporal(
            expression,
            operator_or_value,
            value,
            "or",
        )

    def where_year(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Compare the year extracted from a date or timestamp.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or supported comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        return self._where_temporal(
            cast(
                "ColumnElement[object]",
                extract("year", self._column(column_name)),
            ),
            operator_or_value,
            value,
            "and",
        )

    def where_month(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Compare the month extracted from a date or timestamp.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or supported comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        return self._where_temporal(
            cast(
                "ColumnElement[object]",
                extract("month", self._column(column_name)),
            ),
            operator_or_value,
            value,
            "and",
        )

    def where_day(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Compare the day of month extracted from a date or timestamp.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or supported comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        return self._where_temporal(
            cast(
                "ColumnElement[object]",
                extract("day", self._column(column_name)),
            ),
            operator_or_value,
            value,
            "and",
        )

    def where_in(
        self,
        column_name: str,
        values: Sequence[object] | DatabaseQueryBuilder,
    ) -> QueryBuilder:
        """Match a column against a bound sequence of values.

        Args:
            column_name: Safe column name or qualified name.
            values: Bound values or a single-column subquery.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(
            self._column(column_name).in_(self._membership_values(values)),
            "and",
        )

    def or_where_in(
        self,
        column_name: str,
        values: Sequence[object] | DatabaseQueryBuilder,
    ) -> QueryBuilder:
        """Match a bound sequence or subquery through SQL OR.

        Args:
            column_name: Safe column name or qualified name.
            values: Bound values or a single-column subquery.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(
            self._column(column_name).in_(self._membership_values(values)),
            "or",
        )

    def or_where_null(self, column_name: str) -> QueryBuilder:
        """Match SQL NULL and join the condition with SQL OR.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(self._column(column_name).is_(None), "or")

    def or_where_not_null(self, column_name: str) -> QueryBuilder:
        """Match non-NULL values and join the condition with SQL OR.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(self._column(column_name).is_not(None), "or")

    def where_not_in(
        self,
        column_name: str,
        values: Sequence[object] | DatabaseQueryBuilder,
    ) -> QueryBuilder:
        """Exclude values using a bound sequence.

        Args:
            column_name: Safe column name or qualified name.
            values: Bound values or a single-column subquery.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(
            self._column(column_name).not_in(
                self._membership_values(values),
            ),
            "and",
        )

    def or_where_not_in(
        self,
        column_name: str,
        values: Sequence[object] | DatabaseQueryBuilder,
    ) -> QueryBuilder:
        """Exclude values through SQL OR using values or a subquery.

        Args:
            column_name: Safe column name or qualified name.
            values: Bound values or a single-column subquery.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(
            self._column(column_name).not_in(
                self._membership_values(values),
            ),
            "or",
        )

    def where_between(
        self,
        column_name: str,
        lower: object,
        upper: object,
    ) -> QueryBuilder:
        """Match a value within an inclusive lower and upper bound.

        Args:
            column_name: Safe column name or qualified name.
            lower: Inclusive lower bound.
            upper: Inclusive upper bound.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(
            self._column(column_name).between(lower, upper),
            "and",
        )

    def where_not_between(
        self,
        column_name: str,
        lower: object,
        upper: object,
    ) -> QueryBuilder:
        """Exclude values within an inclusive range.

        Args:
            column_name: Safe column name or qualified name.
            lower: Inclusive lower bound.
            upper: Inclusive upper bound.

        Returns:
            This builder for further query composition.
        """
        condition = self._column(column_name).between(lower, upper)
        return self._add_where(not_(condition), "and")

    def or_where_between(
        self,
        column_name: str,
        lower: object,
        upper: object,
    ) -> QueryBuilder:
        """Match values inside a range and join the condition with OR.

        Args:
            column_name: Safe column name or qualified name.
            lower: Inclusive lower bound.
            upper: Inclusive upper bound.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(
            self._column(column_name).between(lower, upper),
            "or",
        )

    def or_where_not_between(
        self,
        column_name: str,
        lower: object,
        upper: object,
    ) -> QueryBuilder:
        """Exclude a range and join the negated condition with OR.

        Args:
            column_name: Safe column name or qualified name.
            lower: Inclusive lower bound.
            upper: Inclusive upper bound.

        Returns:
            This builder for further query composition.
        """
        condition = self._column(column_name).between(lower, upper)
        return self._add_where(not_(condition), "or")

    def where_like(self, column_name: str, pattern: str) -> QueryBuilder:
        """Match a text column against a bound SQL LIKE pattern.

        Args:
            column_name: Safe text column name or qualified name.
            pattern: Bound SQL LIKE pattern.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(
            cast("_Condition", self._column(column_name).like(pattern)),
            "and",
        )

    def where_not_like(
        self,
        column_name: str,
        pattern: str,
    ) -> QueryBuilder:
        """Exclude values matching a bound SQL LIKE pattern.

        Args:
            column_name: Safe text column name or qualified name.
            pattern: Bound SQL LIKE pattern.

        Returns:
            This builder for further query composition.
        """
        condition = self._column(column_name).like(pattern)
        return self._add_where(not_(condition), "and")

    def or_where_like(self, column_name: str, pattern: str) -> QueryBuilder:
        """Match a LIKE pattern and join the condition with SQL OR.

        Args:
            column_name: Safe text column name or qualified name.
            pattern: Bound SQL LIKE pattern.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(
            cast("_Condition", self._column(column_name).like(pattern)),
            "or",
        )

    def or_where_not_like(
        self,
        column_name: str,
        pattern: str,
    ) -> QueryBuilder:
        """Exclude a LIKE pattern and join the condition with SQL OR.

        Args:
            column_name: Safe text column name or qualified name.
            pattern: Bound SQL LIKE pattern.

        Returns:
            This builder for further query composition.
        """
        condition = self._column(column_name).like(pattern)
        return self._add_where(not_(condition), "or")

    def where_full_text(
        self,
        columns: str | Sequence[str],
        value: str,
    ) -> QueryBuilder:
        """Match full-text content using a supported dialect expression.

        Args:
            columns: One or more safe text column names.
            value: Bound full-text search expression.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect or column selection is invalid.
        """
        return self._add_where(self._full_text_condition(columns, value), "and")

    def or_where_full_text(
        self,
        columns: str | Sequence[str],
        value: str,
    ) -> QueryBuilder:
        """Match full-text content and join the condition with SQL OR.

        Args:
            columns: One or more safe text column names.
            value: Bound full-text search expression.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect or column selection is invalid.
        """
        return self._add_where(self._full_text_condition(columns, value), "or")

    def where_column(
        self,
        left: str,
        operator: str,
        right: str,
    ) -> QueryBuilder:
        """Compare two validated column references.

        Args:
            left: Safe left column name or qualified name.
            operator: Supported comparison operator.
            right: Safe right column name or qualified name.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(
            self._compare(
                self._column(left),
                operator,
                self._column(right),
            ),
            "and",
        )

    def where_row_values(
        self,
        columns: Sequence[str],
        operator: str,
        values: Sequence[object],
    ) -> QueryBuilder:
        """Compare corresponding columns and values as an SQL row tuple.

        Args:
            columns: Ordered, safe column references.
            operator: Supported comparison operator.
            values: Bound values in the same order as the columns.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect or tuple shape is unsupported.
        """
        return self._where_row_values(columns, operator, values, "and")

    def or_where_row_values(
        self,
        columns: Sequence[str],
        operator: str,
        values: Sequence[object],
    ) -> QueryBuilder:
        """Compare row tuples and join the condition with SQL OR.

        Args:
            columns: Ordered, safe column references.
            operator: Supported comparison operator.
            values: Bound values in the same order as the columns.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect or tuple shape is unsupported.
        """
        return self._where_row_values(columns, operator, values, "or")

    def where_json_value(
        self,
        column_name: str,
        path: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Compare one scalar value at a validated JSON object path.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object keys using identifier characters.
            operator_or_value: Equality value or supported comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        return self._where_json_value(
            column_name,
            path,
            operator_or_value,
            value,
            "and",
        )

    def or_where_json_value(
        self,
        column_name: str,
        path: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Compare one JSON scalar value as an SQL OR predicate.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object keys using identifier characters.
            operator_or_value: Equality value or supported comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        return self._where_json_value(
            column_name,
            path,
            operator_or_value,
            value,
            "or",
        )

    def where_json_contains(
        self,
        column_name: str,
        path: str,
        value: object,
    ) -> QueryBuilder:
        """Require a JSON value to contain a candidate at a nested path.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object path using identifier characters.
            value: JSON-compatible containment candidate.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect lacks containment support.
        """
        return self._where_json_contains(
            column_name,
            path,
            value,
            "and",
            negated=False,
        )

    def or_where_json_contains(
        self,
        column_name: str,
        path: str,
        value: object,
    ) -> QueryBuilder:
        """Join a nested JSON containment predicate using SQL OR.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object path using identifier characters.
            value: JSON-compatible containment candidate.

        Returns:
            This builder for further query composition.
        """
        return self._where_json_contains(
            column_name,
            path,
            value,
            "or",
            negated=False,
        )

    def where_json_doesnt_contain(
        self,
        column_name: str,
        path: str,
        value: object,
    ) -> QueryBuilder:
        """Exclude JSON values containing a candidate at a nested path.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object path using identifier characters.
            value: JSON-compatible containment candidate.

        Returns:
            This builder for further query composition.
        """
        return self._where_json_contains(
            column_name,
            path,
            value,
            "and",
            negated=True,
        )

    def or_where_json_doesnt_contain(
        self,
        column_name: str,
        path: str,
        value: object,
    ) -> QueryBuilder:
        """Join a negated JSON containment predicate using SQL OR.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object path using identifier characters.
            value: JSON-compatible containment candidate.

        Returns:
            This builder for further query composition.
        """
        return self._where_json_contains(
            column_name,
            path,
            value,
            "or",
            negated=True,
        )

    def where_json_contains_key(
        self,
        column_name: str,
        path: str,
    ) -> QueryBuilder:
        """Require a nested JSON key to exist, including JSON null values.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object path using identifier characters.

        Returns:
            This builder for further query composition.
        """
        return self._where_json_contains_key(
            column_name,
            path,
            "and",
            negated=False,
        )

    def or_where_json_contains_key(
        self,
        column_name: str,
        path: str,
    ) -> QueryBuilder:
        """Join nested JSON key existence using SQL OR.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object path using identifier characters.

        Returns:
            This builder for further query composition.
        """
        return self._where_json_contains_key(
            column_name,
            path,
            "or",
            negated=False,
        )

    def where_json_doesnt_contain_key(
        self,
        column_name: str,
        path: str,
    ) -> QueryBuilder:
        """Require a nested JSON key not to exist.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object path using identifier characters.

        Returns:
            This builder for further query composition.
        """
        return self._where_json_contains_key(
            column_name,
            path,
            "and",
            negated=True,
        )

    def or_where_json_doesnt_contain_key(
        self,
        column_name: str,
        path: str,
    ) -> QueryBuilder:
        """Join absent nested JSON key checks using SQL OR.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object path using identifier characters.

        Returns:
            This builder for further query composition.
        """
        return self._where_json_contains_key(
            column_name,
            path,
            "or",
            negated=True,
        )

    def where_json_length(
        self,
        column_name: str,
        path: str,
        operator_or_length: object,
        length: object = _MISSING,
    ) -> QueryBuilder:
        """Compare the array length at a validated JSON object path.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object path using identifier characters.
            operator_or_length: Expected length or comparison operator.
            length: Expected length when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        return self._where_json_length(
            column_name,
            path,
            operator_or_length,
            length,
            "and",
        )

    def or_where_json_length(
        self,
        column_name: str,
        path: str,
        operator_or_length: object,
        length: object = _MISSING,
    ) -> QueryBuilder:
        """Join a JSON array length comparison using SQL OR.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object path using identifier characters.
            operator_or_length: Expected length or comparison operator.
            length: Expected length when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        return self._where_json_length(
            column_name,
            path,
            operator_or_length,
            length,
            "or",
        )

    def join(
        self,
        table_name: str,
        left: str,
        operator_or_right: str,
        right: str | object = _MISSING,
    ) -> QueryBuilder:
        """Join another table with a column comparison.

        Three column arguments imply equality. Four arguments specify a
        comparison operator, which is validated before SQLAlchemy constructs
        the expression.

        Args:
            table_name: Safe joined table identifier.
            left: Safe left column name or qualified name.
            operator_or_right: Right column name or comparison operator.
            right: Right column name when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        return self._join(
            table_name,
            left,
            operator_or_right,
            right,
            join_type="inner",
        )

    def left_join(
        self,
        table_name: str,
        left: str,
        operator_or_right: str,
        right: str | object = _MISSING,
    ) -> QueryBuilder:
        """Left-join another table with a column comparison.

        Args:
            table_name: Safe joined table identifier.
            left: Safe left column name or qualified name.
            operator_or_right: Right column name or comparison operator.
            right: Right column name when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        return self._join(
            table_name,
            left,
            operator_or_right,
            right,
            join_type="left",
        )

    def join_with(
        self,
        table_name: str,
        callback: Callable[[DatabaseJoinClause], object],
        *,
        join_type: _JoinType = "inner",
    ) -> QueryBuilder:
        """Join a table with validated column and value ON conditions.

        Args:
            table_name: Safe joined table identifier.
            callback: Synchronous function that defines join conditions.
            join_type: Inner, left, right, or full join behavior.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the condition, join type, or dialect is
                unsupported.
        """
        if join_type not in {"inner", "left", "right", "full"}:
            msg = "The requested join type is unsupported."
            raise DatabaseQueryError(msg)
        dialect = self._connection.dialect_name
        if join_type == "right" and dialect not in {
            "mysql",
            "postgresql",
            "sqlite",
        }:
            msg = "Right outer joins are unsupported by this dialect."
            raise DatabaseQueryError(msg)
        if join_type == "full" and dialect not in {"postgresql", "sqlite"}:
            msg = "Full outer joins are unsupported by this dialect."
            raise DatabaseQueryError(msg)

        target = self._ensure_table(table_name)
        clause = _JoinClause(self._column, self._compare)
        callback(clause)
        condition = clause.expression()
        if join_type == "right":
            self._from = target.join(self._from, condition, isouter=True)
        elif join_type == "full":
            self._from = self._from.join(
                target,
                condition,
                isouter=True,
                full=True,
            )
        else:
            self._from = self._from.join(
                target,
                condition,
                isouter=join_type == "left",
            )
        return self

    def right_join(
        self,
        table_name: str,
        left: str,
        operator_or_right: str,
        right: str | object = _MISSING,
    ) -> QueryBuilder:
        """Right-join another table while preserving its unmatched rows.

        SQLAlchemy Core expresses a right join by reversing the FROM sides of
        a left outer join, so it does not depend on native right-join syntax.

        Args:
            table_name: Safe table identifier to retain on the right side.
            left: Safe left column reference.
            operator_or_right: Right column or comparison operator.
            right: Right column when an operator is supplied.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect does not support this join.
        """
        if self._connection.dialect_name not in {
            "mysql",
            "postgresql",
            "sqlite",
        }:
            msg = "Right outer joins are unsupported by this dialect."
            raise DatabaseQueryError(msg)
        return self._join(
            table_name,
            left,
            operator_or_right,
            right,
            join_type="right",
        )

    def full_outer_join(
        self,
        table_name: str,
        left: str,
        operator_or_right: str,
        right: str | object = _MISSING,
    ) -> QueryBuilder:
        """Join both sides while preserving unmatched rows from each table.

        PostgreSQL supports full outer joins. SQLite requires version 3.39 or
        later. MySQL and MariaDB do not provide this join form.

        Args:
            table_name: Safe table identifier joined to the current source.
            left: Safe left column reference.
            operator_or_right: Right column or comparison operator.
            right: Right column when an operator is supplied.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the configured dialect is unsupported.
        """
        if self._connection.dialect_name not in {"postgresql", "sqlite"}:
            msg = "Full outer joins are unsupported by this dialect."
            raise DatabaseQueryError(msg)
        return self._join(
            table_name,
            left,
            operator_or_right,
            right,
            join_type="full",
        )

    def join_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
        left: str,
        operator_or_right: str,
        right: str | object = _MISSING,
    ) -> QueryBuilder:
        """Join a fluent subquery using validated alias columns.

        Args:
            query: Query whose statement becomes a SQL subquery.
            alias: Safe unique name used to reference the subquery.
            left: Safe left column reference.
            operator_or_right: Right column or comparison operator.
            right: Right column when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        return self._join_sub(
            query,
            alias,
            left,
            operator_or_right,
            right,
            join_type="inner",
        )

    def left_join_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
        left: str,
        operator_or_right: str,
        right: str | object = _MISSING,
    ) -> QueryBuilder:
        """Left-join a fluent subquery using validated alias columns.

        Args:
            query: Query whose statement becomes a SQL subquery.
            alias: Safe unique name used to reference the subquery.
            left: Safe left column reference.
            operator_or_right: Right column or comparison operator.
            right: Right column when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        return self._join_sub(
            query,
            alias,
            left,
            operator_or_right,
            right,
            join_type="left",
        )

    def right_join_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
        left: str,
        operator_or_right: str,
        right: str | object = _MISSING,
    ) -> QueryBuilder:
        """Right-join a fluent subquery using a safe unique alias.

        Args:
            query: Query whose statement becomes a SQL subquery.
            alias: Safe unique alias exposed to selected expressions.
            left: Safe left column reference.
            operator_or_right: Right column or comparison operator.
            right: Right column when an operator is supplied.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect or alias is unsupported.
        """
        if self._connection.dialect_name not in {
            "mysql",
            "postgresql",
            "sqlite",
        }:
            msg = "Right outer joins are unsupported by this dialect."
            raise DatabaseQueryError(msg)
        return self._join_sub(
            query,
            alias,
            left,
            operator_or_right,
            right,
            join_type="right",
        )

    def full_outer_join_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
        left: str,
        operator_or_right: str,
        right: str | object = _MISSING,
    ) -> QueryBuilder:
        """Full-outer-join a fluent subquery where supported.

        Args:
            query: Query whose statement becomes a SQL subquery.
            alias: Safe unique alias exposed to selected expressions.
            left: Safe left column reference.
            operator_or_right: Right column or comparison operator.
            right: Right column when an operator is supplied.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect or alias is unsupported.
        """
        if self._connection.dialect_name not in {"postgresql", "sqlite"}:
            msg = "Full outer joins are unsupported by this dialect."
            raise DatabaseQueryError(msg)
        return self._join_sub(
            query,
            alias,
            left,
            operator_or_right,
            right,
            join_type="full",
        )

    def cross_join_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
    ) -> QueryBuilder:
        """Cross-join a fluent subquery using a safe unique alias.

        Args:
            query: Query whose statement becomes a SQL subquery.
            alias: Safe alias exposed to selected expressions.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the alias is invalid or already in use.
        """
        self._add_subquery(alias, query)
        self._from = self._from.join(self._tables[alias], true())
        return self

    def join_lateral(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
    ) -> QueryBuilder:
        """Inner-join a correlated subquery using PostgreSQL LATERAL.

        Args:
            query: Correlated builder whose statement becomes a lateral source.
            alias: Safe unique alias exposed to selected expressions.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect or alias is unsupported.
        """
        return self._join_lateral(query, alias, outer=False)

    def left_join_lateral(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
    ) -> QueryBuilder:
        """Left-join a correlated subquery using PostgreSQL LATERAL.

        Args:
            query: Correlated builder whose statement becomes a lateral source.
            alias: Safe unique alias exposed to selected expressions.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect or alias is unsupported.
        """
        return self._join_lateral(query, alias, outer=True)

    def _join_lateral(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
        *,
        outer: bool,
    ) -> QueryBuilder:
        """Attach one PostgreSQL lateral source with an always-true ON clause.

        Args:
            query: Correlated builder converted to a SQLAlchemy Lateral.
            alias: Safe unique alias for the result columns.
            outer: Whether unmatched outer rows remain visible.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect or alias is unsupported.
        """
        if self._connection.dialect_name != "postgresql":
            msg = "Lateral joins are supported only by PostgreSQL."
            raise DatabaseQueryError(msg)
        parts = _identifier_parts(alias)
        if len(parts) != 1 or alias in self._tables:
            msg = "A lateral join requires a unique safe alias."
            raise DatabaseQueryError(msg)
        target = query.to_statement().lateral(alias)
        self._tables[alias] = target
        self._from = self._from.join(target, true(), isouter=outer)
        return self

    def cross_join(self, table_name: str) -> QueryBuilder:
        """Join every row from another table to every current row.

        SQLAlchemy renders the dialect-supported equivalent of a cross join.

        Args:
            table_name: Safe joined table identifier.

        Returns:
            This builder for further query composition.
        """
        target = self._ensure_table(table_name)
        self._from = self._from.join(target, true())
        return self

    def lock_for_update(
        self,
        *,
        nowait: bool = False,
        skip_locked: bool = False,
    ) -> QueryBuilder:
        """Request a dialect-supported exclusive row lock.

        Lock operations require an explicit active transaction and are
        supported only by the configured PostgreSQL and MySQL dialects.

        Args:
            nowait: Fail immediately if a selected row is already locked.
            skip_locked: Omit rows that another transaction has locked.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect or lock options are invalid.
            DatabaseTransactionError: If no transaction is active.
        """
        self._set_lock("update", nowait=nowait, skip_locked=skip_locked)
        return self

    def shared_lock(
        self,
        *,
        nowait: bool = False,
        skip_locked: bool = False,
    ) -> QueryBuilder:
        """Request a dialect-supported shared row lock.

        Args:
            nowait: Fail immediately if a selected row is already locked.
            skip_locked: Omit rows that another transaction has locked.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect or lock options are invalid.
            DatabaseTransactionError: If no transaction is active.
        """
        self._set_lock("share", nowait=nowait, skip_locked=skip_locked)
        return self

    def _set_lock(
        self,
        mode: _LockMode,
        *,
        nowait: bool,
        skip_locked: bool,
    ) -> None:
        """Validate and store one dialect-supported row-lock request.

        Args:
            mode: Exclusive update lock or shared read lock.
            nowait: Whether to fail instead of waiting for a lock.
            skip_locked: Whether to omit already locked rows.

        Raises:
            DatabaseQueryError: If the dialect or options are unsupported.
            DatabaseTransactionError: If the connection has no active scope.
        """
        if self._connection.dialect_name not in {"postgresql", "mysql"}:
            msg = "Pessimistic row locks are unsupported by this dialect."
            raise DatabaseQueryError(msg)
        if nowait and skip_locked:
            msg = "Choose either nowait or skip_locked for a row lock."
            raise DatabaseQueryError(msg)
        if self._connection.transaction_level < 1:
            msg = "Pessimistic row locks require an active transaction."
            raise DatabaseTransactionError(msg)
        self._lock_mode = mode
        self._lock_nowait = nowait
        self._lock_skip_locked = skip_locked

    def order_by(
        self,
        column_name: str,
        *,
        descending: bool = False,
    ) -> QueryBuilder:
        """Append a validated column ordering.

        Args:
            column_name: Safe column name or qualified name.
            descending: Whether to order from high values to low values.

        Returns:
            This builder for further query composition.
        """
        expression = self._column(column_name)
        self._orders.append(
            expression.desc() if descending else expression.asc()
        )
        self._order_specs.append((column_name, descending))
        return self

    def latest(self, column_name: str = "created_at") -> QueryBuilder:
        """Order a timestamp column from newest to oldest.

        Args:
            column_name: Timestamp column or qualified reference.

        Returns:
            This builder for further query composition.
        """
        return self.order_by(column_name, descending=True)

    def oldest(self, column_name: str = "created_at") -> QueryBuilder:
        """Order a timestamp column from oldest to newest.

        Args:
            column_name: Timestamp column or qualified reference.

        Returns:
            This builder for further query composition.
        """
        return self.order_by(column_name)

    def reorder(self, column_name: str | None = None) -> QueryBuilder:
        """Clear existing ordering and optionally set one new order.

        Args:
            column_name: Optional safe column to order ascending.

        Returns:
            This builder for further query composition.
        """
        self._orders.clear()
        self._order_specs.clear()
        if column_name is not None:
            self.order_by(column_name)
        return self

    def in_random_order(self) -> QueryBuilder:
        """Append backend-native random ordering to the query.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect has no supported random
                ordering expression.
        """
        dialect = self._connection.dialect_name
        if dialect == "mysql":
            expression = func.rand()
        elif dialect in {"sqlite", "postgresql"}:
            expression = func.random()
        else:
            msg = "Random ordering is unsupported by this dialect."
            raise DatabaseQueryError(msg)
        self._orders.append(cast("ColumnElement[object]", expression))
        return self

    def group_by(self, *columns: str) -> QueryBuilder:
        """Group rows by validated columns.

        Args:
            columns: Safe column names or qualified names.

        Returns:
            This builder for further query composition.
        """
        self._group_columns.extend(self._column(name) for name in columns)
        return self

    def having(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Filter grouped results with a bound comparison.

        Args:
            column_name: Safe selected or grouped column.
            operator_or_value: Equality value or explicit comparison operator.
            value: Value used with an explicit comparison operator.

        Returns:
            This builder for further query composition.
        """
        operator, right = _comparison_arguments(operator_or_value, value)
        condition = self._compare(
            self._column(column_name),
            operator,
            right,
        )
        self._add_group(self._having_groups, condition, "and")
        return self

    def or_having(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> QueryBuilder:
        """Filter grouped rows with a comparison joined by SQL OR.

        Args:
            column_name: Safe selected or grouped column.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        operator, right = _comparison_arguments(operator_or_value, value)
        condition = self._compare(
            self._column(column_name),
            operator,
            right,
        )
        self._add_group(self._having_groups, condition, "or")
        return self

    def limit(self, count: int | None) -> QueryBuilder:
        """Set a non-negative result limit.

        Args:
            count: Maximum result count or ``None`` to clear the limit.

        Returns:
            This builder for further query composition.

        Raises:
            ValueError: If the limit is negative or is not an integer.
        """
        if count is not None and (type(count) is not int or count < 0):
            msg = "The query limit must be a non-negative integer."
            raise ValueError(msg)
        self._limit = count
        return self

    def offset(self, count: int) -> QueryBuilder:
        """Set a non-negative number of rows to skip.

        Args:
            count: Number of rows to skip.

        Returns:
            This builder for further query composition.

        Raises:
            ValueError: If the offset is negative or is not an integer.
        """
        if type(count) is not int or count < 0:
            msg = "The query offset must be a non-negative integer."
            raise ValueError(msg)
        self._offset = count
        return self

    def take(self, count: int | None) -> QueryBuilder:
        """Set the maximum number of rows returned by this query.

        Args:
            count: Maximum result count or ``None`` to clear the limit.

        Returns:
            This builder for further query composition.
        """
        return self.limit(count)

    def skip(self, count: int) -> QueryBuilder:
        """Set the number of leading rows omitted from results.

        Args:
            count: Number of rows to skip.

        Returns:
            This builder for further query composition.
        """
        return self.offset(count)

    def paginate(
        self,
        per_page: int = 15,
        *,
        page: int = _FIRST_PAGE,
    ) -> LengthAwarePaginator[Mapping[str, object]]:
        """Retrieve a page and the total number of matching rows.

        Args:
            per_page: Positive maximum page size.
            page: Positive one-based page number.

        Returns:
            Page items and total-count navigation metadata.
        """
        _validate_page(per_page, page)
        total = self.count()
        rows = (
            self.clone()
            .limit(per_page)
            .offset(
                (page - _FIRST_PAGE) * per_page,
            )
            .get()
        )
        return LengthAwarePaginator(
            tuple(rows),
            total,
            per_page,
            page,
        )

    async def paginate_async(
        self,
        per_page: int = 15,
        *,
        page: int = _FIRST_PAGE,
    ) -> LengthAwarePaginator[Mapping[str, object]]:
        """Asynchronously retrieve a page and total row count.

        Args:
            per_page: Positive maximum page size.
            page: Positive one-based page number.

        Returns:
            Page items and total-count navigation metadata.
        """
        _validate_page(per_page, page)
        total = await self.count_async()
        rows = (
            await self.clone()
            .limit(per_page)
            .offset(
                (page - _FIRST_PAGE) * per_page,
            )
            .get_async()
        )
        return LengthAwarePaginator(
            tuple(rows),
            total,
            per_page,
            page,
        )

    def simple_paginate(
        self,
        per_page: int = 15,
        *,
        page: int = _FIRST_PAGE,
    ) -> Paginator[Mapping[str, object]]:
        """Retrieve a page without a total-count query.

        Args:
            per_page: Positive maximum page size.
            page: Positive one-based page number.

        Returns:
            Page items and a bounded next-page indicator.
        """
        _validate_page(per_page, page)
        rows = (
            self.clone()
            .limit(per_page + 1)
            .offset(
                (page - _FIRST_PAGE) * per_page,
            )
            .get()
        )
        has_more = len(rows) > per_page
        return Paginator(
            tuple(rows[:per_page]),
            per_page,
            page,
            has_more,
        )

    async def simple_paginate_async(
        self,
        per_page: int = 15,
        *,
        page: int = _FIRST_PAGE,
    ) -> Paginator[Mapping[str, object]]:
        """Asynchronously retrieve a count-free page with one-row lookahead.

        Args:
            per_page: Positive maximum page size.
            page: Positive one-based page number.

        Returns:
            Page items and a bounded next-page indicator.
        """
        _validate_page(per_page, page)
        rows = (
            await self.clone()
            .limit(per_page + 1)
            .offset(
                (page - _FIRST_PAGE) * per_page,
            )
            .get_async()
        )
        has_more = len(rows) > per_page
        return Paginator(
            tuple(rows[:per_page]),
            per_page,
            page,
            has_more,
        )

    def cursor_paginate(
        self,
        per_page: int = 15,
        *,
        cursor: str | None = None,
        key_column: str = "id",
    ) -> CursorPaginator[Mapping[str, object]]:
        """Retrieve one page using ordered keyset values.

        Every order is stabilized by ``key_column``. Cursor values are
        validated data and are never interpreted as SQL or Python code.

        Args:
            per_page: Positive maximum number of page rows.
            cursor: Optional opaque cursor returned by a prior result.
            key_column: Unique, non-null tie-breaker column.

        Returns:
            Page rows and previous or next cursor tokens.
        """
        return self._cursor_paginate(
            per_page,
            cursor=cursor,
            key_column=key_column,
        )

    async def cursor_paginate_async(
        self,
        per_page: int = 15,
        *,
        cursor: str | None = None,
        key_column: str = "id",
    ) -> CursorPaginator[Mapping[str, object]]:
        """Asynchronously retrieve one page using ordered keyset values.

        Args:
            per_page: Positive maximum number of page rows.
            cursor: Optional opaque cursor returned by a prior result.
            key_column: Unique, non-null tie-breaker column.

        Returns:
            Page rows and previous or next cursor tokens.
        """
        return await self._cursor_paginate_async(
            per_page,
            cursor=cursor,
            key_column=key_column,
        )

    def _cursor_paginate(
        self,
        per_page: int,
        *,
        cursor: str | None,
        key_column: str,
    ) -> CursorPaginator[Mapping[str, object]]:
        """Execute one bounded cursor page synchronously.

        Args:
            per_page: Positive maximum number of returned rows.
            cursor: Optional validated cursor token.
            key_column: Unique, non-null tie-breaker column.

        Returns:
            Cursor page containing detached result mappings.
        """
        statement, specs, aliases, direction = self._cursor_statement(
            per_page,
            cursor,
            key_column,
        )
        result = self._connection.execute_statement(statement)
        return self._cursor_page(
            result.rows,
            per_page,
            cursor,
            direction,
            specs,
            aliases,
        )

    async def _cursor_paginate_async(
        self,
        per_page: int,
        *,
        cursor: str | None,
        key_column: str,
    ) -> CursorPaginator[Mapping[str, object]]:
        """Execute one bounded cursor page asynchronously.

        Args:
            per_page: Positive maximum number of returned rows.
            cursor: Optional validated cursor token.
            key_column: Unique, non-null tie-breaker column.

        Returns:
            Cursor page containing detached result mappings.
        """
        statement, specs, aliases, direction = self._cursor_statement(
            per_page,
            cursor,
            key_column,
        )
        result = await self._connection.execute_statement_async(statement)
        return self._cursor_page(
            result.rows,
            per_page,
            cursor,
            direction,
            specs,
            aliases,
        )

    def _cursor_statement(
        self,
        per_page: int,
        cursor: str | None,
        key_column: str,
    ) -> tuple[
        Select[tuple[object, ...]],
        tuple[_CursorOrder, ...],
        tuple[str, ...],
        _CursorDirection | None,
    ]:
        """Build a bounded lexicographic page query.

        Args:
            per_page: Positive maximum number of returned rows.
            cursor: Optional validated cursor token.
            key_column: Unique, non-null tie-breaker column.

        Returns:
            Statement, stable order specification, hidden aliases, and cursor
            direction.

        Raises:
            DatabaseQueryError: If the query cannot be paginated safely.
        """
        _validate_page(per_page, _FIRST_PAGE)
        self._ensure_lock_transaction()
        if self._group_columns or self._having_groups or self._is_distinct:
            msg = (
                "Cursor pagination requires a non-grouped, non-distinct query."
            )
            raise DatabaseQueryError(msg)
        if len(self._orders) != len(self._order_specs):
            msg = "Cursor pagination requires stable ordering by columns."
            raise DatabaseQueryError(msg)
        specs = list(self._order_specs)
        if key_column not in {name for name, _ in specs}:
            specs.append((key_column, False))
        if not specs or len({name for name, _ in specs}) != len(specs):
            msg = "Cursor pagination requires unique order columns."
            raise DatabaseQueryError(msg)
        for name, _ in specs:
            self._column(name)
        stable_specs = tuple(specs)
        direction: _CursorDirection | None = None
        cursor_values: tuple[object, ...] = ()
        if cursor is not None:
            direction, cursor_values = _decode_cursor(cursor, stable_specs)

        query = self.clone()
        query._orders.clear()  # noqa: SLF001  # Use stable cursor ordering.
        query._order_specs.clear()  # noqa: SLF001  # Use stable cursor order.
        if direction is not None:
            predicate = query._cursor_predicate(  # noqa: SLF001
                stable_specs,
                cursor_values,
                after=direction == "after",
            )
            scope = query._scope_condition  # noqa: SLF001
            query.set_scope_condition(
                predicate if scope is None else and_(scope, predicate),
            )
        reverse = direction == "before"
        for name, descending in stable_specs:
            query.order_by(name, descending=descending != reverse)
        query.limit(per_page + 1).offset(0)
        statement = query.to_statement()
        aliases: list[str] = []
        for name, _ in stable_specs:
            alias = _unique_chunk_key(statement)
            statement = statement.add_columns(
                query._column(name).label(alias),  # noqa: SLF001
            )
            aliases.append(alias)
        return (
            cast("Select[tuple[object, ...]]", statement),
            stable_specs,
            tuple(aliases),
            direction,
        )

    def _cursor_predicate(
        self,
        specs: tuple[_CursorOrder, ...],
        values: tuple[object, ...],
        *,
        after: bool,
    ) -> _Condition:
        """Build a lexicographic keyset predicate from bound cursor values.

        Args:
            specs: Stable column names and their natural sort directions.
            values: Decoded data values corresponding to ``specs``.
            after: Whether to retrieve rows after the supplied position.

        Returns:
            An SQLAlchemy predicate with explicit lexicographic grouping.
        """
        alternatives: list[_Condition] = []
        equal_prefix: list[_Condition] = []
        for (name, descending), value in zip(specs, values, strict=True):
            if value is None:
                msg = "Cursor ordering values cannot be null."
                raise DatabaseQueryError(msg)
            operator = ">" if after != descending else "<"
            comparison = self._compare(self._column(name), operator, value)
            alternatives.append(
                and_(*equal_prefix, comparison) if equal_prefix else comparison,
            )
            equal_prefix.append(
                self._compare(self._column(name), "=", value),
            )
        return or_(*alternatives)

    def _cursor_page(
        self,
        rows: Sequence[Mapping[str, object]],
        per_page: int,
        cursor: str | None,
        direction: _CursorDirection | None,
        specs: tuple[_CursorOrder, ...],
        aliases: tuple[str, ...],
    ) -> CursorPaginator[Mapping[str, object]]:
        """Detach rows and construct cursor navigation for one page.

        Args:
            rows: Result rows with hidden keyset values.
            per_page: Positive maximum number of returned rows.
            cursor: Input cursor token, if supplied.
            direction: Input cursor direction.
            specs: Stable order columns and directions.
            aliases: Hidden order-value projection aliases.

        Returns:
            Cursor page with values restored to natural query ordering.
        """
        has_extra = len(rows) > per_page
        page_rows = list(rows[:per_page])
        if direction == "before":
            page_rows.reverse()
        visible_rows: list[Mapping[str, object]] = []
        values_per_row: list[tuple[_CursorScalar, ...]] = []
        for row in page_rows:
            values = dict(row)
            cursor_values: list[_CursorScalar] = []
            for alias in aliases:
                cursor_value = values.pop(alias, _MISSING)
                if cursor_value is _MISSING or cursor_value is None:
                    msg = (
                        "Cursor ordering values must be selected and non-null."
                    )
                    raise DatabaseQueryError(msg)
                cursor_values.append(_cursor_scalar(cursor_value))
            visible_rows.append(values)
            values_per_row.append(tuple(cursor_values))

        first_values = values_per_row[0] if values_per_row else None
        last_values = values_per_row[-1] if values_per_row else None
        if direction == "before":
            next_cursor = (
                _encode_cursor("after", specs, last_values)
                if cursor is not None and last_values is not None
                else None
            )
            previous_cursor = (
                _encode_cursor("before", specs, first_values)
                if has_extra and first_values is not None
                else None
            )
        else:
            next_cursor = (
                _encode_cursor("after", specs, last_values)
                if has_extra and last_values is not None
                else None
            )
            previous_cursor = (
                _encode_cursor("before", specs, first_values)
                if cursor is not None and first_values is not None
                else None
            )
        return CursorPaginator(
            tuple(visible_rows),
            per_page,
            next_cursor,
            previous_cursor,
            next_cursor is not None,
        )

    def when(
        self,
        condition: object,
        callback: Callable[[QueryBuilder], object],
        default: Callable[[QueryBuilder], object] | None = None,
    ) -> QueryBuilder:
        """Apply a callback conditionally to this builder.

        Args:
            condition: Value whose truthiness selects the callback.
            callback: Query transformation used for a truthy value.
            default: Optional transformation used for a falsey value.

        Returns:
            This builder for further query composition.
        """
        if condition:
            callback(self)
        elif default is not None:
            default(self)
        return self

    def unless(
        self,
        condition: object,
        callback: Callable[[QueryBuilder], object],
        default: Callable[[QueryBuilder], object] | None = None,
    ) -> QueryBuilder:
        """Apply a callback when a condition is false.

        Args:
            condition: Value whose falsey state selects the callback.
            callback: Query transformation used for a falsey value.
            default: Optional transformation used for a truthy value.

        Returns:
            This builder for further query composition.
        """
        if not condition:
            callback(self)
        elif default is not None:
            default(self)
        return self

    def clone(self) -> QueryBuilder:
        """Copy mutable query state for an independent query branch.

        Returns:
            A builder with separate selection, filters, ordering, and limits.
        """
        cloned = copy(self)
        cloned._tables = self._tables.copy()  # noqa: SLF001  # Copy state.
        cloned._ctes = self._ctes.copy()  # noqa: SLF001  # Copy state.
        cloned._selection = (  # noqa: SLF001  # Copy state.
            None if self._selection is None else self._selection.copy()
        )
        cloned._where_groups = [  # noqa: SLF001  # Copy state.
            conditions.copy() for conditions in self._where_groups
        ]
        cloned._scope_condition = self._scope_condition  # noqa: SLF001
        cloned._having_groups = [  # noqa: SLF001  # Copy state.
            conditions.copy() for conditions in self._having_groups
        ]
        cloned._group_columns = self._group_columns.copy()  # noqa: SLF001
        cloned._orders = self._orders.copy()  # noqa: SLF001
        cloned._order_specs = self._order_specs.copy()  # noqa: SLF001
        return cloned

    def subquery(self, table_name: str) -> QueryBuilder:
        """Start a query that can refer to this query's table expressions.

        SQLAlchemy correlates shared outer table expressions when the result
        is embedded through a scalar or EXISTS subquery.

        Args:
            table_name: Safe table name that becomes the subquery's FROM.

        Returns:
            A new builder sharing this query's known table references.

        Raises:
            DatabaseQueryError: If the subquery table repeats a visible name.
        """
        nested = QueryBuilder(self._connection, table_name)
        table_key = next(iter(nested._tables))
        if table_key in self._tables:
            msg = (
                "A correlated subquery must use a table name that is not "
                "already visible."
            )
            raise DatabaseQueryError(msg)
        nested._tables = {**self._tables, **nested._tables}
        return nested

    def union(self, query: DatabaseQueryBuilder) -> QueryBuilder:
        """Combine this query with another using duplicate-eliminating UNION.

        Existing clauses apply to their respective branches. Later clauses
        apply to the combined result through an outer SQLAlchemy query.

        Args:
            query: Query selecting the same number of compatible columns.

        Returns:
            This builder with the union result as its new source.
        """
        return self._union_query(query, all_rows=False)

    def union_all(self, query: DatabaseQueryBuilder) -> QueryBuilder:
        """Combine this query with another while retaining duplicate rows.

        Args:
            query: Query selecting the same number of compatible columns.

        Returns:
            This builder with the union-all result as its new source.
        """
        return self._union_query(query, all_rows=True)

    def _union_query(
        self,
        query: DatabaseQueryBuilder,
        *,
        all_rows: bool,
    ) -> QueryBuilder:
        """Replace this query source with a SQLAlchemy compound subquery.

        Args:
            query: Query selecting compatible union columns.
            all_rows: Whether to preserve duplicate result rows.

        Returns:
            This builder with reset outer query state.

        Raises:
            DatabaseQueryError: If an ORM entity projection is present.
        """
        if self._entity is not None:
            msg = "Query Builder unions do not accept ORM entity queries."
            raise DatabaseQueryError(msg)
        if self._lock_mode is not None:
            msg = "Pessimistic locks cannot be combined with query unions."
            raise DatabaseQueryError(msg)
        left = self.to_statement()
        right = query.to_statement()
        combined = (
            sql_union_all(left, right) if all_rows else sql_union(left, right)
        ).subquery("__titanspan_union")
        self._from = combined
        self._default_source = combined
        self._tables = {"__titanspan_union": combined}
        self._ctes = []
        self._selection = None
        self._where_groups = []
        self._scope_condition = None
        self._group_columns = []
        self._having_groups = []
        self._orders = []
        self._order_specs = []
        self._limit = None
        self._offset = None
        self._is_distinct = False
        self._lock_mode = None
        self._lock_nowait = False
        self._lock_skip_locked = False
        self._allow_unknown_columns = False
        self._is_derived = True
        return self

    def to_statement(
        self,
        *,
        entity: type[object] | None = None,
    ) -> Select[tuple[object, ...]]:
        """Build the equivalent SQLAlchemy Select expression.

        Returns:
            A composable SQLAlchemy statement using this builder's state.
        """
        selected_entity = self._entity if entity is None else entity
        if selected_entity is None:
            columns = self._selection
            if columns is None:
                columns = [cast("ColumnElement[object]", literal_column("*"))]
            statement = select(*columns).select_from(self._from)
        else:
            statement = select(
                cast("ColumnElement[object]", selected_entity),
            ).select_from(self._from)
        where = self._where_expression()
        if where is not None:
            statement = statement.where(where)
        if self._group_columns:
            statement = statement.group_by(*self._group_columns)
        having = self._where_expression(self._having_groups)
        if having is not None:
            statement = statement.having(having)
        if self._orders:
            statement = statement.order_by(*self._orders)
        if self._limit is not None:
            statement = statement.limit(self._limit)
        if self._offset is not None:
            statement = statement.offset(self._offset)
        if self._is_distinct:
            statement = statement.distinct()
        statement = self._attach_ctes(
            cast("Select[tuple[object, ...]]", statement),
        )
        return self._apply_lock(statement)

    def to_sql(self) -> str:
        """Compile the current query without interpolating bound values.

        Returns:
            SQL text with placeholders from the configured dialect.
        """
        sql, _ = self._connection.compile_statement(self.to_statement())
        return sql

    def get_bindings(
        self,
        *,
        redact: bool = True,
    ) -> Mapping[str, object]:
        """Inspect compiled values with redaction enabled by default.

        Args:
            redact: Replace every parameter value unless trusted diagnostic
                code explicitly disables redaction.

        Returns:
            Compiled parameter values keyed by SQLAlchemy's bind names.
        """
        _, bindings = self._connection.compile_statement(self.to_statement())
        if redact:
            return dict.fromkeys(bindings, _REDACTED_QUERY_BINDING)
        return dict(bindings)

    def explain(self) -> list[Mapping[str, object]]:
        """Return this query's plan without executing the selected statement.

        Returns:
            Database-specific plan rows.

        Raises:
            DatabaseQueryError: If the dialect lacks a supported EXPLAIN form.
        """
        statement, bindings = self._explain_statement()
        result = self._connection.execute_statement(statement, bindings)
        return list(result.rows)

    async def explain_async(self) -> list[Mapping[str, object]]:
        """Asynchronously inspect the plan without executing the query.

        Returns:
            Database-specific plan rows.

        Raises:
            DatabaseQueryError: If the dialect lacks a supported EXPLAIN form.
        """
        statement, bindings = self._explain_statement()
        result = await self._connection.execute_statement_async(
            statement,
            bindings,
        )
        return list(result.rows)

    def _explain_statement(
        self,
    ) -> tuple[TextClause, Mapping[str, object]]:
        """Wrap the compiled fluent query in a supported EXPLAIN prefix.

        Returns:
            Text statement and separately bound query values.

        Raises:
            DatabaseQueryError: If the dialect lacks a supported EXPLAIN form.
        """
        prefix = _EXPLAIN_PREFIXES.get(self._connection.dialect_name)
        if prefix is None:
            msg = "The selected database dialect does not support EXPLAIN."
            raise DatabaseQueryError(msg)
        sql, bindings = self._connection.compile_statement(
            self.to_statement(),
            named_parameters=True,
        )
        # TextClause treats PostgreSQL's ``::`` casts as escaped colons. Escape
        # them explicitly so the preceding named bind remains recognized.
        escaped_sql = sql.replace("::", r"\:\:")
        return text(f"{prefix} {escaped_sql}"), bindings

    def _apply_lock(
        self,
        statement: Select[tuple[object, ...]],
    ) -> Select[tuple[object, ...]]:
        """Apply an already validated row-lock mode to a SELECT expression.

        Args:
            statement: SQLAlchemy SELECT expression.

        Returns:
            The statement with the requested SQLAlchemy lock option.
        """
        if self._lock_mode is None:
            return statement
        return statement.with_for_update(
            read=self._lock_mode == "share",
            nowait=self._lock_nowait,
            skip_locked=self._lock_skip_locked,
        )

    def _ensure_lock_transaction(self) -> None:
        """Reject locked execution after its explicit transaction has ended.

        Raises:
            DatabaseTransactionError: If the current scope does not own the
                transaction required by a configured row lock.
        """
        if (
            self._lock_mode is not None
            and self._connection.transaction_level < 1
        ):
            msg = "Pessimistic row locks require an active transaction."
            raise DatabaseTransactionError(msg)

    def _reject_lock_for_aggregate(self) -> None:
        """Reject lock modifiers on scalar operations that return no rows.

        Raises:
            DatabaseQueryError: If a row lock was applied to this builder.
        """
        if self._lock_mode is not None:
            msg = "Pessimistic row locks require row retrieval operations."
            raise DatabaseQueryError(msg)

    def _attach_ctes(
        self,
        statement: Select[tuple[object, ...]],
    ) -> Select[tuple[object, ...]]:
        """Attach configured CTEs through SQLAlchemy's Select API.

        Args:
            statement: Fully composed base SELECT statement.

        Returns:
            The original or CTE-extended statement.
        """
        if not self._ctes:
            return statement
        return statement.add_cte(*self._ctes)

    def get(self) -> list[Mapping[str, object]]:
        """Execute the query synchronously and detach its mapping rows.

        Returns:
            Rows detached from the SQLAlchemy result and session.
        """
        self._ensure_lock_transaction()
        return list(
            self._connection.execute_statement(
                self.to_statement(),
            ).rows
        )

    async def get_async(self) -> list[Mapping[str, object]]:
        """Execute the query asynchronously and detach its rows.

        Returns:
            Rows detached from the SQLAlchemy result and session.
        """
        self._ensure_lock_transaction()
        result = await self._connection.execute_statement_async(
            self.to_statement(),
        )
        return list(result.rows)

    def cursor(
        self,
        *,
        batch_size: int = 1000,
    ) -> AbstractContextManager[Iterator[Mapping[str, object]]]:
        """Open a bounded stream whose resources live through context exit.

        Args:
            batch_size: Positive maximum batch size used by SQLAlchemy.

        Returns:
            A context manager yielding detached mapping rows.
        """
        _validate_batch_size(batch_size)
        return self._stream_rows(batch_size)

    def cursor_async(
        self,
        *,
        batch_size: int = 1000,
    ) -> AbstractAsyncContextManager[AsyncIterator[Mapping[str, object]]]:
        """Open a bounded async stream owned by this context manager.

        Args:
            batch_size: Positive maximum batch size used by SQLAlchemy.

        Returns:
            An async context manager yielding detached mapping rows.
        """
        _validate_batch_size(batch_size)
        return self._stream_rows_async(batch_size)

    @contextmanager
    def _stream_rows(
        self,
        batch_size: int,
    ) -> Generator[Iterator[Mapping[str, object]], None, None]:
        """Validate execution ownership when a cursor context is entered.

        Args:
            batch_size: Maximum number of rows buffered by SQLAlchemy.

        Yields:
            The live stream owned by the connection context.
        """
        self._ensure_lock_transaction()
        with self._connection.stream_statement(
            self.to_statement(),
            batch_size=batch_size,
        ) as rows:
            yield rows

    @asynccontextmanager
    async def _stream_rows_async(
        self,
        batch_size: int,
    ) -> AsyncGenerator[
        AsyncIterator[Mapping[str, object]],
        None,
    ]:
        """Validate execution ownership when an async cursor is entered.

        Args:
            batch_size: Maximum number of rows buffered by SQLAlchemy.

        Yields:
            The live async stream owned by the connection context.
        """
        self._ensure_lock_transaction()
        async with self._connection.stream_statement_async(
            self.to_statement(),
            batch_size=batch_size,
        ) as rows:
            yield rows

    @contextmanager
    def chunks(
        self,
        batch_size: int = 1000,
    ) -> Generator[Iterator[list[Mapping[str, object]]], None, None]:
        """Yield bounded row groups while holding a sync stream open.

        Args:
            batch_size: Positive number of rows yielded in each group.

        Yields:
            An iterator of at most ``batch_size`` detached rows per group.
        """
        _validate_batch_size(batch_size)
        with self.cursor(batch_size=batch_size) as rows:
            yield _chunk_rows(rows, batch_size)

    @asynccontextmanager
    async def chunks_async(
        self,
        batch_size: int = 1000,
    ) -> AsyncGenerator[
        AsyncIterator[list[Mapping[str, object]]],
        None,
    ]:
        """Yield bounded row groups while holding an async stream open.

        Args:
            batch_size: Positive number of rows yielded in each group.

        Yields:
            An async iterator of at most ``batch_size`` detached rows.
        """
        _validate_batch_size(batch_size)
        async with self.cursor_async(batch_size=batch_size) as rows:

            async def grouped() -> AsyncIterator[list[Mapping[str, object]]]:
                """Collect one bounded group at a time from the live cursor.

                Yields:
                    Groups no larger than the requested batch size.
                """
                group: list[Mapping[str, object]] = []
                async for row in rows:
                    group.append(row)
                    if len(group) == batch_size:
                        yield group
                        group = []
                if group:
                    yield group

            yield grouped()

    def chunks_by_id(
        self,
        batch_size: int = 1000,
        *,
        key_column: str = "id",
    ) -> Iterator[list[Mapping[str, object]]]:
        """Retrieve bounded keyset pages for mutation-safe processing.

        Each page owns and closes its operation session before it is yielded.
        The key column must be unique, non-null, and orderable.

        Args:
            batch_size: Maximum number of rows in each page.
            key_column: Unique key used for ascending keyset continuation.

        Yields:
            Detached rows in key order without exposing an internal key
            column added for the next-page boundary.
        """
        _validate_batch_size(batch_size)
        last_key: object = _MISSING
        first_page = True
        remaining = self._limit

        while remaining is None or remaining > 0:
            self._ensure_lock_transaction()
            page_size = (
                batch_size if remaining is None else min(batch_size, remaining)
            )
            offset = (self._offset or 0) if first_page else 0
            statement, key_alias = self._id_chunk_statement(
                key_column,
                last_key,
                page_size,
                offset,
            )
            result = self._connection.execute_statement(statement)
            chunk, last_key = _remove_chunk_key(result.rows, key_alias)
            if not chunk:
                return
            yield chunk
            first_page = False
            if remaining is not None:
                remaining -= len(chunk)
            if len(chunk) < page_size:
                return

    async def chunks_by_id_async(
        self,
        batch_size: int = 1000,
        *,
        key_column: str = "id",
    ) -> AsyncIterator[list[Mapping[str, object]]]:
        """Asynchronously retrieve mutation-safe keyset pages.

        Each page owns and closes its operation session before it is yielded.
        The key column must be unique, non-null, and orderable.

        Args:
            batch_size: Maximum number of rows in each page.
            key_column: Unique key used for ascending keyset continuation.

        Yields:
            Detached rows without exposing the internal continuation key.
        """
        _validate_batch_size(batch_size)
        last_key: object = _MISSING
        first_page = True
        remaining = self._limit

        while remaining is None or remaining > 0:
            self._ensure_lock_transaction()
            page_size = (
                batch_size if remaining is None else min(batch_size, remaining)
            )
            offset = (self._offset or 0) if first_page else 0
            statement, key_alias = self._id_chunk_statement(
                key_column,
                last_key,
                page_size,
                offset,
            )
            result = await self._connection.execute_statement_async(
                statement,
            )
            chunk, last_key = _remove_chunk_key(result.rows, key_alias)
            if not chunk:
                return
            yield chunk
            first_page = False
            if remaining is not None:
                remaining -= len(chunk)
            if len(chunk) < page_size:
                return

    def first(self) -> Mapping[str, object] | None:
        """Return the first row synchronously, if one exists.

        Returns:
            The first detached row or ``None``.
        """
        rows = self.clone().limit(1).get()
        return rows[0] if rows else None

    async def doesnt_exist_async(self) -> bool:
        """Return whether no row matches this query's filters.

        Returns:
            ``True`` when the query matches no rows.
        """
        return not await self.exists_async()

    def doesnt_exist(self) -> bool:
        """Return whether no row matches this query's filters.

        Returns:
            ``True`` when the query matches no rows.
        """
        return not self.exists()

    async def first_async(self) -> Mapping[str, object] | None:
        """Return the first row asynchronously, if one exists.

        Returns:
            The first detached row or ``None``.
        """
        rows = await self.clone().limit(1).get_async()
        return rows[0] if rows else None

    def first_or_fail(self) -> Mapping[str, object]:
        """Return the first matching row or raise a not-found error.

        Returns:
            The first detached row.

        Raises:
            ModelNotFoundError: If the query matched no rows.
        """
        row = self.first()
        if row is None:
            raise ModelNotFoundError(_NO_ROWS_FOUND)
        return row

    async def first_or_fail_async(self) -> Mapping[str, object]:
        """Asynchronously return the first row or raise a not-found error.

        Returns:
            The first detached row.

        Raises:
            ModelNotFoundError: If the query matched no rows.
        """
        row = await self.first_async()
        if row is None:
            raise ModelNotFoundError(_NO_ROWS_FOUND)
        return row

    def find(
        self,
        identifier: object,
        *,
        key_column: str = "id",
    ) -> Mapping[str, object] | None:
        """Find one row by a safe key column.

        Args:
            identifier: Bound key value to match.
            key_column: Validated key column name.

        Returns:
            The matching detached row or ``None``.
        """
        return self.clone().where(key_column, identifier).first()

    async def find_async(
        self,
        identifier: object,
        *,
        key_column: str = "id",
    ) -> Mapping[str, object] | None:
        """Asynchronously find one row by a safe key column.

        Args:
            identifier: Bound key value to match.
            key_column: Validated key column name.

        Returns:
            The matching detached row or ``None``.
        """
        return await self.clone().where(key_column, identifier).first_async()

    def find_many(
        self,
        identifiers: Sequence[object],
        *,
        key_column: str = "id",
    ) -> list[Mapping[str, object]]:
        """Find rows whose key is included in a bound sequence.

        Args:
            identifiers: Key values selected by trusted application code.
            key_column: Validated key column name.

        Returns:
            Matching detached rows in database result order.
        """
        return self.clone().where_in(key_column, identifiers).get()

    async def find_many_async(
        self,
        identifiers: Sequence[object],
        *,
        key_column: str = "id",
    ) -> list[Mapping[str, object]]:
        """Asynchronously find rows matching a bound key sequence.

        Args:
            identifiers: Key values selected by trusted application code.
            key_column: Validated key column name.

        Returns:
            Matching detached rows in database result order.
        """
        return await self.clone().where_in(key_column, identifiers).get_async()

    def sole(self) -> Mapping[str, object]:
        """Require exactly one row using a query capped at two results.

        Returns:
            The one matching detached row.

        Raises:
            ModelNotFoundError: If the query matched no row.
            MultipleModelsFoundError: If the query matched multiple rows.
        """
        return _sole_row(self.clone().limit(2).get())

    async def sole_async(self) -> Mapping[str, object]:
        """Asynchronously require exactly one matching row.

        Returns:
            The one matching detached row.

        Raises:
            ModelNotFoundError: If the query matched no row.
            MultipleModelsFoundError: If the query matched multiple rows.
        """
        rows = await self.clone().limit(2).get_async()
        return _sole_row(rows)

    def sole_value(self, column_name: str) -> object:
        """Return a selected value when exactly one row matches.

        Args:
            column_name: Safe selected column name.

        Returns:
            The value from the sole matching row.

        Raises:
            ModelNotFoundError: If the query matched no row.
            MultipleModelsFoundError: If the query matched multiple rows.
        """
        row = self.clone().select(f"{column_name} as __sole_value").sole()
        return row["__sole_value"]

    async def sole_value_async(self, column_name: str) -> object:
        """Asynchronously return a value when exactly one row matches.

        Args:
            column_name: Safe selected column name.

        Returns:
            The value from the sole matching row.

        Raises:
            ModelNotFoundError: If the query matched no row.
            MultipleModelsFoundError: If the query matched multiple rows.
        """
        row = (
            await self.clone()
            .select(
                f"{column_name} as __sole_value",
            )
            .sole_async()
        )
        return row["__sole_value"]

    def value(self, column_name: str) -> object | None:
        """Return one selected column from the first matching row.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            The selected value or ``None`` if no row matches.
        """
        row = self.clone().select(f"{column_name} as __value").first()
        return None if row is None else row["__value"]

    async def value_async(self, column_name: str) -> object | None:
        """Asynchronously return one column from the first matching row.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            The selected value or ``None`` if no row matches.
        """
        row = (
            await self.clone().select(f"{column_name} as __value").first_async()
        )
        return None if row is None else row["__value"]

    def pluck(
        self,
        column_name: str,
        key: str | None = None,
    ) -> list[object] | dict[object, object]:
        """Retrieve one column or map values by a second selected column.

        Args:
            column_name: Safe value column name or qualified name.
            key: Optional safe key column name or qualified name.

        Returns:
            Values in row order, or a mapping when ``key`` is supplied.
        """
        query = self.clone().select(f"{column_name} as __value")
        if key is None:
            rows = query.get()
            return [row["__value"] for row in rows]
        rows = query.add_select(f"{key} as __key").get()
        return {row["__key"]: row["__value"] for row in rows}

    async def pluck_async(
        self,
        column_name: str,
        key: str | None = None,
    ) -> list[object] | dict[object, object]:
        """Asynchronously retrieve values from one or two columns.

        Args:
            column_name: Safe value column name or qualified name.
            key: Optional safe key column name or qualified name.

        Returns:
            Values in row order, or a mapping when ``key`` is supplied.
        """
        query = self.clone().select(f"{column_name} as __value")
        if key is None:
            rows = await query.get_async()
            return [row["__value"] for row in rows]
        rows = await query.add_select(f"{key} as __key").get_async()
        return {row["__key"]: row["__value"] for row in rows}

    def count(self) -> int:
        """Count matching table rows without hydrating row data.

        Returns:
            The database count for the current filters.
        """
        self._reject_lock_for_aggregate()
        result = self._connection.execute_statement(
            self._count_statement(),
        )
        return _integer_count(_first_value(result.rows))

    async def count_async(self) -> int:
        """Count matching rows asynchronously without hydrating them.

        Returns:
            The database count for the current filters.
        """
        self._reject_lock_for_aggregate()
        result = await self._connection.execute_statement_async(
            self._count_statement(),
        )
        return _integer_count(_first_value(result.rows))

    def sum(self, column_name: str) -> object | None:
        """Sum one validated column in the database.

        Args:
            column_name: Safe numeric column name or qualified name.

        Returns:
            The database aggregate value or ``None``.
        """
        return self._aggregate(func.sum(self._column(column_name)))

    async def sum_async(self, column_name: str) -> object | None:
        """Sum one validated column asynchronously.

        Args:
            column_name: Safe numeric column name or qualified name.

        Returns:
            The database aggregate value or ``None``.
        """
        return await self._aggregate_async(func.sum(self._column(column_name)))

    def avg(self, column_name: str) -> object | None:
        """Average one validated numeric column in the database.

        Args:
            column_name: Safe numeric column name or qualified name.

        Returns:
            The database aggregate value or ``None``.
        """
        return self._aggregate(func.avg(self._column(column_name)))

    async def avg_async(self, column_name: str) -> object | None:
        """Asynchronously average one validated numeric column.

        Args:
            column_name: Safe numeric column name or qualified name.

        Returns:
            The database aggregate value or ``None``.
        """
        return await self._aggregate_async(func.avg(self._column(column_name)))

    def min(self, column_name: str) -> object | None:
        """Return the minimum value of one selected column.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            The database aggregate value or ``None``.
        """
        return self._aggregate(func.min(self._column(column_name)))

    async def min_async(self, column_name: str) -> object | None:
        """Asynchronously return the minimum selected value.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            The database aggregate value or ``None``.
        """
        return await self._aggregate_async(func.min(self._column(column_name)))

    def max(self, column_name: str) -> object | None:
        """Return the maximum value of one selected column.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            The database aggregate value or ``None``.
        """
        return self._aggregate(func.max(self._column(column_name)))

    async def max_async(self, column_name: str) -> object | None:
        """Asynchronously return the maximum selected value.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            The database aggregate value or ``None``.
        """
        return await self._aggregate_async(func.max(self._column(column_name)))

    def exists(self) -> bool:
        """Return whether any row matches this query's filters.

        Returns:
            ``True`` when the database finds at least one row.
        """
        return self.clone().limit(1).first() is not None

    async def exists_async(self) -> bool:
        """Check asynchronously whether any row matches the filters.

        Returns:
            ``True`` when the database finds at least one row.
        """
        return await self.clone().limit(1).first_async() is not None

    def insert(self, values: Mapping[str, object]) -> bool:
        """Insert one row using SQLAlchemy's bound Core values.

        Args:
            values: Column names and values for the inserted row.

        Returns:
            ``True`` after the statement executes successfully.
        """
        self._validate_value_columns(values)
        statement = insert(self._table).values(dict(values))
        self._connection.execute_statement(
            statement,
        )
        return True

    async def insert_async(self, values: Mapping[str, object]) -> bool:
        """Insert one row asynchronously with bound values.

        Args:
            values: Column names and values for the inserted row.

        Returns:
            ``True`` after the statement executes successfully.
        """
        self._validate_value_columns(values)
        statement = insert(self._table).values(dict(values))
        await self._connection.execute_statement_async(
            statement,
        )
        return True

    def insert_returning(
        self,
        values: Mapping[str, object],
        *columns: str,
    ) -> list[Mapping[str, object]]:
        """Insert one row and return selected database-produced columns.

        Args:
            values: Column values for the inserted row.
            columns: Safe columns returned by the database.

        Returns:
            Detached mappings returned by the database.

        Raises:
            DatabaseQueryError: If the dialect or requested columns are not
                supported.
        """
        self._ensure_returning_supported()
        self._validate_value_columns(values)
        statement = cast(
            "Executable",
            insert(self._table)
            .values(dict(values))
            .returning(*self._returning_columns(columns)),
        )
        return list(self._connection.execute_statement(statement).rows)

    async def insert_returning_async(
        self,
        values: Mapping[str, object],
        *columns: str,
    ) -> list[Mapping[str, object]]:
        """Asynchronously insert one row and return database-produced values.

        Args:
            values: Column values for the inserted row.
            columns: Safe columns returned by the database.

        Returns:
            Detached mappings returned by the database.

        Raises:
            DatabaseQueryError: If the dialect or requested columns are not
                supported.
        """
        self._ensure_returning_supported()
        self._validate_value_columns(values)
        statement = cast(
            "Executable",
            insert(self._table)
            .values(dict(values))
            .returning(*self._returning_columns(columns)),
        )
        result = await self._connection.execute_statement_async(statement)
        return list(result.rows)

    def update_returning(
        self,
        values: Mapping[str, object],
        *columns: str,
    ) -> list[Mapping[str, object]]:
        """Update matching rows and return selected changed values.

        Args:
            values: Bound replacement values.
            columns: Safe columns returned by the database.

        Returns:
            Detached mappings for rows returned by the backend.
        """
        statement = self._update_returning_statement(values, columns)
        return list(self._connection.execute_statement(statement).rows)

    async def update_returning_async(
        self,
        values: Mapping[str, object],
        *columns: str,
    ) -> list[Mapping[str, object]]:
        """Asynchronously update rows and return selected changed values.

        Args:
            values: Bound replacement values.
            columns: Safe columns returned by the database.

        Returns:
            Detached mappings for rows returned by the backend.
        """
        statement = self._update_returning_statement(values, columns)
        result = await self._connection.execute_statement_async(statement)
        return list(result.rows)

    def _update_returning_statement(
        self,
        values: Mapping[str, object],
        columns: Sequence[str],
    ) -> Executable:
        """Build a validated UPDATE RETURNING expression.

        Args:
            values: Bound replacement values.
            columns: Safe columns returned by the database.

        Returns:
            SQLAlchemy Update with explicit return projections.
        """
        self._ensure_returning_supported()
        self._validate_value_columns(values)
        statement = update(self._table).values(dict(values))
        condition = self._where_expression()
        if condition is not None:
            statement = statement.where(condition)
        return cast(
            "Executable",
            statement.returning(*self._returning_columns(columns)),
        )

    def delete_returning(
        self,
        *columns: str,
    ) -> list[Mapping[str, object]]:
        """Delete matching rows and return selected deleted values.

        Args:
            columns: Safe columns returned by the database.

        Returns:
            Detached mappings for rows returned by the backend.
        """
        statement = self._delete_returning_statement(columns)
        return list(self._connection.execute_statement(statement).rows)

    async def delete_returning_async(
        self,
        *columns: str,
    ) -> list[Mapping[str, object]]:
        """Asynchronously delete matching rows and return deleted values.

        Args:
            columns: Safe columns returned by the database.

        Returns:
            Detached mappings for rows returned by the backend.
        """
        statement = self._delete_returning_statement(columns)
        result = await self._connection.execute_statement_async(statement)
        return list(result.rows)

    def _delete_returning_statement(
        self,
        columns: Sequence[str],
    ) -> Executable:
        """Build a validated DELETE RETURNING expression.

        Args:
            columns: Safe columns returned by the database.

        Returns:
            SQLAlchemy Delete with explicit return projections.
        """
        self._ensure_returning_supported()
        self._validate_value_columns({})
        statement = delete(self._table)
        condition = self._where_expression()
        if condition is not None:
            statement = statement.where(condition)
        return statement.returning(*self._returning_columns(columns))

    def _returning_columns(
        self,
        columns: Sequence[str],
    ) -> tuple[ColumnElement[object], ...]:
        """Resolve one or more safe returning identifiers.

        Args:
            columns: Safe selected column references.

        Returns:
            SQLAlchemy column expressions in requested order.

        Raises:
            DatabaseQueryError: If no output columns were requested.
        """
        if not columns:
            msg = "A returning mutation requires at least one output column."
            raise DatabaseQueryError(msg)
        return tuple(self._column(name) for name in columns)

    def _ensure_returning_supported(self) -> None:
        """Reject RETURNING on dialects without verified native support.

        Raises:
            DatabaseQueryError: If the configured dialect is not verified.
        """
        if self._connection.dialect_name not in {"sqlite", "postgresql"}:
            msg = "Mutation returning is unsupported by this dialect."
            raise DatabaseQueryError(msg)

    def insert_get_id(
        self,
        values: Mapping[str, object],
        *,
        key_column: str = "id",
    ) -> object:
        """Insert one row and return its generated or supplied key.

        SQLite and PostgreSQL use SQLAlchemy's ``RETURNING`` support. Other
        dialects reject this operation until their key semantics are verified.

        Args:
            values: Column values for the inserted row.
            key_column: Safe key column returned by the database.

        Returns:
            The value returned for the inserted key column.

        Raises:
            DatabaseQueryError: If the dialect lacks RETURNING or no key is
                returned by the database.
        """
        statement = self._insert_returning_statement(values, key_column)
        result = self._connection.execute_statement(statement)
        return _inserted_id(result.rows)

    async def insert_get_id_async(
        self,
        values: Mapping[str, object],
        *,
        key_column: str = "id",
    ) -> object:
        """Asynchronously insert one row and return its database key.

        Args:
            values: Column values for the inserted row.
            key_column: Safe key column returned by the database.

        Returns:
            The value returned for the inserted key column.

        Raises:
            DatabaseQueryError: If the dialect lacks RETURNING or no key is
                returned by the database.
        """
        statement = self._insert_returning_statement(values, key_column)
        result = await self._connection.execute_statement_async(statement)
        return _inserted_id(result.rows)

    def insert_using(
        self,
        columns: Sequence[str],
        query: DatabaseQueryBuilder,
    ) -> int:
        """Insert a selected query projection into validated target columns.

        Args:
            columns: Safe target column names in projection order.
            query: Source query selecting the same number of expressions.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.

        Raises:
            DatabaseQueryError: If the target or source projection is invalid.
        """
        statement = self._insert_using_statement(columns, query)
        return self._connection.execute_statement(statement).rowcount

    async def insert_using_async(
        self,
        columns: Sequence[str],
        query: DatabaseQueryBuilder,
    ) -> int:
        """Asynchronously insert the result of a SQLAlchemy source query.

        Args:
            columns: Safe target column names in projection order.
            query: Source query selecting the same number of expressions.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.

        Raises:
            DatabaseQueryError: If the target or source projection is invalid.
        """
        statement = self._insert_using_statement(columns, query)
        result = await self._connection.execute_statement_async(statement)
        return result.rowcount

    def _insert_using_statement(
        self,
        columns: Sequence[str],
        query: DatabaseQueryBuilder,
    ) -> Executable:
        """Build a validated INSERT FROM SELECT through SQLAlchemy Core.

        Args:
            columns: Safe target column names in projection order.
            query: Source query selecting the same number of expressions.

        Returns:
            A SQLAlchemy Insert statement using the source Select expression.

        Raises:
            DatabaseQueryError: If names or projection cardinality are invalid.
        """
        target_columns = tuple(columns)
        if not target_columns:
            msg = "Insert-from-query requires at least one target column."
            raise DatabaseQueryError(msg)
        self._validate_value_columns(dict.fromkeys(target_columns))
        source = query.to_statement()
        if len(source.selected_columns) != len(target_columns):
            msg = "Insert target and source projections must have equal size."
            raise DatabaseQueryError(msg)
        return insert(self._table).from_select(target_columns, source)

    def _insert_returning_statement(
        self,
        values: Mapping[str, object],
        key_column: str,
    ) -> Executable:
        """Build a validated single-row insert with a returned key.

        Args:
            values: Column values for one inserted row.
            key_column: Validated key column name.

        Returns:
            A SQLAlchemy INSERT statement with a labeled RETURNING column.

        Raises:
            DatabaseQueryError: If input is empty or the dialect is unsupported.
        """
        if self._connection.dialect_name not in {"sqlite", "postgresql"}:
            msg = "Inserted-key retrieval is unsupported by this dialect."
            raise DatabaseQueryError(msg)
        if not values:
            msg = "Inserted-key retrieval requires at least one value."
            raise DatabaseQueryError(msg)
        self._validate_value_columns(values)
        return (
            insert(self._table)
            .values(dict(values))
            .returning(
                self._column(key_column).label("__inserted_id"),
            )
        )

    def insert_many(self, rows: Sequence[Mapping[str, object]]) -> int:
        """Insert multiple rows through one SQLAlchemy Core statement.

        Args:
            rows: Ordered mappings with compatible column keys.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
        if not rows:
            return 0
        for row in rows:
            self._validate_value_columns(row)
        result = self._connection.execute_statement(
            insert(self._table).values([dict(row) for row in rows]),
        )
        return result.rowcount

    async def insert_many_async(
        self,
        rows: Sequence[Mapping[str, object]],
    ) -> int:
        """Insert multiple rows asynchronously in one statement.

        Args:
            rows: Ordered mappings with compatible column keys.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
        if not rows:
            return 0
        for row in rows:
            self._validate_value_columns(row)
        result = await self._connection.execute_statement_async(
            insert(self._table).values([dict(row) for row in rows]),
        )
        return result.rowcount

    def insert_or_ignore(
        self,
        rows: Sequence[Mapping[str, object]],
    ) -> int:
        """Insert rows while ignoring supported unique-key conflicts.

        Args:
            rows: Row mappings with the same inserted columns.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.

        Raises:
            DatabaseQueryError: If the selected dialect lacks conflict support.
        """
        prepared = self._prepare_rows(rows)
        if not prepared:
            return 0
        statement = self._insert_or_ignore_statement(prepared)
        result = self._connection.execute_statement(statement)
        return result.rowcount

    async def insert_or_ignore_async(
        self,
        rows: Sequence[Mapping[str, object]],
    ) -> int:
        """Insert rows asynchronously while ignoring unique-key conflicts.

        Args:
            rows: Row mappings with the same inserted columns.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.

        Raises:
            DatabaseQueryError: If the selected dialect lacks conflict support.
        """
        prepared = self._prepare_rows(rows)
        if not prepared:
            return 0
        statement = self._insert_or_ignore_statement(prepared)
        result = await self._connection.execute_statement_async(statement)
        return result.rowcount

    def upsert(
        self,
        rows: Sequence[Mapping[str, object]],
        *,
        unique_by: Sequence[str],
        update: Sequence[str] | None = None,
    ) -> int:
        """Insert or update rows through native dialect conflict handling.

        Args:
            rows: Row mappings with the same inserted columns.
            unique_by: Columns matching a unique index or constraint.
            update: Inserted columns to update, defaulting to non-key columns.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.

        Raises:
            DatabaseQueryError: If the conflict target or dialect is invalid.
        """
        statement = self._upsert_statement(rows, unique_by, update)
        if statement is None:
            return 0
        result = self._connection.execute_statement(statement)
        return result.rowcount

    async def upsert_async(
        self,
        rows: Sequence[Mapping[str, object]],
        *,
        unique_by: Sequence[str],
        update: Sequence[str] | None = None,
    ) -> int:
        """Insert or update rows asynchronously through the native dialect.

        Args:
            rows: Row mappings with the same inserted columns.
            unique_by: Columns matching a unique index or constraint.
            update: Inserted columns to update, defaulting to non-key columns.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.

        Raises:
            DatabaseQueryError: If the conflict target or dialect is invalid.
        """
        statement = self._upsert_statement(rows, unique_by, update)
        if statement is None:
            return 0
        result = await self._connection.execute_statement_async(statement)
        return result.rowcount

    def update_or_insert(
        self,
        attributes: Mapping[str, object],
        values: Mapping[str, object],
    ) -> int:
        """Atomically insert or update using unique matching attributes.

        The keys in ``attributes`` must match a database unique constraint.
        Values cannot change those keys because one native upsert cannot match
        one key and insert a different value for it.

        Args:
            attributes: Values identifying the database unique constraint.
            values: Non-key values inserted or updated on conflict.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.

        Raises:
            DatabaseQueryError: If matching attributes are empty or changed.
        """
        row, unique_by, update_columns = _update_or_insert_values(
            attributes,
            values,
            self._connection.dialect_name,
        )
        return self.upsert(
            [row],
            unique_by=unique_by,
            update=update_columns,
        )

    async def update_or_insert_async(
        self,
        attributes: Mapping[str, object],
        values: Mapping[str, object],
    ) -> int:
        """Asynchronously atomically insert or update a unique-key row.

        Args:
            attributes: Values identifying the database unique constraint.
            values: Non-key values inserted or updated on conflict.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.

        Raises:
            DatabaseQueryError: If matching attributes are empty or changed.
        """
        row, unique_by, update_columns = _update_or_insert_values(
            attributes,
            values,
            self._connection.dialect_name,
        )
        return await self.upsert_async(
            [row],
            unique_by=unique_by,
            update=update_columns,
        )

    def _insert_or_ignore_statement(
        self,
        rows: Sequence[Mapping[str, object]],
    ) -> Executable:
        """Build one dialect-native insert that ignores unique conflicts.

        Args:
            rows: Validated, copied row mappings.

        Returns:
            A SQLAlchemy insert statement for the selected dialect.

        Raises:
            DatabaseQueryError: If the selected dialect lacks conflict support.
        """
        values = [dict(row) for row in rows]
        dialect = self._connection.dialect_name
        if dialect == "sqlite":
            statement = sqlite_insert(self._table).values(values)
            return statement.on_conflict_do_nothing()
        if dialect == "postgresql":
            return (
                postgresql_insert(self._table)
                .values(values)
                .on_conflict_do_nothing()
            )
        if dialect == "mysql":
            statement = mysql_insert(self._table).values(values)
            return statement.prefix_with("IGNORE")
        return _raise_unsupported_conflict_dialect(dialect)

    def _upsert_statement(
        self,
        rows: Sequence[Mapping[str, object]],
        unique_by: Sequence[str],
        update: Sequence[str] | None,
    ) -> Executable | None:
        """Build a dialect-native insert or update statement.

        Args:
            rows: Row mappings with identical inserted columns.
            unique_by: Validated conflict-target column names.
            update: Optional inserted columns updated on conflict.

        Returns:
            A statement, or ``None`` for an empty row sequence.

        Raises:
            DatabaseQueryError: If a key, update column, or dialect is invalid.
        """
        prepared = self._prepare_rows(rows)
        if not prepared:
            return None
        row_columns = tuple(prepared[0])
        conflict_columns = self._validate_conflict_columns(
            unique_by,
            row_columns,
        )
        update_columns = self._resolve_update_columns(
            row_columns,
            conflict_columns,
            update,
        )
        values = [dict(row) for row in prepared]
        dialect = self._connection.dialect_name
        if dialect == "sqlite":
            statement = sqlite_insert(self._table).values(values)
            index_elements = [self._table.c[name] for name in conflict_columns]
            if not update_columns:
                return statement.on_conflict_do_nothing(
                    index_elements=index_elements,
                )
            update_values = {
                name: statement.excluded[name] for name in update_columns
            }
            return statement.on_conflict_do_update(
                index_elements=index_elements,
                set_=update_values,
            )
        if dialect == "postgresql":
            statement = postgresql_insert(self._table).values(values)
            index_elements = [self._table.c[name] for name in conflict_columns]
            if not update_columns:
                return statement.on_conflict_do_nothing(
                    index_elements=index_elements,
                )
            update_values = {
                name: statement.excluded[name] for name in update_columns
            }
            return statement.on_conflict_do_update(
                index_elements=index_elements,
                set_=update_values,
            )
        if dialect == "mysql":
            if not update_columns:
                msg = "MySQL upsert requires at least one update column."
                raise DatabaseQueryError(msg)
            statement = mysql_insert(self._table).values(values)
            return statement.on_duplicate_key_update(
                {name: statement.inserted[name] for name in update_columns},
            )
        return _raise_unsupported_conflict_dialect(dialect)

    def _prepare_rows(
        self,
        rows: Sequence[Mapping[str, object]],
    ) -> tuple[Mapping[str, object], ...]:
        """Validate identifiers and matching row shapes before insertion.

        Args:
            rows: Row mappings supplied to a bulk mutation.

        Returns:
            Immutable row mappings copied from the caller's values.

        Raises:
            DatabaseQueryError: If columns are empty or row shapes differ.
        """
        if not rows:
            return ()
        columns = tuple(rows[0])
        expected_columns = frozenset(columns)
        if not columns:
            msg = "Bulk mutations require at least one inserted column."
            raise DatabaseQueryError(msg)
        prepared: list[Mapping[str, object]] = []
        for row in rows:
            if frozenset(row) != expected_columns:
                msg = "Bulk mutation rows must use the same columns."
                raise DatabaseQueryError(msg)
            self._validate_value_columns(row)
            prepared.append({name: row[name] for name in columns})
        return tuple(prepared)

    def _validate_conflict_columns(
        self,
        unique_by: Sequence[str],
        row_columns: Sequence[str],
    ) -> tuple[str, ...]:
        """Validate an upsert target against every inserted row.

        Args:
            unique_by: Candidate unique-index column names.
            row_columns: Names present in every input row.

        Returns:
            Unique conflict column names in caller order.

        Raises:
            DatabaseQueryError: If the target is missing, repeated, or unsafe.
        """
        if isinstance(unique_by, str) or not unique_by:
            msg = "Upserts require one or more unique conflict columns."
            raise DatabaseQueryError(msg)
        columns = _identifier_sequence(unique_by)
        if len(set(columns)) != len(columns):
            msg = "Upsert conflict columns must not repeat."
            raise DatabaseQueryError(msg)
        if not set(columns).issubset(row_columns):
            msg = "Upsert conflict columns must be present in every row."
            raise DatabaseQueryError(msg)
        self._validate_value_columns(dict.fromkeys(columns))
        return columns

    def _resolve_update_columns(
        self,
        row_columns: Sequence[str],
        conflict_columns: Sequence[str],
        update_columns: Sequence[str] | None,
    ) -> tuple[str, ...]:
        """Validate the inserted columns selected for conflict updates.

        Args:
            row_columns: Names present in every input row.
            conflict_columns: Unique columns identifying conflicts.
            update_columns: Explicit update list or default selection.

        Returns:
            Validated update columns in input or row order.

        Raises:
            DatabaseQueryError: If an update column is repeated or missing.
        """
        if update_columns is None:
            conflict_set = set(conflict_columns)
            columns = tuple(
                name for name in row_columns if name not in conflict_set
            )
        else:
            if isinstance(update_columns, str):
                msg = "Upsert update columns must be a sequence of names."
                raise DatabaseQueryError(msg)
            columns = _identifier_sequence(update_columns)
            if len(set(columns)) != len(columns):
                msg = "Upsert update columns must not repeat."
                raise DatabaseQueryError(msg)
            if not set(columns).issubset(row_columns):
                msg = "Upsert update columns must be present in every row."
                raise DatabaseQueryError(msg)
        self._validate_value_columns(dict.fromkeys(columns))
        return columns

    def update(self, values: Mapping[str, object]) -> int:
        """Update rows matching this query's conditions.

        Args:
            values: Column names and replacement values.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
        self._validate_value_columns(values)
        statement = update(self._table).values(dict(values))
        condition = self._where_expression()
        if condition is not None:
            statement = statement.where(condition)
        result = self._connection.execute_statement(
            statement,
        )
        return result.rowcount

    async def update_async(self, values: Mapping[str, object]) -> int:
        """Update matching rows asynchronously with bound values.

        Args:
            values: Column names and replacement values.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
        self._validate_value_columns(values)
        statement = update(self._table).values(dict(values))
        condition = self._where_expression()
        if condition is not None:
            statement = statement.where(condition)
        result = await self._connection.execute_statement_async(
            statement,
        )
        return result.rowcount

    def update_json(
        self,
        column_name: str,
        path: str,
        value: object,
    ) -> int:
        """Set one nested JSON value for rows matching this query.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object path using identifier characters.
            value: JSON-compatible value assigned to the path.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.

        Raises:
            DatabaseQueryError: If the dialect lacks JSON mutation support.
        """
        expression = self._json_set_expression(column_name, path, value)
        return self.update({column_name: expression})

    async def update_json_async(
        self,
        column_name: str,
        path: str,
        value: object,
    ) -> int:
        """Set one nested JSON value asynchronously for matching rows.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object path using identifier characters.
            value: JSON-compatible value assigned to the path.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.

        Raises:
            DatabaseQueryError: If the dialect lacks JSON mutation support.
        """
        expression = self._json_set_expression(column_name, path, value)
        return await self.update_async({column_name: expression})

    def delete(self) -> int:
        """Delete rows matching this query's conditions.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
        self._validate_value_columns({})
        statement = delete(self._table)
        condition = self._where_expression()
        if condition is not None:
            statement = statement.where(condition)
        result = self._connection.execute_statement(
            statement,
        )
        return result.rowcount

    async def delete_async(self) -> int:
        """Delete matching rows asynchronously.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
        self._validate_value_columns({})
        statement = delete(self._table)
        condition = self._where_expression()
        if condition is not None:
            statement = statement.where(condition)
        result = await self._connection.execute_statement_async(
            statement,
        )
        return result.rowcount

    def increment(self, column_name: str, amount: int = 1) -> int:
        """Atomically add an integer amount to one numeric column.

        Args:
            column_name: Safe numeric column name or qualified name.
            amount: Integer amount bound as part of the update expression.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
        return self._change_integer_column(column_name, amount)

    def decrement(self, column_name: str, amount: int = 1) -> int:
        """Atomically subtract an integer amount from one numeric column.

        Args:
            column_name: Safe numeric column name or qualified name.
            amount: Integer amount bound as part of the update expression.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
        return self._change_integer_column(column_name, -amount)

    async def increment_async(
        self,
        column_name: str,
        amount: int = 1,
    ) -> int:
        """Atomically increment matching rows asynchronously.

        Args:
            column_name: Safe numeric column name.
            amount: Integer delta to add.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
        return await self._change_integer_column_async(column_name, amount)

    async def decrement_async(
        self,
        column_name: str,
        amount: int = 1,
    ) -> int:
        """Atomically decrement matching rows asynchronously.

        Args:
            column_name: Safe numeric column name.
            amount: Integer delta to subtract.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
        return await self._change_integer_column_async(column_name, -amount)

    def increment_each(self, amounts: Mapping[str, int]) -> int:
        """Atomically increment several numeric columns in one update.

        Args:
            amounts: Safe column names mapped to non-negative integer deltas.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.

        Raises:
            DatabaseQueryError: If no columns are provided.
            ValueError: If a delta is not a non-negative integer.
        """
        return self.update(self._integer_column_updates(amounts, 1))

    def decrement_each(self, amounts: Mapping[str, int]) -> int:
        """Atomically decrement several numeric columns in one update.

        Args:
            amounts: Safe column names mapped to non-negative integer deltas.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.

        Raises:
            DatabaseQueryError: If no columns are provided.
            ValueError: If a delta is not a non-negative integer.
        """
        return self.update(self._integer_column_updates(amounts, -1))

    async def increment_each_async(
        self,
        amounts: Mapping[str, int],
    ) -> int:
        """Asynchronously increment several columns with one SQL update.

        Args:
            amounts: Safe column names mapped to non-negative integer deltas.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.

        Raises:
            DatabaseQueryError: If no columns are provided.
            ValueError: If a delta is not a non-negative integer.
        """
        updates = self._integer_column_updates(amounts, 1)
        return await self.update_async(updates)

    async def decrement_each_async(
        self,
        amounts: Mapping[str, int],
    ) -> int:
        """Asynchronously decrement several columns with one SQL update.

        Args:
            amounts: Safe column names mapped to non-negative integer deltas.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.

        Raises:
            DatabaseQueryError: If no columns are provided.
            ValueError: If a delta is not a non-negative integer.
        """
        updates = self._integer_column_updates(amounts, -1)
        return await self.update_async(updates)

    def _integer_column_updates(
        self,
        amounts: Mapping[str, int],
        direction: int,
    ) -> dict[str, ColumnElement[object]]:
        """Build validated atomic SQL deltas for one or more columns.

        Args:
            amounts: Column names mapped to non-negative integer deltas.
            direction: ``1`` for addition or ``-1`` for subtraction.

        Returns:
            SQLAlchemy column expressions for a single UPDATE statement.

        Raises:
            DatabaseQueryError: If no columns are provided or names are
                invalid.
            ValueError: If any delta is not a non-negative integer.
        """
        if not amounts:
            msg = "A multi-column increment requires at least one column."
            raise DatabaseQueryError(msg)
        self._validate_value_columns(amounts)
        updates: dict[str, ColumnElement[object]] = {}
        for name, amount in amounts.items():
            if type(amount) is not int or amount < 0:
                msg = "Multi-column deltas must be non-negative integers."
                raise ValueError(msg)
            updates[name] = self._column(name) + direction * amount
        return updates

    def _change_integer_column(self, column_name: str, amount: int) -> int:
        """Perform an atomic SQL increment or decrement.

        Args:
            column_name: Safe numeric column reference.
            amount: Signed delta bound by SQLAlchemy.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
        self._validate_value_columns({column_name: amount})
        expression = self._column(column_name) + amount
        statement = update(self._table).values({column_name: expression})
        condition = self._where_expression()
        if condition is not None:
            statement = statement.where(condition)
        result = self._connection.execute_statement(
            statement,
        )
        return result.rowcount

    async def _change_integer_column_async(
        self,
        column_name: str,
        amount: int,
    ) -> int:
        """Perform an atomic asynchronous SQL increment or decrement.

        Args:
            column_name: Safe numeric column reference.
            amount: Signed delta bound by SQLAlchemy.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
        self._validate_value_columns({column_name: amount})
        expression = self._column(column_name) + amount
        statement = update(self._table).values({column_name: expression})
        condition = self._where_expression()
        if condition is not None:
            statement = statement.where(condition)
        result = await self._connection.execute_statement_async(
            statement,
        )
        return result.rowcount

    def _aggregate(self, expression: ColumnElement[object]) -> object | None:
        """Execute one scalar aggregate for the current row conditions.

        Args:
            expression: SQLAlchemy aggregate expression.

        Returns:
            The first scalar value or ``None``.
        """
        self._reject_lock_for_aggregate()
        result = self._connection.execute_statement(
            self._aggregate_statement(expression),
        )
        return _first_value(result.rows)

    async def _aggregate_async(
        self,
        expression: ColumnElement[object],
    ) -> object | None:
        """Execute one scalar aggregate asynchronously.

        Args:
            expression: SQLAlchemy aggregate expression.

        Returns:
            The first scalar value or ``None``.
        """
        self._reject_lock_for_aggregate()
        result = await self._connection.execute_statement_async(
            self._aggregate_statement(expression),
        )
        return _first_value(result.rows)

    def _aggregate_statement(
        self,
        expression: ColumnElement[object],
    ) -> Select[tuple[object]]:
        """Build an aggregate query while preserving table filters.

        Args:
            expression: SQLAlchemy aggregate expression.

        Returns:
            A one-column SQLAlchemy Select expression.
        """
        statement = select(expression).select_from(self._from)
        where = self._where_expression()
        if where is not None:
            statement = statement.where(where)
        return cast("Select[tuple[object]]", statement)

    def _id_chunk_statement(
        self,
        key_column: str,
        last_key: object,
        limit: int,
        offset: int,
    ) -> tuple[Select[tuple[object, ...]], str]:
        """Build one keyset page with a hidden continuation projection.

        Args:
            key_column: Validated unique ordering key.
            last_key: Previous page key or the initial sentinel.
            limit: Maximum rows in this page.
            offset: Initial offset or zero for subsequent pages.

        Returns:
            A SQLAlchemy statement and collision-free continuation label.
        """
        if self._is_distinct or self._group_columns:
            msg = "ID chunking requires an ungrouped, non-distinct query."
            raise DatabaseQueryError(msg)
        query = self.clone()
        query.reorder(key_column).limit(limit).offset(offset)
        if last_key is not _MISSING:
            predicate = self._compare(
                self._column(key_column),
                ">",
                last_key,
            )
            condition = self._scope_condition
            query.set_scope_condition(
                predicate if condition is None else and_(condition, predicate),
            )
        statement = query.to_statement()
        key_alias = _unique_chunk_key(statement)
        statement = statement.add_columns(
            self._column(key_column).label(key_alias),
        )
        return cast("Select[tuple[object, ...]]", statement), key_alias

    def _count_statement(self) -> Select[tuple[object]]:
        """Count rows from a pagination-free subquery.

        Returns:
            A scalar count statement that preserves joins, groups, and filters.
        """
        query = self.clone()
        query._orders.clear()  # noqa: SLF001  # Remove irrelevant order.
        query._limit = None  # noqa: SLF001  # Count matching rows.
        query._offset = None  # noqa: SLF001  # Count matching rows.
        subquery = query.to_statement().subquery()
        return cast(
            "Select[tuple[object]]",
            select(func.count()).select_from(subquery),
        )

    def _join(
        self,
        table_name: str,
        left: str,
        operator_or_right: str,
        right: str | object,
        *,
        join_type: _JoinType,
    ) -> QueryBuilder:
        """Add one supported join after validating its identifiers.

        Args:
            table_name: Safe table to join.
            left: Left column reference.
            operator_or_right: Right column or explicit operator.
            right: Optional right column when an operator is supplied.
            join_type: Supported inner, left, right, or full join behavior.

        Returns:
            This builder for further query composition.
        """
        target = self._ensure_table(table_name)
        operator, right_name = _join_arguments(operator_or_right, right)
        condition = self._compare(
            self._column(left),
            operator,
            self._column(right_name),
        )
        if join_type == "right":
            self._from = target.join(self._from, condition, isouter=True)
        elif join_type == "full":
            self._from = self._from.join(
                target,
                condition,
                isouter=True,
                full=True,
            )
        else:
            self._from = self._from.join(
                target,
                condition,
                isouter=join_type == "left",
            )
        return self

    def _join_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
        left: str,
        operator_or_right: str,
        right: str | object,
        *,
        join_type: _JoinType,
    ) -> QueryBuilder:
        """Join a safely named SQLAlchemy subquery expression.

        Args:
            query: Query whose statement becomes a subquery.
            alias: Safe unique local table alias.
            left: Validated left column reference.
            operator_or_right: Right column or comparison operator.
            right: Optional right column when an operator is supplied.
            join_type: Supported inner, left, right, or full join behavior.

        Returns:
            This builder with the subquery join appended.

        Raises:
            DatabaseQueryError: If the alias is invalid or already in use.
        """
        self._add_subquery(alias, query)
        target = self._tables[alias]
        operator, right_name = _join_arguments(operator_or_right, right)
        condition = self._compare(
            self._column(left),
            operator,
            self._column(right_name),
        )
        if join_type == "right":
            self._from = target.join(self._from, condition, isouter=True)
        elif join_type == "full":
            self._from = self._from.join(
                target,
                condition,
                isouter=True,
                full=True,
            )
        else:
            self._from = self._from.join(
                target,
                condition,
                isouter=join_type == "left",
            )
        return self

    def _add_subquery(
        self,
        alias: str,
        query: DatabaseQueryBuilder,
    ) -> None:
        """Register one validated subquery alias exactly once.

        Args:
            alias: Safe unique name for the local FROM clause.
            query: Builder that produces the subquery statement.

        Raises:
            DatabaseQueryError: If the alias is invalid or already in use.
        """
        parts = _identifier_parts(alias)
        if len(parts) != 1 or alias in self._tables:
            msg = "A subquery join requires a unique safe alias."
            raise DatabaseQueryError(msg)
        self._tables[alias] = query.to_statement().subquery(alias)

    def _validate_value_columns(
        self,
        values: Mapping[str, object],
    ) -> None:
        """Validate every mutation identifier before constructing a statement.

        Args:
            values: Mutation values keyed by SQL column names.
        """
        if self._is_derived:
            msg = "Mutations require a table-backed query builder."
            raise DatabaseQueryError(msg)
        if self._lock_mode is not None:
            msg = "Pessimistic locks apply only to row retrieval queries."
            raise DatabaseQueryError(msg)
        for raw_name in values:
            name = _identifier_text(raw_name)
            parts = _identifier_parts(name)
            if len(parts) != 1:
                _raise_invalid_identifier()
            self._column(name)

    def _projection(self, expression: str) -> _Projection:
        """Parse one safe column projection and optional label.

        Args:
            expression: Column name or ``column as label`` declaration.

        Returns:
            A SQLAlchemy column expression with an optional output label.
        """
        match = re.fullmatch(
            r"(?i)(.+?)\s+as\s+([A-Za-z_][A-Za-z0-9_$]*)",
            expression.strip(),
        )
        if match is None:
            return self._column(expression)
        source, label = match.groups()
        return self._column(source.strip()).label(label)

    def _subquery_projection(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
    ) -> _Projection:
        """Create a safely labeled scalar projection from another builder.

        Args:
            query: Subquery expected to select one column.
            alias: Output column identifier.

        Returns:
            A SQLAlchemy scalar subquery labeled with the validated alias.
        """
        if len(_identifier_parts(alias)) != 1:
            _raise_invalid_identifier()
        expression = query.to_statement().scalar_subquery().label(alias)
        return cast("_Projection", expression)

    def _membership_values(
        self,
        values: Sequence[object] | DatabaseQueryBuilder,
    ) -> Sequence[object] | SelectBase:
        """Resolve one bound sequence or native fluent subquery operand.

        Args:
            values: Query Builder projection or sequence of bound values.

        Returns:
            A SQLAlchemy-selectable subquery or the supplied value sequence.
        """
        if isinstance(values, DatabaseQueryBuilder):
            return values.to_statement()
        return values

    def _full_text_condition(
        self,
        columns: str | Sequence[str],
        value: str,
    ) -> _Condition:
        """Build a dialect-native full-text predicate with bound input.

        Args:
            columns: Safe column names participating in the search.
            value: Search text passed as a bound parameter.

        Returns:
            A SQLAlchemy boolean expression.

        Raises:
            DatabaseQueryError: If the dialect or column selection is invalid.
        """
        names = (columns,) if isinstance(columns, str) else tuple(columns)
        if not names:
            msg = "Full-text search requires at least one column."
            raise DatabaseQueryError(msg)
        resolved = tuple(self._column(name) for name in names)
        dialect = self._connection.dialect_name
        if dialect in {"mysql", "mariadb"}:
            return cast(
                "_Condition",
                mysql_match(
                    *resolved,
                    against=value,
                    in_natural_language_mode=True,
                ),
            )
        if dialect == "postgresql":
            searchable = (
                resolved[0]
                if len(resolved) == 1
                else func.concat_ws(" ", *resolved)
            )
            return searchable.match(value)
        if dialect == "sqlite":
            if len(resolved) != 1:
                msg = (
                    "SQLite full-text search accepts one column per predicate."
                )
                raise DatabaseQueryError(msg)
            return resolved[0].match(value)
        msg = f"Full-text search is unsupported for the {dialect} dialect."
        raise DatabaseQueryError(msg)

    def _column(self, reference: str) -> ColumnElement[object]:
        """Resolve a safe column reference against known query tables.

        Args:
            reference: Column, table-qualified, or schema-qualified name.

        Returns:
            A SQLAlchemy ColumnClause attached to the correct table.
        """
        parts = _identifier_parts(reference)
        if len(parts) == 1:
            source = self._default_source
            column_name = parts[0]
        else:
            table_key = ".".join(parts[:-1])
            source = self._tables.get(table_key)
            if source is None:
                msg = "A qualified column must refer to a table in this query."
                raise DatabaseQueryError(msg)
            column_name = parts[-1]
        columns = cast("_ColumnCollectionSource", source).c
        if column_name not in columns:
            if not isinstance(source, TableClause):
                msg = "The joined query does not expose the selected column."
                raise DatabaseQueryError(msg)
            if not self._allow_unknown_columns and source is self._table:
                msg = "The selected model column is not mapped."
                raise DatabaseQueryError(msg)
            source.append_column(column(column_name))
            columns = cast("_ColumnCollectionSource", source).c
        return columns[column_name]

    def _ensure_table(self, name: str) -> FromClause:
        """Get or add a safe table reference for a join.

        Args:
            name: Table name, optionally qualified by a schema.

        Returns:
            The SQLAlchemy TableClause registered for this builder.
        """
        source, key = _make_table(name)
        existing = self._tables.get(key)
        if existing is not None:
            return existing
        self._tables[key] = source
        return source

    def _compare(
        self,
        left: ColumnElement[object],
        operator: str,
        right: object,
    ) -> _Condition:
        """Create a parameterized comparison from the fixed operator set.

        Args:
            left: Validated SQLAlchemy left expression.
            operator: One allowlisted comparison operator.
            right: Value bound by SQLAlchemy or another column expression.

        Returns:
            A boolean SQLAlchemy expression.

        Raises:
            DatabaseQueryError: If the operator is unsupported.
        """
        sql_operator = _COMPARISON_OPERATORS.get(operator.casefold())
        if sql_operator is None:
            msg = "The query comparison operator is not supported."
            raise DatabaseQueryError(msg)
        return cast("_Condition", left.operate(sql_operator, right))

    def _where_row_values(
        self,
        columns: Sequence[str],
        operator: str,
        values: Sequence[object],
        boolean: _Boolean,
    ) -> QueryBuilder:
        """Build one dialect-supported bound row-value comparison.

        Args:
            columns: Ordered, safe column references.
            operator: Allowlisted SQL comparison operator.
            values: Ordered values bound independently by SQLAlchemy.
            boolean: Connector used to group the predicate.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect or tuple shape is unsupported.
        """
        if self._connection.dialect_name not in {
            "mysql",
            "postgresql",
            "sqlite",
        }:
            msg = "Row-value comparisons are unsupported by this dialect."
            raise DatabaseQueryError(msg)
        column_names = _identifier_sequence(columns)
        if (
            not column_names
            or isinstance(values, (str, bytes))
            or len(column_names) != len(values)
        ):
            msg = (
                "Row comparison requires the same number of columns and values."
            )
            raise DatabaseQueryError(msg)
        left = cast(
            "ColumnElement[object]",
            tuple_(*(self._column(name) for name in column_names)),
        )
        right = cast(
            "ColumnElement[object]",
            tuple_(*(literal(value) for value in values)),
        )
        return self._add_where(
            self._compare(left, operator, right),
            boolean,
        )

    def _where_json_value(
        self,
        column_name: str,
        path: str,
        operator_or_value: object,
        value: object,
        boolean: _Boolean,
    ) -> QueryBuilder:
        """Add a safely extracted JSON scalar comparison.

        Args:
            column_name: Safe JSON column reference.
            path: Validated dot-separated JSON object path.
            operator_or_value: Equality value or comparison operator.
            value: Explicit comparison value or the missing sentinel.
            boolean: SQL connector for the predicate.

        Returns:
            This builder for further query composition.
        """
        if value is _MISSING:
            operator = "="
            comparison_value = operator_or_value
        else:
            if not isinstance(operator_or_value, str):
                _raise_invalid_condition()
            operator = operator_or_value
            comparison_value = value
        expression = self._json_value_expression(
            column_name,
            path,
            comparison_value,
        )
        return self._add_where(
            self._compare(expression, operator, comparison_value),
            boolean,
        )

    def _where_json_contains(
        self,
        column_name: str,
        path: str,
        value: object,
        boolean: _Boolean,
        *,
        negated: bool,
    ) -> QueryBuilder:
        """Add one dialect-supported JSON containment comparison.

        Args:
            column_name: Safe JSON column reference.
            path: Validated nested object path.
            value: Candidate JSON value bound by SQLAlchemy.
            boolean: SQL connector for the new condition.
            negated: Whether the containment result is negated.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect lacks JSON containment.
        """
        parts = _json_path_parts(path)
        source = self._column(column_name)
        dialect = self._connection.dialect_name
        if dialect == "postgresql":
            target = source.op("#>")(postgresql_array(list(parts)))
            condition = target.op("@>")(literal(value, type_=JSONB))
        elif dialect in {"mysql", "mariadb"}:
            json_path = "$" + "".join(f".{part}" for part in parts)
            condition = (
                func.json_contains(
                    source,
                    literal(value, type_=JSON),
                    json_path,
                )
                == 1
            )
        else:
            msg = (
                f"JSON containment is unsupported by {dialect}; supported "
                "dialects are PostgreSQL, MySQL, and MariaDB."
            )
            raise DatabaseQueryError(msg)
        expression = cast("_Condition", condition)
        if negated:
            expression = not_(expression)
        return self._add_where(expression, boolean)

    def _where_json_contains_key(
        self,
        column_name: str,
        path: str,
        boolean: _Boolean,
        *,
        negated: bool,
    ) -> QueryBuilder:
        """Add one dialect-supported nested JSON key-existence check.

        Args:
            column_name: Safe JSON column reference.
            path: Validated nested object path.
            boolean: SQL connector for the new condition.
            negated: Whether the existence result is negated.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect lacks safe JSON path support.
        """
        parts = _json_path_parts(path)
        source = self._column(column_name)
        json_path = "$" + "".join(f".{part}" for part in parts)
        dialect = self._connection.dialect_name
        if dialect == "postgresql":
            target = source.op("#>")(postgresql_array(list(parts)))
            condition = target.is_not(None)
        elif dialect in {"mysql", "mariadb"}:
            condition = (
                func.json_contains_path(
                    source,
                    "one",
                    json_path,
                )
                == 1
            )
        elif dialect == "sqlite":
            condition = func.json_type(source, json_path).is_not(None)
        else:
            msg = f"JSON key checks are unsupported by the {dialect} dialect."
            raise DatabaseQueryError(msg)
        expression = cast("_Condition", condition)
        if negated:
            expression = not_(expression)
        return self._add_where(expression, boolean)

    def _where_json_length(
        self,
        column_name: str,
        path: str,
        operator_or_length: object,
        length: object,
        boolean: _Boolean,
    ) -> QueryBuilder:
        """Compare a native JSON array-length expression with a bound integer.

        Args:
            column_name: Safe JSON column reference.
            path: Validated nested object path.
            operator_or_length: Expected length or comparison operator.
            length: Expected length when an operator is supplied.
            boolean: SQL connector for the new condition.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the dialect or comparison is unsupported.
        """
        if length is _MISSING:
            operator = "="
            expected = operator_or_length
        else:
            if not isinstance(operator_or_length, str):
                _raise_invalid_condition()
            operator = operator_or_length
            expected = length
        if type(expected) is not int:
            msg = "JSON array length comparisons require an integer value."
            raise DatabaseQueryError(msg)

        parts = _json_path_parts(path)
        source = self._column(column_name)
        json_path = "$" + "".join(f".{part}" for part in parts)
        dialect = self._connection.dialect_name
        if dialect == "postgresql":
            target = source.op("#>")(postgresql_array(list(parts)))
            expression = func.jsonb_array_length(target)
        elif dialect in {"mysql", "mariadb"}:
            expression = func.json_length(source, json_path)
        elif dialect == "sqlite":
            expression = func.json_array_length(source, json_path)
        else:
            msg = f"JSON array lengths are unsupported by {dialect}."
            raise DatabaseQueryError(msg)
        return self._add_where(
            self._compare(expression, operator, expected),
            boolean,
        )

    def _json_set_expression(
        self,
        column_name: str,
        path: str,
        value: object,
    ) -> ColumnElement[object]:
        """Build a dialect-native, parameterized nested JSON assignment.

        Args:
            column_name: Safe JSON column reference.
            path: Validated nested object path.
            value: JSON-compatible value bound by SQLAlchemy.

        Returns:
            A SQLAlchemy expression assigning the nested JSON value.

        Raises:
            DatabaseQueryError: If the dialect lacks JSON mutation support.
        """
        parts = _json_path_parts(path)
        source = self._column(column_name)
        dialect = self._connection.dialect_name
        if dialect == "postgresql":
            return cast(
                "ColumnElement[object]",
                func.jsonb_set(
                    source,
                    postgresql_array(list(parts)),
                    literal(value, type_=JSONB),
                    True,
                ),
            )
        json_path = "$" + "".join(f".{part}" for part in parts)
        encoded = literal(value, type_=JSON)
        if dialect in {"mysql", "mariadb"}:
            json_value = func.json_extract(encoded, "$")
            return cast(
                "ColumnElement[object]",
                func.json_set(source, json_path, json_value),
            )
        if dialect == "sqlite":
            return cast(
                "ColumnElement[object]",
                func.json_set(source, json_path, func.json(encoded)),
            )
        msg = f"JSON updates are unsupported by the {dialect} dialect."
        raise DatabaseQueryError(msg)

    def _json_value_expression(
        self,
        column_name: str,
        path: str,
        value: object,
    ) -> ColumnElement[object]:
        """Build a dialect-specific JSON scalar expression with bound paths.

        Args:
            column_name: Safe JSON column reference.
            path: Validated dot-separated JSON object path.
            value: Comparison value used to select a compatible cast.

        Returns:
            SQLAlchemy expression for the requested JSON scalar.

        Raises:
            DatabaseQueryError: If the path, value, or dialect is unsupported.
        """
        parts = _json_path_parts(path)
        source = self._column(column_name)
        dialect = self._connection.dialect_name
        if dialect == "postgresql":
            extracted = source.op("#>>")(postgresql_array(list(parts)))
        elif dialect in {"sqlite", "mysql"}:
            json_path = "$" + "".join(f".{part}" for part in parts)
            extracted = func.json_extract(source, json_path)
            if dialect == "mysql":
                extracted = func.json_unquote(extracted)
        else:
            msg = "JSON path predicates are unsupported by this dialect."
            raise DatabaseQueryError(msg)
        if value is None or type(value) is str:
            return cast("ColumnElement[object]", sql_cast(extracted, String()))
        if type(value) is bool:
            return cast("ColumnElement[object]", sql_cast(extracted, Boolean()))
        if type(value) is int:
            return cast("ColumnElement[object]", sql_cast(extracted, Integer()))
        if type(value) is float and math.isfinite(value):
            return cast("ColumnElement[object]", sql_cast(extracted, Float()))
        if isinstance(value, Decimal) and value.is_finite():
            return cast("ColumnElement[object]", sql_cast(extracted, Numeric()))
        msg = "JSON path comparisons require a supported scalar value."
        raise DatabaseQueryError(msg)

    def _date_expression(
        self,
        column_name: str,
    ) -> ColumnElement[object]:
        """Build a date-only expression supported by verified dialects.

        Args:
            column_name: Safe date or timestamp column reference.

        Returns:
            A SQLAlchemy expression returning the date component.

        Raises:
            DatabaseQueryError: If the current dialect has no supported form.
        """
        source = self._column(column_name)
        if self._connection.dialect_name in {"sqlite", "mysql"}:
            return cast("ColumnElement[object]", func.date(source))
        if self._connection.dialect_name == "postgresql":
            return cast("ColumnElement[object]", sql_cast(source, Date()))
        msg = "Date-part predicates are unsupported by this dialect."
        raise DatabaseQueryError(msg)

    def _where_temporal(
        self,
        expression: ColumnElement[object],
        operator_or_value: object,
        value: object,
        boolean: _Boolean,
    ) -> QueryBuilder:
        """Add a bound comparison against one date or time expression.

        Args:
            expression: SQLAlchemy date-part or time-part expression.
            operator_or_value: Equality value or comparison operator.
            value: Explicit comparison value or the missing sentinel.
            boolean: SQL connector for the new predicate.

        Returns:
            This builder for further query composition.

        Raises:
            DatabaseQueryError: If the comparison arguments are invalid.
        """
        if value is _MISSING:
            operator = "="
            right = operator_or_value
        else:
            if not isinstance(operator_or_value, str):
                _raise_invalid_condition()
            operator = operator_or_value
            right = value
        return self._add_where(
            self._compare(expression, operator, right),
            boolean,
        )

    def _add_where(
        self,
        condition: _Condition,
        boolean: _Boolean,
    ) -> QueryBuilder:
        """Add one predicate with explicit SQL AND or OR grouping.

        Args:
            condition: SQLAlchemy boolean expression.
            boolean: Connector selected by the caller.

        Returns:
            This builder for further query composition.
        """
        self._add_group(self._where_groups, condition, boolean)
        return self

    @staticmethod
    def _add_group(
        groups: list[list[_Condition]],
        condition: _Condition,
        boolean: _Boolean,
    ) -> None:
        """Append an AND term or start an OR group.

        Args:
            groups: Ordered SQL where or having groups.
            condition: SQLAlchemy boolean expression to add.
            boolean: Connector selected by the caller.
        """
        _append_boolean_group(groups, condition, boolean)

    def _where_expression(
        self,
        groups: list[list[_Condition]] | None = None,
    ) -> _Condition | None:
        """Combine ordered conditions without implicit operator precedence.

        Args:
            groups: Specific where or having groups to combine.

        Returns:
            The equivalent parenthesized boolean expression.
        """
        selected = self._where_groups if groups is None else groups
        user_condition = (
            None
            if not selected
            else or_(*[_conjunction(group) for group in selected])
        )
        if groups is None and self._scope_condition is not None:
            if user_condition is None:
                return self._scope_condition
            return and_(self._scope_condition, user_condition)
        return user_condition

    def set_scope_condition(
        self,
        condition: _Condition | None,
    ) -> None:
        """Set a global condition for reads and set-based mutations.

        Args:
            condition: SQLAlchemy predicate or ``None`` to remove the scope.
        """
        self._scope_condition = condition


class _JoinClause(DatabaseJoinClause):
    """Build parameterized and parenthesized conditions for one join.
    """  # fmt: skip

    def __init__(
        self,
        column_resolver: _ColumnResolver,
        compare: _ColumnComparator,
    ) -> None:
        """Bind condition construction to the query's validated identifiers.

        Args:
            column_resolver: Query-owned validated column lookup.
            compare: Query-owned operator validation and expression builder.
        """
        self._column = column_resolver
        self._compare = compare
        self._groups: list[list[_Condition]] = []

    def on(
        self,
        left: str,
        operator: str,
        right: str,
        *,
        boolean: _Boolean = "and",
    ) -> _JoinClause:
        """Add a column-to-column condition to the ON clause.

        Args:
            left: Safe left column reference.
            operator: Supported comparison operator.
            right: Safe right column reference.
            boolean: Connector to the preceding condition.

        Returns:
            This clause for further condition composition.
        """
        condition = self._compare(
            self._column(left),
            operator,
            self._column(right),
        )
        return self._append(condition, boolean)

    def where(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
        *,
        boolean: _Boolean = "and",
    ) -> _JoinClause:
        """Add a column-to-value comparison inside the ON clause.

        Args:
            column_name: Safe column reference from the join.
            operator_or_value: Equality value or explicit comparison operator.
            value: Comparison value when an operator is supplied.
            boolean: Connector to the preceding condition.

        Returns:
            This clause for further condition composition.
        """
        operator, right = _comparison_arguments(operator_or_value, value)
        condition = self._compare(
            self._column(column_name),
            operator,
            right,
        )
        return self._append(condition, boolean)

    def or_where(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> _JoinClause:
        """Add a column-to-value comparison joined through SQL OR.

        Args:
            column_name: Safe column reference from the join.
            operator_or_value: Equality value or explicit comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This clause for further condition composition.
        """
        return self.where(
            column_name,
            operator_or_value,
            value,
            boolean="or",
        )

    def where_group(
        self,
        callback: Callable[[DatabaseJoinClause], object],
        *,
        boolean: _Boolean = "and",
    ) -> _JoinClause:
        """Add a parenthesized group to the ON clause.

        Args:
            callback: Synchronous function that adds nested conditions.
            boolean: Connector to the preceding condition.

        Returns:
            This clause for further condition composition.
        """
        nested = _JoinClause(self._column, self._compare)
        callback(nested)
        return self._append(nested.expression(), boolean)

    def _append(
        self,
        condition: _Condition,
        boolean: _Boolean,
    ) -> _JoinClause:
        """Append one condition with explicit boolean grouping.

        Args:
            condition: SQLAlchemy boolean condition.
            boolean: Connector to the preceding condition.

        Returns:
            This clause for further condition composition.
        """
        _append_boolean_group(self._groups, condition, boolean)
        return self

    def expression(self) -> _Condition:
        """Combine the join conditions while preserving AND precedence.

        Returns:
            One SQLAlchemy expression for the complete ON clause.

        Raises:
            DatabaseQueryError: If the join has no conditions.
        """
        if not self._groups:
            msg = "A composed join requires at least one ON condition."
            raise DatabaseQueryError(msg)
        return or_(*[_conjunction(group) for group in self._groups])


def _make_table(name: str) -> tuple[TableClause, str]:
    """Construct a quoted SQLAlchemy table reference from safe identifiers.

    Args:
        name: Table name with at most one schema qualifier.

    Returns:
        A table clause and its canonical query-local key.
    """
    parts = _identifier_parts(name)
    if len(parts) == 1:
        return table(parts[0]), parts[0]
    if len(parts) == _SCHEMA_PART_COUNT:
        schema, table_name = parts
        return table(table_name, schema=schema), name
    return _raise_invalid_identifier()


def _identifier_parts(value: str) -> tuple[str, ...]:
    """Split and validate one unquoted SQL identifier path.

    Args:
        value: Identifier input supplied by trusted application code.

    Returns:
        One to three validated schema, table, or column components.
    """
    parts = tuple(value.split("."))
    if not 1 <= len(parts) <= _SCHEMA_COLUMN_PART_COUNT or any(
        _IDENTIFIER.fullmatch(part) is None for part in parts
    ):
        _raise_invalid_identifier()
    return parts


def _comparison_arguments(
    operator_or_value: object,
    value: object,
) -> tuple[str, object]:
    """Normalize equality and explicit-operator call forms.

    Args:
        operator_or_value: Equality value or explicit operator.
        value: Explicit comparison value or the internal missing sentinel.

    Returns:
        A comparison operator and its bound right operand.
    """
    if value is _MISSING:
        return "=", operator_or_value
    if not isinstance(operator_or_value, str):
        _raise_invalid_condition()
    return operator_or_value, value


def _join_arguments(
    operator_or_right: str,
    right: str | object,
) -> tuple[str, str]:
    """Normalize two-column join comparison forms.

    Args:
        operator_or_right: Right column name or comparison operator.
        right: Optional right column name.

    Returns:
        The comparison operator and right column reference.
    """
    if right is _MISSING:
        return "=", operator_or_right
    if not isinstance(right, str):
        _raise_invalid_condition()
    return operator_or_right, right


def _conjunction(conditions: Sequence[_Condition]) -> _Condition:
    """Combine one group with SQL AND.

    Args:
        conditions: Conditions in a parenthesized group.

    Returns:
        One SQLAlchemy boolean expression.
    """
    if len(conditions) == 1:
        return conditions[0]
    return and_(*conditions)


def _append_boolean_group(
    groups: list[list[_Condition]],
    condition: _Condition,
    boolean: _Boolean,
) -> None:
    """Append one AND term or begin a new OR group.

    Args:
        groups: Ordered boolean groups owned by a query or join clause.
        condition: SQLAlchemy boolean expression to add.
        boolean: Connector selected by the caller.
    """
    if not groups or boolean == "or":
        groups.append([condition])
    else:
        groups[-1].append(condition)


def _json_path_parts(path: str) -> tuple[str, ...]:
    """Validate a bounded dot-separated path containing only object keys.

    Args:
        path: Untrusted path supplied to the native query builder.

    Returns:
        Safe object keys used in a parameterized JSON extraction expression.

    Raises:
        DatabaseQueryError: If the path is empty, oversized, or unsafe.
    """
    if (
        type(path) is not str
        or not path
        or len(path) > _MAXIMUM_JSON_PATH_LENGTH
    ):
        _raise_invalid_json_path()
    parts = tuple(path.split("."))
    if any(_JSON_PATH_PART.fullmatch(part) is None for part in parts):
        _raise_invalid_json_path()
    return parts


def _raise_invalid_json_path() -> NoReturn:
    """Reject unsafe or unsupported JSON object path syntax.
    """  # fmt: skip
    msg = "The JSON path must contain only dot-separated object keys."
    raise DatabaseQueryError(msg)


def _encode_cursor(
    direction: _CursorDirection,
    specs: tuple[_CursorOrder, ...],
    values: tuple[_CursorScalar, ...] | None,
) -> str:
    """Encode only validated ordering metadata and scalar data values.

    Args:
        direction: Whether the cursor points before or after its values.
        specs: Stable order column names and directions.
        values: Scalar order values from the selected boundary row.

    Returns:
        A URL-safe, base64-encoded JSON token.

    Raises:
        DatabaseQueryError: If a cursor value cannot be encoded safely.
    """
    if values is None:
        msg = "A cursor cannot be generated without a boundary row."
        raise DatabaseQueryError(msg)
    payload = {
        "version": 1,
        "direction": direction,
        "columns": [[name, descending] for name, descending in specs],
        "values": [_encode_cursor_scalar(value) for value in values],
    }
    token = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), allow_nan=False).encode(),
    ).decode("ascii")
    if len(token) > _MAXIMUM_CURSOR_LENGTH:
        msg = "The cursor token exceeds the supported size limit."
        raise DatabaseQueryError(msg)
    return token


def _decode_cursor(
    token: str,
    specs: tuple[_CursorOrder, ...],
) -> tuple[_CursorDirection, tuple[object, ...]]:
    """Validate and decode one non-executable cursor data token.

    Args:
        token: URL-safe base64 JSON token supplied by the caller.
        specs: Expected order column names and directions.

    Returns:
        A direction and decoded bound data values.

    Raises:
        DatabaseQueryError: If the token is malformed or does not match.
    """
    if (
        type(token) is not str
        or not token
        or len(token) > _MAXIMUM_CURSOR_LENGTH
    ):
        _raise_invalid_cursor()
    try:
        raw = base64.b64decode(
            token.encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
        parsed = cast("object", json.loads(raw.decode("utf-8")))
    except (binascii.Error, UnicodeDecodeError, UnicodeEncodeError, ValueError):
        _raise_invalid_cursor()
    if not isinstance(parsed, dict):
        _raise_invalid_cursor()
    payload = cast("dict[str, object]", parsed)
    if set(payload) != {"version", "direction", "columns", "values"}:
        _raise_invalid_cursor()
    direction_value = payload["direction"]
    if type(direction_value) is not str or direction_value not in {
        "after",
        "before",
    }:
        _raise_invalid_cursor()
    direction = cast("_CursorDirection", direction_value)
    expected_columns = [[name, descending] for name, descending in specs]
    if (
        type(payload["version"]) is not int
        or payload["version"] != 1
        or payload["columns"] != expected_columns
    ):
        _raise_invalid_cursor()
    raw_values = payload["values"]
    if not isinstance(raw_values, list):
        _raise_invalid_cursor()
    cursor_items = cast("list[object]", raw_values)
    if len(cursor_items) != len(specs):
        _raise_invalid_cursor()
    values = tuple(_decode_cursor_scalar(item) for item in cursor_items)
    return direction, values


def _encode_cursor_scalar(value: _CursorScalar) -> list[object]:
    """Return a safe tagged JSON representation for one cursor value.

    Args:
        value: Driver-returned value from a cursor ordering column.

    Returns:
        A type tag and JSON-safe scalar representation.

    Raises:
        DatabaseQueryError: If the value type is unsupported.
    """
    if type(value) in {bool, int, float, str}:
        return _encode_basic_cursor_scalar(value)
    return _encode_extended_cursor_scalar(value)


def _encode_basic_cursor_scalar(value: object) -> list[object]:
    """Encode one built-in cursor scalar without coercing its type.

    Args:
        value: Boolean, integer, finite float, or string value.

    Returns:
        A type tag and JSON-safe scalar representation.

    Raises:
        DatabaseQueryError: If the value is not a supported built-in scalar.
    """
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", value]
    if type(value) is float and math.isfinite(value):
        return ["float", value]
    if type(value) is str:
        return ["str", value]
    msg = "The cursor ordering contains an unsupported value type."
    raise DatabaseQueryError(msg)


def _encode_extended_cursor_scalar(value: object) -> list[object]:
    """Encode one standard-library temporal, decimal, or UUID scalar.

    Args:
        value: Decimal, date, datetime, time, or UUID value.

    Returns:
        A type tag and JSON-safe string representation.

    Raises:
        DatabaseQueryError: If the value type is unsupported.
    """
    if isinstance(value, Decimal) and value.is_finite():
        return ["decimal", str(value)]
    if isinstance(value, datetime):
        return ["datetime", value.isoformat()]
    if isinstance(value, date):
        return ["date", value.isoformat()]
    if isinstance(value, time):
        return ["time", value.isoformat()]
    if isinstance(value, UUID):
        return ["uuid", str(value)]
    msg = "The cursor ordering contains an unsupported value type."
    raise DatabaseQueryError(msg)


def _cursor_scalar(value: object) -> _CursorScalar:
    """Validate one result value before including it in a cursor token.

    Args:
        value: Driver-returned ordering value.

    Returns:
        A supported scalar value suitable for cursor encoding.

    Raises:
        DatabaseQueryError: If the value is null or unsupported.
    """
    if type(value) in {bool, int, float, str} or isinstance(
        value, (Decimal, datetime, date, time, UUID)
    ):
        return cast("_CursorScalar", value)
    msg = "The cursor ordering contains an unsupported value type."
    raise DatabaseQueryError(msg)


def _decode_cursor_scalar(value: object) -> object:
    """Decode one whitelisted type tag from untrusted cursor JSON.

    Args:
        value: One parsed JSON cursor value.

    Returns:
        A built-in scalar that SQLAlchemy can bind as query data.

    Raises:
        DatabaseQueryError: If the tag or value shape is invalid.
    """
    if not isinstance(value, list):
        _raise_invalid_cursor()
    entry = cast("list[object]", value)
    if len(entry) != _CURSOR_PAIR_LENGTH:
        _raise_invalid_cursor()
    tag, raw = entry
    if type(tag) is not str:
        _raise_invalid_cursor()
    try:
        if tag in {"bool", "int", "float", "str"}:
            decoded = _decode_basic_cursor_scalar(tag, raw)
        else:
            decoded = _decode_extended_cursor_scalar(tag, raw)
    except (InvalidOperation, ValueError):
        _raise_invalid_cursor()
    return decoded


def _decode_basic_cursor_scalar(tag: str, value: object) -> object:
    """Decode one built-in scalar using an exact type check.

    Args:
        tag: Boolean, integer, float, or string type tag.
        value: JSON scalar from an untrusted cursor token.

    Returns:
        The scalar after its type matches the supplied tag.

    Raises:
        DatabaseQueryError: If the data does not match its type tag.
    """
    if tag == "bool" and type(value) is bool:
        return value
    if tag == "int" and type(value) is int:
        return value
    if tag == "float" and type(value) is float and math.isfinite(value):
        return value
    if tag == "str" and type(value) is str:
        return value
    return _raise_invalid_cursor()


def _decode_extended_cursor_scalar(tag: str, value: object) -> object:
    """Decode a temporal, decimal, or UUID string through fixed parsers.

    Args:
        tag: Whitelisted standard-library scalar type tag.
        value: JSON string from an untrusted cursor token.

    Returns:
        The parsed scalar value.

    Raises:
        DatabaseQueryError: If the tag or string value is invalid.
    """
    if type(value) is not str:
        _raise_invalid_cursor()
    if tag == "decimal":
        return Decimal(value)
    if tag == "datetime":
        return datetime.fromisoformat(value)
    if tag == "date":
        return date.fromisoformat(value)
    if tag == "time":
        return time.fromisoformat(value)
    if tag == "uuid":
        return UUID(value)
    return _raise_invalid_cursor()


def _raise_invalid_cursor() -> NoReturn:
    """Raise one safe error for malformed or incompatible cursor tokens.
    """  # fmt: skip
    msg = "The cursor token is invalid for this query."
    raise DatabaseQueryError(msg)


def _first_value(
    rows: Sequence[Mapping[str, object]],
) -> object | None:
    """Extract the first scalar from a detached aggregate result.

    Args:
        rows: Detached SQLAlchemy mapping rows.

    Returns:
        First value or ``None`` when the query returned no rows.
    """
    if not rows:
        return None
    return next(iter(rows[0].values()), None)


def _inserted_id(rows: Sequence[Mapping[str, object]]) -> object:
    """Read the returned key from a single-row INSERT result.

    Args:
        rows: Detached RETURNING rows from the database.

    Returns:
        The inserted key value.

    Raises:
        DatabaseQueryError: If the database did not return the key column.
    """
    if not rows or "__inserted_id" not in rows[0]:
        msg = "The database did not return the inserted key."
        raise DatabaseQueryError(msg)
    return rows[0]["__inserted_id"]


def _update_or_insert_values(
    attributes: Mapping[str, object],
    values: Mapping[str, object],
    dialect: str,
) -> tuple[dict[str, object], tuple[str, ...], tuple[str, ...]]:
    """Prepare one atomic upsert from matching and update values.

    Args:
        attributes: Unique key values used to identify a conflict.
        values: Additional or same-valued fields to insert or update.
        dialect: Normalized SQLAlchemy dialect identifier.

    Returns:
        Insert values, conflict columns, and conflict update columns.

    Raises:
        DatabaseQueryError: If match attributes are empty or changed.
    """
    if not attributes:
        msg = "Update-or-insert requires at least one unique match value."
        raise DatabaseQueryError(msg)
    changed_keys = [
        key
        for key, value in values.items()
        if key in attributes and attributes[key] != value
    ]
    if changed_keys:
        msg = "Update-or-insert cannot change its unique match values."
        raise DatabaseQueryError(msg)
    inserted = dict(attributes)
    inserted.update(values)
    unique_by = tuple(attributes)
    updates = tuple(key for key in values if key not in attributes)
    if not updates and dialect == "mysql":
        updates = (unique_by[0],)
    return inserted, unique_by, updates


def _sole_row(
    rows: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    """Require exactly one row from a result limited to at most two.

    Args:
        rows: Bounded result rows selected by ``sole``.

    Returns:
        The only matching row.

    Raises:
        ModelNotFoundError: If no row matched.
        MultipleModelsFoundError: If multiple rows matched.
    """
    if not rows:
        raise ModelNotFoundError(_NO_ROWS_FOUND)
    if len(rows) > 1:
        raise MultipleModelsFoundError(_MULTIPLE_ROWS_FOUND)
    return rows[0]


def _raise_invalid_identifier() -> NoReturn:
    """Reject identifier strings that cannot be represented safely.
    """  # fmt: skip
    msg = "Database identifiers must contain letters, digits, and underscores."
    raise DatabaseQueryError(msg)


def _raise_invalid_condition() -> NoReturn:
    """Reject condition calls that do not match a supported typed form.
    """  # fmt: skip
    msg = "The database query condition has an unsupported argument shape."
    raise DatabaseQueryError(msg)


def _integer_count(value: object | None) -> int:
    """Validate a scalar database result before exposing an integer count.

    Args:
        value: Database result returned by SQLAlchemy's integer aggregate.

    Returns:
        The aggregate count, or zero when SQL returned no scalar row.

    Raises:
        DatabaseQueryError: If the backend returns a non-integer count.
    """
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    msg = "The database returned an invalid count value."
    raise DatabaseQueryError(msg)


def _identifier_text(value: object) -> str:
    """Require a dynamic identifier value to be a Python string.

    Args:
        value: Runtime value supplied for a database identifier.

    Returns:
        A string suitable for the existing identifier grammar check.

    Raises:
        DatabaseQueryError: If the runtime value is not a string.
    """
    if not isinstance(value, str):
        _raise_invalid_identifier()
    return value


def _identifier_sequence(value: object) -> tuple[str, ...]:
    """Validate a runtime sequence of dynamic database identifier values.

    Args:
        value: Runtime value expected to be a sequence of strings.

    Returns:
        Validated names in their supplied order.

    Raises:
        DatabaseQueryError: If the value or any item is not a string.
    """
    if isinstance(value, str) or not isinstance(value, Sequence):
        _raise_invalid_identifier()
    values = cast("Sequence[object]", value)
    return tuple(_identifier_text(item) for item in values)


def _raise_unsupported_conflict_dialect(dialect: str) -> NoReturn:
    """Reject conflict operations without native dialect support.

    Args:
        dialect: Normalized SQLAlchemy backend identifier.

    Raises:
        DatabaseQueryError: Always, with a safe dialect-only message.
    """
    msg = f"Native conflict operations are unsupported for {dialect}."
    raise DatabaseQueryError(msg)


def _validate_page(per_page: int, page: int) -> None:
    """Require positive page size and one-based page numbering.

    Args:
        per_page: Requested maximum number of items.
        page: Requested one-based page number.

    Raises:
        ValueError: If either value is not a positive integer.
    """
    if type(per_page) is not int or per_page < _MINIMUM_PAGE_SIZE:
        msg = "Page size must be a positive integer."
        raise ValueError(msg)
    if type(page) is not int or page < _FIRST_PAGE:
        msg = "Page number must be a positive integer."
        raise ValueError(msg)


def _validate_batch_size(batch_size: int) -> None:
    """Require a positive integer before any stream acquires resources.

    Args:
        batch_size: Requested SQLAlchemy fetch batch size.

    Raises:
        ValueError: If the batch size is not a positive integer.
    """
    if type(batch_size) is not int or batch_size < 1:
        msg = "The stream batch size must be a positive integer."
        raise ValueError(msg)


def _chunk_rows(
    rows: Iterator[Mapping[str, object]],
    batch_size: int,
) -> Iterator[list[Mapping[str, object]]]:
    """Group a live row iterator without buffering beyond one batch.

    Args:
        rows: Live mapping iterator owned by an outer context manager.
        batch_size: Maximum number of mappings in each yielded list.

    Yields:
        Non-empty lists containing no more than ``batch_size`` mappings.
    """
    while chunk := list(islice(rows, batch_size)):
        yield chunk


def _unique_chunk_key(statement: Select[tuple[object, ...]]) -> str:
    """Choose an internal label that cannot replace a selected value.

    Args:
        statement: Current SQLAlchemy projection.

    Returns:
        A label absent from the statement's public selected columns.
    """
    selected = set(statement.selected_columns.keys())
    alias = "__titanspan_chunk_key"
    suffix = 1
    while alias in selected:
        alias = f"__titanspan_chunk_key_{suffix}"
        suffix += 1
    return alias


def _remove_chunk_key(
    rows: Sequence[Mapping[str, object]],
    key_alias: str,
) -> tuple[list[Mapping[str, object]], object]:
    """Remove an internal key projection and preserve its final value.

    Args:
        rows: Detached page rows with the internal key column.
        key_alias: Collision-free internal projection label.

    Returns:
        Public rows without the key and the last row's continuation value.

    Raises:
        DatabaseQueryError: If the key is absent or null in a result row.
    """
    visible_rows: list[Mapping[str, object]] = []
    last_key: object = _MISSING
    for row in rows:
        values = dict(row)
        last_key = values.pop(key_alias, _MISSING)
        if last_key is _MISSING or last_key is None:
            msg = "The ID chunk key must be selected and non-null."
            raise DatabaseQueryError(msg)
        visible_rows.append(values)
    return visible_rows, last_key


def _raw_clause(
    expression: str,
    bindings: Mapping[str, object] | None,
) -> TextClause:
    """Build a trusted SQL expression with explicit bound values.

    Args:
        expression: Application-authored SQL text.
        bindings: Optional named values for SQLAlchemy placeholders.

    Returns:
        A SQLAlchemy text clause with values bound separately.
    """
    clause = text(expression)
    return clause if not bindings else clause.bindparams(**dict(bindings))


def _exists_predicate(
    subquery: (
        str | TextClause | DatabaseQueryBuilder | Select[tuple[object, ...]]
    ),
) -> _Condition:
    """Build an EXISTS condition from a trusted SQLAlchemy query input.

    Args:
        subquery: Trusted SQL text, a QueryBuilder, or a Core Select.

    Returns:
        A SQLAlchemy boolean condition for the EXISTS expression.
    """
    if isinstance(subquery, DatabaseQueryBuilder):
        return cast("_Condition", sql_exists(subquery.to_statement()))
    if isinstance(subquery, str):
        text_subquery = text(subquery)
    elif isinstance(subquery, TextClause):
        text_subquery = subquery
    else:
        return cast("_Condition", sql_exists(subquery))

    selectable = text_subquery.columns().subquery()
    statement = select(1).select_from(selectable)
    return cast("_Condition", sql_exists(statement))


__all__ = ["QueryBuilder"]
