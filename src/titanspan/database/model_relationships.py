"""Mutate mapped many-to-many collections through SQLAlchemy's Unit of Work.

SQLAlchemy owns association-table persistence. This module adds explicit
sync and async operations for detached Titanspan models.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    ClassVar,
    Literal,
    Protocol,
    cast,
)

from sqlalchemy import Select, Table, and_, select, update
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import set_committed_value

from titanspan.database.exceptions import DatabaseQueryError, ModelNotFoundError
from titanspan.database.model_state import (
    ensure_session_owner,
    remember_service_graph,
)
from titanspan.facades.database import DB

if TYPE_CHECKING:
    from typing import Any

    from sqlalchemy import Column
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.base import ReadOnlyColumnCollection
    from sqlalchemy.sql.dml import Update

    from titanspan.contracts.database import DatabaseService

_RELATIONSHIP_NOT_FOUND_ERROR = "The mapped relation was not found."
_MANY_TO_MANY_REQUIRED_ERROR = (
    "Relationship operations require a writable many-to-many relation."
)
_PERSISTED_PARENT_REQUIRED_ERROR = (
    "Relationship operations require a persisted parent model."
)
_PERSISTED_RELATED_REQUIRED_ERROR = (
    "Related models must be persisted before they can be attached."
)
_RELATED_MODEL_TYPE_ERROR = "The value is not an instance of the related model."
_RELATED_MODEL_NOT_FOUND_ERROR = "The requested related model was not found."
_INVALID_RELATED_IDENTIFIER_ERROR = (
    "Related model identifiers must be non-null and hashable."
)
_CROSS_CONNECTION_ERROR = (
    "Many-to-many models must use the same database connection."
)
_PIVOT_UPDATE_UNSUPPORTED_ERROR = (
    "Pivot updates require an unambiguous mapped association table."
)
_PIVOT_UPDATE_ATTRIBUTES_ERROR = (
    "Pivot updates require non-key association attributes."
)
_PIVOT_UPDATE_SINGLE_RELATED_ERROR = (
    "Pivot updates accept exactly one related identifier."
)
_PIVOT_UPDATE_ROWCOUNT_ERROR = (
    "The database backend did not report the pivot update row count."
)
_RELATIONSHIP_QUERY_CHUNK_SIZE = 500
_RelationOperation = Literal["attach", "detach", "sync", "toggle"]


@dataclass(frozen=True, slots=True)
class RelationshipChanges:
    """Describe many-to-many association rows changed by one operation.

    Attributes:
        attached: Related identifiers newly associated with the parent.
        detached: Related identifiers removed from the parent.
    """

    attached: tuple[object, ...] = ()
    detached: tuple[object, ...] = ()


class _ModelHost(Protocol):
    """Describe the mapped model operations needed by a relation manager.

    Attributes:
        connection: Optional named connection for this model type.
    """

    connection: ClassVar[str | None]

    @classmethod
    def primary_key_name(cls) -> str:
        """Return the model's primary-key attribute name.

        Returns:
            The mapped single-column primary-key attribute.
        """
        ...


class ManyToManyRelation[ParentT: _ModelHost]:
    """Provide explicit operations for one mapped many-to-many relation.

    Related models are loaded through the owning application's session.
    SQLAlchemy's mapped collection writes the association rows.
    """

    def __init__(self, parent: ParentT, name: str) -> None:
        """Bind one persisted-model candidate to a mapped relation.

        Args:
            parent: Model that owns the selected relationship.
            name: Mapped relationship attribute on the parent.

        Raises:
            DatabaseQueryError: If the relation is absent or unsupported.
        """
        self._parent = parent
        self._parent_type = cast("type[_ModelHost]", type(parent))
        self._name = name
        mapper = sa_inspect(self._parent_type)
        relationship = mapper.relationships.get(name)
        if relationship is None:
            raise DatabaseQueryError(_RELATIONSHIP_NOT_FOUND_ERROR)
        secondary = relationship.secondary
        if (
            secondary is None
            or relationship.viewonly
            or not relationship.uselist
        ):
            raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)
        self._related_type = cast(
            "type[_ModelHost]",
            relationship.mapper.class_,
        )
        self._parent_key = self._parent_type.primary_key_name()
        self._related_key = self._related_type.primary_key_name()
        if self._parent_type.connection != self._related_type.connection:
            raise DatabaseQueryError(_CROSS_CONNECTION_ERROR)
        self._relationship_attribute = getattr(self._parent_type, name)
        self._secondary: object = secondary

    def attach(
        self,
        related: object | Sequence[object],
    ) -> tuple[object, ...]:
        """Attach persisted related models in one transaction.

        Args:
            related: Related identifiers or persisted related model instances.

        Returns:
            Identifiers newly attached to the parent.

        Raises:
            DatabaseQueryError: If the parent or relationship is invalid.
            ModelNotFoundError: If a requested related identifier is absent.
        """
        return self._mutate_sync("attach", related).attached

    async def attach_async(
        self,
        related: object | Sequence[object],
    ) -> tuple[object, ...]:
        """Asynchronously attach persisted related models.

        Args:
            related: Related identifiers or persisted related model instances.

        Returns:
            Identifiers newly attached to the parent.

        Raises:
            DatabaseQueryError: If the parent or relationship is invalid.
            ModelNotFoundError: If a requested related identifier is absent.
        """
        return (await self._mutate_async("attach", related)).attached

    def detach(
        self,
        related: object | Sequence[object] | None = None,
    ) -> tuple[object, ...]:
        """Detach selected related models, or every current relation.

        Args:
            related: Related identifiers or models. ``None`` removes all.

        Returns:
            Identifiers detached from the parent.

        Raises:
            DatabaseQueryError: If the parent or relationship is invalid.
        """
        return self._mutate_sync("detach", related).detached

    async def detach_async(
        self,
        related: object | Sequence[object] | None = None,
    ) -> tuple[object, ...]:
        """Asynchronously detach selected or all related models.

        Args:
            related: Related identifiers or models. ``None`` removes all.

        Returns:
            Identifiers detached from the parent.

        Raises:
            DatabaseQueryError: If the parent or relationship is invalid.
        """
        return (await self._mutate_async("detach", related)).detached

    def sync(
        self,
        related: object | Sequence[object],
        *,
        detaching: bool = True,
    ) -> RelationshipChanges:
        """Synchronize related identifiers inside one transaction.

        Args:
            related: Desired identifiers or persisted related models.
            detaching: Remove existing associations absent from ``related``.

        Returns:
            The attached and detached identifier groups.

        Raises:
            DatabaseQueryError: If the parent or relationship is invalid.
            ModelNotFoundError: If a requested related identifier is absent.
        """
        return self._mutate_sync(
            "sync",
            related,
            detaching=detaching,
        )

    async def sync_async(
        self,
        related: object | Sequence[object],
        *,
        detaching: bool = True,
    ) -> RelationshipChanges:
        """Asynchronously synchronize related identifiers transactionally.

        Args:
            related: Desired identifiers or persisted related models.
            detaching: Remove existing associations absent from ``related``.

        Returns:
            The attached and detached identifier groups.

        Raises:
            DatabaseQueryError: If the parent or relationship is invalid.
            ModelNotFoundError: If a requested related identifier is absent.
        """
        return await self._mutate_async(
            "sync",
            related,
            detaching=detaching,
        )

    def sync_without_detaching(
        self,
        related: object | Sequence[object],
    ) -> RelationshipChanges:
        """Add the requested associations while keeping existing ones.

        Args:
            related: Related identifiers or persisted related models.

        Returns:
            The newly attached identifiers.
        """
        return self.sync(related, detaching=False)

    async def sync_without_detaching_async(
        self,
        related: object | Sequence[object],
    ) -> RelationshipChanges:
        """Asynchronously add associations without detaching existing rows.

        Args:
            related: Related identifiers or persisted related models.

        Returns:
            The newly attached identifiers.
        """
        return await self.sync_async(related, detaching=False)

    def toggle(
        self,
        related: object | Sequence[object],
    ) -> RelationshipChanges:
        """Attach absent identifiers and detach currently related identifiers.

        Args:
            related: Related identifiers or persisted related models.

        Returns:
            The attached and detached identifier groups.
        """
        return self._mutate_sync("toggle", related)

    async def toggle_async(
        self,
        related: object | Sequence[object],
    ) -> RelationshipChanges:
        """Asynchronously toggle selected association rows.

        Args:
            related: Related identifiers or persisted related models.

        Returns:
            The attached and detached identifier groups.
        """
        return await self._mutate_async("toggle", related)

    def update_existing_pivot(
        self,
        related: object,
        attributes: Mapping[str, object],
    ) -> int:
        """Update non-key columns on one existing association row.

        Args:
            related: Related identifier or persisted related model.
            attributes: Association-table values to write.

        Returns:
            Number of matching association rows updated by the backend.

        Raises:
            DatabaseQueryError: If input or the association mapping is invalid.
            ModelNotFoundError: If the parent row no longer exists.
        """
        identifier, input_models = self._pivot_update_input(related)
        statement = self._pivot_update_statement(identifier, attributes)
        service = DB.resolve_service()
        with service.session(self._parent_type.connection) as session:
            ensure_session_owner(self._parent, service, session)
            self._load_parent_sync(session)
            self._validate_input_ownership(input_models, service, session)
            # Session.execute exposes Result; Core DML returns a cursor result.
            result = cast(
                "CursorResult[tuple[object, ...]]",
                session.execute(statement),
            )
            return _updated_row_count(result.rowcount)

    async def update_existing_pivot_async(
        self,
        related: object,
        attributes: Mapping[str, object],
    ) -> int:
        """Asynchronously update one existing association row.

        Args:
            related: Related identifier or persisted related model.
            attributes: Association-table values to write.

        Returns:
            Number of matching association rows updated by the backend.

        Raises:
            DatabaseQueryError: If input or the association mapping is invalid.
            ModelNotFoundError: If the parent row no longer exists.
        """
        identifier, input_models = self._pivot_update_input(related)
        statement = self._pivot_update_statement(identifier, attributes)
        service = DB.resolve_service()
        async with service.session_async(
            self._parent_type.connection,
        ) as session:
            ensure_session_owner(self._parent, service, session)
            await self._load_parent_async(session)
            self._validate_input_ownership(input_models, service, session)
            # Session.execute exposes Result; Core DML returns a cursor result.
            result = cast(
                "CursorResult[tuple[object, ...]]",
                await session.execute(statement),
            )
            return _updated_row_count(result.rowcount)

    def _pivot_update_input(
        self,
        related: object,
    ) -> tuple[object, tuple[_ModelHost, ...]]:
        """Require exactly one valid relation identifier.

        Args:
            related: Related identifier or persisted related model.

        Returns:
            The identifier and any model instance supplied by the caller.

        Raises:
            DatabaseQueryError: If the identifier is invalid or ambiguous.
        """
        identifiers, models = self._normalize(related)
        if identifiers is None or len(identifiers) != 1:
            raise DatabaseQueryError(_PIVOT_UPDATE_SINGLE_RELATED_ERROR)
        return identifiers[0], models

    def _pivot_update_statement(
        self,
        identifier: object,
        attributes: Mapping[str, object],
    ) -> Update:
        """Build a bound update limited to one parent's association row.

        Args:
            identifier: Related primary-key value to match.
            attributes: Association-table column names and values.

        Returns:
            SQLAlchemy Core update statement for the mapped association table.

        Raises:
            DatabaseQueryError: If attributes include keys or unknown columns.
        """
        secondary_value: object = self._secondary
        if not isinstance(secondary_value, Table):
            raise DatabaseQueryError(_PIVOT_UPDATE_UNSUPPORTED_ERROR)
        # Dynamic SQLAlchemy metadata exposes an unknown column collection.
        # This cast confines that third-party type boundary to the adapter.
        secondary = cast(
            "Table[ReadOnlyColumnCollection[str, Column[Any]]]",
            secondary_value,
        )
        parent_column, related_column = _association_columns(
            secondary,
            self._parent_type,
            self._related_type,
        )
        updates = dict(attributes)
        association_keys = {
            column.key for column in secondary.primary_key.columns
        }
        protected = association_keys | {
            parent_column.key,
            related_column.key,
        }
        if not updates or not set(updates).issubset(secondary.c.keys()):
            raise DatabaseQueryError(_PIVOT_UPDATE_ATTRIBUTES_ERROR)
        if set(updates).intersection(protected):
            raise DatabaseQueryError(_PIVOT_UPDATE_ATTRIBUTES_ERROR)
        return (
            update(secondary)
            .where(
                and_(
                    parent_column
                    == _persisted_identifier(
                        self._parent,
                        self._parent_key,
                    ),
                    related_column == identifier,
                ),
            )
            .values(**updates)
        )

    def _mutate_sync(
        self,
        operation: _RelationOperation,
        values: object | Sequence[object] | None,
        *,
        detaching: bool = True,
    ) -> RelationshipChanges:
        """Apply one relationship operation through a synchronous session.

        Args:
            operation: Relationship change to perform.
            values: Input identifiers or mapped related models.
            detaching: Whether sync removes associations not in the input.

        Returns:
            The changed identifier groups.
        """
        identifiers, input_models = self._normalize(values)
        if operation == "detach" and identifiers is None:
            requested_ids: tuple[object, ...] | None = None
        else:
            requested_ids = identifiers or ()
        if not requested_ids and operation in {"attach", "toggle"}:
            return RelationshipChanges()
        if operation == "sync" and not requested_ids and not detaching:
            return RelationshipChanges()

        service = DB.resolve_service()
        with service.session(self._parent_type.connection) as session:
            ensure_session_owner(self._parent, service, session)
            owner = self._load_parent_sync(session)
            current_models = list(
                cast("Iterable[_ModelHost]", getattr(owner, self._name)),
            )
            current_by_id = {
                getattr(model, self._related_key): model
                for model in current_models
            }
            to_attach, to_detach = _plan_relationship_changes(
                operation,
                tuple(current_by_id),
                requested_ids,
                detaching=detaching,
            )
            self._validate_input_ownership(
                input_models,
                service,
                session,
            )
            related_models = self._load_related_sync(
                session,
                to_attach,
            )
            collection = getattr(owner, self._name)
            for identifier in to_detach:
                _remove_related(
                    collection,
                    current_by_id[identifier],
                )
            for identifier in to_attach:
                _append_related(collection, related_models[identifier])
            if to_attach or to_detach:
                session.flush()
                committed_models = tuple(
                    cast("Iterable[_ModelHost]", collection),
                )
                service.after_commit(
                    lambda: set_committed_value(
                        self._parent,
                        self._name,
                        list(committed_models),
                    ),
                    self._parent_type.connection,
                )
        return RelationshipChanges(
            attached=to_attach,
            detached=to_detach,
        )

    async def _mutate_async(
        self,
        operation: _RelationOperation,
        values: object | Sequence[object] | None,
        *,
        detaching: bool = True,
    ) -> RelationshipChanges:
        """Apply one relationship operation through an async session.

        Args:
            operation: Relationship change to perform.
            values: Input identifiers or mapped related models.
            detaching: Whether sync removes associations not in the input.

        Returns:
            The changed identifier groups.
        """
        identifiers, input_models = self._normalize(values)
        if operation == "detach" and identifiers is None:
            requested_ids: tuple[object, ...] | None = None
        else:
            requested_ids = identifiers or ()
        if not requested_ids and operation in {"attach", "toggle"}:
            return RelationshipChanges()
        if operation == "sync" and not requested_ids and not detaching:
            return RelationshipChanges()

        service = DB.resolve_service()
        async with service.session_async(
            self._parent_type.connection,
        ) as session:
            ensure_session_owner(self._parent, service, session)
            owner = await self._load_parent_async(session)
            current_models = list(
                cast("Iterable[_ModelHost]", getattr(owner, self._name)),
            )
            current_by_id = {
                getattr(model, self._related_key): model
                for model in current_models
            }
            to_attach, to_detach = _plan_relationship_changes(
                operation,
                tuple(current_by_id),
                requested_ids,
                detaching=detaching,
            )
            self._validate_input_ownership(
                input_models,
                service,
                session,
            )
            related_models = await self._load_related_async(
                session,
                to_attach,
            )
            collection = getattr(owner, self._name)
            for identifier in to_detach:
                _remove_related(
                    collection,
                    current_by_id[identifier],
                )
            for identifier in to_attach:
                _append_related(collection, related_models[identifier])
            if to_attach or to_detach:
                await session.flush()
                committed_models = tuple(
                    cast("Iterable[_ModelHost]", collection),
                )

                async def update_parent_cache() -> None:
                    """Reflect committed state on the detached parent.

                    Returns:
                        None.
                    """
                    set_committed_value(
                        self._parent,
                        self._name,
                        list(committed_models),
                    )
                    remember_service_graph(
                        self._parent,
                        service,
                        self._parent_type.connection,
                    )

                await service.after_commit_async(
                    update_parent_cache,
                    self._parent_type.connection,
                )
        return RelationshipChanges(
            attached=to_attach,
            detached=to_detach,
        )

    def _normalize(
        self,
        values: object | Sequence[object] | None,
    ) -> tuple[tuple[object, ...] | None, tuple[_ModelHost, ...]]:
        """Validate and de-duplicate relation identifiers in input order.

        Args:
            values: Related identifiers or model instances.

        Returns:
            Unique identifiers and any supplied mapped model instances.

        Raises:
            DatabaseQueryError: If an identifier or mapped model is invalid.
        """
        if values is None:
            return None, ()
        raw_values = _sequence_values(values)

        identifiers: list[object] = []
        input_models: list[_ModelHost] = []
        seen: set[object] = set()
        for value in raw_values:
            identifier, model = _related_identifier(
                value,
                self._related_type,
            )
            if model is not None:
                input_models.append(model)
            if identifier not in seen:
                identifiers.append(identifier)
                seen.add(identifier)
        return tuple(identifiers), tuple(input_models)

    def _validate_input_ownership(
        self,
        models: tuple[_ModelHost, ...],
        service: DatabaseService,
        session: Session | AsyncSession,
    ) -> None:
        """Reject related model instances owned by another application/session.

        Args:
            models: Mapped inputs supplied by the caller.
            service: Active application Database service.
            session: Owning synchronous or asynchronous session.
        """
        for model in models:
            ensure_session_owner(model, service, session)

    def _load_parent_sync(self, session: Session) -> _ModelHost:
        """Load the parent and selected collection in one sync session.

        Args:
            session: Session owned by the active Database service.

        Returns:
            Parent instance with the mapped relation eagerly loaded.

        Raises:
            DatabaseQueryError: If the parent has no persisted identity.
            ModelNotFoundError: If the parent row no longer exists.
        """
        identifier = _persisted_identifier(
            self._parent,
            self._parent_key,
        )
        statement = self._parent_statement(identifier)
        parent = session.scalars(statement).first()
        if parent is None:
            raise ModelNotFoundError(_PERSISTED_PARENT_REQUIRED_ERROR)
        return cast("_ModelHost", parent)

    async def _load_parent_async(
        self,
        session: AsyncSession,
    ) -> _ModelHost:
        """Load the parent and selected collection in one async session.

        Args:
            session: Session owned by the active Database service.

        Returns:
            Parent instance with the mapped relation eagerly loaded.

        Raises:
            DatabaseQueryError: If the parent has no persisted identity.
            ModelNotFoundError: If the parent row no longer exists.
        """
        identifier = _persisted_identifier(
            self._parent,
            self._parent_key,
        )
        statement = self._parent_statement(identifier)
        result = await session.scalars(statement)
        parent = result.first()
        if parent is None:
            raise ModelNotFoundError(_PERSISTED_PARENT_REQUIRED_ERROR)
        return cast("_ModelHost", parent)

    def _parent_statement(
        self,
        identifier: object,
    ) -> Select[object]:
        """Create a typed select that eagerly loads the requested collection.

        Args:
            identifier: Persisted primary-key value for the parent.

        Returns:
            SQLAlchemy select statement for the mapped parent.
        """
        parent_type = cast("type[object]", self._parent_type)
        parent_attribute = getattr(self._parent_type, self._parent_key)
        relationship_attribute = getattr(self._parent_type, self._name)
        return (
            select(parent_type)
            .where(parent_attribute == identifier)
            .options(selectinload(relationship_attribute))
        )

    def _load_related_sync(
        self,
        session: Session,
        identifiers: tuple[object, ...],
    ) -> dict[object, _ModelHost]:
        """Load all new related rows through one synchronous ORM query.

        Args:
            session: Session that owns the relation mutation.
            identifiers: Related primary keys to load.

        Returns:
            Related models keyed by their primary-key values.

        Raises:
            ModelNotFoundError: If any requested row does not exist.
        """
        if not identifiers:
            return {}
        models: list[object] = []
        for start in range(0, len(identifiers), _RELATIONSHIP_QUERY_CHUNK_SIZE):
            chunk = identifiers[start : start + _RELATIONSHIP_QUERY_CHUNK_SIZE]
            models.extend(session.scalars(self._related_statement(chunk)).all())
        return self._index_related_models(identifiers, models)

    async def _load_related_async(
        self,
        session: AsyncSession,
        identifiers: tuple[object, ...],
    ) -> dict[object, _ModelHost]:
        """Asynchronously load all new related rows in one ORM query.

        Args:
            session: Session that owns the relation mutation.
            identifiers: Related primary keys to load.

        Returns:
            Related models keyed by their primary-key values.

        Raises:
            ModelNotFoundError: If any requested row does not exist.
        """
        if not identifiers:
            return {}
        models: list[object] = []
        for start in range(0, len(identifiers), _RELATIONSHIP_QUERY_CHUNK_SIZE):
            chunk = identifiers[start : start + _RELATIONSHIP_QUERY_CHUNK_SIZE]
            result = await session.scalars(self._related_statement(chunk))
            models.extend(result.all())
        return self._index_related_models(identifiers, models)

    def _related_statement(
        self,
        identifiers: tuple[object, ...],
    ) -> Select[object]:
        """Create a select for related rows requested by primary key.

        Args:
            identifiers: Related primary keys to load.

        Returns:
            SQLAlchemy select statement for the mapped related model.
        """
        related_type = cast("type[object]", self._related_type)
        primary_key = sa_inspect(self._related_type).primary_key[0]
        return select(related_type).where(primary_key.in_(identifiers))

    def _index_related_models(
        self,
        identifiers: tuple[object, ...],
        models: Sequence[object],
    ) -> dict[object, _ModelHost]:
        """Ensure all requested rows exist and preserve input identifier order.

        Args:
            identifiers: Requested related primary keys.
            models: Related rows returned by SQLAlchemy.

        Returns:
            Related models keyed by their primary-key values.

        Raises:
            ModelNotFoundError: If a requested row does not exist.
        """
        indexed = {
            getattr(model, self._related_key): cast("_ModelHost", model)
            for model in models
        }
        if any(identifier not in indexed for identifier in identifiers):
            raise ModelNotFoundError(_RELATED_MODEL_NOT_FOUND_ERROR)
        return indexed


def _sequence_values(values: object | Sequence[object]) -> Sequence[object]:
    """Wrap one scalar input or preserve a caller-supplied sequence.

    Args:
        values: Related identifier, mapped model, or sequence of values.

    Returns:
        A sequence suitable for deterministic validation.
    """
    if isinstance(values, (str, bytes, bytearray)):
        return (values,)
    if isinstance(values, Sequence):
        return cast("Sequence[object]", values)
    return (values,)


def _association_columns(
    secondary: Table[ReadOnlyColumnCollection[str, Column[Any]]],
    parent_type: type[_ModelHost],
    related_type: type[_ModelHost],
) -> tuple[Column[object], Column[object]]:
    """Find unambiguous association foreign keys for a direct relation.

    Args:
        secondary: SQLAlchemy association table for the relation.
        parent_type: Mapped parent model class.
        related_type: Mapped related model class.

    Returns:
        Association columns referencing each model's single primary key.

    Raises:
        DatabaseQueryError: If the table does not directly reference both
            models through one foreign-key column each.
    """
    parent_keys = sa_inspect(parent_type).primary_key
    related_keys = sa_inspect(related_type).primary_key
    if len(parent_keys) != 1 or len(related_keys) != 1:
        raise DatabaseQueryError(_PIVOT_UPDATE_UNSUPPORTED_ERROR)
    parent_candidates = tuple(
        foreign_key.parent
        for foreign_key in secondary.foreign_keys
        if foreign_key.column.compare(parent_keys[0])
    )
    related_candidates = tuple(
        foreign_key.parent
        for foreign_key in secondary.foreign_keys
        if foreign_key.column.compare(related_keys[0])
    )
    if (
        len(parent_candidates) != 1
        or len(related_candidates) != 1
        or parent_candidates[0] is related_candidates[0]
    ):
        raise DatabaseQueryError(_PIVOT_UPDATE_UNSUPPORTED_ERROR)
    return (
        cast("Column[object]", parent_candidates[0]),
        cast("Column[object]", related_candidates[0]),
    )


def _updated_row_count(rowcount: int | None) -> int:
    """Normalize an unavailable or unsupported database row count.

    Args:
        rowcount: Affected-row count returned by the SQLAlchemy dialect.

    Returns:
        A non-negative affected-row count.

    Raises:
        DatabaseQueryError: If the backend cannot report the affected rows.
    """
    if rowcount is None or rowcount < 0:
        raise DatabaseQueryError(_PIVOT_UPDATE_ROWCOUNT_ERROR)
    return rowcount


def _related_identifier(
    value: object,
    related_type: type[_ModelHost],
) -> tuple[object, _ModelHost | None]:
    """Extract and validate one related identifier or persisted model.

    Args:
        value: Identifier or mapped model supplied by the caller.
        related_type: Model class configured for the relationship.

    Returns:
        The non-null hashable identifier and an input model when supplied.

    Raises:
        DatabaseQueryError: If the value is invalid or belongs to another
            mapped model.
    """
    identifier = value
    model: _ModelHost | None = None
    mapped_state = sa_inspect(value, raiseerr=False)
    if isinstance(value, related_type):
        identity = mapped_state.identity if mapped_state is not None else None
        if identity is None or len(identity) != 1:
            raise DatabaseQueryError(_PERSISTED_RELATED_REQUIRED_ERROR)
        identifier = identity[0]
        model = value
    elif mapped_state is not None:
        raise DatabaseQueryError(_RELATED_MODEL_TYPE_ERROR)
    if identifier is None:
        raise DatabaseQueryError(_INVALID_RELATED_IDENTIFIER_ERROR)
    try:
        hash(identifier)
    except TypeError as error:
        raise DatabaseQueryError(
            _INVALID_RELATED_IDENTIFIER_ERROR,
        ) from error
    return identifier, model


def _persisted_identifier(model: _ModelHost, key_name: str) -> object:
    """Require one persisted primary-key identity for a model instance.

    Args:
        model: Parent model supplied to a relationship manager.
        key_name: Mapped primary-key attribute name.

    Returns:
        Persisted identifier read from SQLAlchemy's identity state.

    Raises:
        DatabaseQueryError: If the parent has not been persisted.
    """
    identity = sa_inspect(model).identity
    if identity is None or len(identity) != 1:
        raise DatabaseQueryError(_PERSISTED_PARENT_REQUIRED_ERROR)
    identifier = identity[0]
    if identifier is None or getattr(model, key_name) is None:
        raise DatabaseQueryError(_PERSISTED_PARENT_REQUIRED_ERROR)
    return identifier


def _plan_relationship_changes(
    operation: _RelationOperation,
    current_ids: tuple[object, ...],
    requested_ids: tuple[object, ...] | None,
    *,
    detaching: bool,
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    """Compute association additions and removals without mutating state.

    Args:
        operation: Requested relationship operation.
        current_ids: Identifiers currently loaded through the ORM relation.
        requested_ids: Requested identifiers, or ``None`` to detach all.
        detaching: Whether sync removes identifiers omitted from the request.

    Returns:
        Identifiers to attach and detach, preserving deterministic order.
    """
    current = set(current_ids)
    requested = tuple(requested_ids or ())
    requested_set = set(requested)
    if operation == "attach":
        return tuple(item for item in requested if item not in current), ()
    if operation == "detach":
        if requested_ids is None:
            return (), current_ids
        return (), tuple(item for item in current_ids if item in requested_set)
    if operation == "toggle":
        return (
            tuple(item for item in requested if item not in current),
            tuple(item for item in requested if item in current),
        )
    to_attach = tuple(item for item in requested if item not in current)
    to_detach = (
        tuple(item for item in current_ids if item not in requested_set)
        if detaching
        else ()
    )
    return to_attach, to_detach


def _append_related(collection: object, model: _ModelHost) -> None:
    """Append or add a model through the mapped collection protocol.

    Args:
        collection: SQLAlchemy-instrumented relationship collection.
        model: Persisted related model to associate.

    Raises:
        DatabaseQueryError: If the collection exposes no supported mutator.
    """
    append = getattr(collection, "append", None)
    if callable(append):
        append(model)
        return
    add = getattr(collection, "add", None)
    if callable(add):
        add(model)
        return
    raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)


def _remove_related(collection: object, model: _ModelHost) -> None:
    """Remove one model through the mapped collection protocol.

    Args:
        collection: SQLAlchemy-instrumented relationship collection.
        model: Existing related model to disassociate.

    Raises:
        DatabaseQueryError: If the collection exposes no supported mutator.
    """
    remove = getattr(collection, "remove", None)
    if not callable(remove):
        raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)
    remove(model)


__all__ = ["ManyToManyRelation", "RelationshipChanges"]
