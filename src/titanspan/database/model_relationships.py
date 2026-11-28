"""Mutate mapped many-to-many collections through SQLAlchemy's Unit of Work.

SQLAlchemy owns association-table persistence. This module adds explicit
sync and async operations for detached Titanspan models.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from inspect import getattr_static
from typing import (
    TYPE_CHECKING,
    ClassVar,
    Literal,
    Protocol,
    Self,
    cast,
)

from sqlalchemy import Select, Table, and_, delete, insert, select, update
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.associationproxy import AssociationProxy
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import set_committed_value

from titanspan.database.exceptions import (
    DatabaseConfigurationError,
    DatabaseQueryError,
    ModelNotFoundError,
    ModelPersistenceCancelledError,
)
from titanspan.database.model_state import (
    ensure_session_owner,
    remember_service_graph,
)
from titanspan.database.relationships import MorphPivot
from titanspan.facades.database import DB

if TYPE_CHECKING:
    from typing import Any

    from sqlalchemy import Column
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Mapper
    from sqlalchemy.sql.base import ReadOnlyColumnCollection
    from sqlalchemy.sql.dml import Delete, Insert, Update

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
_PIVOT_TIMESTAMP_MAPPING_ERROR = (
    "Pivot timestamp operations require a direct association table."
)
_PIVOT_TIMESTAMP_COLUMNS_ERROR = (
    "Pivot timestamps must use non-key association columns."
)
_PIVOT_TIMESTAMP_COLUMN_COUNT = 2
_PIVOT_MODEL_SAVE_CANCELLED_ERROR = (
    "Saving the custom pivot model was cancelled."
)
_RELATIONSHIP_QUERY_CHUNK_SIZE = 500
_MORPH_RELATION_INFO_ITEM_COUNT = 2
_NO_ASSOCIATION_PROXY = object()
_RelationOperation = Literal["attach", "detach", "sync", "toggle"]


@dataclass(frozen=True, slots=True)
class RelationshipChanges:
    """Describe many-to-many association rows changed by one operation.

    Attributes:
        attached: Related identifiers newly associated with the parent.
        detached: Related identifiers removed from the parent.
        updated: Existing pivot rows updated by synchronization.
    """

    attached: tuple[object, ...] = ()
    detached: tuple[object, ...] = ()
    updated: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class _NormalizedRelationInput:
    """Hold normalized identifiers, models, and optional per-row values.

    Attributes:
        identifiers: Unique requested related keys, or ``None`` for detach all.
        models: Related models supplied directly by the caller.
        pivot_values: Validated input mappings grouped by related key.
    """

    identifiers: tuple[object, ...] | None
    models: tuple[_ModelHost, ...]
    pivot_values: Mapping[object, Mapping[str, object]]


@dataclass(frozen=True, slots=True)
class _AppliedRelationshipChanges:
    """Return committed related models and actually updated pivot keys.

    Attributes:
        related_models: Relationship collection after applying the mutation.
        updated: Existing pivot keys whose update matched a stored row.
        association_models: Mapped association objects after the mutation.
    """

    related_models: tuple[_ModelHost, ...]
    updated: tuple[object, ...]
    association_models: tuple[_AssociationPivot, ...] = ()


@dataclass(frozen=True, slots=True)
class _MorphManyToManyInfo:
    """Store validated morph configuration from mapped relationship info.

    Attributes:
        direction: Side whose model class selects the trusted alias.
        pivot: Explicit pivot columns and endpoint keys.
    """

    direction: Literal["morph_to_many", "morphed_by_many"]
    pivot: MorphPivot


@dataclass(frozen=True, slots=True)
class _PivotMutation:
    """Carry one prepared pivot mutation into its sync or async writer.

    Attributes:
        operation: Requested relation mutation, including sync semantics.
        owner: Parent loaded by the active session.
        current_by_id: Current related models indexed by primary key.
        related_models: New related models indexed by primary key.
        attached: Related primary keys to insert.
        detached: Related primary keys to delete.
        alias: Trusted discriminator value from the active morph map.
        pivot_values: Per-related association attributes from the caller.
        service: Active Database service for scoped pivot updates.
    """

    operation: _RelationOperation
    owner: _ModelHost
    current_by_id: Mapping[object, _ModelHost]
    related_models: Mapping[object, _ModelHost]
    attached: tuple[object, ...]
    detached: tuple[object, ...]
    alias: str
    pivot_values: Mapping[object, Mapping[str, object]]
    service: DatabaseService


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


class _AssociationPivot(_ModelHost, Protocol):
    """Describe Model behavior needed to mutate mapped pivot instances.

    Association rows remain SQLAlchemy models and use their normal timestamp
    and mapped-column assignment behavior.
    """

    timestamps: ClassVar[bool]
    created_at_name: ClassVar[str]
    updated_at_name: ClassVar[str]

    def force_fill(self, attributes: Mapping[str, object]) -> Self:
        """Assign validated pivot columns without mass-assignment filtering.

        Args:
            attributes: Values already validated against mapped pivot columns.

        Returns:
            This association model.
        """
        ...

    def save(self) -> bool:
        """Persist the pivot through its active synchronous Unit of Work.

        Returns:
            Whether model lifecycle events permitted the write.
        """
        ...

    async def save_async(self) -> bool:
        """Persist the pivot through its active asynchronous Unit of Work.

        Returns:
            Whether model lifecycle events permitted the write.
        """
        ...


@dataclass(frozen=True, slots=True)
class _AssociationObjectInfo:
    """Describe a mapped association object exposed through a proxy.

    Attributes:
        collection_attribute: Parent relationship containing pivot models.
        parent_attribute: Optional association relationship back to parent.
        related_attribute: Pivot relationship referencing the related model.
        association_type: Mapped Titanspan model used for pivot rows.
        related_type: Mapped model exposed by the association proxy.
    """

    collection_attribute: str
    parent_attribute: str | None
    related_attribute: str
    association_type: type[_AssociationPivot]
    related_type: type[_ModelHost]


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
        association_info = _association_proxy_info(
            self._parent_type,
            name,
            mapper,
        )
        if association_info is None:
            if relationship is None:
                raise DatabaseQueryError(_RELATIONSHIP_NOT_FOUND_ERROR)
            secondary = relationship.secondary
            morph_info = _parse_morph_many_to_many_info(
                relationship.info.get("titanspan_morph_many_to_many"),
            )
            if (
                secondary is None
                or (relationship.viewonly and morph_info is None)
                or not relationship.uselist
            ):
                raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)
            related_type = relationship.mapper.class_
        else:
            secondary = None
            morph_info = None
            related_type = association_info.related_type
        self._association_info = association_info
        self._related_type = related_type
        self._parent_key = self._parent_type.primary_key_name()
        self._related_key = self._related_type.primary_key_name()
        self._morph_info = morph_info
        self._parent_pivot_key = (
            self._morph_info.pivot.owner_key
            if self._morph_info is not None
            else self._parent_key
        )
        self._related_pivot_key = (
            self._morph_info.pivot.related_key
            if self._morph_info is not None
            else self._related_key
        )
        connections = {
            self._parent_type.connection,
            self._related_type.connection,
        }
        if association_info is not None:
            connections.add(association_info.association_type.connection)
        if len(connections) != 1:
            raise DatabaseQueryError(_CROSS_CONNECTION_ERROR)
        self._relationship_attribute = getattr(self._parent_type, name)
        self._secondary: object = secondary
        (
            self._pivot_timestamps,
            self._timestamped_secondary,
            self._timestamped_columns,
        ) = self._configure_pivot_timestamps(
            (
                relationship.info.get("titanspan_pivot_timestamps")
                if relationship is not None
                else None
            ),
        )
        if self._morph_info is not None:
            self._morph_association_columns()

    def _configure_pivot_timestamps(
        self,
        timestamp_names: object,
    ) -> tuple[
        tuple[str, str] | None,
        Table[ReadOnlyColumnCollection[str, Column[Any]]] | None,
        tuple[Column[object], Column[object]] | None,
    ]:
        """Validate direct-table timestamp columns for this relation.

        Args:
            timestamp_names: Optional pair stored in relationship metadata.

        Returns:
            Validated timestamp names, table, and endpoint columns.

        Raises:
            DatabaseQueryError: If timestamp metadata cannot safely mutate the
                configured relation.
        """
        if timestamp_names is None:
            return None, None, None
        if self._morph_info is not None or not isinstance(
            timestamp_names,
            tuple,
        ):
            raise DatabaseQueryError(_PIVOT_TIMESTAMP_MAPPING_ERROR)
        timestamp_values = cast("tuple[object, ...]", timestamp_names)
        if len(timestamp_values) != _PIVOT_TIMESTAMP_COLUMN_COUNT or any(
            not isinstance(name, str) for name in timestamp_values
        ):
            raise DatabaseQueryError(_PIVOT_TIMESTAMP_MAPPING_ERROR)
        names = cast("tuple[str, str]", timestamp_values)
        secondary = self._secondary
        if not isinstance(secondary, Table):
            raise DatabaseQueryError(_PIVOT_TIMESTAMP_MAPPING_ERROR)
        timestamped_secondary = cast(
            "Table[ReadOnlyColumnCollection[str, Column[Any]]]",
            secondary,
        )
        parent_column, related_column = _association_columns(
            timestamped_secondary,
            self._parent_type,
            self._related_type,
        )
        timestamp_columns = set(names)
        key_columns = {
            column.key for column in timestamped_secondary.primary_key.columns
        } | {parent_column.key, related_column.key}
        if not timestamp_columns.issubset(
            timestamped_secondary.c.keys()
        ) or timestamp_columns.intersection(key_columns):
            raise DatabaseQueryError(_PIVOT_TIMESTAMP_COLUMNS_ERROR)
        return names, timestamped_secondary, (parent_column, related_column)

    def _morph_association_columns(
        self,
    ) -> tuple[Column[object], Column[object], Column[object]]:
        """Resolve parent, related, and discriminator pivot columns.

        Returns:
            Association columns in parent, related, discriminator order.

        Raises:
            DatabaseQueryError: If the morph relation has no direct table.
        """
        info = self._morph_info
        if info is None:
            raise DatabaseQueryError(_PIVOT_UPDATE_UNSUPPORTED_ERROR)
        secondary = self._morph_secondary()
        parent_key = (
            info.pivot.morph_key
            if info.direction == "morph_to_many"
            else info.pivot.other_key
        )
        related_key = (
            info.pivot.other_key
            if info.direction == "morph_to_many"
            else info.pivot.morph_key
        )
        try:
            return (
                cast("Column[object]", secondary.c[parent_key]),
                cast("Column[object]", secondary.c[related_key]),
                cast(
                    "Column[object]",
                    secondary.c[info.pivot.type_column],
                ),
            )
        except KeyError as error:
            raise DatabaseQueryError(
                _PIVOT_UPDATE_UNSUPPORTED_ERROR,
            ) from error

    def _morph_alias(self, service: DatabaseService) -> str:
        """Resolve the trusted alias that scopes this relation's pivot rows.

        Args:
            service: Active application-owned Database service.

        Returns:
            The configured alias for the morph endpoint class.

        Raises:
            DatabaseConfigurationError: If the active service has no alias.
        """
        info = self._morph_info
        if info is None:
            raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)
        morph_type: type[object] = (
            cast("type[object]", self._parent_type)
            if info.direction == "morph_to_many"
            else cast("type[object]", self._related_type)
        )
        alias = service.morph_alias_for(morph_type)
        if alias is None:
            message = "The active database morph map has no model alias."
            raise DatabaseConfigurationError(message)
        return alias

    def _pivot_identifier(self, model: _ModelHost, key_name: str) -> object:
        """Read one non-null configured key from a mapped relation endpoint.

        Args:
            model: Parent or related model participating in the pivot.
            key_name: Mapped attribute persisted in the association table.

        Returns:
            The configured pivot key value.

        Raises:
            DatabaseQueryError: If the mapped endpoint key is null.
        """
        value = getattr(model, key_name, None)
        if value is None:
            message = "Polymorphic pivot keys must be non-null."
            raise DatabaseQueryError(message)
        return value

    def _morph_secondary(
        self,
    ) -> Table[ReadOnlyColumnCollection[str, Column[Any]]]:
        """Return the direct association table for a morph relation.

        Returns:
            SQLAlchemy table receiving explicit polymorphic pivot writes.

        Raises:
            DatabaseQueryError: If the relationship uses another selectable.
        """
        secondary_value: object = self._secondary
        if not isinstance(secondary_value, Table):
            raise DatabaseQueryError(_PIVOT_UPDATE_UNSUPPORTED_ERROR)
        return cast(
            "Table[ReadOnlyColumnCollection[str, Column[Any]]]",
            cast("object", secondary_value),
        )

    def _morph_delete_statement(
        self,
        owner: _ModelHost,
        current_by_id: Mapping[object, _ModelHost],
        identifiers: tuple[object, ...],
        alias: str,
    ) -> Delete | None:
        """Build a type-qualified delete for selected current pivot rows.

        Args:
            owner: Parent loaded by the active session.
            current_by_id: Current related models indexed by primary key.
            identifiers: Related primary keys selected for removal.
            alias: Trusted discriminator value resolved from the app map.

        Returns:
            A bound delete statement, or ``None`` when no rows are removed.
        """
        if not identifiers:
            return None
        parent_column, related_column, type_column = (
            self._morph_association_columns()
        )
        parent_value = self._pivot_identifier(
            owner,
            self._parent_pivot_key,
        )
        related_values = tuple(
            self._pivot_identifier(
                current_by_id[identifier],
                self._related_pivot_key,
            )
            for identifier in identifiers
        )
        return delete(self._morph_secondary()).where(
            and_(
                parent_column == parent_value,
                related_column.in_(related_values),
                type_column == alias,
            ),
        )

    def _morph_insert_values(
        self,
        mutation: _PivotMutation,
    ) -> list[dict[str, object]]:
        """Build bound morph association rows and caller pivot attributes.

        Args:
            mutation: Prepared parent, related rows, alias, and pivot values.

        Returns:
            One association mapping for each newly attached model.
        """
        if not mutation.attached:
            return []
        parent_column, related_column, type_column = (
            self._morph_association_columns()
        )
        parent_value = self._pivot_identifier(
            mutation.owner,
            self._parent_pivot_key,
        )
        values: list[dict[str, object]] = []
        for identifier in mutation.attached:
            row = {
                parent_column.key: parent_value,
                related_column.key: self._pivot_identifier(
                    mutation.related_models[identifier],
                    self._related_pivot_key,
                ),
                type_column.key: mutation.alias,
            }
            row.update(
                self._validated_pivot_attributes(
                    mutation.pivot_values.get(identifier, {}),
                ),
            )
            values.append(row)
        return values

    def _write_morph_pivot_sync(
        self,
        session: Session,
        mutation: _PivotMutation,
    ) -> tuple[object, ...]:
        """Apply pivot writes in the current synchronous Unit of Work.

        Args:
            session: Active SQLAlchemy session.
            mutation: Prepared parent, model, key, and alias values.

        Returns:
            Existing pivot identifiers updated by this operation.
        """
        statement = self._morph_delete_statement(
            mutation.owner,
            mutation.current_by_id,
            mutation.detached,
            mutation.alias,
        )
        if statement is not None:
            session.execute(statement)
        values = self._morph_insert_values(mutation)
        if values:
            session.execute(insert(self._morph_secondary()), values)
        updated: list[object] = []
        for identifier in self._pivot_update_identifiers(mutation):
            result = cast(
                "CursorResult[tuple[object, ...]]",
                session.execute(
                    self._pivot_update_statement(
                        identifier,
                        mutation.pivot_values[identifier],
                        mutation.service,
                    ),
                ),
            )
            if _updated_row_count(result.rowcount) > 0:
                updated.append(identifier)
        return tuple(updated)

    async def _write_morph_pivot_async(
        self,
        session: AsyncSession,
        mutation: _PivotMutation,
    ) -> tuple[object, ...]:
        """Apply pivot writes in the current asynchronous Unit of Work.

        Args:
            session: Active SQLAlchemy async session.
            mutation: Prepared parent, model, key, and alias values.

        Returns:
            Existing pivot identifiers updated by this operation.
        """
        statement = self._morph_delete_statement(
            mutation.owner,
            mutation.current_by_id,
            mutation.detached,
            mutation.alias,
        )
        if statement is not None:
            await session.execute(statement)
        values = self._morph_insert_values(mutation)
        if values:
            await session.execute(insert(self._morph_secondary()), values)
        updated: list[object] = []
        for identifier in self._pivot_update_identifiers(mutation):
            result = cast(
                "CursorResult[tuple[object, ...]]",
                await session.execute(
                    self._pivot_update_statement(
                        identifier,
                        mutation.pivot_values[identifier],
                        mutation.service,
                    ),
                ),
            )
            if _updated_row_count(result.rowcount) > 0:
                updated.append(identifier)
        return tuple(updated)

    def attach(
        self,
        related: object | Sequence[object],
        *,
        pivot_values: Mapping[str, object] | None = None,
    ) -> tuple[object, ...]:
        """Attach persisted related models in one transaction.

        Args:
            related: Related identifiers or persisted related model instances.
                A mapping may supply separate pivot values for each identifier.
            pivot_values: Values shared by each newly attached pivot row.

        Returns:
            Identifiers newly attached to the parent.

        Raises:
            DatabaseQueryError: If the parent or relationship is invalid.
            ModelNotFoundError: If a requested related identifier is absent.
        """
        return self._mutate_sync(
            "attach",
            related,
            pivot_values=pivot_values,
        ).attached

    async def attach_async(
        self,
        related: object | Sequence[object],
        *,
        pivot_values: Mapping[str, object] | None = None,
    ) -> tuple[object, ...]:
        """Asynchronously attach persisted related models.

        Args:
            related: Related identifiers or persisted related model instances.
                A mapping may supply separate pivot values for each identifier.
            pivot_values: Values shared by each newly attached pivot row.

        Returns:
            Identifiers newly attached to the parent.

        Raises:
            DatabaseQueryError: If the parent or relationship is invalid.
            ModelNotFoundError: If a requested related identifier is absent.
        """
        return (
            await self._mutate_async(
                "attach",
                related,
                pivot_values=pivot_values,
            )
        ).attached

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
        pivot_values: Mapping[str, object] | None = None,
    ) -> RelationshipChanges:
        """Synchronize related identifiers inside one transaction.

        Args:
            related: Desired identifiers or persisted related models.
                A mapping may supply values for individual pivot rows.
            detaching: Remove existing associations absent from ``related``.
            pivot_values: Values shared by newly attached and existing rows.

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
            pivot_values=pivot_values,
        )

    async def sync_async(
        self,
        related: object | Sequence[object],
        *,
        detaching: bool = True,
        pivot_values: Mapping[str, object] | None = None,
    ) -> RelationshipChanges:
        """Asynchronously synchronize related identifiers transactionally.

        Args:
            related: Desired identifiers or persisted related models.
                A mapping may supply values for individual pivot rows.
            detaching: Remove existing associations absent from ``related``.
            pivot_values: Values shared by newly attached and existing rows.

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
            pivot_values=pivot_values,
        )

    def sync_without_detaching(
        self,
        related: object | Sequence[object],
        *,
        pivot_values: Mapping[str, object] | None = None,
    ) -> RelationshipChanges:
        """Add the requested associations while keeping existing ones.

        Args:
            related: Related identifiers or persisted related models.
                A mapping may supply values for individual pivot rows.
            pivot_values: Values shared by newly attached and existing rows.

        Returns:
            The newly attached identifiers.
        """
        return self.sync(
            related,
            detaching=False,
            pivot_values=pivot_values,
        )

    async def sync_without_detaching_async(
        self,
        related: object | Sequence[object],
        *,
        pivot_values: Mapping[str, object] | None = None,
    ) -> RelationshipChanges:
        """Asynchronously add associations without detaching existing rows.

        Args:
            related: Related identifiers or persisted related models.
                A mapping may supply values for individual pivot rows.
            pivot_values: Values shared by newly attached and existing rows.

        Returns:
            The newly attached identifiers.
        """
        return await self.sync_async(
            related,
            detaching=False,
            pivot_values=pivot_values,
        )

    def toggle(
        self,
        related: object | Sequence[object],
        *,
        pivot_values: Mapping[str, object] | None = None,
    ) -> RelationshipChanges:
        """Attach absent identifiers and detach currently related identifiers.

        Args:
            related: Related identifiers or persisted related models.
                A mapping may supply separate pivot values for each identifier.
            pivot_values: Values shared by newly attached pivot rows.

        Returns:
            The attached and detached identifier groups.
        """
        return self._mutate_sync(
            "toggle",
            related,
            pivot_values=pivot_values,
        )

    async def toggle_async(
        self,
        related: object | Sequence[object],
        *,
        pivot_values: Mapping[str, object] | None = None,
    ) -> RelationshipChanges:
        """Asynchronously toggle selected association rows.

        Args:
            related: Related identifiers or persisted related models.
                A mapping may supply separate pivot values for each identifier.
            pivot_values: Values shared by newly attached pivot rows.

        Returns:
            The attached and detached identifier groups.
        """
        return await self._mutate_async(
            "toggle",
            related,
            pivot_values=pivot_values,
        )

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
        association_info = self._association_info
        if association_info is not None:
            updates = self._validated_pivot_attributes(attributes)
            if not updates:
                raise DatabaseQueryError(_PIVOT_UPDATE_ATTRIBUTES_ERROR)
            service = DB.resolve_service()
            with service.session(self._parent_type.connection) as session:
                ensure_session_owner(self._parent, service, session)
                owner = self._load_parent_sync(session)
                self._validate_input_ownership(
                    input_models,
                    service,
                    session,
                )
                pivot = self._find_association_model(
                    owner,
                    identifier,
                    association_info,
                )
                if pivot is None:
                    return 0
                pivot.force_fill(updates)
                if not pivot.save():
                    raise ModelPersistenceCancelledError(
                        _PIVOT_MODEL_SAVE_CANCELLED_ERROR,
                    )
                association_models = self._association_models(
                    owner,
                    association_info,
                )
                service.after_commit(
                    lambda: self._remember_association_cache(
                        association_models,
                        service,
                        association_info,
                    ),
                    self._parent_type.connection,
                )
                return 1
        service = DB.resolve_service() if self._morph_info is not None else None
        statement = self._pivot_update_statement(
            identifier,
            attributes,
            service,
        )
        if service is None:
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
        association_info = self._association_info
        if association_info is not None:
            updates = self._validated_pivot_attributes(attributes)
            if not updates:
                raise DatabaseQueryError(_PIVOT_UPDATE_ATTRIBUTES_ERROR)
            service = DB.resolve_service()
            async with service.session_async(
                self._parent_type.connection,
            ) as session:
                ensure_session_owner(self._parent, service, session)
                owner = await self._load_parent_async(session)
                self._validate_input_ownership(
                    input_models,
                    service,
                    session,
                )
                pivot = self._find_association_model(
                    owner,
                    identifier,
                    association_info,
                )
                if pivot is None:
                    return 0
                pivot.force_fill(updates)
                if not await pivot.save_async():
                    raise ModelPersistenceCancelledError(
                        _PIVOT_MODEL_SAVE_CANCELLED_ERROR,
                    )
                association_models = self._association_models(
                    owner,
                    association_info,
                )

                async def update_parent_pivots() -> None:
                    """Refresh the detached parent's mapped pivot collection.

                    Returns:
                        None.
                    """
                    self._remember_association_cache(
                        association_models,
                        service,
                        association_info,
                    )

                await service.after_commit_async(
                    update_parent_pivots,
                    self._parent_type.connection,
                )
                return 1
        service = DB.resolve_service() if self._morph_info is not None else None
        statement = self._pivot_update_statement(
            identifier,
            attributes,
            service,
        )
        if service is None:
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

    def _association_models(
        self,
        owner: _ModelHost,
        info: _AssociationObjectInfo,
    ) -> tuple[_AssociationPivot, ...]:
        """Return the parent's loaded mapped association objects.

        Args:
            owner: Parent loaded by the active Database session.
            info: Validated association-object mapping for this relation.

        Returns:
            Association model instances from its mapped collection.

        """
        return tuple(
            cast(
                "Iterable[_AssociationPivot]",
                getattr(owner, info.collection_attribute),
            ),
        )

    def _find_association_model(
        self,
        owner: _ModelHost,
        identifier: object,
        info: _AssociationObjectInfo,
    ) -> _AssociationPivot | None:
        """Find one loaded pivot by its related model identifier.

        Args:
            owner: Parent loaded by the active Database session.
            identifier: Related model primary-key value to match.
            info: Validated association-object mapping for this relation.

        Returns:
            The matching association model, if its row exists.
        """
        return next(
            (
                pivot
                for pivot in self._association_models(owner, info)
                if getattr(
                    getattr(pivot, info.related_attribute),
                    self._related_key,
                )
                == identifier
            ),
            None,
        )

    def _remember_association_cache(
        self,
        association_models: tuple[_AssociationPivot, ...],
        service: DatabaseService,
        info: _AssociationObjectInfo,
    ) -> None:
        """Transfer committed pivot instances to the caller's parent cache.

        Args:
            association_models: Pivot instances committed by the Unit of Work.
            service: Database service that owns the committed model graph.
            info: Validated association-object mapping for this relation.
        """
        if info.parent_attribute is not None:
            for pivot in association_models:
                set_committed_value(
                    pivot,
                    info.parent_attribute,
                    self._parent,
                )
        set_committed_value(
            self._parent,
            info.collection_attribute,
            list(association_models),
        )
        remember_service_graph(
            self._parent,
            service,
            self._parent_type.connection,
        )

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
        normalized = self._normalize(
            related,
            allow_pivot_values=False,
            pivot_values=None,
        )
        identifiers = normalized.identifiers
        models = normalized.models
        if identifiers is None or len(identifiers) != 1:
            raise DatabaseQueryError(_PIVOT_UPDATE_SINGLE_RELATED_ERROR)
        return identifiers[0], models

    def _pivot_update_statement(
        self,
        identifier: object,
        attributes: Mapping[str, object],
        service: DatabaseService | None,
    ) -> Update:
        """Build a bound update limited to one parent's association row.

        Args:
            identifier: Related primary-key value to match.
            attributes: Association-table column names and values.
            service: Active application-owned Database service.

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
        parent_column, related_column = self._association_columns_for(
            secondary,
        )
        predicates = [
            parent_column
            == self._pivot_identifier(
                self._parent,
                self._parent_pivot_key,
            ),
        ]
        related_primary_key = getattr(self._related_type, self._related_key)
        related_pivot_key = getattr(
            self._related_type,
            self._related_pivot_key,
        )
        related_value = (
            select(related_pivot_key)
            .where(related_primary_key == identifier)
            .scalar_subquery()
        )
        predicates.append(related_column == related_value)
        updates = self._validated_pivot_attributes(attributes)
        if not updates:
            raise DatabaseQueryError(_PIVOT_UPDATE_ATTRIBUTES_ERROR)
        if self._morph_info is not None:
            if service is None:
                raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)
            _, _, type_column = self._morph_association_columns()
            predicates.append(type_column == self._morph_alias(service))
        if self._pivot_timestamps is not None:
            updates[self._pivot_timestamps[1]] = datetime.now(UTC)
        return update(secondary).where(and_(*predicates)).values(**updates)

    def _association_columns_for(
        self,
        secondary: Table[ReadOnlyColumnCollection[str, Column[Any]]],
    ) -> tuple[Column[object], Column[object]]:
        """Return the pivot columns paired with the relation endpoints.

        Args:
            secondary: Direct SQLAlchemy association table.

        Returns:
            Parent and related key columns in relationship order.
        """
        if self._morph_info is not None:
            parent_column, related_column, _ = self._morph_association_columns()
            return parent_column, related_column
        return _association_columns(
            secondary,
            self._parent_type,
            self._related_type,
        )

    def _timestamped_pivot_insert(
        self,
        mutation: _PivotMutation,
    ) -> tuple[Insert, list[dict[str, object]]]:
        """Build timestamped association rows for one attachment batch.

        Args:
            mutation: New related rows and any supplied pivot attributes.

        Returns:
            Core insert and bound parameter mappings for SQLAlchemy.

        Raises:
            DatabaseQueryError: If the relationship lacks a validated table.
        """
        secondary = self._timestamped_secondary
        columns = self._timestamped_columns
        timestamps = self._pivot_timestamps
        if secondary is None or columns is None or timestamps is None:
            raise DatabaseQueryError(_PIVOT_TIMESTAMP_MAPPING_ERROR)
        timestamp = datetime.now(UTC)
        parent_identifier = self._pivot_identifier(
            mutation.owner,
            self._parent_pivot_key,
        )
        parameters: list[dict[str, object]] = []
        for identifier in mutation.attached:
            row = {
                columns[0].key: parent_identifier,
                columns[1].key: self._pivot_identifier(
                    mutation.related_models[identifier],
                    self._related_pivot_key,
                ),
            }
            row.update(
                self._validated_pivot_attributes(
                    mutation.pivot_values.get(identifier, {}),
                ),
            )
            row[timestamps[0]] = timestamp
            row[timestamps[1]] = timestamp
            parameters.append(row)
        return insert(secondary), parameters

    def _pivot_insert_statement(
        self,
        mutation: _PivotMutation,
    ) -> tuple[Insert, list[dict[str, object]]]:
        """Build an insert for ordinary pivots with explicit row values.

        Args:
            mutation: New related rows and any supplied pivot attributes.

        Returns:
            Core insert and bound parameter mappings for SQLAlchemy.

        Raises:
            DatabaseQueryError: If the relation has no direct association table.
        """
        if self._pivot_timestamps is not None:
            return self._timestamped_pivot_insert(mutation)
        secondary_value: object = self._secondary
        if not isinstance(secondary_value, Table):
            raise DatabaseQueryError(_PIVOT_UPDATE_UNSUPPORTED_ERROR)
        secondary = cast(
            "Table[ReadOnlyColumnCollection[str, Column[Any]]]",
            secondary_value,
        )
        parent_column, related_column = self._association_columns_for(secondary)
        parent_value = self._pivot_identifier(
            mutation.owner,
            self._parent_pivot_key,
        )
        parameters: list[dict[str, object]] = []
        for identifier in mutation.attached:
            row = {
                parent_column.key: parent_value,
                related_column.key: self._pivot_identifier(
                    mutation.related_models[identifier],
                    self._related_pivot_key,
                ),
            }
            row.update(
                self._validated_pivot_attributes(
                    mutation.pivot_values.get(identifier, {}),
                ),
            )
            parameters.append(row)
        return insert(secondary), parameters

    def _validated_pivot_attributes(
        self,
        attributes: Mapping[str, object],
    ) -> dict[str, object]:
        """Reject unknown, key, discriminator, and managed timestamp values.

        Args:
            attributes: Caller values for one association row.

        Returns:
            A copied mapping safe to pass to SQLAlchemy Core DML.

        Raises:
            DatabaseQueryError: If an attribute is unsupported or protected.
        """
        if not attributes:
            return {}
        association_info = self._association_info
        if association_info is not None:
            return self._validated_association_pivot_attributes(
                attributes,
                association_info,
            )
        if self._morph_info is not None:
            secondary = self._morph_secondary()
            parent_column, related_column, type_column = (
                self._morph_association_columns()
            )
            protected = {
                parent_column.key,
                related_column.key,
                type_column.key,
            }
        else:
            secondary_value: object = self._secondary
            if not isinstance(secondary_value, Table):
                raise DatabaseQueryError(_PIVOT_UPDATE_UNSUPPORTED_ERROR)
            secondary = cast(
                "Table[ReadOnlyColumnCollection[str, Column[Any]]]",
                secondary_value,
            )
            parent_column, related_column = self._association_columns_for(
                secondary,
            )
            protected = {parent_column.key, related_column.key}
        protected.update(column.key for column in secondary.primary_key.columns)
        if self._pivot_timestamps is not None:
            protected.update(self._pivot_timestamps)
        keys = set(attributes)
        if (
            not _mapping_has_string_keys(
                cast("Mapping[object, object]", attributes),
            )
            or not keys.issubset(secondary.c.keys())
            or keys.intersection(protected)
        ):
            raise DatabaseQueryError(_PIVOT_UPDATE_ATTRIBUTES_ERROR)
        return dict(attributes)

    def _validated_association_pivot_attributes(
        self,
        attributes: Mapping[str, object],
        info: _AssociationObjectInfo,
    ) -> dict[str, object]:
        """Validate scalar values against a custom mapped pivot model.

        Args:
            attributes: Candidate values for one association model.
            info: Validated mapping for the custom association model.

        Returns:
            Values restricted to writable non-key model columns.

        Raises:
            DatabaseQueryError: If a value targets an unknown or protected
                association attribute.
        """
        pivot_mapper = sa_inspect(info.association_type)
        allowed = {attribute.key for attribute in pivot_mapper.column_attrs}
        protected = {
            pivot_mapper.get_property_by_column(column).key
            for column in pivot_mapper.primary_key
        }
        endpoint_tables = set(sa_inspect(self._parent_type).tables) | set(
            sa_inspect(self._related_type).tables,
        )
        for attribute in pivot_mapper.column_attrs:
            if any(
                foreign_key.column.table in endpoint_tables
                for column in attribute.columns
                for foreign_key in column.foreign_keys
            ):
                protected.add(attribute.key)
        if info.association_type.timestamps:
            managed_names = {
                info.association_type.created_at_name,
                info.association_type.updated_at_name,
            }
            protected.update(
                attribute.key
                for attribute in pivot_mapper.column_attrs
                if attribute.key in managed_names
                or any(
                    column.name in managed_names for column in attribute.columns
                )
            )
        keys = set(attributes)
        if (
            not _mapping_has_string_keys(
                cast("Mapping[object, object]", attributes),
            )
            or not keys.issubset(allowed)
            or keys.intersection(protected)
        ):
            raise DatabaseQueryError(_PIVOT_UPDATE_ATTRIBUTES_ERROR)
        return dict(attributes)

    def _direct_pivot_delete(
        self,
        mutation: _PivotMutation,
    ) -> Delete:
        """Build a bound delete for ordinary direct association rows.

        Args:
            mutation: Parent and currently related rows to remove.

        Returns:
            Delete scoped to this parent and selected related keys.

        Raises:
            DatabaseQueryError: If the association table is not directly
                mapped to the relation endpoints.
        """
        secondary_value: object = self._secondary
        if not isinstance(secondary_value, Table):
            raise DatabaseQueryError(_PIVOT_UPDATE_UNSUPPORTED_ERROR)
        secondary = cast(
            "Table[ReadOnlyColumnCollection[str, Column[Any]]]",
            secondary_value,
        )
        parent_column, related_column = self._association_columns_for(secondary)
        parent_value = self._pivot_identifier(
            mutation.owner,
            self._parent_pivot_key,
        )
        related_values = tuple(
            self._pivot_identifier(
                mutation.current_by_id[identifier],
                self._related_pivot_key,
            )
            for identifier in mutation.detached
        )
        return delete(secondary).where(
            and_(
                parent_column == parent_value,
                related_column.in_(related_values),
            ),
        )

    def _timestamped_pivot_delete(
        self,
        identifiers: tuple[object, ...],
    ) -> Delete:
        """Build a bound deletion for one parent and selected associations.

        Args:
            identifiers: Related primary-key values to detach.

        Returns:
            Core delete statement scoped to this parent.

        Raises:
            DatabaseQueryError: If the relationship lacks a validated table.
        """
        secondary = self._timestamped_secondary
        columns = self._timestamped_columns
        if secondary is None or columns is None:
            raise DatabaseQueryError(_PIVOT_TIMESTAMP_MAPPING_ERROR)
        parent_identifier = _persisted_identifier(
            self._parent,
            self._parent_key,
        )
        return delete(secondary).where(
            and_(
                columns[0] == parent_identifier,
                columns[1].in_(identifiers),
            ),
        )

    def _apply_sync_changes(
        self,
        session: Session,
        mutation: _PivotMutation,
    ) -> _AppliedRelationshipChanges:
        """Persist one relationship change set synchronously.

        Args:
            session: Database session owning the operation.
            mutation: Prepared relation changes and trusted morph alias.

        Returns:
            Related models after the mutation and updated existing pivots.
        """
        association_info = self._association_info
        if association_info is not None:
            return self._apply_association_object_sync(
                session,
                mutation,
                association_info,
            )
        if self._morph_info is not None:
            morph_updated_ids = self._write_morph_pivot_sync(session, mutation)
            self._expire_parent_collection(session, mutation.owner)
            return _AppliedRelationshipChanges(
                related_models=_desired_related_models(
                    mutation.current_by_id,
                    mutation.related_models,
                    mutation.attached,
                    mutation.detached,
                ),
                updated=morph_updated_ids,
            )
        has_pivot_values = any(mutation.pivot_values.values())
        if self._pivot_timestamps is None and not has_pivot_values:
            collection = getattr(mutation.owner, self._name)
            for identifier in mutation.detached:
                _remove_related(
                    collection,
                    mutation.current_by_id[identifier],
                )
            for identifier in mutation.attached:
                _append_related(
                    collection,
                    mutation.related_models[identifier],
                )
            session.flush()
            return _AppliedRelationshipChanges(
                related_models=tuple(cast("Iterable[_ModelHost]", collection)),
                updated=(),
            )

        committed_models = _desired_related_models(
            mutation.current_by_id,
            mutation.related_models,
            mutation.attached,
            mutation.detached,
        )
        if mutation.detached:
            statement = (
                self._timestamped_pivot_delete(mutation.detached)
                if self._pivot_timestamps is not None
                else self._direct_pivot_delete(mutation)
            )
            session.execute(statement)
        if mutation.attached:
            statement, parameters = self._pivot_insert_statement(mutation)
            # Core executemany keeps large attach batches within backend limits.
            session.execute(statement, parameters)
        updated_ids: list[object] = []
        for identifier in self._pivot_update_identifiers(mutation):
            result = cast(
                "CursorResult[tuple[object, ...]]",
                session.execute(
                    self._pivot_update_statement(
                        identifier,
                        mutation.pivot_values[identifier],
                        mutation.service,
                    ),
                ),
            )
            if _updated_row_count(result.rowcount) > 0:
                updated_ids.append(identifier)
        self._expire_parent_collection(session, mutation.owner)
        return _AppliedRelationshipChanges(
            related_models=committed_models,
            updated=tuple(updated_ids),
        )

    def _apply_association_object_sync(
        self,
        session: Session,
        mutation: _PivotMutation,
        info: _AssociationObjectInfo,
    ) -> _AppliedRelationshipChanges:
        """Persist custom pivots through synchronous Model save operations.

        Args:
            session: Active SQLAlchemy session for the relationship operation.
            mutation: Planned changes for mapped association model instances.
            info: Validated mapping for the custom association model.

        Returns:
            Related and association models after the Unit of Work flushes.

        Raises:
            ModelPersistenceCancelledError: If a pivot save event rejects a
                write.
        """
        related_models, association_models, updated, touched = (
            self._mutate_association_object_collection(mutation, info)
        )
        for pivot in touched:
            if not pivot.save():
                raise ModelPersistenceCancelledError(
                    _PIVOT_MODEL_SAVE_CANCELLED_ERROR,
                )
        session.flush()
        return _AppliedRelationshipChanges(
            related_models=related_models,
            updated=updated,
            association_models=association_models,
        )

    async def _apply_async_changes(
        self,
        session: AsyncSession,
        mutation: _PivotMutation,
    ) -> _AppliedRelationshipChanges:
        """Persist one relationship change set asynchronously.

        Args:
            session: Async Database session owning the operation.
            mutation: Prepared relation changes and trusted morph alias.

        Returns:
            Related models after the mutation and updated existing pivots.
        """
        association_info = self._association_info
        if association_info is not None:
            return await self._apply_association_object_async(
                session,
                mutation,
                association_info,
            )
        if self._morph_info is not None:
            morph_updated_ids = await self._write_morph_pivot_async(
                session,
                mutation,
            )
            self._expire_parent_collection(session, mutation.owner)
            return _AppliedRelationshipChanges(
                related_models=_desired_related_models(
                    mutation.current_by_id,
                    mutation.related_models,
                    mutation.attached,
                    mutation.detached,
                ),
                updated=morph_updated_ids,
            )
        has_pivot_values = any(mutation.pivot_values.values())
        if self._pivot_timestamps is None and not has_pivot_values:
            collection = getattr(mutation.owner, self._name)
            for identifier in mutation.detached:
                _remove_related(
                    collection,
                    mutation.current_by_id[identifier],
                )
            for identifier in mutation.attached:
                _append_related(
                    collection,
                    mutation.related_models[identifier],
                )
            await session.flush()
            return _AppliedRelationshipChanges(
                related_models=tuple(cast("Iterable[_ModelHost]", collection)),
                updated=(),
            )

        committed_models = _desired_related_models(
            mutation.current_by_id,
            mutation.related_models,
            mutation.attached,
            mutation.detached,
        )
        if mutation.detached:
            statement = (
                self._timestamped_pivot_delete(mutation.detached)
                if self._pivot_timestamps is not None
                else self._direct_pivot_delete(mutation)
            )
            await session.execute(statement)
        if mutation.attached:
            statement, parameters = self._pivot_insert_statement(mutation)
            # Core executemany keeps large attach batches within backend limits.
            await session.execute(statement, parameters)
        updated_ids: list[object] = []
        for identifier in self._pivot_update_identifiers(mutation):
            result = cast(
                "CursorResult[tuple[object, ...]]",
                await session.execute(
                    self._pivot_update_statement(
                        identifier,
                        mutation.pivot_values[identifier],
                        mutation.service,
                    ),
                ),
            )
            if _updated_row_count(result.rowcount) > 0:
                updated_ids.append(identifier)
        self._expire_parent_collection(session, mutation.owner)
        return _AppliedRelationshipChanges(
            related_models=committed_models,
            updated=tuple(updated_ids),
        )

    async def _apply_association_object_async(
        self,
        session: AsyncSession,
        mutation: _PivotMutation,
        info: _AssociationObjectInfo,
    ) -> _AppliedRelationshipChanges:
        """Persist custom pivots through asynchronous Model save operations.

        Args:
            session: Active SQLAlchemy async session for the operation.
            mutation: Planned changes for mapped association model instances.
            info: Validated mapping for the custom association model.

        Returns:
            Related and association models after the Unit of Work flushes.

        Raises:
            ModelPersistenceCancelledError: If a pivot save event rejects a
                write.
        """
        related_models, association_models, updated, touched = (
            self._mutate_association_object_collection(mutation, info)
        )
        for pivot in touched:
            if not await pivot.save_async():
                raise ModelPersistenceCancelledError(
                    _PIVOT_MODEL_SAVE_CANCELLED_ERROR,
                )
        await session.flush()
        return _AppliedRelationshipChanges(
            related_models=related_models,
            updated=updated,
            association_models=association_models,
        )

    def _mutate_association_object_collection(
        self,
        mutation: _PivotMutation,
        info: _AssociationObjectInfo,
    ) -> tuple[
        tuple[_ModelHost, ...],
        tuple[_AssociationPivot, ...],
        tuple[object, ...],
        tuple[_AssociationPivot, ...],
    ]:
        """Apply changes through mapped association model instances.

        Args:
            mutation: Relationship changes planned by the active session.
            info: Validated mapping for the custom association model.

        Returns:
            Related models, association models, and updated related keys.

        Raises:
            DatabaseQueryError: If the mapped association collection cannot
                accept the required model changes.
        """
        collection = getattr(mutation.owner, info.collection_attribute)
        association_models = cast(
            "list[_AssociationPivot]",
            list(collection),
        )
        pivots_by_related_id = {
            getattr(
                getattr(pivot, info.related_attribute),
                self._related_key,
            ): pivot
            for pivot in association_models
        }
        for identifier in mutation.detached:
            pivot = pivots_by_related_id[identifier]
            _remove_related(collection, pivot)
            association_models.remove(pivot)
        for identifier in mutation.attached:
            pivot_factory = cast(
                "Callable[[], _AssociationPivot]",
                info.association_type,
            )
            pivot = pivot_factory()
            setattr(
                pivot,
                info.related_attribute,
                mutation.related_models[identifier],
            )
            pivot.force_fill(
                self._validated_pivot_attributes(
                    mutation.pivot_values.get(identifier, {}),
                ),
            )
            _append_related(collection, cast("_ModelHost", pivot))
            association_models.append(pivot)
            pivots_by_related_id[identifier] = pivot
        touched: list[_AssociationPivot] = [
            pivots_by_related_id[identifier] for identifier in mutation.attached
        ]
        updated: list[object] = []
        for identifier in self._pivot_update_identifiers(mutation):
            pivot = pivots_by_related_id[identifier]
            pivot.force_fill(mutation.pivot_values[identifier])
            updated.append(identifier)
            touched.append(pivot)
        current_associations = tuple(
            cast("Iterable[_AssociationPivot]", collection),
        )
        related_models = tuple(
            cast(
                "Iterable[_ModelHost]",
                (
                    getattr(pivot, info.related_attribute)
                    for pivot in current_associations
                ),
            ),
        )
        return (
            related_models,
            current_associations,
            tuple(updated),
            tuple(touched),
        )

    def _expire_parent_collection(
        self,
        session: Session | AsyncSession,
        owner: _ModelHost,
    ) -> None:
        """Expire the mapped collection after direct pivot-table writes.

        Args:
            session: Active sync or async SQLAlchemy session.
            owner: Session-loaded parent whose collection Core DML bypassed.

        Returns:
            None.
        """
        # Core DML bypasses relationship instrumentation. Expiration makes the
        # next operation in this Unit of Work reload rows, including savepoints.
        session.expire(owner, [self._name])

    def _mutate_sync(
        self,
        operation: _RelationOperation,
        values: object | Sequence[object] | None,
        *,
        detaching: bool = True,
        pivot_values: Mapping[str, object] | None = None,
    ) -> RelationshipChanges:
        """Apply one relationship operation through a synchronous session.

        Args:
            operation: Relationship change to perform.
            values: Input identifiers or mapped related models.
            detaching: Whether sync removes associations not in the input.
            pivot_values: Shared pivot values for attach, sync, or toggle.

        Returns:
            The changed identifier groups.
        """
        normalized = self._normalize(
            values,
            allow_pivot_values=operation != "detach",
            pivot_values=pivot_values,
        )
        identifiers = normalized.identifiers
        input_models = normalized.models
        if operation == "detach" and identifiers is None:
            requested_ids: tuple[object, ...] | None = None
        else:
            requested_ids = identifiers or ()
        if not requested_ids and operation in {"attach", "toggle"}:
            return RelationshipChanges()
        if operation == "sync" and not requested_ids and not detaching:
            return RelationshipChanges()

        updated: tuple[object, ...] = ()
        service = DB.resolve_service()
        morph_alias = (
            self._morph_alias(service) if self._morph_info is not None else None
        )
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
            mutation = _PivotMutation(
                operation=operation,
                owner=owner,
                current_by_id=current_by_id,
                related_models=related_models,
                attached=to_attach,
                detached=to_detach,
                alias=cast("str", morph_alias),
                pivot_values=normalized.pivot_values,
                service=service,
            )
            if (
                to_attach
                or to_detach
                or self._pivot_update_identifiers(mutation)
            ):
                applied = self._apply_sync_changes(
                    session,
                    mutation,
                )
                updated = applied.updated
                association_info = self._association_info
                if association_info is not None:
                    service.after_commit(
                        lambda: self._remember_association_cache(
                            applied.association_models,
                            service,
                            association_info,
                        ),
                        self._parent_type.connection,
                    )
                else:
                    service.after_commit(
                        lambda: set_committed_value(
                            self._parent,
                            self._name,
                            list(applied.related_models),
                        ),
                        self._parent_type.connection,
                    )
        return RelationshipChanges(
            attached=to_attach,
            detached=to_detach,
            updated=updated,
        )

    async def _mutate_async(
        self,
        operation: _RelationOperation,
        values: object | Sequence[object] | None,
        *,
        detaching: bool = True,
        pivot_values: Mapping[str, object] | None = None,
    ) -> RelationshipChanges:
        """Apply one relationship operation through an async session.

        Args:
            operation: Relationship change to perform.
            values: Input identifiers or mapped related models.
            detaching: Whether sync removes associations not in the input.
            pivot_values: Shared pivot values for attach, sync, or toggle.

        Returns:
            The changed identifier groups.
        """
        normalized = self._normalize(
            values,
            allow_pivot_values=operation != "detach",
            pivot_values=pivot_values,
        )
        identifiers = normalized.identifiers
        input_models = normalized.models
        if operation == "detach" and identifiers is None:
            requested_ids: tuple[object, ...] | None = None
        else:
            requested_ids = identifiers or ()
        if not requested_ids and operation in {"attach", "toggle"}:
            return RelationshipChanges()
        if operation == "sync" and not requested_ids and not detaching:
            return RelationshipChanges()

        updated: tuple[object, ...] = ()
        service = DB.resolve_service()
        morph_alias = (
            self._morph_alias(service) if self._morph_info is not None else None
        )
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
            mutation = _PivotMutation(
                operation=operation,
                owner=owner,
                current_by_id=current_by_id,
                related_models=related_models,
                attached=to_attach,
                detached=to_detach,
                alias=cast("str", morph_alias),
                pivot_values=normalized.pivot_values,
                service=service,
            )
            if (
                to_attach
                or to_detach
                or self._pivot_update_identifiers(mutation)
            ):
                applied = await self._apply_async_changes(
                    session,
                    mutation,
                )
                updated = applied.updated

                async def update_parent_cache() -> None:
                    """Reflect committed state on the detached parent.

                    Returns:
                        None.
                    """
                    association_info = self._association_info
                    if association_info is not None:
                        self._remember_association_cache(
                            applied.association_models,
                            service,
                            association_info,
                        )
                    else:
                        set_committed_value(
                            self._parent,
                            self._name,
                            list(applied.related_models),
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
            updated=updated,
        )

    def _normalize(
        self,
        values: object | Sequence[object] | None,
        *,
        allow_pivot_values: bool,
        pivot_values: Mapping[str, object] | None,
    ) -> _NormalizedRelationInput:
        """Validate identifiers and associate any requested pivot values.

        Args:
            values: Related identifiers or model instances.
            allow_pivot_values: Whether this operation accepts keyed values.
            pivot_values: Values to apply to each requested identifier.

        Returns:
            Unique identifiers, supplied models, and per-row pivot values.

        Raises:
            DatabaseQueryError: If identifiers or pivot value mappings are
                invalid.
        """
        shared_values = _shared_pivot_values(pivot_values)
        if values is None:
            return _NormalizedRelationInput(None, (), {})
        raw_values = _related_value_pairs(values, allow_pivot_values)

        identifiers: list[object] = []
        input_models: list[_ModelHost] = []
        values_by_id: dict[object, Mapping[str, object]] = {}
        seen: set[object] = set()
        for value, row_values in raw_values:
            identifier, model = _related_identifier(
                value,
                self._related_type,
            )
            if model is not None:
                input_models.append(model)
            if identifier not in seen:
                identifiers.append(identifier)
                seen.add(identifier)
            combined_values = dict(shared_values)
            combined_values.update(row_values)
            if combined_values:
                self._validated_pivot_attributes(combined_values)
                values_by_id[identifier] = combined_values
        return _NormalizedRelationInput(
            tuple(identifiers),
            tuple(input_models),
            values_by_id,
        )

    def _pivot_update_identifiers(
        self,
        mutation: _PivotMutation,
    ) -> tuple[object, ...]:
        """Select existing rows whose attributes a sync operation updates.

        Args:
            mutation: Prepared sync request and current mapped relation rows.

        Returns:
            Existing requested keys with at least one supplied pivot value.
        """
        if mutation.operation != "sync":
            return ()
        return tuple(
            identifier
            for identifier, attributes in mutation.pivot_values.items()
            if attributes
            and identifier in mutation.current_by_id
            and identifier not in mutation.detached
        )

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
        if self._association_info is None:
            load_option = selectinload(
                getattr(self._parent_type, self._name),
            )
        else:
            collection_attribute = getattr(
                self._parent_type,
                self._association_info.collection_attribute,
            )
            related_attribute = getattr(
                self._association_info.association_type,
                self._association_info.related_attribute,
            )
            load_option = selectinload(collection_attribute).selectinload(
                related_attribute,
            )
        return (
            select(parent_type)
            .where(parent_attribute == identifier)
            .options(load_option)
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


def _association_proxy_info(
    parent_type: type[_ModelHost],
    name: str,
    mapper: Mapper[Any],
) -> _AssociationObjectInfo | None:
    """Resolve a writable association-object proxy through mapped relations.

    Args:
        parent_type: Mapped parent class that declares the proxy.
        name: Candidate proxy attribute name.
        mapper: SQLAlchemy mapper for the parent class.

    Returns:
        Validated association-object metadata when the attribute is a proxy.

    Raises:
        DatabaseQueryError: If a proxy does not describe a writable many-to-
            many association object backed by Titanspan models.
    """
    descriptor = getattr_static(
        parent_type,
        name,
        _NO_ASSOCIATION_PROXY,
    )
    if not isinstance(descriptor, AssociationProxy):
        return None
    proxy = cast("AssociationProxy[object]", descriptor)
    collection_relationship = mapper.relationships.get(proxy.target_collection)
    if (
        collection_relationship is None
        or not collection_relationship.uselist
        or collection_relationship.secondary is not None
        or collection_relationship.viewonly
    ):
        raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)
    association_type = cast(
        "type[object]",
        collection_relationship.mapper.class_,
    )
    association_mapper = cast(
        "Mapper[Any]",
        sa_inspect(association_type),
    )
    related_relationship = association_mapper.relationships.get(
        proxy.value_attr,
    )
    if (
        related_relationship is None
        or related_relationship.uselist
        or related_relationship.secondary is not None
        or related_relationship.viewonly
    ):
        raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)
    if not all(
        callable(getattr(association_type, attribute, None))
        for attribute in (
            "primary_key_name",
            "force_fill",
            "save",
            "save_async",
        )
    ) or not isinstance(getattr(association_type, "timestamps", None), bool):
        raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)
    if not all(
        isinstance(getattr(association_type, attribute, None), str)
        for attribute in ("created_at_name", "updated_at_name")
    ):
        raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)
    related_type = cast(
        "type[_ModelHost]",
        related_relationship.mapper.class_,
    )
    return _AssociationObjectInfo(
        collection_attribute=proxy.target_collection,
        parent_attribute=collection_relationship.back_populates,
        related_attribute=proxy.value_attr,
        association_type=cast("type[_AssociationPivot]", association_type),
        related_type=related_type,
    )


def _parse_morph_many_to_many_info(
    value: object,
) -> _MorphManyToManyInfo | None:
    """Validate relationship metadata before enabling direct pivot writes.

    Args:
        value: Application-independent SQLAlchemy relationship info value.

    Returns:
        Validated morph relation settings, or ``None`` for ordinary relations.

    Raises:
        DatabaseQueryError: If the relationship info is malformed.
    """
    if value is None:
        return None
    if not isinstance(value, tuple):
        raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)
    values = cast("tuple[object, ...]", value)
    if len(values) != _MORPH_RELATION_INFO_ITEM_COUNT:
        raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)
    direction_value, pivot_value = values
    if direction_value == "morph_to_many":
        direction: Literal["morph_to_many", "morphed_by_many"] = "morph_to_many"
    elif direction_value == "morphed_by_many":
        direction = "morphed_by_many"
    else:
        raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)
    if not isinstance(pivot_value, MorphPivot):
        raise DatabaseQueryError(_MANY_TO_MANY_REQUIRED_ERROR)
    return _MorphManyToManyInfo(direction, pivot_value)


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


def _shared_pivot_values(
    values: Mapping[str, object] | None,
) -> dict[str, object]:
    """Validate and copy values shared by requested association rows.

    Args:
        values: Optional mapping of association columns to values.

    Returns:
        A mutable copy of the caller mapping.

    Raises:
        DatabaseQueryError: If a shared association column name is invalid.
    """
    if values is None:
        return {}
    mapping = cast("Mapping[object, object]", values)
    if not _mapping_has_string_keys(mapping):
        raise DatabaseQueryError(_PIVOT_UPDATE_ATTRIBUTES_ERROR)
    return dict(cast("Mapping[str, object]", mapping))


def _related_value_pairs(
    values: object | Sequence[object],
    allow_pivot_values: bool,
) -> tuple[tuple[object, Mapping[str, object]], ...]:
    """Pair related identifiers with optional per-row association values.

    Args:
        values: Related identifiers, models, or a keyed pivot-value mapping.
        allow_pivot_values: Whether a mapping denotes row-specific values.

    Returns:
        Ordered related values and their association mappings.

    Raises:
        DatabaseQueryError: If a per-row association mapping is malformed.
    """
    if not allow_pivot_values or not isinstance(values, Mapping):
        return tuple((related, {}) for related in _sequence_values(values))
    entries: list[tuple[object, Mapping[str, object]]] = []
    mapping = cast("Mapping[object, object]", values)
    for related, attributes in mapping.items():
        if not isinstance(attributes, Mapping):
            raise DatabaseQueryError(_PIVOT_UPDATE_ATTRIBUTES_ERROR)
        attribute_mapping = cast("Mapping[object, object]", attributes)
        if not _mapping_has_string_keys(attribute_mapping):
            raise DatabaseQueryError(_PIVOT_UPDATE_ATTRIBUTES_ERROR)
        entries.append(
            (related, cast("Mapping[str, object]", attribute_mapping)),
        )
    return tuple(entries)


def _mapping_has_string_keys(values: Mapping[object, object]) -> bool:
    """Check that dynamically supplied mapping keys are strings.

    Args:
        values: Mapping received from a runtime caller.

    Returns:
        Whether every key is a string.
    """
    return all(isinstance(name, str) for name in values)


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


def _desired_related_models(
    current: Mapping[object, _ModelHost],
    added: Mapping[object, _ModelHost],
    to_attach: tuple[object, ...],
    to_detach: tuple[object, ...],
) -> tuple[_ModelHost, ...]:
    """Build the collection cache resulting from timestamped pivot changes.

    Args:
        current: Existing related models in relationship load order.
        added: Newly loaded related models indexed by their identifiers.
        to_attach: Related identifiers to append after existing models.
        to_detach: Existing related identifiers to remove.

    Returns:
        Existing retained models followed by newly attached models.
    """
    detached = set(to_detach)
    retained = tuple(
        model
        for identifier, model in current.items()
        if identifier not in detached
    )
    return retained + tuple(added[identifier] for identifier in to_attach)


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
