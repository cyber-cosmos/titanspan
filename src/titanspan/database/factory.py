"""Generate and persist mapped models through native Database sessions.

Factories produce ordinary SQLAlchemy-instrumented models. Titanspan owns
definition composition and callbacks while the active Database service owns
their Unit of Work and transaction.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, ClassVar, Protocol, Self, TypeGuard, cast

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.orm.attributes import set_committed_value

from titanspan.database.exceptions import (
    DatabaseFactoryError,
    ModelPersistenceCancelledError,
)
from titanspan.database.model_collection import ModelCollection
from titanspan.database.model_state import ensure_session_owner
from titanspan.facades.database import DB

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import RelationshipProperty, Session

    from titanspan.contracts.database import DatabaseService


class _FactoryModel(Protocol):
    """Describe only the Active Record behavior consumed by factories.

    This protocol keeps factory batches independent of model classes.
    """

    connection: ClassVar[str | None]

    @property
    def exists(self) -> bool:
        """Whether the model already represents a persisted row.

        Returns:
            Whether the model has been persisted.
        """
        ...

    def force_fill(self, attributes: Mapping[str, object], /) -> Self:
        """Assign factory-owned values to mapped columns.

        Args:
            attributes: Trusted model column values.

        Returns:
            The instrumented model instance.
        """
        ...

    def save(self) -> bool:
        """Flush the model through its thread-owned session.

        The factory uses the standard Active Record save lifecycle.
        """
        ...

    async def save_async(self) -> bool:
        """Flush the model through its task-owned session.

        The factory uses the standard asynchronous save lifecycle.
        """
        ...


type _FactoryValue = object | Callable[[int], object]
type _FactoryState = (
    Mapping[str, _FactoryValue] | Callable[[int], Mapping[str, _FactoryValue]]
)
type _FactoryCallback[ModelT] = Callable[[ModelT], None]

_EMPTY_INDEX = 0
_FACTORY_RELATIONSHIP_ERROR = (
    "The factory relationship must name a compatible mapped relation."
)
_FACTORY_RELATIONSHIP_COUNT_ERROR = (
    "Scalar or recycled factory relationships require a count of one."
)
_FACTORY_RECYCLED_MODEL_ERROR = (
    "A recycled factory relationship requires a persisted model."
)


@dataclass(frozen=True, slots=True)
class _FactoryRelationship:
    """Describe related values and callbacks for one model graph.

    Attributes:
        name: Mapped relationship name on the owner model.
        collection: Whether the mapped relationship accepts a collection.
        count: Number of related models built by the factory.
        recycled: Whether the factory reuses a caller-owned model.
        populate_foreign_keys: Copy keys for a recycled scalar relation.
        make_related: Build or reuse one related instance.
        schedule_created: Register child factory callbacks after commit.
    """

    name: str
    collection: bool
    count: int
    recycled: bool
    populate_foreign_keys: Callable[[object, _FactoryModel], None] | None
    make_related: Callable[[int], _FactoryModel]
    schedule_created: Callable[[DatabaseService, object], None] | None


@dataclass(frozen=True, slots=True)
class _FactoryOptions[ModelT: _FactoryModel]:
    """Retain immutable builder options for one model factory.

    Attributes:
        states: Ordered attribute overrides applied to each model.
        sequence_values: Repeating per-item attribute overrides.
        after_making: Callbacks run after transient model construction.
        after_creating: Callbacks deferred until the transaction commits.
        relationships: Related factories or existing mapped records.
    """

    states: tuple[_FactoryState, ...] = ()
    sequence_values: tuple[Mapping[str, _FactoryValue], ...] = ()
    after_making: tuple[_FactoryCallback[ModelT], ...] = ()
    after_creating: tuple[_FactoryCallback[ModelT], ...] = ()
    relationships: tuple[_FactoryRelationship, ...] = ()


class ModelFactory[ModelT: _FactoryModel]:
    """Build transient or persistent models from declared attributes.

    A model's ``factory_attributes`` mapping may contain values or callables
    that receive the zero-based item index. Factory builders are immutable;
    reuse them safely by deriving separate states or sequences.
    """

    def __init__(
        self,
        model_class: type[ModelT],
        definition: Mapping[str, _FactoryValue],
        options: _FactoryOptions[ModelT] | None = None,
    ) -> None:
        """Bind a model type and copy its trusted factory definition.

        Args:
            model_class: Mapped class that the factory constructs.
            definition: Default values declared by the application model.
            options: Immutable builder settings copied by fluent operations.
        """
        self._model_class = model_class
        self._definition = dict(definition)
        self._options = options or _FactoryOptions[ModelT]()

    def state(self, values: _FactoryState) -> ModelFactory[ModelT]:
        """Return a factory with one additional attribute state.

        Args:
            values: Attribute mapping or a callable that returns one per index.

        Returns:
            A new factory that preserves this factory's defaults and hooks.
        """
        return self._copy(
            replace(
                self._options,
                states=(*self._options.states, values),
            ),
        )

    def sequence(
        self,
        *values: Mapping[str, _FactoryValue],
    ) -> ModelFactory[ModelT]:
        """Return a factory with repeating ordered per-item overrides.

        Args:
            *values: Attribute maps applied in order and then repeated.

        Returns:
            A new factory with the requested sequence.

        Raises:
            DatabaseFactoryError: If no sequence values are provided.
        """
        if not values:
            message = "A model factory sequence requires at least one value."
            raise DatabaseFactoryError(message)
        return self._copy(
            replace(
                self._options,
                sequence_values=tuple(dict(value) for value in values),
            ),
        )

    def after_making(
        self,
        callback: _FactoryCallback[ModelT],
    ) -> ModelFactory[ModelT]:
        """Return a factory that calls back after transient construction.

        Args:
            callback: Synchronous callback invoked before persistence.

        Returns:
            A new factory that includes the callback.
        """
        return self._copy(
            replace(
                self._options,
                after_making=(*self._options.after_making, callback),
            ),
        )

    def after_creating(
        self,
        callback: _FactoryCallback[ModelT],
    ) -> ModelFactory[ModelT]:
        """Return a factory with a callback deferred until transaction commit.

        Args:
            callback: Synchronous callback invoked after successful commit.

        Returns:
            A new factory that includes the callback.
        """
        return self._copy(
            replace(
                self._options,
                after_creating=(*self._options.after_creating, callback),
            ),
        )

    def relationship[RelatedT: _FactoryModel](
        self,
        name: str,
        related: ModelFactory[RelatedT] | RelatedT,
        *,
        count: int = 1,
    ) -> ModelFactory[ModelT]:
        """Build one mapped related value or a collection of related models.

        A related factory creates fresh models for each parent. A persisted
        model can be supplied for a single-valued relation.

        Args:
            name: Mapped relationship on this factory's model.
            related: Related-model factory or an existing mapped model.
            count: Number of models for a collection relationship.

        Returns:
            A new factory with the related graph attached during ``make``.

        Raises:
            DatabaseFactoryError: If the relationship or related type is
                invalid, or the count conflicts with its mapped cardinality.
        """
        _validate_count(count)
        mapped_relationship = _resolve_mapped_relationship(
            self._model_class,
            name,
        )
        if not mapped_relationship.uselist and count != 1:
            raise DatabaseFactoryError(_FACTORY_RELATIONSHIP_COUNT_ERROR)
        if isinstance(related, ModelFactory):
            relationship = self._factory_relationship(
                name,
                mapped_relationship,
                related,
                count,
            )
        else:
            if mapped_relationship.uselist and count != 1:
                raise DatabaseFactoryError(
                    _FACTORY_RELATIONSHIP_COUNT_ERROR,
                )
            if not isinstance(related, mapped_relationship.mapper.class_):
                raise DatabaseFactoryError(_FACTORY_RELATIONSHIP_ERROR)
            relationship = _recycled_relationship(
                self._model_class,
                name,
                mapped_relationship,
                related,
            )
        return self._copy(
            replace(
                self._options,
                relationships=(
                    *self._options.relationships,
                    relationship,
                ),
            ),
        )

    def _factory_relationship[RelatedT: _FactoryModel](
        self,
        name: str,
        mapped_relationship: RelationshipProperty[object],
        related: ModelFactory[RelatedT],
        count: int,
    ) -> _FactoryRelationship:
        """Build a recursive relationship specification from a factory.

        Args:
            name: Relationship attribute on the owner model.
            mapped_relationship: SQLAlchemy's relationship property.
            related: Factory for transient related models.
            count: Number of models for collection relationships.

        Returns:
            Relation construction and callback behavior.

        Raises:
            DatabaseFactoryError: If the related type is incompatible.
        """
        related_type = related._model_class
        if not issubclass(related_type, mapped_relationship.mapper.class_):
            raise DatabaseFactoryError(_FACTORY_RELATIONSHIP_ERROR)

        def make_related(index: int) -> _FactoryModel:
            """Build one related model without database I/O.

            Args:
                index: Deterministic index passed to the related factory.

            Returns:
                One transient mapped related model.
            """
            return related._make_one(index, None)

        def schedule_related(
            service: DatabaseService,
            related_model: object,
        ) -> None:
            """Schedule nested callbacks after the complete graph commits.

            Args:
                service: Database service that owns the transaction.
                related_model: Related instance flushed with its parent.
            """
            if not isinstance(related_model, related_type):
                raise DatabaseFactoryError(_FACTORY_RELATIONSHIP_ERROR)
            related._schedule_after_creating(service, related_model)
            related._schedule_relationship_callbacks(
                service,
                related_model,
            )

        return _FactoryRelationship(
            name=name,
            collection=bool(mapped_relationship.uselist),
            count=count,
            recycled=False,
            populate_foreign_keys=None,
            make_related=make_related,
            schedule_created=schedule_related,
        )

    def count(self, count: int) -> FactoryBatch[ModelT]:
        """Select a typed batch operation with a fixed item count.

        Args:
            count: Non-negative number of model instances to make or create.

        Returns:
            A batch builder whose operations return ``ModelCollection``.

        Raises:
            DatabaseFactoryError: If count is not a non-negative integer.
        """
        _validate_count(count)
        return FactoryBatch(self, count)

    def make(
        self,
        attributes: Mapping[str, object] | None = None,
    ) -> ModelT:
        """Build one transient model without performing database I/O.

        Args:
            attributes: Trusted final overrides for this generated model.

        Returns:
            An unsaved, instrumented model instance.
        """
        return self._make_one(_EMPTY_INDEX, attributes)

    def make_many(
        self,
        count: int,
        attributes: Mapping[str, object] | None = None,
    ) -> ModelCollection[ModelT]:
        """Build a collection of transient models without database I/O.

        Args:
            count: Non-negative number of model instances to build.
            attributes: Trusted overrides applied to every generated model.

        Returns:
            A native model collection of unsaved instances.
        """
        _validate_count(count)
        return ModelCollection(
            self._make_one(index, attributes) for index in range(count)
        )

    def create(
        self,
        attributes: Mapping[str, object] | None = None,
    ) -> ModelT:
        """Create and persist one model in the current sync transaction.

        Args:
            attributes: Trusted final overrides for this generated model.

        Returns:
            The persisted detached model instance.

        Raises:
            ModelPersistenceCancelledError: If a model event rejects creation.
        """
        return self.create_many(1, attributes)[0]

    def create_many(
        self,
        count: int,
        attributes: Mapping[str, object] | None = None,
    ) -> ModelCollection[ModelT]:
        """Persist models sequentially in one sync transaction.

        Args:
            count: Non-negative number of model instances to persist.
            attributes: Trusted overrides applied to every generated model.

        Returns:
            A native model collection in creation order.

        Raises:
            ModelPersistenceCancelledError: If a model event rejects a write.
        """
        models = self.make_many(count, attributes)
        if not models:
            return models
        service = DB.resolve_service()
        with (
            service.transaction(self._model_class.connection),
            service.session(self._model_class.connection) as session,
        ):
            for model in models:
                self._validate_recycled_relationships(
                    service,
                    session,
                    model,
                )
                saved = model.save()
                _require_successful_save(model, saved)
                self._schedule_after_creating(service, model)
                self._schedule_relationship_callbacks(service, model)
        return models

    async def create_async(
        self,
        attributes: Mapping[str, object] | None = None,
    ) -> ModelT:
        """Create and persist one model in the current async transaction.

        Args:
            attributes: Trusted final overrides for this generated model.

        Returns:
            The persisted detached model instance.

        Raises:
            ModelPersistenceCancelledError: If a model event rejects creation.
        """
        return (await self.create_many_async(1, attributes))[0]

    async def create_many_async(
        self,
        count: int,
        attributes: Mapping[str, object] | None = None,
    ) -> ModelCollection[ModelT]:
        """Persist models sequentially in one task-owned transaction.

        Args:
            count: Non-negative number of model instances to persist.
            attributes: Trusted overrides applied to every generated model.

        Returns:
            A native model collection in creation order.

        Raises:
            ModelPersistenceCancelledError: If a model event rejects a write.
        """
        models = self.make_many(count, attributes)
        if not models:
            return models
        service = DB.resolve_service()
        async with (
            service.transaction_async(self._model_class.connection),
            service.session_async(
                self._model_class.connection,
            ) as session,
        ):
            for model in models:
                self._validate_recycled_relationships(
                    service,
                    session,
                    model,
                )
                saved = await model.save_async()
                _require_successful_save(model, saved)
                self._schedule_after_creating(service, model)
                self._schedule_relationship_callbacks(service, model)
        return models

    def _validate_recycled_relationships(
        self,
        service: DatabaseService,
        session: Session | AsyncSession,
        model: ModelT,
    ) -> None:
        """Verify reused related models share the active app and session.

        Args:
            service: Database service owning the factory operation.
            session: Current Unit of Work session.
            model: Factory-created parent or child with assigned relations.
        """
        for relationship in self._options.relationships:
            if not relationship.recycled:
                continue
            related_model = getattr(model, relationship.name)
            ensure_session_owner(related_model, service, session)

    def _make_one(
        self,
        index: int,
        attributes: Mapping[str, object] | None,
    ) -> ModelT:
        """Compose one model's defaults, sequence, states, and final values.

        Args:
            index: Zero-based index within the generated batch.
            attributes: Optional trusted final overrides.

        Returns:
            One transient model after its make callbacks have run.
        """
        values = _resolve_mapping(self._definition, index)
        if self._options.sequence_values:
            sequence_index = index % len(self._options.sequence_values)
            values.update(
                _resolve_mapping(
                    self._options.sequence_values[sequence_index],
                    index,
                ),
            )
        for state in self._options.states:
            state_values = (
                cast("Mapping[str, _FactoryValue]", state)
                if isinstance(state, Mapping)
                else state(index)
            )
            values.update(_resolve_mapping(state_values, index))
        if attributes is not None:
            values.update(attributes)
        model = self._model_class().force_fill(values)
        # SQLAlchemy's Unit of Work persists this graph through its mapped
        # relationship cascade, keeping parent and related rows atomic.
        for relationship in self._options.relationships:
            related_models = [
                relationship.make_related(
                    index * max(relationship.count, 1) + related_index,
                )
                for related_index in range(relationship.count)
            ]
            related_value: object = (
                related_models if relationship.collection else related_models[0]
            )
            if relationship.recycled and not relationship.collection:
                # Keep a reused parent's inverse collection untouched while
                # this child remains transient.
                if relationship.populate_foreign_keys is None:
                    raise DatabaseFactoryError(
                        _FACTORY_RELATIONSHIP_ERROR,
                    )
                relationship.populate_foreign_keys(
                    model,
                    related_models[0],
                )
                set_committed_value(
                    model,
                    relationship.name,
                    related_value,
                )
            else:
                setattr(model, relationship.name, related_value)
        for callback in self._options.after_making:
            callback(model)
        return model

    def _schedule_after_creating(
        self,
        service: DatabaseService,
        model: ModelT,
    ) -> None:
        """Register successful-create callbacks with transaction ownership.

        Args:
            service: Active application Database service.
            model: Model whose flush completed in the current transaction.
        """
        for callback in self._options.after_creating:
            service.after_commit(
                lambda callback=callback, model=model: callback(model),
                self._model_class.connection,
            )

    def _schedule_relationship_callbacks(
        self,
        service: DatabaseService,
        model: ModelT,
    ) -> None:
        """Schedule related factory callbacks after their shared commit.

        Args:
            service: Application Database service that owns the transaction.
            model: Persisted model whose related graph was flushed.
        """
        for relationship in self._options.relationships:
            if relationship.schedule_created is None:
                continue
            related_value = getattr(model, relationship.name)
            related_models = (
                tuple(related_value)
                if relationship.collection
                else (related_value,)
            )
            for related_model in related_models:
                relationship.schedule_created(service, related_model)

    def _copy(
        self,
        options: _FactoryOptions[ModelT],
    ) -> ModelFactory[ModelT]:
        """Create a builder copy with selected immutable options.

        Args:
            options: New options applied to the copied factory.

        Returns:
            A new factory with unchanged options copied from this instance.
        """
        return ModelFactory(
            self._model_class,
            self._definition,
            options,
        )

    _model_class: type[ModelT]
    _definition: dict[str, _FactoryValue]
    _options: _FactoryOptions[ModelT]


def _resolve_mapped_relationship(
    owner_type: type[object],
    name: str,
) -> RelationshipProperty[object]:
    """Resolve one mapped relationship or report a native factory error.

    Args:
        owner_type: Candidate mapped class that owns the relationship.
        name: Relationship attribute requested by the factory.

    Returns:
        SQLAlchemy's mapped relationship property.

    Raises:
        DatabaseFactoryError: If the class is not mapped or the name is absent.
    """
    try:
        relationship = sa_inspect(owner_type).relationships.get(name)
    except NoInspectionAvailable as error:
        raise DatabaseFactoryError(
            _FACTORY_RELATIONSHIP_ERROR,
        ) from error
    if relationship is None:
        raise DatabaseFactoryError(_FACTORY_RELATIONSHIP_ERROR)
    return relationship


def _recycled_relationship(
    owner_type: type[object],
    name: str,
    mapped_relationship: RelationshipProperty[object],
    related: _FactoryModel,
) -> _FactoryRelationship:
    """Build safe behavior for one persisted single-valued relation.

    Args:
        owner_type: Mapped class that owns the relationship.
        name: Relationship attribute name on the owner model.
        mapped_relationship: SQLAlchemy relationship property.
        related: Persisted related model selected by the caller.

    Returns:
        Construction and foreign-key behavior for one reused value.

    Raises:
        DatabaseFactoryError: If the related model is transient or the
            relationship does not expose direct foreign-key synchronization.
    """
    if mapped_relationship.uselist:
        raise DatabaseFactoryError(_FACTORY_RELATIONSHIP_ERROR)
    if not related.exists:
        raise DatabaseFactoryError(_FACTORY_RECYCLED_MODEL_ERROR)
    related_type = type(related)
    owner_mapper = sa_inspect(owner_type)
    related_mapper = sa_inspect(related_type)

    def populate_foreign_keys(
        owner: object,
        related_model: _FactoryModel,
    ) -> None:
        """Set owner foreign keys before assigning the recycled relation.

        Args:
            owner: Transient model being constructed by this factory.
            related_model: Existing related row selected by the caller.

        Raises:
            DatabaseFactoryError: If the relationship uses a custom join.
        """
        if not isinstance(owner, owner_type) or not isinstance(
            related_model,
            related_type,
        ):
            raise DatabaseFactoryError(_FACTORY_RELATIONSHIP_ERROR)
        copied = False
        for (
            source_column,
            target_column,
        ) in mapped_relationship.synchronize_pairs:
            if (
                source_column.table is not related_mapper.local_table
                or target_column.table is not owner_mapper.local_table
            ):
                raise DatabaseFactoryError(_FACTORY_RELATIONSHIP_ERROR)
            source_key = related_mapper.get_property_by_column(
                source_column,
            ).key
            target_key = owner_mapper.get_property_by_column(
                target_column,
            ).key
            setattr(owner, target_key, getattr(related_model, source_key))
            copied = True
        if not copied:
            raise DatabaseFactoryError(_FACTORY_RELATIONSHIP_ERROR)

    def make_related(index: int) -> _FactoryModel:
        """Return the selected existing model without copying it.

        Args:
            index: Unused factory item index.

        Returns:
            The existing model selected by the caller.
        """
        del index
        return related

    return _FactoryRelationship(
        name=name,
        collection=False,
        count=1,
        recycled=True,
        populate_foreign_keys=populate_foreign_keys,
        make_related=make_related,
        schedule_created=None,
    )


class FactoryBatch[ModelT: _FactoryModel]:
    """Apply factory states and persistence operations to a fixed batch.

    Creation remains sequential within the owning transaction.
    """

    def __init__(
        self,
        factory: ModelFactory[ModelT],
        count: int,
    ) -> None:
        """Retain one factory and its validated item count.

        Args:
            factory: Immutable model factory configuration.
            count: Non-negative item count validated by ``ModelFactory``.
        """
        _validate_count(count)
        self._factory = factory
        self._count = count

    def state(self, values: _FactoryState) -> FactoryBatch[ModelT]:
        """Add one state to every model in this batch.

        Args:
            values: Attribute mapping or an index-based mapping factory.

        Returns:
            A new batch builder preserving the selected item count.
        """
        return FactoryBatch(self._factory.state(values), self._count)

    def sequence(
        self,
        *values: Mapping[str, _FactoryValue],
    ) -> FactoryBatch[ModelT]:
        """Set repeating per-item values for this batch.

        Args:
            *values: Ordered mappings applied to generated items.

        Returns:
            A new batch builder preserving the selected item count.
        """
        return FactoryBatch(self._factory.sequence(*values), self._count)

    def after_making(
        self,
        callback: _FactoryCallback[ModelT],
    ) -> FactoryBatch[ModelT]:
        """Add a callback invoked for each transient batch model.

        Args:
            callback: Synchronous callback invoked before persistence.

        Returns:
            A new batch builder preserving the selected item count.
        """
        return FactoryBatch(
            self._factory.after_making(callback),
            self._count,
        )

    def after_creating(
        self,
        callback: _FactoryCallback[ModelT],
    ) -> FactoryBatch[ModelT]:
        """Add a callback deferred until each row's transaction commits.

        Args:
            callback: Synchronous callback invoked after successful commit.

        Returns:
            A new batch builder preserving the selected item count.
        """
        return FactoryBatch(
            self._factory.after_creating(callback),
            self._count,
        )

    def make(
        self,
        attributes: Mapping[str, object] | None = None,
    ) -> ModelCollection[ModelT]:
        """Build this batch as transient models.

        Args:
            attributes: Trusted overrides applied to each generated model.

        Returns:
            A collection of unsaved models.
        """
        return self._factory.make_many(self._count, attributes)

    def create(
        self,
        attributes: Mapping[str, object] | None = None,
    ) -> ModelCollection[ModelT]:
        """Persist this batch through the synchronous transaction policy.

        Args:
            attributes: Trusted overrides applied to each generated model.

        Returns:
            A collection of persisted models in creation order.

        Raises:
            ModelPersistenceCancelledError: If a model event rejects a write.
        """
        return self._factory.create_many(self._count, attributes)

    async def create_async(
        self,
        attributes: Mapping[str, object] | None = None,
    ) -> ModelCollection[ModelT]:
        """Persist this batch through the task-owned async transaction.

        Args:
            attributes: Trusted overrides applied to each generated model.

        Returns:
            A collection of persisted models in creation order.

        Raises:
            ModelPersistenceCancelledError: If a model event rejects a write.
        """
        return await self._factory.create_many_async(
            self._count,
            attributes,
        )

    _factory: ModelFactory[ModelT]
    _count: int


def _resolve_mapping(
    values: Mapping[str, _FactoryValue],
    index: int,
) -> dict[str, object]:
    """Resolve index-based attribute values into a detached mapping.

    Args:
        values: Trusted factory attributes.
        index: Zero-based item index passed to value callbacks.

    Returns:
        Attribute values ready for mapped model assignment.
    """
    resolved: dict[str, object] = {}
    for name, value in values.items():
        resolved[name] = value(index) if _is_indexed_value(value) else value
    return resolved


def _is_indexed_value(
    value: object,
) -> TypeGuard[Callable[[int], object]]:
    """Identify an application value callback using the factory signature.

    Args:
        value: Value declared in a factory definition.

    Returns:
        Whether the value is callable with one zero-based index.
    """
    return callable(value)


def _require_successful_save(model: _FactoryModel, saved: bool) -> None:
    """Reject a factory result whose model save was cancelled.

    Args:
        model: Factory model whose persistence was attempted.
        saved: Result returned by the model's direct save operation.

    Raises:
        ModelPersistenceCancelledError: If a model event cancelled the save.
    """
    if not saved:
        model_name = type(model).__name__
        message = f"Persistence of {model_name} was cancelled by an event."
        raise ModelPersistenceCancelledError(message)


def _validate_count(count: int) -> None:
    """Require a finite, non-negative integer batch size.

    Args:
        count: Requested number of models.

    Raises:
        DatabaseFactoryError: If the requested batch size is invalid.
    """
    if type(count) is not int or count < 0:
        message = "A model factory count must be a non-negative integer."
        raise DatabaseFactoryError(message)


__all__ = ["FactoryBatch", "ModelFactory"]
