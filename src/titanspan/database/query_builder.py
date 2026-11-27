"""Build safe fluent queries with SQLAlchemy Core expressions.

Mutable builders are intended to belong to one request or operation. Clone a
builder before branching it into independent query variations.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from copy import copy
from typing import TYPE_CHECKING, Literal, cast

from sqlalchemy import (
    and_,
    column,
    delete,
    func,
    insert,
    literal_column,
    not_,
    or_,
    select,
    table,
    text,
    true,
    update,
)
from sqlalchemy import (
    exists as sql_exists,
)
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import ColumnElement, TextClause

from titanspan.contracts.database import DatabaseQueryBuilder
from titanspan.database.exceptions import DatabaseQueryError
from titanspan.database.pagination import LengthAwarePaginator, Paginator

if TYPE_CHECKING:
    from typing import NoReturn

    from sqlalchemy.sql.schema import Table
    from sqlalchemy.sql.selectable import (
        FromClause,
        Select,
        TableClause,
    )

    from titanspan.contracts.database.connection import (
        DatabaseConnectionService,
    )

type _Condition = ColumnElement[bool]
type _Projection = ColumnElement[object] | TextClause
type _Boolean = Literal["and", "or"]

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
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
        self._tables: dict[str, TableClause] = {table_key: self._table}
        self._from: FromClause = self._table
        self._selection: list[_Projection] | None = None
        self._where_groups: list[list[_Condition]] = []
        self._scope_condition: _Condition | None = None
        self._group_columns: list[ColumnElement[object]] = []
        self._having_groups: list[list[_Condition]] = []
        self._orders: list[ColumnElement[object]] = []
        self._limit: int | None = None
        self._offset: int | None = None
        self._is_distinct = False

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
        subquery: str | TextClause | QueryBuilder | Select[tuple[object, ...]],
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
        subquery: str | TextClause | QueryBuilder | Select[tuple[object, ...]],
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
        subquery: str | TextClause | QueryBuilder | Select[tuple[object, ...]],
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
        subquery: str | TextClause | QueryBuilder | Select[tuple[object, ...]],
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

    def where_in(
        self,
        column_name: str,
        values: Sequence[object],
    ) -> QueryBuilder:
        """Match a column against a bound sequence of values.

        Args:
            column_name: Safe column name or qualified name.
            values: Values passed through SQLAlchemy's expanding bind.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(
            self._column(column_name).in_(values),
            "and",
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
        values: Sequence[object],
    ) -> QueryBuilder:
        """Exclude values using a bound sequence.

        Args:
            column_name: Safe column name or qualified name.
            values: Values passed through SQLAlchemy's expanding bind.

        Returns:
            This builder for further query composition.
        """
        return self._add_where(
            self._column(column_name).not_in(values),
            "and",
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
            outer=False,
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
            outer=True,
        )

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
        if column_name is not None:
            self.order_by(column_name)
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

    def clone(self) -> QueryBuilder:
        """Copy mutable query state for an independent query branch.

        Returns:
            A builder with separate selection, filters, ordering, and limits.
        """
        cloned = copy(self)
        cloned._tables = self._tables.copy()  # noqa: SLF001  # Copy state.
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
        return cloned

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
        return cast("Select[tuple[object, ...]]", statement)

    def get(self) -> list[Mapping[str, object]]:
        """Execute the query synchronously and detach its mapping rows.

        Returns:
            Rows detached from the SQLAlchemy result and session.
        """
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
        result = await self._connection.execute_statement_async(
            self.to_statement(),
        )
        return list(result.rows)

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
        result = self._connection.execute_statement(
            self._count_statement(),
        )
        return _integer_count(_first_value(result.rows))

    async def count_async(self) -> int:
        """Count matching rows asynchronously without hydrating them.

        Returns:
            The database count for the current filters.
        """
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

    def delete(self) -> int:
        """Delete rows matching this query's conditions.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
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

    def _change_integer_column(self, column_name: str, amount: int) -> int:
        """Perform an atomic SQL increment or decrement.

        Args:
            column_name: Safe numeric column reference.
            amount: Signed delta bound by SQLAlchemy.

        Returns:
            Driver-reported affected rows, or ``-1`` when unknown.
        """
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
        outer: bool,
    ) -> QueryBuilder:
        """Add one inner or left join after validating its identifiers.

        Args:
            table_name: Safe table to join.
            left: Left column reference.
            operator_or_right: Right column or explicit operator.
            right: Optional right column when an operator is supplied.
            outer: Whether to keep unmatched rows from the existing query.

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
        self._from = self._from.join(target, condition, isouter=outer)
        return self

    def _validate_value_columns(
        self,
        values: Mapping[str, object],
    ) -> None:
        """Validate every mutation identifier before constructing a statement.

        Args:
            values: Mutation values keyed by SQL column names.
        """
        for name in values:
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

    def _column(self, reference: str) -> ColumnElement[object]:
        """Resolve a safe column reference against known query tables.

        Args:
            reference: Column, table-qualified, or schema-qualified name.

        Returns:
            A SQLAlchemy ColumnClause attached to the correct table.
        """
        parts = _identifier_parts(reference)
        if len(parts) == 1:
            source = self._table
            column_name = parts[0]
        else:
            table_key = ".".join(parts[:-1])
            source = self._tables.get(table_key)
            if source is None:
                msg = "A qualified column must refer to a table in this query."
                raise DatabaseQueryError(msg)
            column_name = parts[-1]
        if column_name not in source.c:
            if not self._allow_unknown_columns and source is self._table:
                msg = "The selected model column is not mapped."
                raise DatabaseQueryError(msg)
            source.append_column(column(column_name))
        return cast("ColumnElement[object]", source.c[column_name])

    def _ensure_table(self, name: str) -> TableClause:
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
        if not groups or boolean == "or":
            groups.append([condition])
        else:
            groups[-1].append(condition)

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
    subquery: str | TextClause | QueryBuilder | Select[tuple[object, ...]],
) -> _Condition:
    """Build an EXISTS condition from a trusted SQLAlchemy query input.

    Args:
        subquery: Trusted SQL text, a QueryBuilder, or a Core Select.

    Returns:
        A SQLAlchemy boolean condition for the EXISTS expression.
    """
    if isinstance(subquery, QueryBuilder):
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
