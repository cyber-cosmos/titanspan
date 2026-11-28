"""Build typed model queries over the shared SQLAlchemy Core expressions.

The wrapper adds model hydration and ORM loading while QueryBuilder remains
the source of identifiers, predicates, joins, ordering, and SQL statements.
"""

from __future__ import annotations

from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Generator,
    Iterator,
    Mapping,
)
from contextlib import asynccontextmanager, contextmanager
from copy import copy
from datetime import UTC, datetime
from typing import TYPE_CHECKING, NoReturn, Self, cast

import anyio
from sqlalchemy import and_, func, literal, not_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import (
    MappedSQLExpression,
    load_only,
    raiseload,
    selectinload,
    with_expression,
    with_loader_criteria,
)
from sqlalchemy.sql.elements import ColumnElement

from titanspan.database.exceptions import (
    DatabaseQueryError,
    ModelNotFoundError,
    MultipleModelsFoundError,
)
from titanspan.database.model_collection import ModelCollection
from titanspan.database.model_state import remember_service_graph
from titanspan.database.pagination import (
    CursorPaginator,
    LengthAwarePaginator,
    Paginator,
)
from titanspan.database.query_builder import QueryBuilder

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy.engine import ScalarResult
    from sqlalchemy.ext.asyncio import AsyncScalarResult
    from sqlalchemy.orm import Mapper, QueryableAttribute, RelationshipProperty
    from sqlalchemy.orm.strategy_options import Load
    from sqlalchemy.sql.base import ExecutableOption
    from sqlalchemy.sql.schema import Table
    from sqlalchemy.sql.selectable import FromClause, Select, TableClause

    from titanspan.contracts.database import DatabaseService

_MISSING = object()
_NO_MODELS_FOUND = "The query did not match a model."
_MULTIPLE_MODELS_FOUND = "The query matched more than one model."
_FIRST_PAGE = 1
_MINIMUM_PAGE_SIZE = 1
_DEFAULT_STREAM_BATCH_SIZE = 1000
_INVALID_GLOBAL_SCOPES_ERROR = (
    "Global model scopes must be named SQLAlchemy predicate factories."
)
_INVALID_EAGER_CONSTRAINT_ERROR = (
    "An eager-load constraint must return its related query builder."
)
_INVALID_STREAM_BATCH_SIZE_ERROR = (
    "Model stream batch size must be a positive integer."
)
_REPEATED_RELATIONSHIP_AGGREGATE_TABLE_ERROR = (
    "Relationship aggregate paths cannot revisit a mapped table."
)
_RELATIONSHIP_SECONDARY_JOIN_ERROR = (
    "The relationship has no secondary join expression."
)


class ModelQueryBuilder[ModelT]:
    """Compose fluent database expressions and hydrate mapped models.

    Query predicates and statement construction are delegated to the native
    QueryBuilder; SQLAlchemy ORM performs model hydration and relationship
    loading.
    """

    def __init__(
        self,
        model: type[ModelT],
        service: DatabaseService,
    ) -> None:
        """Bind one mapped class to the active service and connection.

        Args:
            model: SQLAlchemy mapped class selected by the caller.
            service: Canonical application-owned Database service.
        """
        self._model = model
        self._service = service
        self._connection_name = getattr(model, "connection", None)
        connection = service.connection(self._connection_name)
        mapper = _mapper(model)
        table = cast("Table", mapper.local_table)
        self._table = table
        table_name = table.fullname
        self._query = QueryBuilder(
            connection,
            table_name,
            table_clause=cast("TableClause", table),
        )
        self._soft_delete_column: str | None = None
        self._soft_delete_condition: ColumnElement[bool] | None = None
        if getattr(model, "__soft_delete_enabled__", False):
            column_name = getattr(model, "deleted_at_name", "deleted_at")
            if not isinstance(column_name, str) or not _is_mapped_column(
                model,
                column_name,
            ):
                msg = "The soft-delete field must be a mapped model column."
                raise DatabaseQueryError(msg)
            self._soft_delete_column = column_name
            self._soft_delete_condition = cast(
                "ColumnElement[bool]",
                table.c[column_name].is_(None),
            )
        self._global_scope_conditions = _resolve_global_scopes(model)
        self._apply_scope_conditions()
        self._eager_paths: list[str] = []
        self._eager_constraints: dict[str, ColumnElement[bool]] = {}
        self._relationship_counts: dict[str, ColumnElement[object]] = {}
        self._prevent_lazy = False
        self._selected_columns: tuple[str, ...] = ()

    def apply(self, scope: Callable[[Self], Self]) -> Self:
        """Apply a reusable typed local query transformation.

        Args:
            scope: Function that mutates or returns a model query builder.

        Returns:
            The builder returned by the local scope function.
        """
        return scope(self)

    def where(
        self,
        column_name: str | Mapping[str, object] | Callable[..., object],
        operator_or_value: object = _MISSING,
        value: object = _MISSING,
    ) -> Self:
        """Add equality, comparison, mapping, or grouped conditions.

        Args:
            column_name: Column, equality mapping, or query callback.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further model query composition.
        """
        if operator_or_value is _MISSING:
            self._query.where(column_name)
        elif value is _MISSING:
            self._query.where(column_name, operator_or_value)
        else:
            self._query.where(column_name, operator_or_value, value)
        return self

    def or_where(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> Self:
        """Add an equality or comparison joined by SQL OR.

        Args:
            column_name: Safe mapped column name.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further model query composition.
        """
        if value is _MISSING:
            self._query.or_where(column_name, operator_or_value)
        else:
            self._query.or_where(column_name, operator_or_value, value)
        return self

    def where_not(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> Self:
        """Add a negated mapped-column comparison.

        Args:
            column_name: Safe mapped column name.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further model query composition.
        """
        if value is _MISSING:
            self._query.where_not(column_name, operator_or_value)
        else:
            self._query.where_not(
                column_name,
                operator_or_value,
                value,
            )
        return self

    def or_where_not(
        self,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> Self:
        """Add a negated comparison joined by SQL OR.

        Args:
            column_name: Safe mapped column name.
            operator_or_value: Equality value or comparison operator.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further model query composition.
        """
        if value is _MISSING:
            self._query.or_where_not(column_name, operator_or_value)
        else:
            self._query.or_where_not(
                column_name,
                operator_or_value,
                value,
            )
        return self

    def where_in(
        self,
        column_name: str,
        values: Sequence[object],
    ) -> Self:
        """Match one mapped column against bound values.

        Args:
            column_name: Safe mapped column name.
            values: Values bound by SQLAlchemy.

        Returns:
            This builder for further model query composition.
        """
        self._query.where_in(column_name, values)
        return self

    def where_not_in(
        self,
        column_name: str,
        values: Sequence[object],
    ) -> Self:
        """Exclude mapped-column values from a bound sequence.

        Args:
            column_name: Safe mapped column name.
            values: Values bound by SQLAlchemy.

        Returns:
            This builder for further model query composition.
        """
        self._query.where_not_in(column_name, values)
        return self

    def where_between(
        self,
        column_name: str,
        lower: object,
        upper: object,
    ) -> Self:
        """Match a mapped value within an inclusive range.

        Args:
            column_name: Safe mapped column name.
            lower: Inclusive lower bound.
            upper: Inclusive upper bound.

        Returns:
            This builder for further model query composition.
        """
        self._query.where_between(column_name, lower, upper)
        return self

    def where_column(
        self,
        left: str,
        operator: str,
        right: str,
    ) -> Self:
        """Compare two mapped columns using a supported operator.

        Args:
            left: Safe left mapped column.
            operator: Allowlisted comparison operator.
            right: Safe right mapped column.

        Returns:
            This builder for further model query composition.
        """
        self._query.where_column(left, operator, right)
        return self

    def where_null(self, column_name: str) -> Self:
        """Require one mapped column to contain SQL NULL.

        Args:
            column_name: Safe mapped column name.

        Returns:
            This builder for further model query composition.
        """
        self._query.where_null(column_name)
        return self

    def where_not_null(self, column_name: str) -> Self:
        """Require one mapped column not to contain SQL NULL.

        Args:
            column_name: Safe mapped column name.

        Returns:
            This builder for further model query composition.
        """
        self._query.where_not_null(column_name)
        return self

    def where_not_between(
        self,
        column_name: str,
        lower: object,
        upper: object,
    ) -> Self:
        """Exclude values within an inclusive range.

        Args:
            column_name: Safe mapped column name.
            lower: Inclusive lower bound.
            upper: Inclusive upper bound.

        Returns:
            This builder for further model query composition.
        """
        self._query.where_not_between(column_name, lower, upper)
        return self

    def where_like(self, column_name: str, pattern: str) -> Self:
        """Match a mapped text column with a bound LIKE pattern.

        Args:
            column_name: Safe mapped text column name.
            pattern: Bound SQL LIKE pattern.

        Returns:
            This builder for further model query composition.
        """
        self._query.where_like(column_name, pattern)
        return self

    def where_not_like(self, column_name: str, pattern: str) -> Self:
        """Exclude values matching a bound LIKE pattern.

        Args:
            column_name: Safe mapped text column name.
            pattern: Bound SQL LIKE pattern.

        Returns:
            This builder for further model query composition.
        """
        self._query.where_not_like(column_name, pattern)
        return self

    def has(self, relationship: str) -> Self:
        """Require at least one related model along a mapped path.

        Args:
            relationship: Mapped relation name or nested path.

        Returns:
            This builder for further model query composition.
        """
        return self.where_has(relationship)

    def doesnt_have(self, relationship: str) -> Self:
        """Require no related model along a mapped path.

        Args:
            relationship: Mapped relation name or nested path.

        Returns:
            This builder for further model query composition.
        """
        condition = self._relationship_predicate(relationship, None)
        self._query.where_predicate(not_(condition))
        return self

    def where_has(
        self,
        relationship: str,
        constraint: Callable[[ModelQueryBuilder[object]], object] | None = None,
    ) -> Self:
        """Require a related model that satisfies an optional query callback.

        Args:
            relationship: Mapped relation name or nested path.
            constraint: Optional query mutation for the final related model.

        Returns:
            This builder for further model query composition.
        """
        condition = self._relationship_predicate(relationship, constraint)
        self._query.where_predicate(condition)
        return self

    def or_where_has(
        self,
        relationship: str,
        constraint: Callable[[ModelQueryBuilder[object]], object] | None = None,
    ) -> Self:
        """Add an OR condition for a matching related model.

        Args:
            relationship: Mapped relation name or nested path.
            constraint: Optional query mutation for the final related model.

        Returns:
            This builder for further model query composition.
        """
        condition = self._relationship_predicate(relationship, constraint)
        self._query.where_predicate(condition, boolean="or")
        return self

    def where_doesnt_have(self, relationship: str) -> Self:
        """Require no matching model along a mapped relationship path.

        Args:
            relationship: Mapped relation name or nested path.

        Returns:
            This builder for further model query composition.
        """
        condition = self._relationship_predicate(relationship, None)
        self._query.where_predicate(not_(condition))
        return self

    def or_where_doesnt_have(self, relationship: str) -> Self:
        """Add an OR condition that requires no related model.

        Args:
            relationship: Mapped relation name or nested path.

        Returns:
            This builder for further model query composition.
        """
        condition = self._relationship_predicate(relationship, None)
        self._query.where_predicate(
            not_(condition),
            boolean="or",
        )
        return self

    def where_relation(
        self,
        relationship: str,
        column_name: str,
        operator_or_value: object,
        value: object = _MISSING,
    ) -> Self:
        """Filter a related model using a bound column comparison.

        Args:
            relationship: Mapped relation name or nested path.
            column_name: Safe mapped column on the final related model.
            operator_or_value: Equality value or allowlisted comparison.
            value: Comparison value when an operator is supplied.

        Returns:
            This builder for further model query composition.
        """
        if value is _MISSING:
            return self.where_has(
                relationship,
                lambda query: query.where(column_name, operator_or_value),
            )
        return self.where_has(
            relationship,
            lambda query: query.where(
                column_name,
                operator_or_value,
                value,
            ),
        )

    def order_by(
        self,
        column_name: str,
        *,
        descending: bool = False,
    ) -> Self:
        """Order model rows by a mapped column.

        Args:
            column_name: Safe mapped column name.
            descending: Whether to sort from highest to lowest.

        Returns:
            This builder for further model query composition.
        """
        self._query.order_by(column_name, descending=descending)
        return self

    def latest(self, column_name: str = "created_at") -> Self:
        """Order model rows from newest to oldest.

        Args:
            column_name: Mapped timestamp column name.

        Returns:
            This builder for further model query composition.
        """
        self._query.latest(column_name)
        return self

    def oldest(self, column_name: str = "created_at") -> Self:
        """Order model rows from oldest to newest.

        Args:
            column_name: Mapped timestamp column name.

        Returns:
            This builder for further model query composition.
        """
        self._query.oldest(column_name)
        return self

    def limit(self, count: int | None) -> Self:
        """Limit the number of model rows returned.

        Args:
            count: Non-negative maximum or ``None`` to clear the limit.

        Returns:
            This builder for further model query composition.
        """
        self._query.limit(count)
        return self

    def offset(self, count: int) -> Self:
        """Skip a non-negative number of model rows.

        Args:
            count: Number of leading rows to omit.

        Returns:
            This builder for further model query composition.
        """
        self._query.offset(count)
        return self

    def paginate(
        self,
        per_page: int = 15,
        *,
        page: int = _FIRST_PAGE,
    ) -> LengthAwarePaginator[ModelT]:
        """Retrieve model items with an exact matching-row count.

        Args:
            per_page: Positive maximum page size.
            page: Positive one-based page number.

        Returns:
            Page items and total-count navigation metadata.
        """
        _validate_page(per_page, page)
        total = self.count()
        items = (
            self.clone()
            .limit(per_page)
            .offset(
                (page - _FIRST_PAGE) * per_page,
            )
            .get()
        )
        return LengthAwarePaginator(
            tuple(items),
            total,
            per_page,
            page,
        )

    async def paginate_async(
        self,
        per_page: int = 15,
        *,
        page: int = _FIRST_PAGE,
    ) -> LengthAwarePaginator[ModelT]:
        """Asynchronously retrieve model items and total row count.

        Args:
            per_page: Positive maximum page size.
            page: Positive one-based page number.

        Returns:
            Page items and total-count navigation metadata.
        """
        _validate_page(per_page, page)
        total = await self.count_async()
        items = (
            await self.clone()
            .limit(per_page)
            .offset(
                (page - _FIRST_PAGE) * per_page,
            )
            .get_async()
        )
        return LengthAwarePaginator(
            tuple(items),
            total,
            per_page,
            page,
        )

    def simple_paginate(
        self,
        per_page: int = 15,
        *,
        page: int = _FIRST_PAGE,
    ) -> Paginator[ModelT]:
        """Retrieve model items without a total-count query.

        Args:
            per_page: Positive maximum page size.
            page: Positive one-based page number.

        Returns:
            Page items and a bounded next-page indicator.
        """
        _validate_page(per_page, page)
        items = (
            self.clone()
            .limit(per_page + 1)
            .offset(
                (page - _FIRST_PAGE) * per_page,
            )
            .get()
        )
        has_more = len(items) > per_page
        return Paginator(
            tuple(items[:per_page]),
            per_page,
            page,
            has_more,
        )

    async def simple_paginate_async(
        self,
        per_page: int = 15,
        *,
        page: int = _FIRST_PAGE,
    ) -> Paginator[ModelT]:
        """Asynchronously retrieve a page with one-row lookahead.

        Args:
            per_page: Positive maximum page size.
            page: Positive one-based page number.

        Returns:
            Page items and a bounded next-page indicator.
        """
        _validate_page(per_page, page)
        items = (
            await self.clone()
            .limit(per_page + 1)
            .offset(
                (page - _FIRST_PAGE) * per_page,
            )
            .get_async()
        )
        has_more = len(items) > per_page
        return Paginator(
            tuple(items[:per_page]),
            per_page,
            page,
            has_more,
        )

    def cursor_paginate(
        self,
        per_page: int = 15,
        *,
        cursor: str | None = None,
    ) -> CursorPaginator[ModelT]:
        """Retrieve a model page through the Core cursor paginator.

        Args:
            per_page: Positive maximum number of models to return.
            cursor: Optional cursor from a previous page.

        Returns:
            Hydrated models in the Core query's stable cursor order.
        """
        key_name = _primary_key_name(self._model)
        page_query = self._query.clone()
        page_query.add_select(key_name)
        page = page_query.cursor_paginate(
            per_page,
            cursor=cursor,
            key_column=key_name,
        )
        identifiers = tuple(row[key_name] for row in page.items)
        if not identifiers:
            return CursorPaginator(
                (),
                page.per_page,
                page.next_cursor,
                page.previous_cursor,
                page.has_more_pages,
            )

        hydration_query = (
            self.clone().limit(None).offset(0).where_in(key_name, identifiers)
        )
        models = hydration_query.get()
        models_by_key = {getattr(model, key_name): model for model in models}
        items = tuple(
            models_by_key[identifier]
            for identifier in identifiers
            if identifier in models_by_key
        )
        return CursorPaginator(
            items,
            page.per_page,
            page.next_cursor,
            page.previous_cursor,
            page.has_more_pages,
        )

    async def cursor_paginate_async(
        self,
        per_page: int = 15,
        *,
        cursor: str | None = None,
    ) -> CursorPaginator[ModelT]:
        """Asynchronously retrieve a model page in stable cursor order.

        Args:
            per_page: Positive maximum number of models to return.
            cursor: Optional cursor from a previous page.

        Returns:
            Hydrated models in the Core query's stable cursor order.
        """
        key_name = _primary_key_name(self._model)
        page_query = self._query.clone()
        page_query.add_select(key_name)
        page = await page_query.cursor_paginate_async(
            per_page,
            cursor=cursor,
            key_column=key_name,
        )
        identifiers = tuple(row[key_name] for row in page.items)
        if not identifiers:
            return CursorPaginator(
                (),
                page.per_page,
                page.next_cursor,
                page.previous_cursor,
                page.has_more_pages,
            )

        hydration_query = (
            self.clone().limit(None).offset(0).where_in(key_name, identifiers)
        )
        models = await hydration_query.get_async()
        models_by_key = {getattr(model, key_name): model for model in models}
        items = tuple(
            models_by_key[identifier]
            for identifier in identifiers
            if identifier in models_by_key
        )
        return CursorPaginator(
            items,
            page.per_page,
            page.next_cursor,
            page.previous_cursor,
            page.has_more_pages,
        )

    def select(self, *columns: str) -> Self:
        """Load only selected mapped columns while returning model instances.

        Args:
            columns: Mapped model attribute names.

        Returns:
            This builder for further model query composition.

        Raises:
            DatabaseQueryError: If a requested column is not mapped.
        """
        for name in columns:
            if not _is_mapped_column(self._model, name):
                msg = "Model projections must name mapped columns."
                raise DatabaseQueryError(msg)
        self._selected_columns = tuple(columns)
        self._query.select(*columns)
        return self

    def with_(self, *paths: str) -> Self:
        """Eager-load mapped relationships through SQLAlchemy select-in load.

        Args:
            paths: Relationship names or dot-separated nested paths.

        Returns:
            This builder for further model query composition.

        Raises:
            DatabaseQueryError: If a path contains an unmapped relationship.
        """
        for path in paths:
            self._validate_relationship_path(path)
            self._eager_paths.append(path)
        return self

    def with_count(
        self,
        relationship_name: str,
        *,
        attribute: str | None = None,
    ) -> Self:
        """Select a related-row count into a mapped query expression.

        Declare the result attribute with SQLAlchemy ``query_expression()``
        to keep the count typed without adding a database column.

        Args:
            relationship_name: Mapped relationship path to count.
            attribute: Result attribute, defaulting to
                ``<relationship_with_dots_replaced>_count``.

        Returns:
            This builder for further model query composition.

        Raises:
            DatabaseQueryError: If the path or result attribute is invalid.
        """
        return self._with_relationship_aggregate(
            relationship_name,
            attribute or f"{relationship_name.replace('.', '_')}_count",
            "count",
        )

    def with_exists(
        self,
        relationship_name: str,
        *,
        attribute: str | None = None,
    ) -> Self:
        """Select whether a mapped relationship path has matching records.

        Declare the result attribute with SQLAlchemy ``query_expression()``.

        Args:
            relationship_name: Mapped relationship path to check.
            attribute: Result attribute, defaulting to the path with dots
                replaced by underscores plus ``_exists``.

        Returns:
            This builder for further model query composition.
        """
        return self._with_relationship_aggregate(
            relationship_name,
            attribute or f"{relationship_name.replace('.', '_')}_exists",
            "exists",
        )

    def with_sum(
        self,
        relationship_name: str,
        column_name: str,
        *,
        attribute: str | None = None,
    ) -> Self:
        """Select the sum of one mapped column across a relationship.

        Declare the result attribute with SQLAlchemy ``query_expression()``.

        Args:
            relationship_name: Mapped relationship path to aggregate.
            column_name: Mapped numeric column to sum.
            attribute: Result attribute, defaulting to the path with dots
                replaced by underscores plus ``_sum_<column>``.

        Returns:
            This builder for further model query composition.
        """
        return self._with_relationship_aggregate(
            relationship_name,
            attribute
            or f"{relationship_name.replace('.', '_')}_sum_{column_name}",
            "sum",
            column_name,
        )

    def with_avg(
        self,
        relationship_name: str,
        column_name: str,
        *,
        attribute: str | None = None,
    ) -> Self:
        """Select the average of one mapped relationship column.

        Declare the result attribute with SQLAlchemy ``query_expression()``.

        Args:
            relationship_name: Mapped relationship path to aggregate.
            column_name: Mapped numeric column to average.
            attribute: Result attribute, defaulting to the path with dots
                replaced by underscores plus ``_avg_<column>``.

        Returns:
            This builder for further model query composition.
        """
        return self._with_relationship_aggregate(
            relationship_name,
            attribute
            or f"{relationship_name.replace('.', '_')}_avg_{column_name}",
            "avg",
            column_name,
        )

    def with_min(
        self,
        relationship_name: str,
        column_name: str,
        *,
        attribute: str | None = None,
    ) -> Self:
        """Select the minimum of one mapped relationship column.

        Declare the result attribute with SQLAlchemy ``query_expression()``.

        Args:
            relationship_name: Mapped relationship path to aggregate.
            column_name: Mapped column whose minimum is selected.
            attribute: Result attribute, defaulting to the path with dots
                replaced by underscores plus ``_min_<column>``.

        Returns:
            This builder for further model query composition.
        """
        return self._with_relationship_aggregate(
            relationship_name,
            attribute
            or f"{relationship_name.replace('.', '_')}_min_{column_name}",
            "min",
            column_name,
        )

    def with_max(
        self,
        relationship_name: str,
        column_name: str,
        *,
        attribute: str | None = None,
    ) -> Self:
        """Select the maximum of one mapped relationship column.

        Declare the result attribute with SQLAlchemy ``query_expression()``.

        Args:
            relationship_name: Mapped relationship path to aggregate.
            column_name: Mapped column whose maximum is selected.
            attribute: Result attribute, defaulting to the path with dots
                replaced by underscores plus ``_max_<column>``.

        Returns:
            This builder for further model query composition.
        """
        return self._with_relationship_aggregate(
            relationship_name,
            attribute
            or f"{relationship_name.replace('.', '_')}_max_{column_name}",
            "max",
            column_name,
        )

    def with_where[RelatedT](
        self,
        path: str,
        constraint: Callable[
            [ModelQueryBuilder[RelatedT]],
            ModelQueryBuilder[RelatedT],
        ],
    ) -> Self:
        """Eager-load a relationship with a typed related-model filter.

        Args:
            path: Relationship name or dot-separated nested path.
            constraint: Query transformation for the final related model.

        Returns:
            This builder with the constrained path eager-loaded.

        Raises:
            DatabaseQueryError: If the path is invalid or its callback
                replaces the related query builder.
        """
        self._validate_relationship_path(path)
        related_model = cast("type[object]", self._model)
        for name in path.split("."):
            relationship = _mapper(related_model).relationships[name]
            related_model = cast("type[object]", relationship.mapper.class_)
        query = cast(
            "ModelQueryBuilder[RelatedT]",
            ModelQueryBuilder(related_model, self._service),
        )
        constrained = constraint(query)
        if constrained is not query:
            raise DatabaseQueryError(_INVALID_EAGER_CONSTRAINT_ERROR)
        condition = query.to_statement().whereclause
        if condition is not None:
            previous = self._eager_constraints.get(path)
            self._eager_constraints[path] = (
                condition if previous is None else and_(previous, condition)
            )
        if path not in self._eager_paths:
            self._eager_paths.append(path)
        return self

    def with_trashed(self) -> Self:
        """Include soft-deleted rows in this query when supported.

        Returns:
            This builder with its default deletion condition removed.
        """
        if self._soft_delete_column is not None:
            self._soft_delete_condition = None
            self._apply_scope_conditions()
        return self

    def without_trashed(self) -> Self:
        """Restrict a soft-delete query to active rows.

        Returns:
            This builder with the active-row condition applied.
        """
        if self._soft_delete_column is not None:
            self._soft_delete_condition = cast(
                "ColumnElement[bool]",
                self._table.c[self._soft_delete_column].is_(None),
            )
            self._apply_scope_conditions()
        return self

    def only_trashed(self) -> Self:
        """Restrict a soft-delete query to deleted rows.

        Returns:
            This builder with the deleted-row condition applied.
        """
        if self._soft_delete_column is not None:
            self._soft_delete_condition = cast(
                "ColumnElement[bool]",
                self._table.c[self._soft_delete_column].is_not(None),
            )
            self._apply_scope_conditions()
        return self

    def without_global_scope(self, name: str) -> Self:
        """Remove one named class-level predicate from this query.

        Args:
            name: Declared global scope key to remove.

        Returns:
            This builder with the selected global scope omitted.
        """
        self._global_scope_conditions.pop(name, None)
        self._apply_scope_conditions()
        return self

    def without_global_scopes(self) -> Self:
        """Remove every class-level predicate from this query.

        Returns:
            This builder with all global scopes omitted.
        """
        self._global_scope_conditions.clear()
        self._apply_scope_conditions()
        return self

    def restore(self) -> int:
        """Restore matching soft-deleted records with one set-based update.

        Returns:
            Driver-reported affected rows or ``-1`` when unknown.
        """
        if self._soft_delete_column is None:
            return 0
        query = self.clone().only_trashed()
        return query._query.update(  # noqa: SLF001
            {self._soft_delete_column: None},
        )

    async def restore_async(self) -> int:
        """Asynchronously restore matching soft-deleted records.

        Returns:
            Driver-reported affected rows or ``-1`` when unknown.
        """
        if self._soft_delete_column is None:
            return 0
        query = self.clone().only_trashed()
        return await query._query.update_async(  # noqa: SLF001
            {self._soft_delete_column: None},
        )

    def prevent_lazy_loading(self, enabled: bool = True) -> Self:
        """Raise on unloaded relationship access for fetched models.

        Args:
            enabled: Whether SQLAlchemy should reject implicit lazy loading.

        Returns:
            This builder for further model query composition.
        """
        self._prevent_lazy = enabled
        return self

    def clone(self) -> Self:
        """Copy query state for an independent model query branch.

        Returns:
            A builder with copied filters, orders, and loader paths.
        """
        cloned = copy(self)
        cloned._query = self._query.clone()  # noqa: SLF001  # Copy query.
        cloned._eager_paths = self._eager_paths.copy()  # noqa: SLF001
        cloned._eager_constraints = (  # noqa: SLF001
            self._eager_constraints.copy()
        )
        cloned._relationship_counts = (  # noqa: SLF001
            self._relationship_counts.copy()
        )
        cloned._selected_columns = self._selected_columns  # noqa: SLF001
        cloned._global_scope_conditions = (  # noqa: SLF001
            self._global_scope_conditions.copy()
        )
        return cloned

    def _apply_scope_conditions(self) -> None:
        """Combine soft-delete and named global predicates on the Core query.

        Keeping framework scopes in the Query Builder's separate scope slot
        preserves user condition grouping and bulk mutation behavior.
        """
        conditions = list(self._global_scope_conditions.values())
        if self._soft_delete_condition is not None:
            conditions.insert(0, self._soft_delete_condition)
        if not conditions:
            self._query.set_scope_condition(None)
        elif len(conditions) == 1:
            self._query.set_scope_condition(conditions[0])
        else:
            self._query.set_scope_condition(and_(*conditions))

    def to_statement(self) -> Select[tuple[ModelT]]:
        """Build the ORM Select statement for the configured model query.

        Returns:
            A SQLAlchemy ORM statement with current criteria and loading rules.
        """
        statement = cast(
            "Select[tuple[ModelT]]",
            self._query.to_statement(entity=self._model),
        )
        options: list[ExecutableOption] = []
        if self._selected_columns:
            selected = [
                cast(
                    "QueryableAttribute[object]",
                    getattr(self._model, name),
                )
                for name in self._selected_columns
            ]
            options.append(load_only(*selected))
        options.extend(self._loader_option(path) for path in self._eager_paths)
        for name, expression in self._relationship_counts.items():
            attribute = cast(
                "QueryableAttribute[object]",
                getattr(self._model, name),
            )
            options.append(with_expression(attribute, expression))
        if self._prevent_lazy:
            options.append(raiseload("*"))
        options.extend(_relationship_loader_criteria(self._model))
        return statement.options(*options)

    def _with_relationship_aggregate(
        self,
        relationship_name: str,
        result_attribute: str,
        aggregate: str,
        column_name: str | None = None,
    ) -> Self:
        """Attach one scoped relationship aggregate to the ORM query.

        Args:
            relationship_name: Mapped relationship path to aggregate.
            result_attribute: Mapped query-expression receiving the value.
            aggregate: Internal aggregate function selected by the public API.
            column_name: Related column used by value aggregates.

        Returns:
            This builder for further model query composition.

        Raises:
            DatabaseQueryError: If the relationship, column, or result is
                not a supported mapped attribute.
        """
        self._validate_relationship_path(relationship_name)
        expression_attribute = _mapper(self._model).attrs.get(
            result_attribute,
        )
        if not isinstance(expression_attribute, MappedSQLExpression):
            msg = (
                "Relationship aggregates require a mapped query_expression "
                f"attribute: {result_attribute}."
            )
            raise DatabaseQueryError(msg)
        self._relationship_counts[result_attribute] = (
            self._relationship_aggregate_expression(
                relationship_name,
                aggregate,
                column_name,
            )
        )
        return self

    def _relationship_aggregate_expression(
        self,
        relationship_name: str,
        aggregate: str,
        column_name: str | None,
    ) -> ColumnElement[object]:
        """Build a correlated aggregate for a mapped relationship path.

        Args:
            relationship_name: Dot-separated path ending at the aggregate rows.
            aggregate: Count, exists, sum, average, minimum, or maximum.
            column_name: Mapped related column used by value aggregates.

        Returns:
            A scalar expression scoped to related-model visibility predicates.

        Raises:
            DatabaseQueryError: If the mapped join or column is invalid.
        """
        parent_table = _mapper(self._model).local_table
        chain = _relationship_aggregate_chain(
            cast("type[object]", self._model),
            relationship_name,
        )
        related_model = chain[-1][1]
        selected: ColumnElement[object]
        if aggregate == "exists":
            selected = literal(1)
        elif aggregate == "count":
            selected = cast("ColumnElement[object]", func.count())
        else:
            if column_name is None or not _is_mapped_column(
                related_model,
                column_name,
            ):
                msg = f"Aggregate column is not mapped: {column_name}."
                raise DatabaseQueryError(msg)
            column = cast(
                "ColumnElement[object]",
                getattr(related_model, column_name),
            )
            selected = cast(
                "ColumnElement[object]",
                getattr(func, aggregate)(column),
            )
        statement = _relationship_aggregate_statement(
            chain,
            selected,
            self._service,
        )
        correlated = statement.correlate(parent_table)
        if aggregate == "exists":
            return cast("ColumnElement[object]", correlated.exists())
        return cast("ColumnElement[object]", correlated.scalar_subquery())

    def get(self) -> ModelCollection[ModelT]:
        """Execute the ORM query and detach its model results.

        Returns:
            SQLAlchemy-hydrated model instances in result order.
        """
        with self._service.session(self._connection_name) as session:
            scalar_result = cast(
                "ScalarResult[ModelT]",
                session.scalars(self.to_statement()),
            )
            results = scalar_result.unique().all()
            for model in results:
                remember_service_graph(
                    model,
                    self._service,
                    self._connection_name,
                )
            return ModelCollection(results)

    async def get_async(self) -> ModelCollection[ModelT]:
        """Execute the ORM query asynchronously and detach model results.

        Returns:
            SQLAlchemy-hydrated model instances in result order.
        """
        async with self._service.session_async(
            self._connection_name,
        ) as session:
            scalar_result = cast(
                "ScalarResult[ModelT]",
                await session.scalars(self.to_statement()),
            )
            models = scalar_result.unique().all()
            for model in models:
                remember_service_graph(
                    model,
                    self._service,
                    self._connection_name,
                )
            return ModelCollection(models)

    @contextmanager
    def stream(
        self,
        *,
        batch_size: int = _DEFAULT_STREAM_BATCH_SIZE,
    ) -> Generator[Iterator[ModelT], None, None]:
        """Stream mapped models while owning the sync Session and cursor.

        Args:
            batch_size: Maximum ORM fetch batch requested from SQLAlchemy.

        Yields:
            An iterator valid only inside this context manager.

        Raises:
            ValueError: If ``batch_size`` is not a positive integer.
        """
        _validate_stream_batch_size(batch_size)
        statement = self.to_statement().execution_options(
            yield_per=batch_size,
        )
        with self._service.session(self._connection_name) as session:
            results = cast(
                "ScalarResult[ModelT]",
                session.scalars(statement),
            )

            def models() -> Iterator[ModelT]:
                """Yield models and attach their service provenance.

                SQLAlchemy retains identity tracking only for this scope.
                """
                for model in results:
                    remember_service_graph(
                        model,
                        self._service,
                        self._connection_name,
                    )
                    yield model

            try:
                yield models()
            finally:
                results.close()

    @asynccontextmanager
    async def stream_async(
        self,
        *,
        batch_size: int = _DEFAULT_STREAM_BATCH_SIZE,
    ) -> AsyncGenerator[AsyncIterator[ModelT], None]:
        """Stream mapped models with task-owned async resources.

        Args:
            batch_size: Maximum ORM fetch batch requested from SQLAlchemy.

        Yields:
            An async iterator valid only inside this context manager.

        Raises:
            ValueError: If ``batch_size`` is not a positive integer.
        """
        _validate_stream_batch_size(batch_size)
        statement = self.to_statement().execution_options(
            yield_per=batch_size,
        )
        async with self._service.session_async(
            self._connection_name,
        ) as session:
            results = cast(
                "AsyncScalarResult[ModelT]",
                await session.stream_scalars(statement),
            )

            async def models() -> AsyncIterator[ModelT]:
                """Yield models and retain their application provenance.

                SQLAlchemy retains identity tracking only for this scope.
                """
                async for model in results:
                    remember_service_graph(
                        model,
                        self._service,
                        self._connection_name,
                    )
                    yield model

            try:
                yield models()
            finally:
                with anyio.CancelScope(shield=True):
                    await results.close()

    def first(self) -> ModelT | None:
        """Return the first matching model, if one exists.

        Returns:
            A detached model or ``None``.
        """
        results = self.clone().limit(1).get()
        return results[0] if results else None

    async def first_async(self) -> ModelT | None:
        """Asynchronously return the first matching model, if present.

        Returns:
            A detached model or ``None``.
        """
        results = await self.clone().limit(1).get_async()
        return results[0] if results else None

    def find(self, identifier: object) -> ModelT | None:
        """Find a model by primary key without applying result selection.

        Args:
            identifier: Primary-key value supported by SQLAlchemy Session.

        Returns:
            A detached model or ``None``.
        """
        key_name = _primary_key_name(self._model)
        return self.clone().where(key_name, identifier).first()

    async def find_async(self, identifier: object) -> ModelT | None:
        """Asynchronously find a model by its primary key.

        Args:
            identifier: Primary-key value supported by AsyncSession.

        Returns:
            A detached model or ``None``.
        """
        key_name = _primary_key_name(self._model)
        return await self.clone().where(key_name, identifier).first_async()

    def find_many(
        self,
        identifiers: Sequence[object],
    ) -> ModelCollection[ModelT]:
        """Retrieve models matching any supplied primary-key value.

        Args:
            identifiers: Primary-key values selected by trusted application
                code.

        Returns:
            Matching detached models in database result order.
        """
        key_name = _primary_key_name(self._model)
        return self.clone().where_in(key_name, identifiers).get()

    async def find_many_async(
        self,
        identifiers: Sequence[object],
    ) -> ModelCollection[ModelT]:
        """Asynchronously retrieve models matching supplied identifiers.

        Args:
            identifiers: Primary-key values selected by trusted application
                code.

        Returns:
            Matching detached models in database result order.
        """
        key_name = _primary_key_name(self._model)
        return await self.clone().where_in(key_name, identifiers).get_async()

    def first_or_fail(self) -> ModelT:
        """Return the first matching model or raise a not-found exception.

        Returns:
            The first detached model.

        Raises:
            ModelNotFoundError: If the query matched no model.
        """
        model = self.first()
        if model is None:
            raise ModelNotFoundError(_NO_MODELS_FOUND)
        return model

    async def first_or_fail_async(self) -> ModelT:
        """Asynchronously return the first model or raise not found.

        Returns:
            The first detached model.

        Raises:
            ModelNotFoundError: If the query matched no model.
        """
        model = await self.first_async()
        if model is None:
            raise ModelNotFoundError(_NO_MODELS_FOUND)
        return model

    def sole(self) -> ModelT:
        """Return exactly one matching model.

        Returns:
            The sole detached model.

        Raises:
            ModelNotFoundError: If no row matched.
            MultipleModelsFoundError: If more than one row matched.
        """
        models = self.clone().limit(2).get().all()
        return _sole_model(models)

    async def sole_async(self) -> ModelT:
        """Asynchronously return exactly one matching model.

        Returns:
            The sole detached model.

        Raises:
            ModelNotFoundError: If no row matched.
            MultipleModelsFoundError: If more than one row matched.
        """
        models = (await self.clone().limit(2).get_async()).all()
        return _sole_model(models)

    def count(self) -> int:
        """Count filtered rows without hydrating models.

        Returns:
            The database-reported row count.
        """
        return self._query.count()

    async def count_async(self) -> int:
        """Asynchronously count filtered rows without model hydration.

        Returns:
            The database-reported row count.
        """
        return await self._query.count_async()

    def exists(self) -> bool:
        """Check whether any model matches without hydrating its full row.

        Returns:
            Whether the database found a matching row.
        """
        return self._query.exists()

    async def exists_async(self) -> bool:
        """Asynchronously check whether any model matches the filters.

        Returns:
            Whether the database found a matching row.
        """
        return await self._query.exists_async()

    def value(self, column_name: str) -> object | None:
        """Return one mapped column from the first matching row.

        Args:
            column_name: Safe mapped column name.

        Returns:
            The selected value or ``None``.
        """
        return self._query.value(column_name)

    async def value_async(self, column_name: str) -> object | None:
        """Asynchronously return one mapped column value.

        Args:
            column_name: Safe mapped column name.

        Returns:
            The selected value or ``None``.
        """
        return await self._query.value_async(column_name)

    def pluck(
        self,
        column_name: str,
        key: str | None = None,
    ) -> list[object] | dict[object, object]:
        """Retrieve mapped values without hydrating model instances.

        Args:
            column_name: Safe mapped value column.
            key: Optional mapped column used as the result mapping key.

        Returns:
            Values in row order or a mapping keyed by the selected column.
        """
        return self._query.pluck(column_name, key)

    async def pluck_async(
        self,
        column_name: str,
        key: str | None = None,
    ) -> list[object] | dict[object, object]:
        """Asynchronously retrieve values without model hydration.

        Args:
            column_name: Safe mapped value column.
            key: Optional mapped column used as the result mapping key.

        Returns:
            Values in row order or a mapping keyed by the selected column.
        """
        return await self._query.pluck_async(column_name, key)

    def sum(self, column_name: str) -> object | None:
        """Sum one mapped column in the database.

        Args:
            column_name: Safe mapped numeric column.

        Returns:
            The scalar sum or ``None`` when the backend returns no value.
        """
        return self._query.sum(column_name)

    async def sum_async(self, column_name: str) -> object | None:
        """Asynchronously sum one mapped database column.

        Args:
            column_name: Safe mapped numeric column.

        Returns:
            The scalar sum or ``None`` when the backend returns no value.
        """
        return await self._query.sum_async(column_name)

    def avg(self, column_name: str) -> object | None:
        """Average one mapped column in the database.

        Args:
            column_name: Safe mapped numeric column.

        Returns:
            The scalar average or ``None`` when the backend returns no value.
        """
        return self._query.avg(column_name)

    async def avg_async(self, column_name: str) -> object | None:
        """Asynchronously average one mapped database column.

        Args:
            column_name: Safe mapped numeric column.

        Returns:
            The scalar average or ``None`` when the backend returns no value.
        """
        return await self._query.avg_async(column_name)

    def min(self, column_name: str) -> object | None:
        """Return the minimum value for one mapped column.

        Args:
            column_name: Safe mapped value column.

        Returns:
            The minimum value or ``None`` when the backend returns no value.
        """
        return self._query.min(column_name)

    async def min_async(self, column_name: str) -> object | None:
        """Asynchronously return a mapped column's minimum value.

        Args:
            column_name: Safe mapped value column.

        Returns:
            The minimum value or ``None`` when the backend returns no value.
        """
        return await self._query.min_async(column_name)

    def max(self, column_name: str) -> object | None:
        """Return the maximum value for one mapped column.

        Args:
            column_name: Safe mapped value column.

        Returns:
            The maximum value or ``None`` when the backend returns no value.
        """
        return self._query.max(column_name)

    async def max_async(self, column_name: str) -> object | None:
        """Asynchronously return a mapped column's maximum value.

        Args:
            column_name: Safe mapped value column.

        Returns:
            The maximum value or ``None`` when the backend returns no value.
        """
        return await self._query.max_async(column_name)

    def update(self, values: Mapping[str, object]) -> int:
        """Apply a set-based update without per-model lifecycle events.

        Args:
            values: Mapped column values for matching rows.

        Returns:
            Driver-reported affected rows or ``-1`` when unknown.
        """
        return self._query.update(values)

    async def update_async(self, values: Mapping[str, object]) -> int:
        """Asynchronously apply a set-based bulk update.

        Args:
            values: Mapped column values for matching rows.

        Returns:
            Driver-reported affected rows or ``-1`` when unknown.
        """
        return await self._query.update_async(values)

    def delete(self) -> int:
        """Delete matching rows as a set without per-model events.

        Returns:
            Driver-reported affected rows or ``-1`` when unknown.
        """
        if self._soft_delete_column is None:
            return self._query.delete()
        return self._query.update(
            {self._soft_delete_column: datetime.now(UTC)},
        )

    async def delete_async(self) -> int:
        """Asynchronously delete matching rows as a set.

        Returns:
            Driver-reported affected rows or ``-1`` when unknown.
        """
        if self._soft_delete_column is None:
            return await self._query.delete_async()
        return await self._query.update_async(
            {self._soft_delete_column: datetime.now(UTC)},
        )

    def force_delete(self) -> int:
        """Hard-delete matching rows, including rows already soft deleted.

        Returns:
            Driver-reported affected rows or ``-1`` when unknown.
        """
        query = self._query.clone()
        query.set_scope_condition(None)
        return query.delete()

    async def force_delete_async(self) -> int:
        """Asynchronously hard-delete matching rows in one statement.

        Returns:
            Driver-reported affected rows or ``-1`` when unknown.
        """
        query = self._query.clone()
        query.set_scope_condition(None)
        return await query.delete_async()

    def increment(self, column_name: str, amount: int = 1) -> int:
        """Atomically increment every matching row without model events.

        Args:
            column_name: Safe mapped numeric column.
            amount: Integer amount to add.

        Returns:
            Driver-reported affected rows or ``-1`` when unknown.
        """
        return self._query.increment(column_name, amount)

    def decrement(self, column_name: str, amount: int = 1) -> int:
        """Atomically decrement matching rows without model events.

        Args:
            column_name: Safe mapped numeric column.
            amount: Integer amount to subtract.

        Returns:
            Driver-reported affected rows or ``-1`` when unknown.
        """
        return self._query.decrement(column_name, amount)

    async def increment_async(
        self,
        column_name: str,
        amount: int = 1,
    ) -> int:
        """Asynchronously increment matching rows without model events.

        Args:
            column_name: Safe mapped numeric column.
            amount: Integer amount to add.

        Returns:
            Driver-reported affected rows or ``-1`` when unknown.
        """
        return await self._query.increment_async(column_name, amount)

    async def decrement_async(
        self,
        column_name: str,
        amount: int = 1,
    ) -> int:
        """Asynchronously decrement matching rows without model events.

        Args:
            column_name: Safe mapped numeric column.
            amount: Integer amount to subtract.

        Returns:
            Driver-reported affected rows or ``-1`` when unknown.
        """
        return await self._query.decrement_async(column_name, amount)

    def _validate_relationship_path(self, path: str) -> None:
        """Validate every segment against the mapped relationship graph.

        Args:
            path: Dot-separated relationship names.

        Raises:
            DatabaseQueryError: If a segment is empty or unmapped.
        """
        current = self._model
        for name in path.split("."):
            if not name:
                _raise_invalid_relationship()
            mapper = _mapper(current)
            relationship = mapper.relationships.get(name)
            if relationship is None:
                _raise_invalid_relationship()
            current = cast("type[ModelT]", relationship.mapper.class_)

    def _relationship_predicate(
        self,
        path: str,
        constraint: Callable[[ModelQueryBuilder[object]], object] | None,
    ) -> ColumnElement[bool]:
        """Build one correlated SQLAlchemy relationship-existence predicate.

        Args:
            path: Dot-separated mapped relationship names.
            constraint: Optional final-model query mutation.

        Returns:
            A SQLAlchemy EXISTS predicate with nested relations correlated.
        """
        self._validate_relationship_path(path)
        chain: list[tuple[type[object], RelationshipProperty[object]]] = []
        current = cast("type[object]", self._model)
        for name in path.split("."):
            relationship = cast(
                "RelationshipProperty[object]",
                _mapper(current).relationships[name],
            )
            chain.append((current, relationship))
            current = relationship.mapper.class_

        related_query = ModelQueryBuilder(current, self._service)
        if constraint is not None:
            constraint(related_query)
        predicate = related_query.to_statement().whereclause
        for index in range(len(chain) - 1, -1, -1):
            parent, relationship = chain[index]
            if index < len(chain) - 1:
                intermediate_type = relationship.mapper.class_
                scope = _soft_delete_condition(intermediate_type)
                if scope is not None:
                    predicate = (
                        scope if predicate is None else and_(scope, predicate)
                    )
                for scope in _resolve_global_scopes(
                    intermediate_type,
                ).values():
                    predicate = (
                        scope if predicate is None else and_(scope, predicate)
                    )
            attribute = cast(
                "QueryableAttribute[object]",
                getattr(parent, relationship.key),
            )
            if relationship.uselist:
                expression = (
                    attribute.any()
                    if predicate is None
                    else attribute.any(predicate)
                )
            else:
                expression = (
                    attribute.has()
                    if predicate is None
                    else attribute.has(predicate)
                )
            predicate = expression
        if predicate is None:
            _raise_invalid_relationship()
        return predicate

    def _loader_option(self, path: str) -> ExecutableOption:
        """Build a nested SQLAlchemy select-in loading option.

        Args:
            path: Previously validated dot-separated relationship path.

        Returns:
            A loader option owned and executed by SQLAlchemy ORM.
        """
        current = self._model
        option: ExecutableOption | None = None
        path_parts: list[str] = []
        for name in path.split("."):
            path_parts.append(name)
            relationship = _mapper(current).relationships[name]
            target = relationship.mapper.class_
            attribute = cast(
                "QueryableAttribute[object]",
                getattr(current, name),
            )
            # Loader criteria are class-wide. A self-relation targets the
            # query root too, so constrain that path directly to preserve the
            # root builder's explicit ``with_trashed`` setting.
            if target is self._model:
                scope = _soft_delete_condition(target)
                if scope is not None:
                    attribute = cast(
                        "QueryableAttribute[object]",
                        attribute.and_(scope),
                    )
                for scope in _resolve_global_scopes(target).values():
                    attribute = cast(
                        "QueryableAttribute[object]",
                        attribute.and_(scope),
                    )
            condition = self._eager_constraints.get(".".join(path_parts))
            if condition is not None:
                attribute = cast(
                    "QueryableAttribute[object]",
                    attribute.and_(condition),
                )
            option = (
                selectinload(attribute)
                if option is None
                else cast("Load", option).selectinload(attribute)
            )
            current = cast("type[ModelT]", relationship.mapper.class_)
        if option is None:
            _raise_invalid_relationship()
        return option


def _relationship_loader_criteria(
    model: type[object],
) -> tuple[ExecutableOption, ...]:
    """Build loader-only criteria for scoped relationship targets.

    SQLAlchemy propagates these options into eager and subsequent lazy
    relationship loads. ``loader_only`` keeps root visibility controlled by
    the explicit model query builder, including its ``with_trashed`` policy.

    Args:
        model: Root model whose mapped relationship graph will be inspected.

    Returns:
        Criteria options for reachable soft-delete and global scopes.
    """
    selected: list[ExecutableOption] = []
    visited: set[type[object]] = set()
    pending = [model]
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        mapper = _mapper(current)
        if current is not model:
            condition = _soft_delete_condition(current)
            if condition is not None:
                selected.append(
                    with_loader_criteria(
                        current,
                        condition,
                        loader_only=True,
                        include_aliases=True,
                    ),
                )
            selected.extend(
                with_loader_criteria(
                    current,
                    condition,
                    loader_only=True,
                    include_aliases=True,
                )
                for condition in _resolve_global_scopes(current).values()
            )
        pending.extend(
            relationship.mapper.class_ for relationship in mapper.relationships
        )
    return tuple(selected)


def _relationship_aggregate_chain(
    model: type[object],
    path: str,
) -> tuple[tuple[RelationshipProperty[object], type[object]], ...]:
    """Resolve relationship joins and reject repeated table paths.

    Args:
        model: Root mapped model class.
        path: Validated dot-separated relationship path.

    Returns:
        Relationship properties paired with their mapped target classes.

    Raises:
        DatabaseQueryError: If the path revisits a mapped table.
    """
    seen_tables: list[FromClause] = [_mapper(model).local_table]
    chain: list[tuple[RelationshipProperty[object], type[object]]] = []
    current_model = model
    for name in path.split("."):
        relationship = _mapper(current_model).relationships[name]
        related_model = cast("type[object]", relationship.mapper.class_)
        related_table = relationship.mapper.local_table
        secondary = relationship.secondary
        if any(table is related_table for table in seen_tables) or (
            secondary is not None
            and any(table is secondary for table in seen_tables)
        ):
            raise DatabaseQueryError(
                _REPEATED_RELATIONSHIP_AGGREGATE_TABLE_ERROR,
            )
        if secondary is not None:
            seen_tables.append(secondary)
        chain.append((relationship, related_model))
        seen_tables.append(related_table)
        current_model = related_model
    return tuple(chain)


def _relationship_aggregate_statement(
    chain: tuple[tuple[RelationshipProperty[object], type[object]], ...],
    selected: ColumnElement[object],
    service: DatabaseService,
) -> Select[object]:
    """Build one scoped aggregate query across a relationship path.

    Args:
        chain: Relationship properties and their mapped targets.
        selected: Aggregate expression selected from the final model.
        service: Active Database service used to resolve model scopes.

    Returns:
        Correlatable statement with every relationship join and visibility
        predicate applied.
    """
    first_relationship = chain[0][0]
    from_clause = _relationship_aggregate_join_target(first_relationship)
    for relationship, _ in chain[1:]:
        from_clause = from_clause.join(
            _relationship_aggregate_join_target(relationship),
            relationship.primaryjoin,
        )
    statement = (
        select(selected)
        .select_from(from_clause)
        .where(first_relationship.primaryjoin)
    )
    for _, intermediate_model in chain[:-1]:
        intermediate_query = ModelQueryBuilder(intermediate_model, service)
        intermediate_filter = intermediate_query.to_statement().whereclause
        if intermediate_filter is not None:
            statement = statement.where(intermediate_filter)
    final_model = chain[-1][1]
    final_query = ModelQueryBuilder(final_model, service)
    final_filter = final_query.to_statement().whereclause
    if final_filter is not None:
        statement = statement.where(final_filter)
    return statement


def _relationship_aggregate_join_target(
    relationship: RelationshipProperty[object],
) -> FromClause:
    """Build one relationship target, including its mapped secondary table.

    Args:
        relationship: SQLAlchemy relationship whose target joins the path.

    Returns:
        Target table or secondary-table join for the relationship.

    Raises:
        DatabaseQueryError: If a secondary relationship lacks its join.
    """
    related_table = relationship.mapper.local_table
    secondary = relationship.secondary
    if secondary is None:
        return related_table
    secondary_join = relationship.secondaryjoin
    if secondary_join is None:
        raise DatabaseQueryError(_RELATIONSHIP_SECONDARY_JOIN_ERROR)
    return secondary.join(related_table, secondary_join)


def _resolve_global_scopes[ModelT](
    model: type[ModelT],
) -> dict[str, ColumnElement[bool]]:
    """Evaluate trusted model scope factories into SQLAlchemy predicates.

    Args:
        model: Mapped class whose global scopes are being evaluated.

    Returns:
        Named SQLAlchemy predicates used by root and relationship queries.

    Raises:
        DatabaseQueryError: If a declared scope is not a named predicate
            factory or does not return a SQLAlchemy column expression.
    """
    declared = getattr(model, "global_scopes", {})
    if not isinstance(declared, Mapping):
        raise DatabaseQueryError(_INVALID_GLOBAL_SCOPES_ERROR)
    scope_factories = cast("Mapping[object, object]", declared)
    resolved: dict[str, ColumnElement[bool]] = {}
    for name, factory in scope_factories.items():
        if not isinstance(name, str) or not name or not callable(factory):
            raise DatabaseQueryError(_INVALID_GLOBAL_SCOPES_ERROR)
        condition = factory()
        if not isinstance(condition, ColumnElement):
            raise DatabaseQueryError(_INVALID_GLOBAL_SCOPES_ERROR)
        resolved[name] = cast("ColumnElement[bool]", condition)
    return resolved


def _soft_delete_condition(
    model: type[object],
) -> ColumnElement[bool] | None:
    """Return a mapped active-row criterion for a soft-delete model.

    Args:
        model: Mapped class that may declare ``SoftDeletes`` behavior.

    Returns:
        A null deletion-timestamp predicate, or ``None`` for other models.

    Raises:
        DatabaseQueryError: If the configured timestamp is not mapped.
    """
    if not getattr(model, "__soft_delete_enabled__", False):
        return None
    column_name = getattr(model, "deleted_at_name", "deleted_at")
    if not isinstance(column_name, str) or not _is_mapped_column(
        model,
        column_name,
    ):
        msg = "The soft-delete field must be a mapped model column."
        raise DatabaseQueryError(msg)
    return cast(
        "ColumnElement[bool]",
        getattr(model, column_name).is_(None),
    )


def _mapper(model: type[object]) -> Mapper[object]:
    """Return SQLAlchemy's mapper for a configured mapped class.

    Args:
        model: Class selected by the model query.

    Returns:
        SQLAlchemy's public mapper inspection object.
    """
    return sa_inspect(model)


def _is_mapped_column(model: type[object], name: str) -> bool:
    """Check a requested projection against mapped column attributes.

    Args:
        model: Mapped class being queried.
        name: Candidate mapped attribute name.

    Returns:
        Whether this name resolves to a mapped column property.
    """
    mapper = _mapper(model)
    return name in mapper.column_attrs


def _primary_key_name(model: type[object]) -> str:
    """Return one mapped key name or reject composite model identities.

    Args:
        model: Mapped class whose identity is being queried.

    Returns:
        The sole primary-key attribute name.

    Raises:
        DatabaseQueryError: If the mapped class has a composite key.
    """
    keys = _mapper(model).primary_key
    if len(keys) != 1 or keys[0].key is None:
        msg = "This model query requires a single-column primary key."
        raise DatabaseQueryError(msg)
    return keys[0].key


def _sole_model[ResultT](models: Sequence[ResultT]) -> ResultT:
    """Require exactly one model from a bounded result sequence.

    Args:
        models: At most two models returned by the caller's limit.

    Returns:
        The only model in the sequence.

    Raises:
        ModelNotFoundError: If the sequence is empty.
        MultipleModelsFoundError: If multiple models were returned.
    """
    if not models:
        raise ModelNotFoundError(_NO_MODELS_FOUND)
    if len(models) > 1:
        raise MultipleModelsFoundError(_MULTIPLE_MODELS_FOUND)
    return models[0]


def _raise_invalid_relationship() -> NoReturn:
    """Reject an unknown or malformed eager-load relationship path.

    Raises:
        DatabaseQueryError: If the requested relationship is not mapped.
    """
    msg = "The requested relationship path is not mapped on this model."
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


def _validate_stream_batch_size(batch_size: int) -> None:
    """Reject invalid result-stream batch sizes before acquiring a Session.

    Args:
        batch_size: Requested positive number of ORM rows per batch.

    Raises:
        ValueError: If ``batch_size`` is not a positive integer.
    """
    if type(batch_size) is not int or batch_size < _MINIMUM_PAGE_SIZE:
        raise ValueError(_INVALID_STREAM_BATCH_SIZE_ERROR)


__all__ = ["ModelQueryBuilder"]
