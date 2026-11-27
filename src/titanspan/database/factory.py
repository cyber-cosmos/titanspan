"""Generate and persist mapped models through native Database sessions.

Factories produce ordinary SQLAlchemy-instrumented models. Titanspan owns
definition composition and callbacks while the active Database service owns
their Unit of Work and transaction.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, ClassVar, Protocol, Self, TypeGuard, cast

from titanspan.database.exceptions import DatabaseFactoryError
from titanspan.database.model_collection import ModelCollection
from titanspan.facades.database import DB

if TYPE_CHECKING:
    from titanspan.contracts.database import DatabaseService


class _FactoryModel(Protocol):
    """Describe only the Active Record behavior consumed by factories.

    This protocol keeps factory batches independent of model classes.
    """

    connection: ClassVar[str | None]

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
        *,
        states: tuple[_FactoryState, ...] = (),
        sequence_values: tuple[Mapping[str, _FactoryValue], ...] = (),
        after_making: tuple[_FactoryCallback[ModelT], ...] = (),
        after_creating: tuple[_FactoryCallback[ModelT], ...] = (),
    ) -> None:
        """Bind a model type and copy its trusted factory definition.

        Args:
            model_class: Mapped class that the factory constructs.
            definition: Default values declared by the application model.
            states: Ordered attribute overrides applied to each generated item.
            sequence_values: Ordered per-item overrides repeated by index.
            after_making: Callbacks invoked after transient construction.
            after_creating: Callbacks deferred until the owning transaction
                commits successfully.
        """
        self._model_class = model_class
        self._definition = dict(definition)
        self._states = states
        self._sequence_values = tuple(
            dict(values) for values in sequence_values
        )
        self._after_making = after_making
        self._after_creating = after_creating

    def state(self, values: _FactoryState) -> ModelFactory[ModelT]:
        """Return a factory with one additional attribute state.

        Args:
            values: Attribute mapping or a callable that returns one per index.

        Returns:
            A new factory that preserves this factory's defaults and hooks.
        """
        return self._copy(states=(*self._states, values))

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
        return self._copy(sequence_values=tuple(values))

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
        return self._copy(after_making=(*self._after_making, callback))

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
        return self._copy(after_creating=(*self._after_creating, callback))

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
        """
        models = self.make_many(count, attributes)
        if not models:
            return models
        service = DB.resolve_service()
        with service.transaction(self._model_class.connection):
            for model in models:
                model.save()
                self._schedule_after_creating(service, model)
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
        """
        models = self.make_many(count, attributes)
        if not models:
            return models
        service = DB.resolve_service()
        async with service.transaction_async(self._model_class.connection):
            for model in models:
                await model.save_async()
                self._schedule_after_creating(service, model)
        return models

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
        if self._sequence_values:
            sequence_index = index % len(self._sequence_values)
            values.update(
                _resolve_mapping(
                    self._sequence_values[sequence_index],
                    index,
                ),
            )
        for state in self._states:
            state_values = (
                cast("Mapping[str, _FactoryValue]", state)
                if isinstance(state, Mapping)
                else state(index)
            )
            values.update(_resolve_mapping(state_values, index))
        if attributes is not None:
            values.update(attributes)
        model = self._model_class().force_fill(values)
        for callback in self._after_making:
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
        for callback in self._after_creating:
            service.after_commit(
                lambda callback=callback, model=model: callback(model),
                self._model_class.connection,
            )

    def _copy(
        self,
        *,
        states: tuple[_FactoryState, ...] | None = None,
        sequence_values: tuple[Mapping[str, _FactoryValue], ...] | None = None,
        after_making: tuple[_FactoryCallback[ModelT], ...] | None = None,
        after_creating: tuple[_FactoryCallback[ModelT], ...] | None = None,
    ) -> ModelFactory[ModelT]:
        """Create a builder copy with selected immutable option changes.

        Args:
            states: Replacement ordered state definitions.
            sequence_values: Replacement sequence definitions.
            after_making: Replacement transient callbacks.
            after_creating: Replacement committed-create callbacks.

        Returns:
            A new factory with unchanged options copied from this instance.
        """
        return ModelFactory(
            self._model_class,
            self._definition,
            states=self._states if states is None else states,
            sequence_values=(
                self._sequence_values
                if sequence_values is None
                else sequence_values
            ),
            after_making=(
                self._after_making if after_making is None else after_making
            ),
            after_creating=(
                self._after_creating
                if after_creating is None
                else after_creating
            ),
        )

    _model_class: type[ModelT]
    _definition: dict[str, _FactoryValue]
    _states: tuple[_FactoryState, ...]
    _sequence_values: tuple[Mapping[str, _FactoryValue], ...]
    _after_making: tuple[_FactoryCallback[ModelT], ...]
    _after_creating: tuple[_FactoryCallback[ModelT], ...]


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
