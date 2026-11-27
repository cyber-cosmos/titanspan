"""Build typed model queries over the shared SQLAlchemy Core expressions.

The wrapper adds model hydration and ORM loading while QueryBuilder remains
the source of identifiers, predicates, joins, ordering, and SQL statements.
"""

from __future__ import annotations

from copy import copy
from datetime import UTC, datetime
from typing import TYPE_CHECKING, NoReturn, Self, cast

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import not_
from sqlalchemy.orm import load_only, raiseload, selectinload

from titanspan.database.exceptions import (
    DatabaseQueryError,
    ModelNotFoundError,
    MultipleModelsFoundError,
)
from titanspan.database.model_collection import ModelCollection
from titanspan.database.model_state import remember_service
from titanspan.database.pagination import LengthAwarePaginator, Paginator
from titanspan.database.query_builder import QueryBuilder

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from sqlalchemy.engine import ScalarResult
    from sqlalchemy.orm import Mapper, QueryableAttribute, RelationshipProperty
    from sqlalchemy.orm.strategy_options import Load
    from sqlalchemy.sql.base import ExecutableOption
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.sql.schema import Table
    from sqlalchemy.sql.selectable import Select, TableClause

    from titanspan.contracts.database import DatabaseService

_MISSING = object()
_NO_MODELS_FOUND = "The query did not match a model."
_MULTIPLE_MODELS_FOUND = "The query matched more than one model."
_FIRST_PAGE = 1
_MINIMUM_PAGE_SIZE = 1


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
        if getattr(model, "__soft_delete_enabled__", False):
            column_name = getattr(model, "deleted_at_name", "deleted_at")
            if not isinstance(column_name, str) or not _is_mapped_column(
                model,
                column_name,
            ):
                msg = "The soft-delete field must be a mapped model column."
                raise DatabaseQueryError(msg)
            self._soft_delete_column = column_name
            self._query.set_scope_condition(
                cast("ColumnElement[bool]", table.c[column_name].is_(None)),
            )
        self._eager_paths: list[str] = []
        self._prevent_lazy = False
        self._selected_columns: tuple[str, ...] = ()

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

    def with_trashed(self) -> Self:
        """Include soft-deleted rows in this query when supported.

        Returns:
            This builder with its default deletion condition removed.
        """
        if self._soft_delete_column is not None:
            self._query.set_scope_condition(None)
        return self

    def without_trashed(self) -> Self:
        """Restrict a soft-delete query to active rows.

        Returns:
            This builder with the active-row condition applied.
        """
        if self._soft_delete_column is not None:
            self._query.set_scope_condition(
                cast(
                    "ColumnElement[bool]",
                    self._table.c[self._soft_delete_column].is_(None),
                ),
            )
        return self

    def only_trashed(self) -> Self:
        """Restrict a soft-delete query to deleted rows.

        Returns:
            This builder with the deleted-row condition applied.
        """
        if self._soft_delete_column is not None:
            self._query.set_scope_condition(
                cast(
                    "ColumnElement[bool]",
                    self._table.c[self._soft_delete_column].is_not(None),
                ),
            )
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
        cloned._selected_columns = self._selected_columns  # noqa: SLF001
        return cloned

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
        if self._prevent_lazy:
            options.append(raiseload("*"))
        return statement.options(*options)

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
                remember_service(model, self._service)
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
                remember_service(model, self._service)
            return ModelCollection(models)

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
        if self._soft_delete_column is not None:
            key_name = _primary_key_name(self._model)
            return self.clone().where(key_name, identifier).first()
        with self._service.session(self._connection_name) as session:
            model = session.get(self._model, identifier)
            if model is not None:
                remember_service(model, self._service)
            return model

    async def find_async(self, identifier: object) -> ModelT | None:
        """Asynchronously find a model by its primary key.

        Args:
            identifier: Primary-key value supported by AsyncSession.

        Returns:
            A detached model or ``None``.
        """
        if self._soft_delete_column is not None:
            key_name = _primary_key_name(self._model)
            return await self.clone().where(key_name, identifier).first_async()
        async with self._service.session_async(
            self._connection_name,
        ) as session:
            model = await session.get(self._model, identifier)
            if model is not None:
                remember_service(model, self._service)
            return model

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
        for parent, relationship in reversed(chain):
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
        for name in path.split("."):
            relationship = _mapper(current).relationships[name]
            attribute = cast(
                "QueryableAttribute[object]",
                getattr(current, name),
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


__all__ = ["ModelQueryBuilder"]
