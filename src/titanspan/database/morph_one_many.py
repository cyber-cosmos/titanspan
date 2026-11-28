"""Provide explicit polymorphic one-to-one and one-to-many relations.

The relation binds safe discriminator values to the native model query API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Self, cast

from sqlalchemy import inspect as sa_inspect

from titanspan.database.exceptions import (
    DatabaseConfigurationError,
    DatabaseQueryError,
)
from titanspan.database.model_collection import ModelCollection
from titanspan.facades.database import DB

if TYPE_CHECKING:
    from collections.abc import Mapping

    from titanspan.database.orm_builder import ModelQueryBuilder

    class _MorphModel[ModelT](Protocol):
        """Describe native model methods used by relation persistence.

        The protocol remains private to the adapter boundary.
        """

        @classmethod
        def query(cls) -> ModelQueryBuilder[ModelT]:
            """Return the native ORM builder for the mapped model.

            Returns:
                The application-owned query builder.
            """
            ...

        def fill(self, attributes: Mapping[str, object]) -> Self:
            """Assign mass-assignable attributes to the mapped model.

            Args:
                attributes: Candidate values accepted by model fill rules.

            Returns:
                This model instance.
            """
            ...

        def save_or_fail(self) -> bool:
            """Persist this model through its native Unit of Work.

            Returns:
                Whether the model was persisted.
            """
            ...

        async def save_or_fail_async(self) -> bool:
            """Persist this model through its async Unit of Work.

            Returns:
                Whether the model was persisted.
            """
            ...


class MorphOne[RelatedT]:
    """Declare an explicit polymorphic one-to-one relationship.

    Args:
        related_model: Child class storing the discriminator and foreign key.
        type_column: Child-model discriminator attribute.
        foreign_key: Child-model attribute referencing the owner key.
        owner_key: Mapped key attribute on the declaring parent model.
    """

    def __init__(
        self,
        related_model: type[RelatedT],
        type_column: str,
        foreign_key: str,
        owner_key: str,
    ) -> None:
        """Store the validated child and mapped relationship attributes.

        Args:
            related_model: Child class storing the discriminator and key.
            type_column: Child-model discriminator attribute.
            foreign_key: Child-model attribute referencing the owner key.
            owner_key: Mapped key attribute on the declaring parent model.
        """
        self.related_model = related_model
        self.type_column = type_column
        self.foreign_key = foreign_key
        self.owner_key = owner_key

    def __get__(
        self,
        instance: object | None,
        _owner: type[object] | None = None,
    ) -> MorphOneRelation[RelatedT]:
        """Bind explicit query and persistence operations to one parent.

        Args:
            instance: Parent instance receiving this descriptor.
            _owner: Parent class supplied by Python's descriptor protocol.

        Returns:
            A bound relation with explicit sync and async operations.

        Raises:
            AttributeError: If accessed on a class without a parent instance.
            DatabaseConfigurationError: If mapped columns are invalid.
        """
        if instance is None:
            message = "A polymorphic relation requires a model instance."
            raise AttributeError(message)
        return MorphOneRelation(
            instance,
            self.related_model,
            type_column=self.type_column,
            foreign_key=self.foreign_key,
            owner_key=self.owner_key,
        )


class MorphMany[RelatedT]:
    """Declare an explicit polymorphic one-to-many relationship.

    Args:
        related_model: Child class storing the discriminator and foreign key.
        type_column: Child-model discriminator attribute.
        foreign_key: Child-model attribute referencing the owner key.
        owner_key: Mapped key attribute on the declaring parent model.
    """

    def __init__(
        self,
        related_model: type[RelatedT],
        type_column: str,
        foreign_key: str,
        owner_key: str,
    ) -> None:
        """Store the validated child and mapped relationship attributes.

        Args:
            related_model: Child class storing the discriminator and key.
            type_column: Child-model discriminator attribute.
            foreign_key: Child-model attribute referencing the owner key.
            owner_key: Mapped key attribute on the declaring parent model.
        """
        self.related_model = related_model
        self.type_column = type_column
        self.foreign_key = foreign_key
        self.owner_key = owner_key

    def __get__(
        self,
        instance: object | None,
        _owner: type[object] | None = None,
    ) -> MorphManyRelation[RelatedT]:
        """Bind explicit query and persistence operations to one parent.

        Args:
            instance: Parent instance receiving this descriptor.
            _owner: Parent class supplied by Python's descriptor protocol.

        Returns:
            A bound relation with explicit sync and async operations.

        Raises:
            AttributeError: If accessed on a class without a parent instance.
            DatabaseConfigurationError: If mapped columns are invalid.
        """
        if instance is None:
            message = "A polymorphic relation requires a model instance."
            raise AttributeError(message)
        return MorphManyRelation(
            instance,
            self.related_model,
            type_column=self.type_column,
            foreign_key=self.foreign_key,
            owner_key=self.owner_key,
        )


class _MorphOneOrManyRelation[RelatedT]:
    """Bind polymorphic child queries and writes to one mapped parent.

    Subclasses select either one row or a model collection from this query.
    """

    def __init__(
        self,
        parent: object,
        related_model: type[RelatedT],
        *,
        type_column: str,
        foreign_key: str,
        owner_key: str,
    ) -> None:
        """Validate mapper attributes and retain their owning model objects.

        Args:
            parent: Owner instance whose key identifies matching children.
            related_model: Mapped child class with polymorphic key columns.
            type_column: Child-model discriminator attribute.
            foreign_key: Child-model attribute referencing the owner key.
            owner_key: Mapped key attribute on the declaring parent model.

        Raises:
            DatabaseConfigurationError: If a declared field is unmapped.
            ValueError: If mapped attribute names are invalid or duplicated.
        """
        names = (type_column, foreign_key, owner_key)
        if any(not _is_non_empty_string(name) for name in names):
            message = "Polymorphic mapped attribute names must not be empty."
            raise ValueError(message)
        if type_column == foreign_key:
            message = "Polymorphic type and foreign-key columns must differ."
            raise ValueError(message)
        if not _is_mapped_model(type(parent)):
            message = "The polymorphic owner must be a mapped model class."
            raise DatabaseConfigurationError(message)
        if not _is_mapped_model(related_model):
            message = "The polymorphic child must be a mapped model class."
            raise DatabaseConfigurationError(message)
        if not _is_mapped_column(type(parent), owner_key):
            message = "The polymorphic owner key must be a mapped column."
            raise DatabaseConfigurationError(message)
        if not _is_mapped_column(related_model, type_column):
            message = "The polymorphic type attribute must be a mapped column."
            raise DatabaseConfigurationError(message)
        if not _is_mapped_column(related_model, foreign_key):
            message = "The polymorphic foreign key must be a mapped column."
            raise DatabaseConfigurationError(message)
        self._parent = parent
        self._related_model = related_model
        self._type_column = type_column
        self._foreign_key = foreign_key
        self._owner_key = owner_key

    def query(self) -> ModelQueryBuilder[RelatedT]:
        """Build a child query constrained to this parent and trusted alias.

        Returns:
            The native model query builder scoped by type and owner key.

        Raises:
            DatabaseConfigurationError: If the active app lacks an alias.
            DatabaseQueryError: If the parent has no mapped key value.
        """
        alias, key = self._association_values()
        related_model = cast(
            "type[_MorphModel[RelatedT]]",
            self._related_model,
        )
        return (
            related_model.query()
            .where(self._foreign_key, key)
            .where(self._type_column, alias)
        )

    def create(self, attributes: Mapping[str, object]) -> RelatedT:
        """Create one child while enforcing trusted owner columns.

        Args:
            attributes: Child attributes accepted by its mass-assignment rules.

        Returns:
            The persisted child with this relation's type and owner key.

        Raises:
            DatabaseConfigurationError: If the active app lacks an alias.
            DatabaseQueryError: If this parent has no mapped key value.
        """
        model = self._new_related_model(attributes)
        self._set_association(model)
        cast("_MorphModel[RelatedT]", model).save_or_fail()
        return model

    async def create_async(
        self,
        attributes: Mapping[str, object],
    ) -> RelatedT:
        """Asynchronously create one child for this parent.

        Args:
            attributes: Child attributes accepted by its mass-assignment rules.

        Returns:
            The persisted child with this relation's type and owner key.

        Raises:
            DatabaseConfigurationError: If the active app lacks an alias.
            DatabaseQueryError: If this parent has no mapped key value.
        """
        model = self._new_related_model(attributes)
        self._set_association(model)
        await cast("_MorphModel[RelatedT]", model).save_or_fail_async()
        return model

    def save(self, model: RelatedT) -> RelatedT:
        """Associate and persist one existing child synchronously.

        Args:
            model: Child instance to attach to this parent.

        Returns:
            The persisted child.

        Raises:
            DatabaseConfigurationError: If the child class is invalid.
            DatabaseQueryError: If this parent has no mapped key value.
        """
        self._set_association(model)
        cast("_MorphModel[RelatedT]", model).save_or_fail()
        return model

    async def save_async(self, model: RelatedT) -> RelatedT:
        """Associate and persist one existing child asynchronously.

        Args:
            model: Child instance to attach to this parent.

        Returns:
            The persisted child.

        Raises:
            DatabaseConfigurationError: If the child class is invalid.
            DatabaseQueryError: If this parent has no mapped key value.
        """
        self._set_association(model)
        await cast("_MorphModel[RelatedT]", model).save_or_fail_async()
        return model

    def dissociate(self, model: RelatedT) -> None:
        """Clear both nullable polymorphic fields on an associated child.

        Args:
            model: Child instance to detach from this parent.

        Raises:
            DatabaseConfigurationError: If either child field is not nullable.
            DatabaseQueryError: If the child does not belong to this parent.
        """
        alias, key = self._association_values()
        if not isinstance(model, self._related_model):
            message = "The polymorphic child has an incompatible model type."
            raise DatabaseConfigurationError(message)
        if (
            getattr(model, self._type_column) != alias
            or getattr(
                model,
                self._foreign_key,
            )
            != key
        ):
            message = "The polymorphic child does not belong to this parent."
            raise DatabaseQueryError(message)
        if not _is_nullable_column(self._related_model, self._type_column):
            message = "The polymorphic type column must be nullable to detach."
            raise DatabaseConfigurationError(message)
        if not _is_nullable_column(self._related_model, self._foreign_key):
            message = "The polymorphic foreign key must be nullable to detach."
            raise DatabaseConfigurationError(message)
        setattr(model, self._type_column, None)
        setattr(model, self._foreign_key, None)

    def _new_related_model(
        self,
        attributes: Mapping[str, object],
    ) -> RelatedT:
        """Construct and mass-assign a new child before trusted key updates.

        Args:
            attributes: Candidate values filtered by child fillable rules.

        Returns:
            A transient mapped child instance.
        """
        model_type = cast(
            "type[_MorphModel[RelatedT]]",
            self._related_model,
        )
        return cast("RelatedT", model_type().fill(attributes))

    def _set_association(self, model: RelatedT) -> None:
        """Set validated discriminator and owner values on a child instance.

        Args:
            model: Mapped child instance receiving this relation's keys.

        Raises:
            DatabaseConfigurationError: If the child has an incompatible type
                or the parent class has no trusted alias.
            DatabaseQueryError: If the parent key is null.
        """
        if not isinstance(model, self._related_model):
            message = "The polymorphic child has an incompatible model type."
            raise DatabaseConfigurationError(message)
        alias, key = self._association_values()
        setattr(model, self._type_column, alias)
        setattr(model, self._foreign_key, key)

    def _association_values(self) -> tuple[str, object]:
        """Return this parent's trusted discriminator and mapped key.

        Returns:
            The configured alias and non-null owner key.

        Raises:
            DatabaseConfigurationError: If the active app lacks an alias.
            DatabaseQueryError: If the owner key has not been assigned.
        """
        alias = DB.resolve_service().morph_alias_for(type(self._parent))
        if alias is None:
            message = "The parent has no trusted morph alias in this app."
            raise DatabaseConfigurationError(message)
        key = getattr(self._parent, self._owner_key)
        if key is None:
            message = "The polymorphic owner requires a non-null owner key."
            raise DatabaseQueryError(message)
        return alias, key


class MorphOneRelation[RelatedT](_MorphOneOrManyRelation[RelatedT]):
    """Resolve or mutate one child row for a polymorphic parent.

    Database access occurs only through explicit query and resolution methods.
    """

    def resolve(self) -> RelatedT | None:
        """Synchronously load the first matching child.

        Returns:
            The related child or ``None`` when no parent key or row exists.
        """
        if getattr(self._parent, self._owner_key) is None:
            return None
        return self.query().first()

    async def resolve_async(self) -> RelatedT | None:
        """Asynchronously load the first matching child.

        Returns:
            The related child or ``None`` when no parent key or row exists.
        """
        if getattr(self._parent, self._owner_key) is None:
            return None
        return await self.query().first_async()


class MorphManyRelation[RelatedT](_MorphOneOrManyRelation[RelatedT]):
    """Resolve a model collection for one polymorphic parent.

    Database access occurs only through explicit query and resolution methods.
    """

    def resolve(self) -> ModelCollection[RelatedT]:
        """Synchronously load every matching child through the ORM.

        Returns:
            Related models in query order, or an empty collection for a
            parent without a key.
        """
        if getattr(self._parent, self._owner_key) is None:
            return ModelCollection(())
        return self.query().get()

    async def resolve_async(self) -> ModelCollection[RelatedT]:
        """Asynchronously load every matching child through the ORM.

        Returns:
            Related models in query order, or an empty collection for a
            parent without a key.
        """
        if getattr(self._parent, self._owner_key) is None:
            return ModelCollection(())
        return await self.query().get_async()


def morph_one[RelatedT](
    related_model: type[RelatedT],
    *,
    type_column: str,
    foreign_key: str,
    owner_key: str = "id",
) -> MorphOne[RelatedT]:
    """Declare an explicit one-to-one relation to a polymorphic child.

    Args:
        related_model: Mapped child class storing the type and owner key.
        type_column: Child-model discriminator attribute.
        foreign_key: Child-model key attribute referencing the owner.
        owner_key: Mapped parent attribute selected by that key.

    Returns:
        A descriptor exposing explicit query, resolve, create, and save APIs.

    Raises:
        DatabaseConfigurationError: If a model or mapped field is invalid.
        ValueError: If relationship attribute names are invalid.
    """
    _validate_relationship(
        related_model,
        type_column,
        foreign_key,
        owner_key,
    )
    return MorphOne(related_model, type_column, foreign_key, owner_key)


def morph_many[RelatedT](
    related_model: type[RelatedT],
    *,
    type_column: str,
    foreign_key: str,
    owner_key: str = "id",
) -> MorphMany[RelatedT]:
    """Declare an explicit one-to-many relation to polymorphic children.

    Args:
        related_model: Mapped child class storing the type and owner key.
        type_column: Child-model discriminator attribute.
        foreign_key: Child-model key attribute referencing the owner.
        owner_key: Mapped parent attribute selected by that key.

    Returns:
        A descriptor exposing explicit query, resolve, create, and save APIs.

    Raises:
        DatabaseConfigurationError: If a model or mapped field is invalid.
        ValueError: If relationship attribute names are invalid.
    """
    _validate_relationship(
        related_model,
        type_column,
        foreign_key,
        owner_key,
    )
    return MorphMany(related_model, type_column, foreign_key, owner_key)


def _validate_relationship(
    related_model: type[object],
    type_column: str,
    foreign_key: str,
    owner_key: str,
) -> None:
    """Validate mapped child attributes before creating a descriptor.

    Args:
        related_model: Child class storing the discriminator and key.
        type_column: Child-model discriminator attribute.
        foreign_key: Child-model key attribute referencing the owner.
        owner_key: Parent attribute selected by that key.

    Raises:
        DatabaseConfigurationError: If the child class or mapped fields are
            invalid.
        ValueError: If a field name is empty or source fields are duplicated.
    """
    names = (type_column, foreign_key, owner_key)
    if any(not _is_non_empty_string(name) for name in names):
        message = "Polymorphic mapped attribute names must not be empty."
        raise ValueError(message)
    if type_column == foreign_key:
        message = "Polymorphic type and foreign-key columns must differ."
        raise ValueError(message)
    if not _is_mapped_model(related_model):
        message = "The polymorphic child must be a mapped model class."
        raise DatabaseConfigurationError(message)
    if not _is_mapped_column(related_model, type_column):
        message = "The polymorphic type attribute must be a mapped column."
        raise DatabaseConfigurationError(message)
    if not _is_mapped_column(related_model, foreign_key):
        message = "The polymorphic foreign key must be a mapped column."
        raise DatabaseConfigurationError(message)


def _is_mapped_model(value: object) -> bool:
    """Return whether a class uses SQLAlchemy and Titanspan model APIs.

    Args:
        value: Runtime value to validate as a mapped class.

    Returns:
        Whether the value is a mapped type with ``query()``.
    """
    return (
        isinstance(value, type)
        and sa_inspect(value, raiseerr=False) is not None
        and callable(getattr(value, "query", None))
    )


def _is_mapped_column(model_type: type[object], name: str) -> bool:
    """Return whether a mapped class exposes a single SQLAlchemy column.

    Args:
        model_type: Mapped class to inspect.
        name: Python attribute name checked against mapped columns.

    Returns:
        Whether the name resolves to exactly one mapped column.
    """
    mapper = sa_inspect(model_type, raiseerr=False)
    if mapper is None or name not in mapper.column_attrs:
        return False
    return len(mapper.column_attrs[name].columns) == 1


def _is_nullable_column(model_type: type[object], name: str) -> bool:
    """Return whether one mapped attribute uses a nullable SQL column.

    Args:
        model_type: Mapped child class.
        name: Mapped attribute whose nullability will be checked.

    Returns:
        Whether its single mapped SQL column accepts null values.

    The relation constructor validates the mapper attribute before use.
    """
    mapper = sa_inspect(model_type)
    column = mapper.column_attrs[name].columns[0]
    return bool(column.nullable)


def _is_non_empty_string(value: object) -> bool:
    """Return whether a relationship name has non-whitespace text.

    Args:
        value: Candidate mapped attribute name.

    Returns:
        Whether the value is a non-empty string after whitespace trimming.
    """
    return isinstance(value, str) and bool(value.strip())


__all__ = [
    "MorphMany",
    "MorphManyRelation",
    "MorphOne",
    "MorphOneRelation",
    "morph_many",
    "morph_one",
]
