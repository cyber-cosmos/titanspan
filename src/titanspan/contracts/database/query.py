"""Define the backend-independent fluent database query boundary.
"""  # fmt: skip

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Literal,
    Protocol,
    Self,
    overload,
    runtime_checkable,
)

if TYPE_CHECKING:
    from collections.abc import (
        AsyncIterator,
        Callable,
        Iterator,
        Mapping,
        Sequence,
    )
    from contextlib import AbstractAsyncContextManager, AbstractContextManager

    from sqlalchemy.sql.selectable import SelectBase

    from titanspan.contracts.database.pagination import (
        CursorPage,
        LengthAwarePage,
        SimplePage,
    )


@runtime_checkable
class DatabaseJoinClause(Protocol):
    """Describe safe ON-clause comparisons for fluent joins.
    """  # fmt: skip

    def on(
        self,
        left: str,
        operator: str,
        right: str,
        *,
        boolean: Literal["and", "or"] = "and",
    ) -> Self:
        """Compare two columns inside a join condition.

        Args:
            left: Safe left column reference.
            operator: Supported comparison operator.
            right: Safe right column reference.
            boolean: Connector to the preceding clause condition.

        Returns:
            This clause for further condition composition.
        """
        ...

    def where(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = ...,
        *,
        boolean: Literal["and", "or"] = "and",
    ) -> Self:
        """Compare a join column with a bound value.

        Args:
            column_name: Safe column reference from the join.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.
            boolean: Connector to the preceding clause condition.

        Returns:
            This clause for further condition composition.
        """
        ...

    def or_where(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Compare a join column with a value using SQL OR.

        Args:
            column_name: Safe column reference from the join.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This clause for further condition composition.
        """
        ...

    def where_group(
        self,
        callback: Callable[[DatabaseJoinClause], object],
        *,
        boolean: Literal["and", "or"] = "and",
    ) -> Self:
        """Add parenthesized join conditions built by a callback.

        Args:
            callback: Synchronous function that adds grouped conditions.
            boolean: Connector to the preceding clause condition.

        Returns:
            This clause for further condition composition.
        """
        ...


@runtime_checkable
class DatabaseQueryBuilder(Protocol):
    """Describe fluent retrieval operations on one selected table.
    """  # fmt: skip

    def select(self, *columns: str) -> Self:
        """Select named or qualified table columns.

        Args:
            columns: Column names or qualified names to retrieve.

        Returns:
            This builder for further query composition.
        """
        ...

    def add_select(self, *columns: str) -> Self:
        """Append columns to the current projection.

        Args:
            columns: Column names or qualified names to append.

        Returns:
            This builder for further query composition.
        """
        ...

    def select_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
    ) -> Self:
        """Replace the projection with a named scalar subquery.

        Args:
            query: Query selecting one column and at most one row.
            alias: Safe output column name.

        Returns:
            This builder for further query composition.
        """
        ...

    def add_select_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
    ) -> Self:
        """Append a named scalar subquery to the current projection.

        Args:
            query: Query selecting one column and at most one row.
            alias: Safe output column name.

        Returns:
            This builder for further query composition.
        """
        ...

    def select_raw(
        self,
        expression: str,
        bindings: Mapping[str, object] | None = None,
    ) -> Self:
        """Append trusted SQL projection text with separately bound values.

        Args:
            expression: Application-authored SQL projection and aliases.
            bindings: Values bound independently by SQLAlchemy.

        Returns:
            This builder for further query composition.
        """
        ...

    @overload
    def where(self, column: str, value: object, /) -> Self:
        """Add an equality condition for one column.
        """  # fmt: skip
        ...

    @overload
    def where(
        self,
        column: str,
        operator: str,
        value: object,
        /,
    ) -> Self:
        """Add a comparison condition using a supported operator.
        """  # fmt: skip
        ...

    @overload
    def or_where(self, column_name: str, value: object, /) -> Self:
        """Add an equality condition joined by SQL OR.
        """  # fmt: skip
        ...

    @overload
    def or_where(
        self,
        column_name: str,
        operator: str,
        value: object,
        /,
    ) -> Self:
        """Add a comparison condition joined by SQL OR.
        """  # fmt: skip
        ...

    def or_where(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Add an equality or comparison condition joined by SQL OR.

        Args:
            column_name: Safe column name or qualified name.
            operator_or_value: Equality value or explicit operator.
            value: Value used with an explicit comparison operator.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_in(
        self,
        column_name: str,
        values: Sequence[object] | DatabaseQueryBuilder,
    ) -> Self:
        """Match a column against values or a single-column subquery.

        Args:
            column_name: Safe column name or qualified name.
            values: Values bound by SQLAlchemy or one query projection.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_in(
        self,
        column_name: str,
        values: Sequence[object] | DatabaseQueryBuilder,
    ) -> Self:
        """Match values or a subquery as an SQL OR condition.

        Args:
            column_name: Safe column name or qualified name.
            values: Bound values or a single-column query projection.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_not_in(
        self,
        column_name: str,
        values: Sequence[object] | DatabaseQueryBuilder,
    ) -> Self:
        """Exclude values using a bound sequence or subquery.

        Args:
            column_name: Safe column name or qualified name.
            values: Values bound by SQLAlchemy or one query projection.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_not_in(
        self,
        column_name: str,
        values: Sequence[object] | DatabaseQueryBuilder,
    ) -> Self:
        """Exclude values or a subquery through SQL OR.

        Args:
            column_name: Safe column name or qualified name.
            values: Bound values or a single-column query projection.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_between(
        self,
        column_name: str,
        lower: object,
        upper: object,
    ) -> Self:
        """Match a value inside an inclusive range.

        Args:
            column_name: Safe column name or qualified name.
            lower: Inclusive lower bound.
            upper: Inclusive upper bound.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_column(
        self,
        left: str,
        operator: str,
        right: str,
    ) -> Self:
        """Compare two validated column references.

        Args:
            left: Safe left column name or qualified name.
            operator: Supported comparison operator.
            right: Safe right column name or qualified name.

        Returns:
            This builder for further query composition.
        """
        ...

    @overload
    def where(self, conditions: Mapping[str, object], /) -> Self:
        """Add equality conditions from a mapping.
        """  # fmt: skip
        ...

    @overload
    def where(
        self,
        callback: Callable[[DatabaseQueryBuilder], object],
        /,
    ) -> Self:
        """Add a parenthesized group built by a callback.
        """  # fmt: skip
        ...

    def where(
        self,
        column: str | Mapping[str, object] | Callable[..., object],
        operator_or_value: object = ...,
        value: object = ...,
    ) -> Self:
        """Add an equality, comparison, mapping, or grouped condition.

        Args:
            column: Column name, equality mapping, or grouping callback.
            operator_or_value: Value for equality or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_null(self, column_name: str) -> Self:
        """Require one column to contain SQL NULL.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_not_null(self, column_name: str) -> Self:
        """Require one column not to contain SQL NULL.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_date(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Compare the date portion using a supported database expression.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_date(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Compare the date portion as an SQL OR predicate.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_time(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Compare the time portion through a supported dialect expression.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_time(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Compare the time portion as an SQL OR predicate.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_year(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Compare the year extracted from a temporal column.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_month(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Compare the month extracted from a temporal column.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_day(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Compare the day extracted from a temporal column.

        Args:
            column_name: Safe date or timestamp column reference.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_row_values(
        self,
        columns: Sequence[str],
        operator: str,
        values: Sequence[object],
    ) -> Self:
        """Compare ordered column and value tuples.

        Args:
            columns: Ordered, safe column references.
            operator: Supported comparison operator.
            values: Bound values matching the column count.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_row_values(
        self,
        columns: Sequence[str],
        operator: str,
        values: Sequence[object],
    ) -> Self:
        """Compare ordered tuples through SQL OR.

        Args:
            columns: Ordered, safe column references.
            operator: Supported comparison operator.
            values: Bound values matching the column count.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_json_value(
        self,
        column_name: str,
        path: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Compare a scalar at a validated JSON object path.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object keys using identifier characters.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_json_value(
        self,
        column_name: str,
        path: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Compare a scalar at a JSON path as an SQL OR predicate.

        Args:
            column_name: Safe JSON column reference.
            path: Dot-separated object keys using identifier characters.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_raw(
        self,
        expression: str,
        bindings: Mapping[str, object] | None = None,
    ) -> Self:
        """Add trusted SQL predicate text with separately bound values.

        Args:
            expression: Application-authored SQL predicate.
            bindings: Values bound independently by SQLAlchemy.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_raw(
        self,
        expression: str,
        bindings: Mapping[str, object] | None = None,
    ) -> Self:
        """Add a trusted bound SQL predicate joined by SQL OR.

        Args:
            expression: Application-authored SQL predicate.
            bindings: Values bound independently by SQLAlchemy.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_exists(
        self,
        subquery: str | DatabaseQueryBuilder,
    ) -> Self:
        """Require a trusted SQL or fluent EXISTS subquery to return rows.

        Args:
            subquery: Trusted SQL text or a fluent query builder.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_not_exists(
        self,
        subquery: str | DatabaseQueryBuilder,
    ) -> Self:
        """Require a trusted SQL or fluent EXISTS subquery to return none.

        Args:
            subquery: Trusted SQL text or a fluent query builder.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_exists(
        self,
        subquery: str | DatabaseQueryBuilder,
    ) -> Self:
        """Add an OR condition for a fluent or trusted SQL EXISTS query.

        Args:
            subquery: Trusted SQL text or a fluent query builder.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_not_exists(
        self,
        subquery: str | DatabaseQueryBuilder,
    ) -> Self:
        """Add an OR condition for a subquery that returns no rows.

        Args:
            subquery: Trusted SQL text or a fluent query builder.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_not(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Add a negated comparison joined by SQL OR.

        Args:
            column_name: Safe column name or qualified name.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_not_between(
        self,
        column_name: str,
        lower: object,
        upper: object,
    ) -> Self:
        """Exclude values in an inclusive range.

        Args:
            column_name: Safe column name or qualified name.
            lower: Inclusive lower range bound.
            upper: Inclusive upper range bound.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_like(self, column_name: str, pattern: str) -> Self:
        """Match a text column with a bound SQL LIKE pattern.

        Args:
            column_name: Safe column name or qualified name.
            pattern: Bound SQL LIKE pattern.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_not_like(self, column_name: str, pattern: str) -> Self:
        """Exclude values matching a bound SQL LIKE pattern.

        Args:
            column_name: Safe column name or qualified name.
            pattern: Bound SQL LIKE pattern.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_like(self, column_name: str, pattern: str) -> Self:
        """Match a LIKE pattern and join the condition with SQL OR.

        Args:
            column_name: Safe column name or qualified name.
            pattern: Bound SQL LIKE pattern.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_not_like(self, column_name: str, pattern: str) -> Self:
        """Exclude a LIKE pattern and join the condition with SQL OR.

        Args:
            column_name: Safe column name or qualified name.
            pattern: Bound SQL LIKE pattern.

        Returns:
            This builder for further query composition.
        """
        ...

    def order_by(
        self,
        column_name: str,
        *,
        descending: bool = False,
    ) -> Self:
        """Order by a validated column name.

        Args:
            column_name: Safe column name or qualified name.
            descending: Whether to sort from highest value to lowest.

        Returns:
            This builder for further query composition.
        """
        ...

    def latest(self, column_name: str = "created_at") -> Self:
        """Order a timestamp column from newest to oldest.

        Args:
            column_name: Safe timestamp column name.

        Returns:
            This builder for further query composition.
        """
        ...

    def oldest(self, column_name: str = "created_at") -> Self:
        """Order a timestamp column from oldest to newest.

        Args:
            column_name: Safe timestamp column name.

        Returns:
            This builder for further query composition.
        """
        ...

    def reorder(self, column_name: str | None = None) -> Self:
        """Clear current ordering and optionally add one ascending order.

        Args:
            column_name: Optional safe column name.

        Returns:
            This builder for further query composition.
        """
        ...

    def in_random_order(self) -> Self:
        """Append backend-native random ordering to the query.

        Returns:
            This builder for further query composition.
        """
        ...

    def join(
        self,
        table_name: str,
        left: str,
        operator_or_right: str,
        right: str | object = ...,
    ) -> Self:
        """Join a table using validated column comparison expressions.

        Args:
            table_name: Safe joined table name.
            left: Left column reference.
            operator_or_right: Right column or comparison operator.
            right: Optional right column when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def join_with(
        self,
        table_name: str,
        callback: Callable[[DatabaseJoinClause], object],
        *,
        join_type: Literal["inner", "left", "right", "full"] = "inner",
    ) -> Self:
        """Join a table using a composed ON condition.

        Args:
            table_name: Safe joined table name.
            callback: Synchronous function that defines the ON conditions.
            join_type: Supported join preservation behavior.

        Returns:
            This builder for further query composition.
        """
        ...

    def left_join(
        self,
        table_name: str,
        left: str,
        operator_or_right: str,
        right: str | object = ...,
    ) -> Self:
        """Left-join a table using validated column comparisons.

        Args:
            table_name: Safe joined table name.
            left: Left column reference.
            operator_or_right: Right column or comparison operator.
            right: Optional right column when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def right_join(
        self,
        table_name: str,
        left: str,
        operator_or_right: str,
        right: str | object = ...,
    ) -> Self:
        """Right-join a table where the configured dialect supports it.

        SQLAlchemy reverses the join sides and uses a left outer join.

        Args:
            table_name: Safe joined table name.
            left: Left column reference.
            operator_or_right: Right column or comparison operator.
            right: Right column when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def full_outer_join(
        self,
        table_name: str,
        left: str,
        operator_or_right: str,
        right: str | object = ...,
    ) -> Self:
        """Join both sides where the configured dialect supports it.

        PostgreSQL and SQLite 3.39 or later support full outer joins.

        Args:
            table_name: Safe joined table name.
            left: Left column reference.
            operator_or_right: Right column or comparison operator.
            right: Right column when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def join_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
        left: str,
        operator_or_right: str,
        right: str | object = ...,
    ) -> Self:
        """Join a composed query using a safe local alias.

        Args:
            query: Query whose statement becomes a subquery.
            alias: Safe alias exposed to selected expressions.
            left: Safe left column reference.
            operator_or_right: Right column or comparison operator.
            right: Right column when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def left_join_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
        left: str,
        operator_or_right: str,
        right: str | object = ...,
    ) -> Self:
        """Left-join a composed query using a safe local alias.

        Args:
            query: Query whose statement becomes a subquery.
            alias: Safe alias exposed to selected expressions.
            left: Safe left column reference.
            operator_or_right: Right column or comparison operator.
            right: Right column when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def right_join_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
        left: str,
        operator_or_right: str,
        right: str | object = ...,
    ) -> Self:
        """Right-join a query using a safe local alias.

        Args:
            query: Builder whose projection becomes a subquery.
            alias: Safe alias exposed to selected expressions.
            left: Left column reference.
            operator_or_right: Right column or comparison operator.
            right: Right column when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def full_outer_join_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
        left: str,
        operator_or_right: str,
        right: str | object = ...,
    ) -> Self:
        """Full-outer-join a query using a safe local alias.

        Args:
            query: Builder whose projection becomes a subquery.
            alias: Safe alias exposed to selected expressions.
            left: Left column reference.
            operator_or_right: Right column or comparison operator.
            right: Right column when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def cross_join_sub(
        self,
        query: DatabaseQueryBuilder,
        alias: str,
    ) -> Self:
        """Cross-join a query using a safe local alias.

        Args:
            query: Builder whose projection becomes a subquery.
            alias: Safe alias exposed to selected expressions.

        Returns:
            This builder for further query composition.
        """
        ...

    def cross_join(self, table_name: str) -> Self:
        """Join every row from the named table to every current row.

        Args:
            table_name: Safe joined table name.

        Returns:
            This builder for further query composition.
        """
        ...

    def lock_for_update(
        self,
        *,
        nowait: bool = False,
        skip_locked: bool = False,
    ) -> Self:
        """Request an exclusive row lock inside an active transaction.

        Args:
            nowait: Fail immediately when a selected row is already locked.
            skip_locked: Omit rows held by another transaction.

        Returns:
            This builder for further query composition.
        """
        ...

    def shared_lock(
        self,
        *,
        nowait: bool = False,
        skip_locked: bool = False,
    ) -> Self:
        """Request a shared row lock inside an active transaction.

        Args:
            nowait: Fail immediately when a selected row is already locked.
            skip_locked: Omit rows held by another transaction.

        Returns:
            This builder for further query composition.
        """
        ...

    def limit(self, count: int | None) -> Self:
        """Limit the number of retrieved rows.

        Args:
            count: Non-negative maximum or ``None`` to clear the limit.

        Returns:
            This builder for further query composition.
        """
        ...

    def offset(self, count: int) -> Self:
        """Skip a non-negative number of retrieved rows.

        Args:
            count: Number of rows to skip.

        Returns:
            This builder for further query composition.
        """
        ...

    def group_by(self, *columns: str) -> Self:
        """Group result rows by safe column references.

        Args:
            columns: Grouping columns.

        Returns:
            This builder for further query composition.
        """
        ...

    def having(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Filter grouped rows with a bound comparison.

        Args:
            column_name: Safe grouped column reference.
            operator_or_value: Equality value or explicit operator.
            value: Value used with an explicit comparison operator.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_having(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = ...,
    ) -> Self:
        """Filter grouped rows with a comparison joined by SQL OR.

        Args:
            column_name: Safe selected or grouped column.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further query composition.
        """
        ...

    def take(self, count: int | None) -> Self:
        """Limit the number of retrieved rows.

        Args:
            count: Non-negative maximum or ``None`` to clear the limit.

        Returns:
            This builder for further query composition.
        """
        ...

    def skip(self, count: int) -> Self:
        """Skip a non-negative number of retrieved rows.

        Args:
            count: Number of rows to skip.

        Returns:
            This builder for further query composition.
        """
        ...

    def when(
        self,
        condition: object,
        callback: Callable[[Self], object],
        default: Callable[[Self], object] | None = None,
    ) -> Self:
        """Apply a query transformation when the condition is truthy.

        Args:
            condition: Value tested using Python truthiness.
            callback: Transformation selected for a truthy value.
            default: Optional transformation selected otherwise.

        Returns:
            This builder for further query composition.
        """
        ...

    def unless(
        self,
        condition: object,
        callback: Callable[[Self], object],
        default: Callable[[Self], object] | None = None,
    ) -> Self:
        """Apply a query transformation when the condition is falsey.

        Args:
            condition: Value tested using Python truthiness.
            callback: Transformation selected for a falsey value.
            default: Optional transformation selected otherwise.

        Returns:
            This builder for further query composition.
        """
        ...

    def clone(self) -> Self:
        """Copy builder state before composing an independent query branch.

        Returns:
            A builder with isolated mutable query lists.
        """
        ...

    def subquery(self, table_name: str) -> DatabaseQueryBuilder:
        """Start a query correlated to this builder's visible table sources.

        Args:
            table_name: Safe table name for the subquery's FROM clause.

        Returns:
            A new builder sharing this query's visible table references.
        """
        ...

    def to_statement(self) -> SelectBase:
        """Expose the composed statement for explicit SQLAlchemy interop.

        Returns:
            A SQLAlchemy statement representing the current query.
        """
        ...

    def with_cte(
        self,
        name: str,
        query: DatabaseQueryBuilder,
        *,
        recursive: bool = False,
    ) -> Self:
        """Attach a SQLAlchemy common table expression.

        Args:
            name: Safe CTE name used by the query's FROM clause.
            query: Query defining the CTE statement.
            recursive: Whether to create a recursive CTE.

        Returns:
            This builder for further query composition.
        """
        ...

    def union(self, query: DatabaseQueryBuilder) -> Self:
        """Combine this query with another and remove duplicate rows.

        Args:
            query: Query selecting compatible columns.

        Returns:
            This builder with the union result as its source.
        """
        ...

    def union_all(self, query: DatabaseQueryBuilder) -> Self:
        """Combine this query with another while preserving duplicates.

        Args:
            query: Query selecting compatible columns.

        Returns:
            This builder with the union result as its source.
        """
        ...

    def get(self) -> list[Mapping[str, object]]:
        """Execute and return detached mapping rows.

        Returns:
            Rows copied out of the completed database result.
        """
        ...

    async def get_async(self) -> list[Mapping[str, object]]:
        """Execute asynchronously and return detached mapping rows.

        Returns:
            Rows copied out of the completed database result.
        """
        ...

    def cursor(
        self,
        *,
        batch_size: int = 1000,
    ) -> AbstractContextManager[Iterator[Mapping[str, object]]]:
        """Open a bounded sync stream owned by the returned context manager.

        Args:
            batch_size: Positive maximum buffer size used by SQLAlchemy.

        Returns:
            A context manager yielding rows until it is closed.
        """
        ...

    def cursor_async(
        self,
        *,
        batch_size: int = 1000,
    ) -> AbstractAsyncContextManager[AsyncIterator[Mapping[str, object]]]:
        """Open a bounded async stream owned by the returned context manager.

        Args:
            batch_size: Positive maximum buffer size used by SQLAlchemy.

        Returns:
            An async context manager yielding rows until it is closed.
        """
        ...

    def chunks(
        self,
        batch_size: int = 1000,
    ) -> AbstractContextManager[Iterator[list[Mapping[str, object]]]]:
        """Yield bounded groups of rows from a sync cursor.

        Args:
            batch_size: Positive number of rows yielded in each group.

        Returns:
            A context manager yielding bounded row lists.
        """
        ...

    def chunks_async(
        self,
        batch_size: int = 1000,
    ) -> AbstractAsyncContextManager[AsyncIterator[list[Mapping[str, object]]]]:
        """Yield bounded groups of rows from an async cursor.

        Args:
            batch_size: Positive number of rows yielded in each group.

        Returns:
            An async context manager yielding bounded row lists.
        """
        ...

    def chunks_by_id(
        self,
        batch_size: int = 1000,
        *,
        key_column: str = "id",
    ) -> Iterator[list[Mapping[str, object]]]:
        """Yield bounded pages using a unique key for continuation.

        Args:
            batch_size: Maximum number of rows per page.
            key_column: Unique, non-null, orderable key column.

        Yields:
            Detached rows in ascending key order.
        """
        ...

    def chunks_by_id_async(
        self,
        batch_size: int = 1000,
        *,
        key_column: str = "id",
    ) -> AsyncIterator[list[Mapping[str, object]]]:
        """Asynchronously yield bounded unique-key continuation pages.

        Args:
            batch_size: Maximum number of rows per page.
            key_column: Unique, non-null, orderable key column.

        Yields:
            Detached rows in ascending key order.
        """
        ...

    def first(self) -> Mapping[str, object] | None:
        """Return the first result row or ``None``.

        Returns:
            The first detached row when one exists.
        """
        ...

    async def first_async(self) -> Mapping[str, object] | None:
        """Return the first row asynchronously or ``None``.

        Returns:
            The first detached row when one exists.
        """
        ...

    def first_or_fail(self) -> Mapping[str, object]:
        """Return the first row or raise a native not-found error.

        Returns:
            The first detached row.
        """
        ...

    async def first_or_fail_async(self) -> Mapping[str, object]:
        """Asynchronously return the first row or raise not found.

        Returns:
            The first detached row.
        """
        ...

    def find(
        self,
        identifier: object,
        *,
        key_column: str = "id",
    ) -> Mapping[str, object] | None:
        """Find a row by a bound value in a validated key column.

        Args:
            identifier: Key value to match.
            key_column: Validated column name used as the key.

        Returns:
            The matching detached row or ``None``.
        """
        ...

    async def find_async(
        self,
        identifier: object,
        *,
        key_column: str = "id",
    ) -> Mapping[str, object] | None:
        """Asynchronously find a row by a bound key value.

        Args:
            identifier: Key value to match.
            key_column: Validated column name used as the key.

        Returns:
            The matching detached row or ``None``.
        """
        ...

    def find_many(
        self,
        identifiers: Sequence[object],
        *,
        key_column: str = "id",
    ) -> list[Mapping[str, object]]:
        """Find rows whose key appears in a bound sequence.

        Args:
            identifiers: Key values to match.
            key_column: Validated column name used as the key.

        Returns:
            Matching detached rows.
        """
        ...

    async def find_many_async(
        self,
        identifiers: Sequence[object],
        *,
        key_column: str = "id",
    ) -> list[Mapping[str, object]]:
        """Asynchronously find rows matching a bound key sequence.

        Args:
            identifiers: Key values to match.
            key_column: Validated column name used as the key.

        Returns:
            Matching detached rows.
        """
        ...

    def sole(self) -> Mapping[str, object]:
        """Require one and only one matching row.

        Returns:
            The sole detached row.
        """
        ...

    async def sole_async(self) -> Mapping[str, object]:
        """Asynchronously require one and only one matching row.

        Returns:
            The sole detached row.
        """
        ...

    def sole_value(self, column_name: str) -> object:
        """Return one column value when exactly one row matches.

        Args:
            column_name: Safe column name to retrieve.

        Returns:
            The selected value from the sole matching row.
        """
        ...

    async def sole_value_async(self, column_name: str) -> object:
        """Asynchronously return one value from the sole matching row.

        Args:
            column_name: Safe column name to retrieve.

        Returns:
            The selected value from the sole matching row.
        """
        ...

    def value(self, column_name: str) -> object | None:
        """Return one selected column from the first matching row.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            The selected value or ``None`` if no row matches.
        """
        ...

    async def value_async(self, column_name: str) -> object | None:
        """Asynchronously return one selected column value.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            The selected value or ``None`` if no row matches.
        """
        ...

    def pluck(
        self,
        column_name: str,
        key: str | None = None,
    ) -> list[object] | dict[object, object]:
        """Retrieve values from one column or map them by another column.

        Args:
            column_name: Safe value column name.
            key: Optional safe key column name.

        Returns:
            Values in row order or a mapping when ``key`` is supplied.
        """
        ...

    async def pluck_async(
        self,
        column_name: str,
        key: str | None = None,
    ) -> list[object] | dict[object, object]:
        """Asynchronously retrieve values from one or two columns.

        Args:
            column_name: Safe value column name.
            key: Optional safe key column name.

        Returns:
            Values in row order or a mapping when ``key`` is supplied.
        """
        ...

    def count(self) -> int:
        """Return the database-side count for the current filters.

        Returns:
            The number of matching rows.
        """
        ...

    async def count_async(self) -> int:
        """Return the database-side count asynchronously.

        Returns:
            The number of matching rows.
        """
        ...

    def paginate(
        self,
        per_page: int = 15,
        *,
        page: int = 1,
    ) -> LengthAwarePage[Mapping[str, object]]:
        """Retrieve page rows and the exact total count.

        Args:
            per_page: Positive maximum page size.
            page: Positive one-based page number.

        Returns:
            Page items and total-count navigation metadata.
        """
        ...

    async def paginate_async(
        self,
        per_page: int = 15,
        *,
        page: int = 1,
    ) -> LengthAwarePage[Mapping[str, object]]:
        """Asynchronously retrieve page rows and the exact total count.

        Args:
            per_page: Positive maximum page size.
            page: Positive one-based page number.

        Returns:
            Page items and total-count navigation metadata.
        """
        ...

    def simple_paginate(
        self,
        per_page: int = 15,
        *,
        page: int = 1,
    ) -> SimplePage[Mapping[str, object]]:
        """Retrieve page rows without an exact total-count query.

        Args:
            per_page: Positive maximum page size.
            page: Positive one-based page number.

        Returns:
            Page items and a bounded next-page indicator.
        """
        ...

    async def simple_paginate_async(
        self,
        per_page: int = 15,
        *,
        page: int = 1,
    ) -> SimplePage[Mapping[str, object]]:
        """Asynchronously retrieve rows with a bounded lookahead.

        Args:
            per_page: Positive maximum page size.
            page: Positive one-based page number.

        Returns:
            Page items and a bounded next-page indicator.
        """
        ...

    def cursor_paginate(
        self,
        per_page: int = 15,
        *,
        cursor: str | None = None,
        key_column: str = "id",
    ) -> CursorPage[Mapping[str, object]]:
        """Retrieve a page using validated keyset cursor navigation.

        Args:
            per_page: Positive maximum number of page rows.
            cursor: Optional opaque cursor returned by a prior page.
            key_column: Unique, non-null tie-breaker column.

        Returns:
            Cursor page items and navigation tokens.
        """
        ...

    async def cursor_paginate_async(
        self,
        per_page: int = 15,
        *,
        cursor: str | None = None,
        key_column: str = "id",
    ) -> CursorPage[Mapping[str, object]]:
        """Asynchronously retrieve a keyset-paginated page.

        Args:
            per_page: Positive maximum number of page rows.
            cursor: Optional opaque cursor returned by a prior page.
            key_column: Unique, non-null tie-breaker column.

        Returns:
            Cursor page items and navigation tokens.
        """
        ...

    def sum(self, column_name: str) -> object | None:
        """Sum a safe numeric column in the database.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            The database sum, or ``None`` when no values are present.
        """
        ...

    async def sum_async(self, column_name: str) -> object | None:
        """Sum a safe numeric column asynchronously.

        Args:
            column_name: Safe column name or qualified name.

        Returns:
            The database sum, or ``None`` when no values are present.
        """
        ...

    def avg(self, column_name: str) -> object | None:
        """Average one safe numeric column in the database.

        Args:
            column_name: Safe numeric column name.

        Returns:
            The aggregate value or ``None`` when no values are present.
        """
        ...

    async def avg_async(self, column_name: str) -> object | None:
        """Asynchronously average one safe numeric column.

        Args:
            column_name: Safe numeric column name.

        Returns:
            The aggregate value or ``None`` when no values are present.
        """
        ...

    def min(self, column_name: str) -> object | None:
        """Return the minimum value of one safe column.

        Args:
            column_name: Safe selected column.

        Returns:
            The aggregate value or ``None`` when no values are present.
        """
        ...

    async def min_async(self, column_name: str) -> object | None:
        """Asynchronously return the minimum selected value.

        Args:
            column_name: Safe selected column.

        Returns:
            The aggregate value or ``None`` when no values are present.
        """
        ...

    def max(self, column_name: str) -> object | None:
        """Return the maximum value of one safe column.

        Args:
            column_name: Safe selected column.

        Returns:
            The aggregate value or ``None`` when no values are present.
        """
        ...

    async def max_async(self, column_name: str) -> object | None:
        """Asynchronously return the maximum selected value.

        Args:
            column_name: Safe selected column.

        Returns:
            The aggregate value or ``None`` when no values are present.
        """
        ...

    def exists(self) -> bool:
        """Return whether any row matches the current filters.

        Returns:
            ``True`` when a matching row exists.
        """
        ...

    async def exists_async(self) -> bool:
        """Check asynchronously whether a matching row exists.

        Returns:
            ``True`` when a matching row exists.
        """
        ...

    def doesnt_exist(self) -> bool:
        """Return whether no row matches the current filters.

        Returns:
            ``True`` when no matching row exists.
        """
        ...

    async def doesnt_exist_async(self) -> bool:
        """Asynchronously check whether no row matches the filters.

        Returns:
            ``True`` when no matching row exists.
        """
        ...

    def insert(self, values: Mapping[str, object]) -> bool:
        """Insert one row with bound values.

        Args:
            values: Safe column names and their values.

        Returns:
            ``True`` when the database accepts the statement.
        """
        ...

    async def insert_async(self, values: Mapping[str, object]) -> bool:
        """Insert one row asynchronously with bound values.

        Args:
            values: Safe column names and their values.

        Returns:
            ``True`` when the database accepts the statement.
        """
        ...

    def insert_returning(
        self,
        values: Mapping[str, object],
        *columns: str,
    ) -> list[Mapping[str, object]]:
        """Insert one row and return selected database-produced values.

        Args:
            values: Safe column names and values.
            columns: Safe columns returned by the database.

        Returns:
            Detached database rows.
        """
        ...

    async def insert_returning_async(
        self,
        values: Mapping[str, object],
        *columns: str,
    ) -> list[Mapping[str, object]]:
        """Asynchronously insert a row and return selected values.

        Args:
            values: Safe column names and values.
            columns: Safe columns returned by the database.

        Returns:
            Detached database rows.
        """
        ...

    def insert_get_id(
        self,
        values: Mapping[str, object],
        *,
        key_column: str = "id",
    ) -> object:
        """Insert one row and return its generated or supplied key.

        Args:
            values: Values for the inserted row.
            key_column: Safe key column returned by the database.

        Returns:
            The inserted key value.
        """
        ...

    async def insert_get_id_async(
        self,
        values: Mapping[str, object],
        *,
        key_column: str = "id",
    ) -> object:
        """Asynchronously insert a row and return its database key.

        Args:
            values: Values for the inserted row.
            key_column: Safe key column returned by the database.

        Returns:
            The inserted key value.
        """
        ...

    def insert_using(
        self,
        columns: Sequence[str],
        query: DatabaseQueryBuilder,
    ) -> int:
        """Insert a selected source query into safe target columns.

        Args:
            columns: Target column names in projection order.
            query: Source query selecting the same number of expressions.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.
        """
        ...

    async def insert_using_async(
        self,
        columns: Sequence[str],
        query: DatabaseQueryBuilder,
    ) -> int:
        """Asynchronously insert rows selected by a source query.

        Args:
            columns: Target column names in projection order.
            query: Source query selecting the same number of expressions.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.
        """
        ...

    def insert_many(self, rows: Sequence[Mapping[str, object]]) -> int:
        """Insert rows through SQLAlchemy Core executemany behavior.

        Args:
            rows: Row mappings with compatible columns.

        Returns:
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...

    async def insert_many_async(
        self,
        rows: Sequence[Mapping[str, object]],
    ) -> int:
        """Insert rows asynchronously through SQLAlchemy Core.

        Args:
            rows: Row mappings with compatible columns.

        Returns:
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...

    def insert_or_ignore(
        self,
        rows: Sequence[Mapping[str, object]],
    ) -> int:
        """Insert rows and ignore supported unique-key conflicts.

        Args:
            rows: Row mappings with the same inserted columns.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.
        """
        ...

    async def insert_or_ignore_async(
        self,
        rows: Sequence[Mapping[str, object]],
    ) -> int:
        """Insert rows asynchronously and ignore supported conflicts.

        Args:
            rows: Row mappings with the same inserted columns.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.
        """
        ...

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
        """
        ...

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
        """
        ...

    def update_or_insert(
        self,
        attributes: Mapping[str, object],
        values: Mapping[str, object],
    ) -> int:
        """Insert or update using attributes matching a unique constraint.

        Args:
            attributes: Unique match values.
            values: Non-key values inserted or updated.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.
        """
        ...

    async def update_or_insert_async(
        self,
        attributes: Mapping[str, object],
        values: Mapping[str, object],
    ) -> int:
        """Asynchronously insert or update a unique-key row.

        Args:
            attributes: Unique match values.
            values: Non-key values inserted or updated.

        Returns:
            Driver-reported affected rows, or ``-1`` when unavailable.
        """
        ...

    def update(self, values: Mapping[str, object]) -> int:
        """Update matching rows with bound replacement values.

        Args:
            values: Safe column names and their new values.

        Returns:
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...

    async def update_async(self, values: Mapping[str, object]) -> int:
        """Update matching rows asynchronously.

        Args:
            values: Safe column names and their new values.

        Returns:
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...

    def update_returning(
        self,
        values: Mapping[str, object],
        *columns: str,
    ) -> list[Mapping[str, object]]:
        """Update matching rows and return selected changed values.

        Args:
            values: Safe column names and replacement values.
            columns: Safe columns returned by the database.

        Returns:
            Detached database rows.
        """
        ...

    async def update_returning_async(
        self,
        values: Mapping[str, object],
        *columns: str,
    ) -> list[Mapping[str, object]]:
        """Asynchronously update rows and return selected values.

        Args:
            values: Safe column names and replacement values.
            columns: Safe columns returned by the database.

        Returns:
            Detached database rows.
        """
        ...

    def delete(self) -> int:
        """Delete rows that match the query's current conditions.

        Returns:
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...

    async def delete_async(self) -> int:
        """Delete matching rows asynchronously.

        Returns:
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...

    def delete_returning(
        self,
        *columns: str,
    ) -> list[Mapping[str, object]]:
        """Delete matching rows and return selected deleted values.

        Args:
            columns: Safe columns returned by the database.

        Returns:
            Detached database rows.
        """
        ...

    async def delete_returning_async(
        self,
        *columns: str,
    ) -> list[Mapping[str, object]]:
        """Asynchronously delete matching rows and return selected values.

        Args:
            columns: Safe columns returned by the database.

        Returns:
            Detached database rows.
        """
        ...

    def increment(self, column_name: str, amount: int = 1) -> int:
        """Atomically increment a numeric column for matching rows.

        Args:
            column_name: Safe numeric column name.
            amount: Integer delta to add.

        Returns:
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...

    def decrement(self, column_name: str, amount: int = 1) -> int:
        """Atomically decrement a numeric column for matching rows.

        Args:
            column_name: Safe numeric column name.
            amount: Integer delta to subtract.

        Returns:
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...

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
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...

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
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...

    def increment_each(self, amounts: Mapping[str, int]) -> int:
        """Atomically increment multiple columns in one update.

        Args:
            amounts: Safe column names mapped to non-negative integer deltas.

        Returns:
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...

    def decrement_each(self, amounts: Mapping[str, int]) -> int:
        """Atomically decrement multiple columns in one update.

        Args:
            amounts: Safe column names mapped to non-negative integer deltas.

        Returns:
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...

    async def increment_each_async(
        self,
        amounts: Mapping[str, int],
    ) -> int:
        """Asynchronously increment multiple columns in one update.

        Args:
            amounts: Safe column names mapped to non-negative integer deltas.

        Returns:
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...

    async def decrement_each_async(
        self,
        amounts: Mapping[str, int],
    ) -> int:
        """Asynchronously decrement multiple columns in one update.

        Args:
            amounts: Safe column names mapped to non-negative integer deltas.

        Returns:
            Driver-reported row count, or ``-1`` when unavailable.
        """
        ...
