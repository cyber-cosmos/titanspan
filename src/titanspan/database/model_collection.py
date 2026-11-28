"""Extend native Collections with database model collection operations.

SQLAlchemy remains the source of model identity and mapped state. This
collection delegates persistence and serialization behavior to each model.
"""

from __future__ import annotations

import json
from itertools import chain
from typing import TYPE_CHECKING, Literal, Protocol, Self, cast

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import InstanceState
from sqlalchemy.orm.attributes import set_committed_value

from titanspan.collections import Collection
from titanspan.database.exceptions import (
    DatabaseQueryError,
    DatabaseTransactionOwnershipError,
    ModelSerializationLimitError,
)
from titanspan.database.model_state import (
    database_ownership,
    remember_service_graph,
    require_service,
)
from titanspan.facades.database import DB

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from titanspan.contracts.database import DatabaseService
    from titanspan.database.model import Model
    from titanspan.database.orm_builder import ModelQueryBuilder

type _Identity = tuple[
    type[object],
    tuple[object, ...],
    object | None,
]
type _RelationshipAggregate = Literal[
    "count",
    "exists",
    "sum",
    "avg",
    "min",
    "max",
]
_MAX_SERIALIZED_MODELS = 256
_AGGREGATE_COLUMN_ERROR = (
    "Sum, average, minimum, and maximum aggregates require a mapped column."
)
_UNSUPPORTED_AGGREGATE_ERROR = "The selected relationship aggregate is invalid."


class ModelCollection[ModelT](Collection[ModelT]):
    """Provide ordered collection operations based on mapped identity.

    Ordinary transformation methods inherited from ``Collection`` return a
    general collection when their result is no longer model-specific.
    """

    def model_keys(self) -> tuple[object | None, ...]:
        """Return primary keys in collection order.

        Returns:
            Single-column keys, composite key tuples, or ``None`` for
            transient models without a persisted SQLAlchemy identity.
        """
        return tuple(_primary_key_value(model) for model in self)

    def find(self, identifier: object) -> ModelT | None:
        """Find the first model with a matching primary key or identity.

        Args:
            identifier: Primary-key value or another mapped model instance.

        Returns:
            The matching model or ``None`` when this collection has no match.
        """
        identity = _model_identity(identifier)
        for model in self:
            if identity is not None and _model_identity(model) == identity:
                return model
            if _primary_key_value(model) == identifier:
                return model
        return None

    def contains(self, value: object) -> bool:
        """Check membership using SQLAlchemy identity for mapped models.

        Args:
            value: Candidate model or other value.

        Returns:
            Whether this collection contains the same mapped model identity.
        """
        identity = _model_identity(value)
        if identity is None:
            return any(model is value for model in self)
        return any(_model_identity(model) == identity for model in self)

    def __contains__(self, value: object, /) -> bool:
        """Apply model identity semantics to the ``in`` operator.

        Args:
            value: Candidate model or other value.

        Returns:
            Whether the matching mapped identity is present.
        """
        return self.contains(value)

    def concat(self, *others: Iterable[ModelT]) -> ModelCollection[ModelT]:
        """Append model values while preserving duplicates and their order.

        Args:
            *others: Additional model iterables appended in argument order.

        Returns:
            A model collection containing all values in source order.
        """
        return ModelCollection(chain(self, *others))

    def unique(self) -> ModelCollection[ModelT]:
        """Keep the first model for each mapped identity.

        Returns:
            A model collection with duplicate identities removed.
        """
        seen: set[tuple[str, object]] = set()
        selected: list[ModelT] = []
        for model in self:
            identity = _model_identity(model)
            marker: tuple[str, object] = (
                ("identity", identity)
                if identity is not None
                else ("object", id(model))
            )
            if marker not in seen:
                seen.add(marker)
                selected.append(model)
        return ModelCollection(selected)

    def difference(
        self,
        *others: Iterable[ModelT],
    ) -> ModelCollection[ModelT]:
        """Return stable unique models absent from every supplied iterable.

        Args:
            *others: Model iterables whose identities should be excluded.

        Returns:
            A model collection preserving this collection's order.
        """
        excluded = tuple(chain.from_iterable(others))
        selected = [
            model
            for model in self
            if not any(_same_model(model, item) for item in excluded)
        ]
        return ModelCollection(selected).unique()

    def intersection(
        self,
        *others: Iterable[ModelT],
    ) -> ModelCollection[ModelT]:
        """Return stable unique models present in each supplied iterable.

        Args:
            *others: Model iterables used for identity membership checks.

        Returns:
            Matching models from this collection in their original order.
        """
        if not others:
            return self.unique()
        groups = tuple(tuple(other) for other in others)
        selected = (
            model
            for model in self
            if all(
                any(_same_model(model, candidate) for candidate in group)
                for group in groups
            )
        )
        return ModelCollection(selected).unique()

    def merge(self, *others: Iterable[ModelT]) -> ModelCollection[ModelT]:
        """Merge model iterables once per identity in first-seen order.

        Args:
            *others: Model iterables appended before duplicate removal.

        Returns:
            A model collection with duplicate identities removed.
        """
        return self.concat(*others).unique()

    def union(self, *others: Iterable[ModelT]) -> ModelCollection[ModelT]:
        """Return the stable model-identity union of supplied iterables.

        Args:
            *others: Additional model iterables.

        Returns:
            A model collection with first-seen identities preserved.
        """
        return self.merge(*others)

    def to_collection(self) -> Collection[ModelT]:
        """Return the same model references as a general Collection.

        Returns:
            An ordinary native collection without model-specific methods.
        """
        return Collection(self)

    def to_dicts(self) -> list[dict[str, object]]:
        """Serialize each model within the bounded collection limit.

        Returns:
            Model dictionaries in collection order.

        Raises:
            ModelSerializationLimitError: If collection size exceeds the
                serialization limit.
        """
        if len(self) > _MAX_SERIALIZED_MODELS:
            message = (
                "Model collection serialization is limited to "
                f"{_MAX_SERIALIZED_MODELS} items."
            )
            raise ModelSerializationLimitError(message)
        return [cast("_SerializableModel", model).to_dict() for model in self]

    def to_json(self) -> str:
        """Serialize the models without exposing ORM instrumentation.

        Returns:
            A JSON array generated from each model's public dictionary.

        Raises:
            ModelSerializationLimitError: If collection size exceeds the
                serialization limit or a model graph exceeds its limits.
        """
        return json.dumps(self.to_dicts(), ensure_ascii=False)

    def make_hidden(self, *attributes: str) -> Self:
        """Hide selected attributes across all models in this collection.

        Args:
            *attributes: Attribute names omitted by model serialization.

        Returns:
            This collection after each model visibility policy is updated.
        """
        for model in self:
            cast("Model", model).make_hidden(*attributes)
        return self

    def merge_hidden(self, attributes: Sequence[str]) -> Self:
        """Add hidden attributes across all models in this collection.

        Args:
            attributes: Attribute names omitted by model serialization.

        Returns:
            This collection after each model visibility policy is updated.
        """
        for model in self:
            cast("Model", model).merge_hidden(attributes)
        return self

    def set_hidden(self, attributes: Sequence[str]) -> Self:
        """Replace hidden attributes across all models in this collection.

        Args:
            attributes: Attribute names omitted by model serialization.

        Returns:
            This collection after each model visibility policy is updated.
        """
        for model in self:
            cast("Model", model).set_hidden(attributes)
        return self

    def make_visible(self, *attributes: str) -> Self:
        """Make selected attributes visible across the collection.

        Args:
            *attributes: Attribute names included by model serialization.

        Returns:
            This collection after each model visibility policy is updated.
        """
        for model in self:
            cast("Model", model).make_visible(*attributes)
        return self

    def merge_visible(self, attributes: Sequence[str]) -> Self:
        """Add visible attributes across all models in this collection.

        Args:
            attributes: Attribute names included by model serialization.

        Returns:
            This collection after each model visibility policy is updated.
        """
        for model in self:
            cast("Model", model).merge_visible(attributes)
        return self

    def set_visible(self, attributes: Sequence[str]) -> Self:
        """Replace visible attributes across all models in this collection.

        Args:
            attributes: Attribute names included by model serialization.

        Returns:
            This collection after each model visibility policy is updated.
        """
        for model in self:
            cast("Model", model).set_visible(attributes)
        return self

    def load(self, *paths: str) -> Self:
        """Load related models in bounded batches through SQLAlchemy ORM.

        Existing model instances retain their scalar state. Requested
        relationships are assigned from a fresh eager-loaded query.

        Args:
            *paths: Mapped relationship paths, including nested dot paths.

        Returns:
            This collection after its related attributes are populated.
        """
        self._load_relationships(paths, missing_only=False)
        return self

    async def load_async(self, *paths: str) -> Self:
        """Asynchronously load related models in bounded batches.

        Args:
            *paths: Mapped relationship paths, including nested dot paths.

        Returns:
            This collection after its related attributes are populated.
        """
        await self._load_relationships_async(paths, missing_only=False)
        return self

    def load_missing(self, *paths: str) -> Self:
        """Load only requested relationships missing from any model.

        Args:
            *paths: Mapped relationship paths, including nested dot paths.

        Returns:
            This collection with previously missing paths populated.
        """
        self._load_relationships(paths, missing_only=True)
        return self

    async def load_missing_async(self, *paths: str) -> Self:
        """Asynchronously load requested relationships that remain missing.

        Args:
            *paths: Mapped relationship paths, including nested dot paths.

        Returns:
            This collection with previously missing paths populated.
        """
        await self._load_relationships_async(paths, missing_only=True)
        return self

    def load_aggregate(
        self,
        relationship: str,
        aggregate: _RelationshipAggregate,
        *,
        column_name: str | None = None,
        attribute: str | None = None,
    ) -> Self:
        """Load one direct relationship aggregate for persisted models.

        The result is assigned to the mapped ``query_expression()`` attribute
        selected by the aggregate kind. One query loads the full collection.

        Args:
            relationship: Mapped relationship path to aggregate.
            aggregate: Count, existence, sum, average, minimum, or maximum.
            column_name: Related mapped column required by numeric aggregates.
            attribute: Declared ``query_expression()`` result attribute.

        Returns:
            This collection after matching aggregate values are populated.

        Raises:
            DatabaseQueryError: If the relation, result attribute, or column
                is invalid.
            DatabaseTransactionOwnershipError: If models have mixed owners.
        """
        self._load_relationship_aggregate(
            relationship,
            aggregate,
            column_name=column_name,
            attribute=attribute,
        )
        return self

    async def load_aggregate_async(
        self,
        relationship: str,
        aggregate: _RelationshipAggregate,
        *,
        column_name: str | None = None,
        attribute: str | None = None,
    ) -> Self:
        """Asynchronously load one aggregate for persisted models.

        Args:
            relationship: Mapped relationship path to aggregate.
            aggregate: Count, existence, sum, average, minimum, or maximum.
            column_name: Related mapped column required by numeric aggregates.
            attribute: Declared ``query_expression()`` result attribute.

        Returns:
            This collection after matching aggregate values are populated.

        Raises:
            DatabaseQueryError: If the relation, result attribute, or column
                is invalid.
            DatabaseTransactionOwnershipError: If models have mixed owners.
        """
        await self._load_relationship_aggregate_async(
            relationship,
            aggregate,
            column_name=column_name,
            attribute=attribute,
        )
        return self

    def to_query(self) -> ModelQueryBuilder[ModelT]:
        """Create a query limited to this collection's persisted model keys.

        Returns:
            A model query builder constrained to the collection members.

        Raises:
            DatabaseQueryError: If the collection has no persisted model keys.
            DatabaseTransactionOwnershipError: If models have different
                classes, application owners, or connection owners.
            ValueError: If a model uses a composite primary key.
        """
        if not self:
            msg = "An empty model collection cannot become a query."
            raise DatabaseQueryError(msg)
        identifiers = _refresh_keys(self)
        if not identifiers:
            msg = "A model collection query requires persisted model keys."
            raise DatabaseQueryError(msg)
        _require_collection_owner(self)
        model_class = cast("type[_ModelQueryHost[ModelT]]", type(self[0]))
        return model_class.query().where_in(
            model_class.primary_key_name(),
            identifiers,
        )

    def refresh(self) -> Self:
        """Refresh each model in place using its owning Database service.

        Returns:
            This collection after every model has been refreshed.

        Raises:
            DatabaseTransactionOwnershipError: If the active application does
                not own a selected model.
            ModelNotFoundError: If a selected model no longer exists.
        """
        for model in self:
            cast("_RefreshableModel", model).refresh()
        return self

    async def refresh_async(self) -> Self:
        """Asynchronously refresh models sequentially in place.

        Sequential refresh gives each model operation exclusive ownership of
        its async session and preserves the collection's original instances.

        Returns:
            This collection after every model has been refreshed.

        Raises:
            DatabaseTransactionOwnershipError: If the active application does
                not own a selected model.
            ModelNotFoundError: If a selected model no longer exists.
        """
        for model in self:
            await cast("_RefreshableModel", model).refresh_async()
        return self

    def fresh(self) -> ModelCollection[ModelT]:
        """Retrieve current database versions for persisted model keys.

        Returns:
            A collection of existing rows in this collection's key order.

        Raises:
            ValueError: If a selected model uses a composite primary key.
        """
        identifiers = _refresh_keys(self)
        if not identifiers:
            return ModelCollection()
        model_class = cast("type[_ModelQueryHost[ModelT]]", type(self[0]))
        service, connection_name = _require_collection_owner(self)
        query = model_class.query()
        if getattr(model_class, "__soft_delete_enabled__", False):
            query.with_trashed()
        fresh_models = query.find_many(identifiers)
        for model in fresh_models:
            remember_service_graph(model, service, connection_name)
        return _ordered_fresh_models(identifiers, fresh_models)

    async def fresh_async(self) -> ModelCollection[ModelT]:
        """Asynchronously retrieve current versions of persisted models.

        Returns:
            A collection of existing rows in this collection's key order.

        Raises:
            ValueError: If a selected model uses a composite primary key.
        """
        identifiers = _refresh_keys(self)
        if not identifiers:
            return ModelCollection()
        model_class = cast("type[_ModelQueryHost[ModelT]]", type(self[0]))
        service, connection_name = _require_collection_owner(self)
        query = model_class.query()
        if getattr(model_class, "__soft_delete_enabled__", False):
            query.with_trashed()
        fresh_models = await query.find_many_async(identifiers)
        for model in fresh_models:
            remember_service_graph(model, service, connection_name)
        return _ordered_fresh_models(identifiers, fresh_models)

    def _load_relationships(
        self,
        paths: tuple[str, ...],
        *,
        missing_only: bool,
    ) -> None:
        """Load and attach mapped relationships for the selected models.

        Args:
            paths: Validated relationship paths requested by the caller.
            missing_only: Whether already-loaded paths should be preserved.
        """
        if not paths or not self:
            return
        model_class = cast("type[_ModelQueryHost[ModelT]]", type(self[0]))
        service, connection_name = _require_collection_owner(self)
        query = model_class.query()
        if getattr(model_class, "__soft_delete_enabled__", False):
            query.with_trashed()
        query.with_(*paths)
        selected = _missing_paths(self, paths) if missing_only else paths
        if not selected:
            return
        identifiers = _refresh_keys(self)
        if not identifiers:
            return
        fresh_models = query.with_(*selected).find_many(identifiers)
        _attach_loaded_relationships(
            self,
            fresh_models,
            selected,
            missing_only=missing_only,
        )
        for model in self:
            remember_service_graph(model, service, connection_name)

    async def _load_relationships_async(
        self,
        paths: tuple[str, ...],
        *,
        missing_only: bool,
    ) -> None:
        """Asynchronously load and attach mapped relationships.

        Args:
            paths: Validated relationship paths requested by the caller.
            missing_only: Whether already-loaded paths should be preserved.
        """
        if not paths or not self:
            return
        model_class = cast("type[_ModelQueryHost[ModelT]]", type(self[0]))
        service, connection_name = _require_collection_owner(self)
        query = model_class.query()
        if getattr(model_class, "__soft_delete_enabled__", False):
            query.with_trashed()
        query.with_(*paths)
        selected = _missing_paths(self, paths) if missing_only else paths
        if not selected:
            return
        identifiers = _refresh_keys(self)
        if not identifiers:
            return
        fresh_models = await query.with_(*selected).find_many_async(identifiers)
        _attach_loaded_relationships(
            self,
            fresh_models,
            selected,
            missing_only=missing_only,
        )
        for model in self:
            remember_service_graph(model, service, connection_name)

    def _load_relationship_aggregate(
        self,
        relationship: str,
        aggregate: _RelationshipAggregate,
        *,
        column_name: str | None,
        attribute: str | None,
    ) -> None:
        """Query aggregate values once and assign them to original models.

        Args:
            relationship: Mapped relationship path to aggregate.
            aggregate: Selected aggregate kind.
            column_name: Related model column for numeric aggregates.
            attribute: Optional result attribute override.
        """
        identifiers = _refresh_keys(self)
        if not identifiers:
            return
        model_class = cast("type[_ModelQueryHost[ModelT]]", type(self[0]))
        service, connection_name = _require_collection_owner(self)
        key_name = model_class.primary_key_name()
        query = model_class.query()
        if getattr(model_class, "__soft_delete_enabled__", False):
            query.with_trashed()
        result_attribute = _apply_relationship_aggregate(
            query,
            relationship,
            aggregate,
            column_name=column_name,
            attribute=attribute,
        )
        fresh_models = query.where_in(key_name, identifiers).get()
        values = {
            getattr(model, key_name): getattr(model, result_attribute)
            for model in fresh_models
        }
        for model in self:
            identifier = getattr(model, key_name)
            if identifier in values:
                set_committed_value(
                    model,
                    result_attribute,
                    values[identifier],
                )
            remember_service_graph(model, service, connection_name)

    async def _load_relationship_aggregate_async(
        self,
        relationship: str,
        aggregate: _RelationshipAggregate,
        *,
        column_name: str | None,
        attribute: str | None,
    ) -> None:
        """Asynchronously query one aggregate for the whole collection.

        Args:
            relationship: Mapped relationship path to aggregate.
            aggregate: Selected aggregate kind.
            column_name: Related model column for numeric aggregates.
            attribute: Optional result attribute override.
        """
        identifiers = _refresh_keys(self)
        if not identifiers:
            return
        model_class = cast("type[_ModelQueryHost[ModelT]]", type(self[0]))
        service, connection_name = _require_collection_owner(self)
        key_name = model_class.primary_key_name()
        query = model_class.query()
        if getattr(model_class, "__soft_delete_enabled__", False):
            query.with_trashed()
        result_attribute = _apply_relationship_aggregate(
            query,
            relationship,
            aggregate,
            column_name=column_name,
            attribute=attribute,
        )
        fresh_models = await query.where_in(key_name, identifiers).get_async()
        values = {
            getattr(model, key_name): getattr(model, result_attribute)
            for model in fresh_models
        }
        for model in self:
            identifier = getattr(model, key_name)
            if identifier in values:
                set_committed_value(
                    model,
                    result_attribute,
                    values[identifier],
                )
            remember_service_graph(model, service, connection_name)


class _SerializableModel(Protocol):
    """Describe a model's public serialization contract.

    This protocol-shaped cast isolates the expected method at the ORM
    boundary without importing the concrete declarative base.
    """

    def to_dict(self) -> dict[str, object]:
        """Return the model's safe public attributes.

        Returns:
            Serialized public attributes.
        """
        ...


class _RefreshableModel(Protocol):
    """Describe the in-place refresh operations supplied by mapped models.

    The collection delegates persistence and session ownership to each model.
    """

    def refresh(self) -> object:
        """Reload mapped values through the model's owning service.

        Returns:
            The refreshed model instance.
        """
        ...

    async def refresh_async(self) -> object:
        """Reload mapped values asynchronously through the owning service.

        Returns:
            The refreshed model instance.
        """
        ...


class _ModelQueryHost[ModelT](Protocol):
    """Describe a mapped model class with a typed query entry point.

    The protocol keeps collection refresh independent from the concrete
    declarative base while preserving the selected model type.
    """

    @classmethod
    def query(cls) -> ModelQueryBuilder[ModelT]:
        """Start a typed query for this mapped model class.

        Returns:
            A query builder that can reload selected model identities.
        """
        ...

    @classmethod
    def primary_key_name(cls) -> str:
        """Return the mapped single-column key used for collection loading.

        Returns:
            The mapped primary-key attribute name.
        """
        ...


def _apply_relationship_aggregate[ModelT](
    query: ModelQueryBuilder[ModelT],
    relationship: str,
    aggregate: _RelationshipAggregate,
    *,
    column_name: str | None,
    attribute: str | None,
) -> str:
    """Add one aggregate to a query and return its result attribute name.

    Args:
        query: Builder for the parent model type.
        relationship: Mapped relationship path to aggregate.
        aggregate: Selected aggregate kind.
        column_name: Related mapped column for numeric aggregates.
        attribute: Optional result attribute override.

    Returns:
        The declared query-expression attribute populated by the builder.

    Raises:
        DatabaseQueryError: If the aggregate or its required column is invalid.
    """
    if aggregate == "count":
        result_attribute = attribute or (
            f"{relationship.replace('.', '_')}_count"
        )
        query.with_count(relationship, attribute=result_attribute)
        return result_attribute
    if aggregate == "exists":
        result_attribute = attribute or (
            f"{relationship.replace('.', '_')}_exists"
        )
        query.with_exists(relationship, attribute=result_attribute)
        return result_attribute
    if column_name is None:
        raise DatabaseQueryError(_AGGREGATE_COLUMN_ERROR)
    result_attribute = attribute or (
        f"{relationship.replace('.', '_')}_{aggregate}_{column_name}"
    )
    if aggregate == "sum":
        query.with_sum(
            relationship,
            column_name,
            attribute=result_attribute,
        )
        return result_attribute
    if aggregate == "avg":
        query.with_avg(
            relationship,
            column_name,
            attribute=result_attribute,
        )
        return result_attribute
    if aggregate == "min":
        query.with_min(
            relationship,
            column_name,
            attribute=result_attribute,
        )
        return result_attribute
    if aggregate == "max":
        query.with_max(
            relationship,
            column_name,
            attribute=result_attribute,
        )
        return result_attribute
    raise DatabaseQueryError(_UNSUPPORTED_AGGREGATE_ERROR)


def _model_identity(value: object) -> _Identity | None:
    """Return SQLAlchemy's persisted identity for one mapped instance.

    Args:
        value: Candidate mapped object.

    Returns:
        Its mapped class and primary-key tuple, or ``None`` when transient.
    """
    state = sa_inspect(value, raiseerr=False)
    if not isinstance(state, InstanceState) or state.identity is None:
        return None
    return (
        type(value),
        cast("tuple[object, ...]", state.identity),
        database_ownership(value),
    )


def _primary_key_value(value: object) -> object | None:
    """Return the scalar or composite key for one persisted model.

    Args:
        value: Candidate mapped model.

    Returns:
        Its SQLAlchemy primary-key value or ``None`` while transient.
    """
    identity = _model_identity(value)
    if identity is None:
        return None
    keys = identity[1]
    return keys[0] if len(keys) == 1 else keys


def _same_model(left: object, right: object) -> bool:
    """Compare two values by mapped identity or transient object identity.

    Args:
        left: First candidate value.
        right: Second candidate value.

    Returns:
        Whether both values refer to the same mapped database row.
    """
    if left is right:
        return True
    left_identity = _model_identity(left)
    return left_identity is not None and left_identity == _model_identity(right)


def _missing_paths[ModelT](
    collection: ModelCollection[ModelT],
    paths: tuple[str, ...],
) -> tuple[str, ...]:
    """Select paths that are not loaded for every model in a collection.

    Args:
        collection: Models whose relationship state is inspected.
        paths: Validated paths requested by the caller.

    Returns:
        Paths missing from at least one model instance.
    """
    return tuple(
        path
        for path in paths
        if any(
            not _relationship_path_loaded(model, path) for model in collection
        )
    )


def _relationship_path_loaded(model: object, path: str) -> bool:
    """Check a relationship path without triggering lazy database I/O.

    Args:
        model: SQLAlchemy mapped model instance.
        path: Dot-separated relationship path.

    Returns:
        Whether all relationship attributes in the path are already loaded.
    """
    current_models = [model]
    for name in path.split("."):
        related_models: list[object] = []
        for current in current_models:
            state = sa_inspect(current, raiseerr=False)
            if not isinstance(state, InstanceState):
                return False
            mapped_state = cast("InstanceState[object]", state)
            mapper = mapped_state.mapper
            relationship = mapper.relationships.get(name)
            if relationship is None:
                return False
            if name in state.unloaded:
                return False
            value = state.attrs[name].loaded_value
            if relationship.uselist:
                related_models.extend(cast("Iterable[object]", value))
            elif value is not None:
                related_models.append(value)
        current_models = related_models
    return True


def _attach_loaded_relationships[ModelT](
    collection: ModelCollection[ModelT],
    fresh_models: Iterable[ModelT],
    paths: tuple[str, ...],
    *,
    missing_only: bool,
) -> None:
    """Attach eagerly loaded relationship values to existing models.

    Args:
        collection: Original model instances whose scalar state is retained.
        fresh_models: New query results with SQLAlchemy eager loading applied.
        paths: Relationship paths returned by that query.
        missing_only: Whether already-loaded paths must remain unchanged.
    """
    models_by_key: dict[object, ModelT] = {}
    for model in fresh_models:
        key = _primary_key_value(model)
        if key is not None:
            models_by_key[key] = model

    for model in collection:
        key = _primary_key_value(model)
        if key is None:
            continue
        fresh_model = models_by_key.get(key)
        if fresh_model is None:
            continue
        relationship_names = {
            path.split(".", maxsplit=1)[0]
            for path in paths
            if not missing_only or not _relationship_path_loaded(model, path)
        }
        for name in relationship_names:
            set_committed_value(
                model,
                name,
                getattr(fresh_model, name),
            )


def _refresh_keys[ModelT](
    collection: ModelCollection[ModelT],
) -> tuple[object, ...]:
    """Collect refreshable single-column identifiers in collection order.

    Args:
        collection: Models selected for a fresh database read.

    Returns:
        Persisted primary-key identifiers.

    Raises:
        ValueError: If a selected model uses a composite primary key.
    """
    if not collection:
        return ()
    identifiers: list[object] = []
    for model in collection:
        identity = _model_identity(model)
        if identity is None:
            continue
        if len(identity[1]) != 1:
            msg = "Collection refresh requires single-column primary keys."
            raise ValueError(msg)
        identifiers.append(identity[1][0])
    return tuple(identifiers)


def _require_collection_owner[ModelT](
    collection: ModelCollection[ModelT],
) -> tuple[DatabaseService, str]:
    """Validate one collection against the active app and connection.

    Args:
        collection: Persisted models selected for refresh or relation loading.

    Returns:
        The canonical service and connection shared by all models.

    Raises:
        DatabaseTransactionOwnershipError: If models have different classes,
            application owners, or logical connection owners.
    """
    model_class = type(collection[0])
    service = DB.resolve_service()
    connection_name = service.connection(
        cast("str | None", getattr(model_class, "connection", None)),
    ).name
    for model in collection:
        if type(model) is not model_class:
            msg = "A model collection refresh requires one mapped model type."
            raise DatabaseTransactionOwnershipError(msg)
        # The mapped class owns one default connection; recorded per-instance
        # ownership catches instances previously used by another connection.
        require_service(model, service, connection_name)
    return service, connection_name


def _ordered_fresh_models[ModelT](
    identifiers: tuple[object, ...],
    models: Iterable[ModelT],
) -> ModelCollection[ModelT]:
    """Order a fresh database result to match the original collection.

    Args:
        identifiers: Persisted keys in the original order.
        models: Models retrieved from the database.

    Returns:
        Existing refreshed rows in the requested order.
    """
    by_key = {_primary_key_value(model): model for model in models}
    return ModelCollection(by_key[key] for key in identifiers if key in by_key)


__all__ = ["ModelCollection"]
