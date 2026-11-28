"""Provide explicit, trusted polymorphic belongs-to access.

The descriptor resolves aliases through the active application's Database
service and delegates model queries to the native ORM builder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from sqlalchemy import inspect as sa_inspect

from titanspan.database.exceptions import (
    DatabaseConfigurationError,
    DatabaseQueryError,
)
from titanspan.facades.database import DB

_MORPH_TO_CACHE_KEY = "titanspan_morph_to_targets"
_MorphTargetCacheEntry = tuple[
    object,
    object | None,
    object | None,
    object | None,
]

if TYPE_CHECKING:
    from titanspan.contracts.database import DatabaseService
    from titanspan.database.orm_builder import ModelQueryBuilder

    class _QueryableModel[ModelT](Protocol):
        """Describe the native query entry point used by mapped models.

        The protocol stays private to this module's model-resolution edge.
        """

        @classmethod
        def query(cls) -> ModelQueryBuilder[ModelT]:
            """Return the model's application-owned ORM builder.

            Returns:
                A builder that resolves operations through the active app.
            """
            ...


class MorphTo[TargetT]:
    """Declare an explicit polymorphic belongs-to accessor.

    Args:
        type_column: Mapped discriminator attribute on the declaring model.
        foreign_key: Mapped target key attribute on the declaring model.
        owner_key: Target attribute matched against ``foreign_key``.
    """

    def __init__(
        self,
        target_models: tuple[type[TargetT], ...],
        type_column: str,
        foreign_key: str,
        owner_key: str,
    ) -> None:
        """Store the mapped column names required by this relationship.

        Args:
            type_column: Declaring-model discriminator attribute.
            foreign_key: Declaring-model target key attribute.
            owner_key: Mapped target attribute selected by that key.
            target_models: Model classes allowed for this relationship.
        """
        self.target_models = target_models
        self.type_column = type_column
        self.foreign_key = foreign_key
        self.owner_key = owner_key
        self._relationship_name: str | None = None

    def __set_name__(self, _owner: type[object], name: str) -> None:
        """Remember the model attribute bound to this descriptor.

        Args:
            _owner: Model class that declares this descriptor.
            name: Python attribute mapped to this polymorphic relation.
        """
        self._relationship_name = name

    def __get__(
        self,
        instance: object | None,
        _owner: type[object] | None = None,
    ) -> MorphToRelation[TargetT]:
        """Bind explicit resolution and association operations to one model.

        Args:
            instance: Declaring model instance receiving this descriptor.
            _owner: Declaring model class supplied by Python's descriptor API.

        Returns:
            A bound relation with explicit sync and async operations.

        Raises:
            AttributeError: If code accesses the relationship on its class.
            DatabaseConfigurationError: If its mapped columns are invalid.
        """
        if instance is None:
            message = "A polymorphic relation requires a model instance."
            raise AttributeError(message)
        return MorphToRelation(
            instance,
            target_models=self.target_models,
            type_column=self.type_column,
            foreign_key=self.foreign_key,
            owner_key=self.owner_key,
            relationship_name=self._relationship_name or "",
        )


class MorphToRelation[TargetT]:
    """Resolve or update one polymorphic belongs-to association.

    Database I/O occurs only in ``resolve`` or ``resolve_async``. Association
    methods update the declaring model's mapped key and discriminator fields.
    """

    def __init__(
        self,
        parent: object,
        *,
        target_models: tuple[type[TargetT], ...],
        type_column: str,
        foreign_key: str,
        owner_key: str,
        relationship_name: str = "",
    ) -> None:
        """Bind relationship columns to one declaring model instance.

        Args:
            parent: Model instance that stores the type and foreign key.
            type_column: Declaring-model discriminator attribute.
            foreign_key: Declaring-model target key attribute.
            owner_key: Mapped target attribute selected by that key.
            target_models: Model classes allowed for this relationship.
            relationship_name: Declaring model attribute used for cache state.
        """
        self._parent = parent
        self._target_models = target_models
        self._type_column = type_column
        self._foreign_key = foreign_key
        self._owner_key = owner_key
        self._relationship_name = relationship_name
        if not _is_mapped_column(type(parent), type_column):
            message = "The polymorphic type attribute must be a mapped column."
            raise DatabaseConfigurationError(message)
        if not _is_mapped_column(type(parent), foreign_key):
            message = "The polymorphic foreign key must be a mapped column."
            raise DatabaseConfigurationError(message)

    def resolve(self) -> TargetT | None:
        """Synchronously load the explicitly mapped target model.

        Returns:
            The matching target model, or ``None`` for a null association.

        Raises:
            DatabaseConfigurationError: If the discriminator is untrusted.
            DatabaseQueryError: If only one association column is null.
        """
        target_type, target_key = self.target_for_eager_loading()
        if target_type is None:
            return None
        service = DB.resolve_service()
        alias = cast("str", getattr(self._parent, self._type_column))
        cached, target = self._cached_eager_target(
            service,
            alias,
            target_key,
        )
        if cached:
            return cast("TargetT | None", target)
        query_type = cast("type[_QueryableModel[TargetT]]", target_type)
        return query_type.query().where(self._owner_key, target_key).first()

    async def resolve_async(self) -> TargetT | None:
        """Asynchronously load the explicitly mapped target model.

        Returns:
            The matching target model, or ``None`` for a null association.

        Raises:
            DatabaseConfigurationError: If the discriminator is untrusted.
            DatabaseQueryError: If only one association column is null.
        """
        target_type, target_key = self.target_for_eager_loading()
        if target_type is None:
            return None
        service = DB.resolve_service()
        alias = cast("str", getattr(self._parent, self._type_column))
        cached, target = self._cached_eager_target(
            service,
            alias,
            target_key,
        )
        if cached:
            return cast("TargetT | None", target)
        query_type = cast("type[_QueryableModel[TargetT]]", target_type)
        return (
            await query_type.query()
            .where(
                self._owner_key,
                target_key,
            )
            .first_async()
        )

    def associate(self, model: TargetT) -> None:
        """Set both declaring-model fields for one trusted target.

        Args:
            model: Mapped target with a non-null configured owner key.

        Raises:
            DatabaseConfigurationError: If its class has no trusted alias.
            DatabaseQueryError: If the target owner key is null.
        """
        if type(model) not in self._target_models:
            message = "The target class is not allowed by this relationship."
            raise DatabaseConfigurationError(message)
        alias = DB.resolve_service().morph_alias_for(type(model))
        if alias is None:
            message = "The target model has no trusted morph alias."
            raise DatabaseConfigurationError(message)
        target_key = getattr(model, self._owner_key, None)
        if target_key is None:
            message = "A polymorphic target must have a non-null owner key."
            raise DatabaseQueryError(message)
        self._clear_eager_target()
        setattr(self._parent, self._foreign_key, target_key)
        setattr(self._parent, self._type_column, alias)

    def dissociate(self) -> None:
        """Clear both mapped fields for this nullable relationship.

        The caller persists the declaring model through its ordinary model
        save operation.
        """
        self._clear_eager_target()
        setattr(self._parent, self._foreign_key, None)
        setattr(self._parent, self._type_column, None)

    def remember_eager_target(
        self,
        service: DatabaseService,
        alias: str | None,
        target_key: object | None,
        target: TargetT | None,
    ) -> None:
        """Cache one target loaded for this model query.

        Args:
            alias: Trusted stored discriminator, or ``None`` for no relation.
            target_key: Stored target key, or ``None`` for no relation.
            target: Loaded target row, or ``None`` when no row matches.
            service: Application database service that loaded the target.
        """
        if not self._relationship_name:
            return
        info = cast("dict[str, object]", sa_inspect(self._parent).info)
        cache_value = info.setdefault(_MORPH_TO_CACHE_KEY, {})
        cache = cast(
            "dict[str, _MorphTargetCacheEntry]",
            cache_value,
        )
        cache[self._relationship_name] = (
            service,
            alias,
            target_key,
            target,
        )

    def _cached_eager_target(
        self,
        service: DatabaseService,
        alias: str,
        target_key: object,
    ) -> tuple[bool, object | None]:
        """Return an eager result only while its type and key still match.

        Args:
            alias: Current trusted stored discriminator.
            target_key: Current mapped target key.
            service: Application database service resolving this relation.

        Returns:
            Whether this relation has a matching eager result and that result.
        """
        if not self._relationship_name:
            return False, None
        info = cast("dict[str, object]", sa_inspect(self._parent).info)
        cache_value = info.get(_MORPH_TO_CACHE_KEY)
        if not isinstance(cache_value, dict):
            return False, None
        cache = cast(
            "dict[str, _MorphTargetCacheEntry]",
            cache_value,
        )
        entry = cache.get(self._relationship_name)
        if entry is None:
            return False, None
        cached_service, cached_alias, cached_key, target = entry
        if (
            cached_service is not service
            or cached_alias != alias
            or cached_key != target_key
        ):
            cache.pop(self._relationship_name, None)
            return False, None
        return True, target

    def _clear_eager_target(self) -> None:
        """Discard cached eager data before changing relation columns.

        The cached target belongs to the current polymorphic key pair, so a
        relation mutation must invalidate it before either mapped value changes.
        """
        if not self._relationship_name:
            return
        info = cast("dict[str, object]", sa_inspect(self._parent).info)
        cache_value = info.get(_MORPH_TO_CACHE_KEY)
        if not isinstance(cache_value, dict):
            return
        cache = cast(
            "dict[str, _MorphTargetCacheEntry]",
            cache_value,
        )
        cache.pop(self._relationship_name, None)

    def target_for_eager_loading(
        self,
        service: DatabaseService | None = None,
    ) -> tuple[type[object] | None, object | None]:
        """Resolve a stored discriminator without importing database values.

        Returns:
            The trusted mapped class and key, or ``(None, None)`` when both
            association columns are null.

        Raises:
            DatabaseConfigurationError: If the discriminator is untrusted.
            DatabaseQueryError: If the association columns are inconsistent.
        """
        alias = getattr(self._parent, self._type_column)
        target_key = getattr(self._parent, self._foreign_key)
        if alias is None and target_key is None:
            return None, None
        if not isinstance(alias, str) or target_key is None:
            message = "Polymorphic type and key columns must both be set."
            raise DatabaseQueryError(message)

        active_service = service or DB.resolve_service()
        model_type = active_service.morph_model_for(alias)
        query_method = getattr(model_type, "query", None)
        if model_type is None or not callable(query_method):
            message = "The stored polymorphic type has no trusted mapped model."
            raise DatabaseConfigurationError(message)
        if model_type not in self._target_models:
            message = (
                "The stored polymorphic type is not allowed by this relation."
            )
            raise DatabaseConfigurationError(message)
        return model_type, target_key


def morph_to[TargetT](
    *target_models: type[TargetT],
    type_column: str,
    foreign_key: str,
    owner_key: str = "id",
) -> MorphTo[TargetT]:
    """Declare a model descriptor for explicit polymorphic target access.

    Args:
        type_column: Mapped discriminator attribute on the declaring model.
        foreign_key: Mapped target key attribute on the declaring model.
        owner_key: Target attribute matched against ``foreign_key``.
        target_models: Mapped classes allowed for this relationship.

    Returns:
        A typed descriptor exposing ``resolve`` and association operations.

    Raises:
        DatabaseConfigurationError: If a target key is not a mapped column.
        DatabaseConfigurationError: If a target class is not mapped.
        ValueError: If target models or mapped attribute names are invalid.
    """
    names = (type_column, foreign_key, owner_key)
    if not target_models:
        message = "Polymorphic relationships require at least one target."
        raise ValueError(message)
    if any(not _is_non_empty_string(name) for name in names):
        message = "Polymorphic mapped attribute names must not be empty."
        raise ValueError(message)
    if any(not _is_mapped_model(target) for target in target_models):
        message = "Polymorphic target models must be mapped model classes."
        raise DatabaseConfigurationError(message)
    if any(
        not _is_mapped_column(target, owner_key) for target in target_models
    ):
        message = "The polymorphic owner key must be a mapped column."
        raise DatabaseConfigurationError(message)
    if len(set(target_models)) != len(target_models):
        message = "Polymorphic target models must be unique."
        raise ValueError(message)
    return MorphTo(target_models, type_column, foreign_key, owner_key)


def _is_mapped_model(value: object) -> bool:
    """Return whether a runtime value is a mapped model class.

    Args:
        value: Untrusted declaration value to validate.

    Returns:
        Whether SQLAlchemy has instrumentation for the supplied class.
    """
    return (
        isinstance(value, type)
        and sa_inspect(value, raiseerr=False) is not None
        and callable(getattr(value, "query", None))
    )


def _is_mapped_column(model_type: type[object], name: str) -> bool:
    """Return whether a mapped class exposes one mapped column attribute.

    Args:
        model_type: Class to inspect for ORM column metadata.
        name: Python attribute name that must map to a column property.

    Returns:
        Whether SQLAlchemy maps the named class attribute as a column.
    """
    mapper = sa_inspect(model_type, raiseerr=False)
    return mapper is not None and name in mapper.column_attrs


def _is_non_empty_string(value: object) -> bool:
    """Return whether a runtime value is a non-blank string.

    Args:
        value: Relationship attribute declaration to validate.

    Returns:
        Whether the value is a string containing non-whitespace text.
    """
    return isinstance(value, str) and bool(value.strip())


__all__ = ["MorphTo", "MorphToRelation", "morph_to"]
