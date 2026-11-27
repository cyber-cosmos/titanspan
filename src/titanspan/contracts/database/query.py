"""Define the backend-independent fluent database query boundary.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Self, overload, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from titanspan.contracts.database.pagination import (
        LengthAwarePage,
        SimplePage,
    )


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
        values: Sequence[object],
    ) -> Self:
        """Match a column against a bound sequence of values.

        Args:
            column_name: Safe column name or qualified name.
            values: Values bound by SQLAlchemy.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_not_in(
        self,
        column_name: str,
        values: Sequence[object],
    ) -> Self:
        """Exclude values using a bound sequence.

        Args:
            column_name: Safe column name or qualified name.
            values: Values bound by SQLAlchemy.

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

    def where_exists(self, subquery: str) -> Self:
        """Require an application-authored EXISTS subquery to return rows.

        Args:
            subquery: Trusted SQL subquery text.

        Returns:
            This builder for further query composition.
        """
        ...

    def where_not_exists(self, subquery: str) -> Self:
        """Require an application-authored EXISTS subquery to return none.

        Args:
            subquery: Trusted SQL subquery text.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_exists(self, subquery: str) -> Self:
        """Add an OR condition for a subquery that returns rows.

        Args:
            subquery: Trusted SQL subquery text.

        Returns:
            This builder for further query composition.
        """
        ...

    def or_where_not_exists(self, subquery: str) -> Self:
        """Add an OR condition for a subquery that returns no rows.

        Args:
            subquery: Trusted SQL subquery text.

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

    def cross_join(self, table_name: str) -> Self:
        """Join every row from the named table to every current row.

        Args:
            table_name: Safe joined table name.

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

    def clone(self) -> Self:
        """Copy builder state before composing an independent query branch.

        Returns:
            A builder with isolated mutable query lists.
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
