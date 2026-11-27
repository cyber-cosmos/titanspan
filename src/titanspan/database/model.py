"""Provide a typed Active Record base over SQLAlchemy declarative mapping.

SQLAlchemy owns identity, attribute history, mapping, and Unit of Work state.
Titanspan adds safe mass assignment and application-aware persistence methods.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections.abc import (
    Awaitable,
    Callable,
    Generator,
    Iterable,
    Mapping,
    Sequence,
)
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import Enum
from inspect import iscoroutinefunction
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Self, cast
from uuid import UUID

import anyio
from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    MetaData,
    Numeric,
    select,
    update,
)
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    declared_attr,
    mapped_column,
)
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.orm.base import NO_VALUE
from sqlalchemy.orm.exc import ObjectDeletedError
from sqlalchemy.orm.session import object_session

from titanspan._application_context import active_application_context
from titanspan.database.events import (
    ModelCreated,
    ModelCreating,
    ModelDeleted,
    ModelDeleting,
    ModelEvent,
    ModelSaved,
    ModelSaving,
    ModelUpdated,
    ModelUpdating,
)
from titanspan.database.exceptions import (
    DatabaseQueryError,
    DatabaseTransactionError,
    DatabaseTransactionOwnershipError,
    MassAssignmentError,
    ModelNotFoundError,
)
from titanspan.database.factory import ModelFactory
from titanspan.database.model_collection import ModelCollection
from titanspan.database.model_state import (
    last_changes,
    recently_created,
    remember_deleted,
    remember_save,
    remember_service,
    require_service,
    was_deleted,
)
from titanspan.database.orm_builder import ModelQueryBuilder
from titanspan.facades.database import DB
from titanspan.facades.event import Event

if TYPE_CHECKING:
    from sqlalchemy.sql.schema import Column

    from titanspan.contracts.database import DatabaseService
    from titanspan.events.dispatcher import ListenerRegistration

@dataclass(frozen=True, slots=True)
class _UnguardedContext:
    """Identify the execution and app allowed to bypass fill guards.

    ContextVars propagate into child tasks. Matching the task, thread, app,
    container, and active scope prevents inherited authority from escaping.
    """

    thread_id: int
    task_id: int | None
    application: object | None
    container: object | None
    scope: object | None


_MASS_ASSIGNMENT_UNGUARDED: ContextVar[_UnguardedContext | None] = ContextVar(
    "titanspan_database_mass_assignment_unguarded",
    default=None,
)
_SNAKE_CASE_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_SNAKE_CASE_ACRONYM = re.compile(r"([A-Z]+)([A-Z][a-z])")
_MODEL_NOT_FOUND_MESSAGE = "The requested model was not found."
_MYSQL_DUPLICATE_ENTRY_CODE = 1062
_DESTROY_CHUNK_SIZE = 500
_OBSERVER_METHODS_ERROR = "A model observer must define a lifecycle method."
_OBSERVER_HOOK_ERROR = "Observer lifecycle hooks must be callable."
_COMPOSITE_KEY_ERROR = (
    "This model operation requires a single-column primary key."
)


class SoftDeletes:
    """Add timestamp-based soft deletion to a declarative model.

    The mixin provides default query filtering and explicit restore or hard
    deletion methods without replacing SQLAlchemy's mapped state machinery.
    """

    __soft_delete_enabled__: ClassVar[bool] = True
    deleted_at_name: ClassVar[str] = "deleted_at"

    @declared_attr
    def deleted_at(self: SoftDeletes) -> Mapped[datetime | None]:
        """Map the configured nullable soft-delete timestamp.

        Returns:
            A timezone-aware timestamp column on the concrete model table.
        """
        return mapped_column(
            self.deleted_at_name,
            DateTime(timezone=True),
            nullable=True,
        )

    def trashed(self) -> bool:
        """Return whether the mapped deletion timestamp is set.

        Returns:
            Whether this model currently represents a soft-deleted row.
        """
        return getattr(self, self.deleted_at_name) is not None

    def restore(self) -> bool:
        """Clear the deletion timestamp and persist the model.

        Returns:
            Whether the model was previously soft deleted and was saved.
        """
        if not self.trashed():
            return False
        setattr(self, self.deleted_at_name, None)
        return cast("Model", self).save()

    async def restore_async(self) -> bool:
        """Asynchronously clear and persist the deletion timestamp.

        Returns:
            Whether the model was previously soft deleted and was saved.
        """
        if not self.trashed():
            return False
        setattr(self, self.deleted_at_name, None)
        return await cast("Model", self).save_async()


class Model(DeclarativeBase):
    """Base SQLAlchemy model with native active-record operations.

    Subclasses declare `Mapped` columns normally, set `fillable`, and may
    override the inferred table or connection through class attributes.
    Direct constructor assignment follows trusted SQLAlchemy mapping semantics;
    request mappings must use guarded `fill` or `create` methods.
    """

    __abstract__ = True
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    table: ClassVar[str | None] = None
    connection: ClassVar[str | None] = None
    fillable: ClassVar[tuple[str, ...]] = ()
    guarded: ClassVar[tuple[str, ...]] = ("*",)
    hidden: ClassVar[tuple[str, ...]] = ()
    visible: ClassVar[tuple[str, ...]] = ()
    appends: ClassVar[tuple[str, ...]] = ()
    factory_attributes: ClassVar[Mapping[str, object]] = MappingProxyType({})
    strict_mass_assignment: ClassVar[bool] = False
    timestamps: ClassVar[bool] = True
    created_at_name: ClassVar[str] = "created_at"
    updated_at_name: ClassVar[str] = "updated_at"
    route_key_name: ClassVar[str] = "id"

    @declared_attr.directive
    def __tablename__(self: Model) -> str:
        """Infer a stable plural snake-case table name unless overridden.

        Returns:
            An explicit ``table`` value or a conventional inferred name.
        """
        configured = self.__dict__.get("table")
        if isinstance(configured, str) and configured:
            return configured
        return _pluralize(_snake_case(self.__name__))

    @declared_attr
    def created_at(self: Model) -> Mapped[datetime | None]:
        """Map the configured creation timestamp when enabled.

        Returns:
            A nullable timezone-aware UTC timestamp mapping or ``None``.
        """
        return mapped_column(
            self.created_at_name,
            DateTime(timezone=True),
            nullable=True,
        )

    @declared_attr
    def updated_at(self: Model) -> Mapped[datetime | None]:
        """Map the configured update timestamp when enabled.

        Returns:
            A nullable timezone-aware UTC timestamp mapping or ``None``.
        """
        return mapped_column(
            self.updated_at_name,
            DateTime(timezone=True),
            nullable=True,
        )

    @classmethod
    def query(cls) -> ModelQueryBuilder[Self]:
        """Start a typed ORM query on the active application service.

        Returns:
            A model-aware query builder for this mapped class.
        """
        return ModelQueryBuilder(cls, DB.resolve_service())

    @classmethod
    def factory(cls) -> ModelFactory[Self]:
        """Create a factory using this model's trusted attribute defaults.

        Returns:
            A reusable native factory bound to this model class, not a database
            application. Persistence resolves the active Database service when
            a factory operation creates records.
        """
        return ModelFactory(cls, cls.factory_attributes)

    @classmethod
    def observe(
        cls,
        observer_type: type[object],
    ) -> tuple[ListenerRegistration, ...]:
        """Register one Container-resolved lifecycle observer for this model.

        The observer may define any subset of supported hook names. Its
        registrations belong to the active application's Events dispatcher.

        Args:
            observer_type: Trusted class resolved by the active Container.

        Returns:
            Removable handles for every registered lifecycle method.

        Raises:
            ValueError: If the observer defines no supported lifecycle method.
            TypeError: If a supported hook exists but is not callable.
        """
        hooks: tuple[tuple[str, type[object]], ...] = (
            ("saving", ModelSaving),
            ("saved", ModelSaved),
            ("creating", ModelCreating),
            ("created", ModelCreated),
            ("updating", ModelUpdating),
            ("updated", ModelUpdated),
            ("deleting", ModelDeleting),
            ("deleted", ModelDeleted),
        )
        registrations: list[ListenerRegistration] = []
        for method_name, event_type in hooks:
            method = getattr(observer_type, method_name, None)
            if method is None:
                continue
            if not callable(method):
                raise TypeError(_OBSERVER_HOOK_ERROR)
            listener = _observer_listener(
                cls,
                observer_type,
                method_name,
                method,
            )
            registrations.append(Event.listen(event_type, listener))
        if not registrations:
            raise ValueError(_OBSERVER_METHODS_ERROR)
        return tuple(registrations)

    @classmethod
    def all(cls) -> ModelCollection[Self]:
        """Retrieve every matching model using the sync database API.

        Returns:
            Detached model instances in database result order.
        """
        return cls.query().get()

    @classmethod
    async def all_async(cls) -> ModelCollection[Self]:
        """Retrieve every matching model using asynchronous database I/O.

        Returns:
            Detached model instances in database result order.
        """
        return await cls.query().get_async()

    @classmethod
    def first(cls) -> Self | None:
        """Return the first row using the model's default query.

        Returns:
            A detached model or ``None`` when its table is empty.
        """
        return cls.query().first()

    @classmethod
    async def first_async(cls) -> Self | None:
        """Asynchronously return the first row from the model's table.

        Returns:
            A detached model or ``None`` when its table is empty.
        """
        return await cls.query().first_async()

    @classmethod
    def first_or_fail(cls) -> Self:
        """Return the first row or raise a native not-found exception.

        Returns:
            The first detached model.

        Raises:
            ModelNotFoundError: If the table contains no matching row.
        """
        return cls.query().first_or_fail()

    @classmethod
    async def first_or_fail_async(cls) -> Self:
        """Asynchronously return the first row or raise not found.

        Returns:
            The first detached model.

        Raises:
            ModelNotFoundError: If the table contains no matching row.
        """
        return await cls.query().first_or_fail_async()

    @classmethod
    def sole(cls) -> Self:
        """Require the model table to contain exactly one row.

        Returns:
            The sole detached model.

        Raises:
            ModelNotFoundError: If no row matched.
            MultipleModelsFoundError: If multiple rows matched.
        """
        return cls.query().sole()

    @classmethod
    async def sole_async(cls) -> Self:
        """Asynchronously require exactly one matching model.

        Returns:
            The sole detached model.

        Raises:
            ModelNotFoundError: If no row matched.
            MultipleModelsFoundError: If multiple rows matched.
        """
        return await cls.query().sole_async()

    @classmethod
    def find(cls, identifier: object) -> Self | None:
        """Find a row by its mapped primary key.

        Args:
            identifier: Primary-key value or composite identity tuple.

        Returns:
            A detached mapped model, or ``None`` when no row matches.
        """
        return cls.query().find(identifier)

    @classmethod
    async def find_async(cls, identifier: object) -> Self | None:
        """Asynchronously find a row by its mapped primary key.

        Args:
            identifier: Primary-key value or composite identity tuple.

        Returns:
            A detached mapped model, or ``None`` when no row matches.
        """
        return await cls.query().find_async(identifier)

    @classmethod
    def find_many(
        cls,
        identifiers: Iterable[object],
    ) -> ModelCollection[Self]:
        """Retrieve rows matching any of the supplied primary keys.

        Args:
            identifiers: Primary-key values chosen by application code.

        Returns:
            Matching detached models in database result order.
        """
        return cls.query().find_many(tuple(identifiers))

    @classmethod
    async def find_many_async(
        cls,
        identifiers: Iterable[object],
    ) -> ModelCollection[Self]:
        """Asynchronously retrieve rows matching supplied identifiers.

        Args:
            identifiers: Primary-key values chosen by application code.

        Returns:
            Matching detached models in database result order.
        """
        return await cls.query().find_many_async(tuple(identifiers))

    @classmethod
    def find_or_fail(cls, identifier: object) -> Self:
        """Find a row or raise a native not-found exception.

        Args:
            identifier: Primary-key value or composite identity tuple.

        Returns:
            The matching detached model.

        Raises:
            ModelNotFoundError: If no row matches.
        """
        model = cls.find(identifier)
        if model is None:
            raise ModelNotFoundError(_MODEL_NOT_FOUND_MESSAGE)
        return model

    @classmethod
    async def find_or_fail_async(cls, identifier: object) -> Self:
        """Asynchronously find a row or raise a native not-found error.

        Args:
            identifier: Primary-key value or composite identity tuple.

        Returns:
            The matching detached model.

        Raises:
            ModelNotFoundError: If no row matches.
        """
        model = await cls.find_async(identifier)
        if model is None:
            raise ModelNotFoundError(_MODEL_NOT_FOUND_MESSAGE)
        return model

    @classmethod
    def find_or(
        cls,
        identifier: object,
        fallback: Callable[[], Self],
    ) -> Self:
        """Find a model or invoke a trusted application fallback.

        Args:
            identifier: Primary-key value or composite identity tuple.
            fallback: Zero-argument factory called only when no row exists.

        Returns:
            The matching model or the fallback result.
        """
        model = cls.find(identifier)
        return fallback() if model is None else model

    @classmethod
    async def find_or_async(
        cls,
        identifier: object,
        fallback: Callable[[], Self],
    ) -> Self:
        """Asynchronously find a model or use an application fallback.

        Args:
            identifier: Primary-key value or composite identity tuple.
            fallback: Zero-argument factory called only when no row exists.

        Returns:
            The matching model or the fallback result.
        """
        model = await cls.find_async(identifier)
        return fallback() if model is None else model

    @classmethod
    def first_or_new(
        cls,
        attributes: Mapping[str, object],
        values: Mapping[str, object] | None = None,
    ) -> Self:
        """Find a matching model or return an unsaved, mass-assigned model.

        Args:
            attributes: Column equality constraints used to find a row.
            values: Additional values assigned only to a new model.

        Returns:
            An existing model or a new transient model.
        """
        model = cls.query().where(attributes).first()
        if model is not None:
            return model
        return cls().fill(_creation_values(attributes, values))

    @classmethod
    async def first_or_new_async(
        cls,
        attributes: Mapping[str, object],
        values: Mapping[str, object] | None = None,
    ) -> Self:
        """Asynchronously find a model or return an unsaved new instance.

        Args:
            attributes: Column equality constraints used to find a row.
            values: Additional values assigned only to a new model.

        Returns:
            An existing model or a new transient model.
        """
        model = await cls.query().where(attributes).first_async()
        if model is not None:
            return model
        return cls().fill(_creation_values(attributes, values))

    @classmethod
    def first_or_create(
        cls,
        attributes: Mapping[str, object],
        values: Mapping[str, object] | None = None,
    ) -> Self:
        """Find a row or persist a new model with race-safe unique handling.

        Args:
            attributes: Column equality constraints used to find a row.
            values: Additional values assigned only when creating a row.

        Returns:
            An existing or newly persisted detached model.
        """
        model = cls.first_or_new(attributes, values)
        if model.exists:
            return model
        return cls.create_or_first(attributes, values)

    @classmethod
    async def first_or_create_async(
        cls,
        attributes: Mapping[str, object],
        values: Mapping[str, object] | None = None,
    ) -> Self:
        """Asynchronously find or create a row with unique-race recovery.

        Args:
            attributes: Column equality constraints used to find a row.
            values: Additional values assigned only when creating a row.

        Returns:
            An existing or newly persisted detached model.
        """
        model = await cls.first_or_new_async(attributes, values)
        if model.exists:
            return model
        return await cls.create_or_first_async(attributes, values)

    @classmethod
    def create_or_first(
        cls,
        attributes: Mapping[str, object],
        values: Mapping[str, object] | None = None,
    ) -> Self:
        """Insert a model or return a row after a unique constraint race.

        Args:
            attributes: Values used both for insert and conflict lookup.
            values: Additional values included in a new row.

        Returns:
            The inserted model or the existing row matching ``attributes``.

        Raises:
            DatabaseTransactionError: If persistence fails for a reason other
                than a recognized unique constraint violation.
        """
        model = cls().fill(_creation_values(attributes, values))
        service = DB.resolve_service()
        try:
            with service.transaction(cls.connection):
                model.save()
        except DatabaseTransactionError as error:
            if not _is_unique_constraint_violation(error):
                raise
            existing = cls.query().where(attributes).first()
            if existing is None:
                raise
            return existing
        return model

    @classmethod
    async def create_or_first_async(
        cls,
        attributes: Mapping[str, object],
        values: Mapping[str, object] | None = None,
    ) -> Self:
        """Asynchronously insert or recover a unique constraint race.

        Args:
            attributes: Values used both for insert and conflict lookup.
            values: Additional values included in a new row.

        Returns:
            The inserted model or the existing row matching ``attributes``.

        Raises:
            DatabaseTransactionError: If persistence fails for a reason other
                than a recognized unique constraint violation.
        """
        model = cls().fill(_creation_values(attributes, values))
        service = DB.resolve_service()
        try:
            async with service.transaction_async(cls.connection):
                await model.save_async()
        except DatabaseTransactionError as error:
            if not _is_unique_constraint_violation(error):
                raise
            existing = await cls.query().where(attributes).first_async()
            if existing is None:
                raise
            return existing
        return model

    @classmethod
    def update_or_create(
        cls,
        attributes: Mapping[str, object],
        values: Mapping[str, object],
    ) -> Self:
        """Find a model, update its values, or create it atomically.

        Args:
            attributes: Column equality constraints used to find a row.
            values: Mass-assigned values for an existing or new model.

        Returns:
            A persisted model after the enclosing transaction commits.
        """
        service = DB.resolve_service()
        with service.transaction(cls.connection):
            model = cls.query().where(attributes).first()
            if model is None:
                model = cls.create_or_first(attributes, values)
            elif values:
                model.update(values)
        return model

    @classmethod
    async def update_or_create_async(
        cls,
        attributes: Mapping[str, object],
        values: Mapping[str, object],
    ) -> Self:
        """Asynchronously find, update, or create in one transaction.

        Args:
            attributes: Column equality constraints used to find a row.
            values: Mass-assigned values for an existing or new model.

        Returns:
            A persisted model after the enclosing transaction commits.
        """
        service = DB.resolve_service()
        async with service.transaction_async(cls.connection):
            model = await cls.query().where(attributes).first_async()
            if model is None:
                model = await cls.create_or_first_async(attributes, values)
            elif values:
                await model.update_async(values)
        return model

    @classmethod
    def create(cls, attributes: Mapping[str, object]) -> Self:
        """Mass-assign and persist one new model synchronously.

        Args:
            attributes: Candidate column values filtered by ``fillable``.

        Returns:
            The newly persisted, detached model.
        """
        model = cls().fill(attributes)
        model.save()
        return model

    @classmethod
    async def create_async(cls, attributes: Mapping[str, object]) -> Self:
        """Mass-assign and persist one new model asynchronously.

        Args:
            attributes: Candidate column values filtered by ``fillable``.

        Returns:
            The newly persisted, detached model.
        """
        model = cls().fill(attributes)
        await model.save_async()
        return model

    @classmethod
    def create_many(
        cls,
        records: Iterable[Mapping[str, object]],
    ) -> ModelCollection[Self]:
        """Persist multiple mass-assigned models in one transaction.

        Args:
            records: Finite sequence of candidate model attributes.

        Returns:
            Persisted models in input order.
        """
        service = DB.resolve_service()
        models: list[Self] = []
        with service.transaction(cls.connection):
            for attributes in records:
                model = cls().fill(attributes)
                model.save()
                models.append(model)
        return ModelCollection(models)

    @classmethod
    async def create_many_async(
        cls,
        records: Iterable[Mapping[str, object]],
    ) -> ModelCollection[Self]:
        """Asynchronously persist models sequentially in one transaction.

        Args:
            records: Finite sequence of candidate model attributes.

        Returns:
            Persisted models in input order.
        """
        service = DB.resolve_service()
        models: list[Self] = []
        async with service.transaction_async(cls.connection):
            for attributes in records:
                model = cls().fill(attributes)
                await model.save_async()
                models.append(model)
        return ModelCollection(models)

    @classmethod
    def force_create(cls, attributes: Mapping[str, object]) -> Self:
        """Explicitly bypass fillable and guarded column policies once.

        Args:
            attributes: Trusted column values supplied by application code.

        Returns:
            The newly persisted, detached model.
        """
        model = cls().force_fill(attributes)
        model.save()
        return model

    @classmethod
    async def force_create_async(
        cls,
        attributes: Mapping[str, object],
    ) -> Self:
        """Asynchronously persist trusted values with explicit force fill.

        Args:
            attributes: Trusted column values supplied by application code.

        Returns:
            The newly persisted, detached model.
        """
        model = cls().force_fill(attributes)
        await model.save_async()
        return model

    @classmethod
    def primary_key_name(cls) -> str:
        """Return the sole mapped primary-key attribute name.

        Returns:
            The mapper's primary-key attribute name.

        Raises:
            DatabaseQueryError: If the model uses a composite primary key
                unsupported by the single-column query helpers.
        """
        mapper = sa_inspect(cls)
        if len(mapper.primary_key) != 1:
            raise DatabaseQueryError(_COMPOSITE_KEY_ERROR)
        name = mapper.primary_key[0].key
        if name is None:
            raise DatabaseQueryError(_COMPOSITE_KEY_ERROR)
        return name

    @classmethod
    @contextmanager
    def unguarded(cls) -> Generator[None, None, None]:
        """Temporarily allow trusted column assignment in this context only.

        Yields:
            Control while mass assignment is explicitly unguarded.
        """
        active = active_application_context()
        context = _UnguardedContext(
            thread_id=threading.get_ident(),
            task_id=_current_task_id(),
            application=active.application if active is not None else None,
            container=active.container if active is not None else None,
            scope=active.scope if active is not None else None,
        )
        token = _MASS_ASSIGNMENT_UNGUARDED.set(context)
        try:
            yield
        finally:
            _MASS_ASSIGNMENT_UNGUARDED.reset(token)

    def fill(self, attributes: Mapping[str, object]) -> Self:
        """Assign only mapped columns allowed by the model policy.

        Args:
            attributes: Candidate values, such as untrusted request data.

        Returns:
            This model for fluent construction.

        Raises:
            MassAssignmentError: If strict mode encounters discarded keys.
        """
        rejected = self._assign_attributes(attributes, force=False)
        if rejected and type(self).strict_mass_assignment:
            names = ", ".join(sorted(rejected))
            msg = f"Mass assignment rejected columns: {names}."
            raise MassAssignmentError(msg)
        return self

    def force_fill(self, attributes: Mapping[str, object]) -> Self:
        """Assign trusted mapped columns while bypassing fillable guards.

        Args:
            attributes: Trusted application-owned column values.

        Returns:
            This model for fluent construction.

        Raises:
            MassAssignmentError: If an attribute is not a mapped column.
        """
        rejected = self._assign_attributes(attributes, force=True)
        if rejected:
            names = ", ".join(sorted(rejected))
            msg = f"Force fill accepts mapped columns only: {names}."
            raise MassAssignmentError(msg)
        return self

    def save(self) -> bool:
        """Flush this model through its application-owned Unit of Work.

        Returns:
            ``True`` after SQLAlchemy flushes the insert or update.

        Raises:
            DatabaseTransactionOwnershipError: If another app or session owns
                this model instance.
        """
        service = DB.resolve_service()
        with service.session(type(self).connection) as session:
            self._ensure_session_owner(service, session)
            state = sa_inspect(self)
            created = state.transient or state.pending
            if state.detached:
                session.add(self)
            before_events: tuple[ModelEvent[Self], ...] = (
                ModelSaving(self),
                ModelCreating(self) if created else ModelUpdating(self),
            )
            if not _dispatch_cancellable_events(before_events):
                _discard_cancelled_save(self, session)
                return False
            changes = self._changed_attributes()
            self._set_timestamps(created=created)
            changes.update(self._changed_attributes())
            if state.transient or state.detached:
                session.add(self)
            session.flush()
            remember_service(self, service)

            def after_commit() -> None:
                """Record state and dispatch committed save events.

                This callback runs only after the selected transaction commits.
                """
                remember_save(
                    self,
                    service,
                    created=created,
                    changes=changes,
                )
                _dispatch_saved_events(self, created)

            service.after_commit(after_commit, type(self).connection)
        return True

    async def save_async(self) -> bool:
        """Flush this model through the current task's Unit of Work.

        Returns:
            ``True`` after SQLAlchemy flushes the insert or update.

        Raises:
            DatabaseTransactionOwnershipError: If another app or session owns
                this model instance.
        """
        service = DB.resolve_service()
        async with service.session_async(type(self).connection) as session:
            self._ensure_session_owner(service, session)
            state = sa_inspect(self)
            created = state.transient or state.pending
            if state.detached:
                session.add(self)
            before_events: tuple[ModelEvent[Self], ...] = (
                ModelSaving(self),
                ModelCreating(self) if created else ModelUpdating(self),
            )
            if not await _dispatch_cancellable_events_async(before_events):
                await _discard_cancelled_save_async(self, session)
                return False
            changes = self._changed_attributes()
            self._set_timestamps(created=created)
            changes.update(self._changed_attributes())
            if state.transient or state.detached:
                session.add(self)
            await session.flush()
            remember_service(self, service)

            async def after_commit() -> None:
                """Record state and await committed save listeners.

                The manager preserves its order with other commit callbacks.
                """
                remember_save(
                    self,
                    service,
                    created=created,
                    changes=changes,
                )
                await _dispatch_saved_events_async(self, created)

            await service.after_commit_async(
                after_commit,
                type(self).connection,
            )
        return True

    def save_or_fail(self) -> bool:
        """Persist this model and propagate native database failures.

        Returns:
            ``True`` after the save succeeds.
        """
        return self.save()

    async def save_or_fail_async(self) -> bool:
        """Asynchronously persist this model and propagate database failures.

        Returns:
            ``True`` after the save succeeds.
        """
        return await self.save_async()

    def update(self, attributes: Mapping[str, object]) -> bool:
        """Mass-assign permitted columns and persist this instance.

        Args:
            attributes: Candidate values filtered by the model policy.

        Returns:
            ``True`` after the save succeeds.
        """
        self.fill(attributes)
        return self.save()

    async def update_async(self, attributes: Mapping[str, object]) -> bool:
        """Asynchronously mass-assign and persist this instance.

        Args:
            attributes: Candidate values filtered by the model policy.

        Returns:
            ``True`` after the save succeeds.
        """
        self.fill(attributes)
        return await self.save_async()

    def delete(self) -> bool:
        """Delete this persisted model in its current application context.

        Returns:
            Whether SQLAlchemy flushed a delete for this instance.
        """
        if isinstance(self, SoftDeletes):
            if not self.exists or self.trashed():
                return False
            setattr(self, type(self).deleted_at_name, datetime.now(UTC))
            return self.save()
        return self._delete_sync()

    async def delete_async(self) -> bool:
        """Asynchronously delete this persisted model instance.

        Returns:
            Whether SQLAlchemy flushed a delete for this instance.
        """
        if isinstance(self, SoftDeletes):
            if not self.exists or self.trashed():
                return False
            setattr(self, type(self).deleted_at_name, datetime.now(UTC))
            return await self.save_async()
        return await self._delete_async()

    def force_delete(self) -> bool:
        """Hard-delete this row regardless of soft-delete behavior.

        Returns:
            Whether SQLAlchemy flushed a delete for this model.
        """
        return self._delete_sync()

    async def force_delete_async(self) -> bool:
        """Asynchronously hard-delete this row.

        Returns:
            Whether SQLAlchemy flushed a delete for this model.
        """
        return await self._delete_async()

    def increment(self, column_name: str, amount: int = 1) -> bool:
        """Atomically increase a persisted numeric column.

        Args:
            column_name: Mapped integer, float, or decimal attribute.
            amount: Signed integer delta to add.

        Returns:
            Whether the row still existed and the update succeeded.

        Raises:
            DatabaseQueryError: If the attribute is absent or non-numeric.
        """
        service = DB.resolve_service()
        with service.session(type(self).connection) as session:
            self._ensure_session_owner(service, session)
            state = sa_inspect(self)
            if state.transient or state.pending:
                current = self._numeric_attribute(column_name)
                setattr(self, column_name, current + amount)
                return self.save()
            if state.detached:
                session.add(self)
            return self._increment_in_session(
                service,
                session,
                column_name,
                amount,
            )

    def decrement(self, column_name: str, amount: int = 1) -> bool:
        """Decrease one loaded numeric attribute and persist the model.

        Args:
            column_name: Mapped integer, float, or decimal attribute.
            amount: Signed integer delta to subtract.

        Returns:
            Whether SQLAlchemy flushed the model update.
        """
        return self.increment(column_name, -amount)

    async def increment_async(
        self,
        column_name: str,
        amount: int = 1,
    ) -> bool:
        """Asynchronously atomically increase a persisted numeric column.

        Args:
            column_name: Mapped integer, float, or decimal attribute.
            amount: Signed integer delta to add.

        Returns:
            Whether the row still existed and the update succeeded.
        """
        service = DB.resolve_service()
        async with service.session_async(type(self).connection) as session:
            self._ensure_session_owner(service, session)
            state = sa_inspect(self)
            if state.transient or state.pending:
                current = self._numeric_attribute(column_name)
                setattr(self, column_name, current + amount)
                return await self.save_async()
            if state.detached:
                session.add(self)
            return await self._increment_in_session_async(
                service,
                session,
                column_name,
                amount,
            )

    async def decrement_async(
        self,
        column_name: str,
        amount: int = 1,
    ) -> bool:
        """Asynchronously decrease a loaded numeric model attribute.

        Args:
            column_name: Mapped integer, float, or decimal attribute.
            amount: Signed integer delta to subtract.

        Returns:
            Whether SQLAlchemy flushed the model update.
        """
        return await self.increment_async(column_name, -amount)

    def _increment_in_session(
        self,
        service: DatabaseService,
        session: Session,
        column_name: str,
        amount: int,
    ) -> bool:
        """Execute and synchronize an atomic update in the owning session.

        Args:
            service: Application-owned Database service.
            session: Session that owns this model and transaction.
            column_name: Mapped numeric attribute to increase.
            amount: Signed integer delta.

        Returns:
            Whether a matching row was updated.
        """
        column = _numeric_column(type(self), column_name)
        if isinstance(self, SoftDeletes) and self.trashed():
            return False
        if not _dispatch_cancellable_events(
            (ModelSaving(self), ModelUpdating(self)),
        ):
            _discard_cancelled_save(self, session)
            return False
        self._set_timestamps(created=False)
        changes = self._changed_attributes()
        session.flush()
        values: dict[object, object] = {column: column + amount}
        updated_at = _updated_at_column(type(self))
        now: datetime | None = None
        if updated_at is not None:
            now = datetime.now(UTC)
            values[updated_at] = now
        statement = update(column.table).values(values)
        conditions = [
            key_column == key_value
            for key_column, key_value in _identity_values(self)
        ]
        if isinstance(self, SoftDeletes):
            deleted_column = sa_inspect(type(self)).attrs[
                type(self).deleted_at_name
            ].columns[0]
            conditions.append(deleted_column.is_(None))
        statement = statement.where(*conditions)
        session.execute(statement)
        row = session.execute(
            select(column).where(*conditions),
        ).one_or_none()
        if row is None:
            return False
        value = row[0]
        set_committed_value(self, column_name, value)
        changes[column_name] = value
        if updated_at is not None and now is not None:
            updated_name = type(self).updated_at_name
            set_committed_value(self, updated_name, now)
            changes[updated_name] = now
        remember_service(self, service)

        def after_commit() -> None:
            """Record the durable change and dispatch model events."""
            remember_save(
                self,
                service,
                created=False,
                changes=changes,
            )
            _dispatch_saved_events(self, created=False)

        service.after_commit(after_commit, type(self).connection)
        return True

    async def _increment_in_session_async(
        self,
        service: DatabaseService,
        session: AsyncSession,
        column_name: str,
        amount: int,
    ) -> bool:
        """Execute and synchronize an async atomic update.

        Args:
            service: Application-owned Database service.
            session: Task-owned session for this model operation.
            column_name: Mapped numeric attribute to increase.
            amount: Signed integer delta.

        Returns:
            Whether a matching row was updated.
        """
        column = _numeric_column(type(self), column_name)
        if isinstance(self, SoftDeletes) and self.trashed():
            return False
        if not await _dispatch_cancellable_events_async(
            (ModelSaving(self), ModelUpdating(self)),
        ):
            await _discard_cancelled_save_async(self, session)
            return False
        self._set_timestamps(created=False)
        changes = self._changed_attributes()
        await session.flush()
        values: dict[object, object] = {column: column + amount}
        updated_at = _updated_at_column(type(self))
        now: datetime | None = None
        if updated_at is not None:
            now = datetime.now(UTC)
            values[updated_at] = now
        statement = update(column.table).values(values)
        identity = _identity_values(self)
        conditions = [
            key_column == key_value for key_column, key_value in identity
        ]
        if isinstance(self, SoftDeletes):
            deleted_column = sa_inspect(type(self)).attrs[
                type(self).deleted_at_name
            ].columns[0]
            conditions.append(deleted_column.is_(None))
        statement = statement.where(*conditions)
        await session.execute(statement)
        row = (
            await session.execute(
                select(column).where(*conditions),
            )
        ).one_or_none()
        if row is None:
            return False
        value = row[0]
        set_committed_value(self, column_name, value)
        changes[column_name] = value
        if updated_at is not None and now is not None:
            updated_name = type(self).updated_at_name
            set_committed_value(self, updated_name, now)
            changes[updated_name] = now
        remember_service(self, service)

        async def after_commit() -> None:
            """Record the durable change and await model event listeners."""
            remember_save(
                self,
                service,
                created=False,
                changes=changes,
            )
            await _dispatch_saved_events_async(self, created=False)

        await service.after_commit_async(
            after_commit,
            type(self).connection,
        )
        return True

    @classmethod
    def destroy(cls, identifiers: Sequence[object]) -> int:
        """Delete matching models individually within one transaction.

        Args:
            identifiers: Explicit primary-key values selected by application
                code.

        Returns:
            Number of rows found and deleted.
        """
        service = DB.resolve_service()
        deleted = 0
        key_name = cls.primary_key_name()
        with service.transaction(cls.connection):
            for chunk in _chunks(identifiers, _DESTROY_CHUNK_SIZE):
                models = cls.query().where_in(key_name, chunk).get()
                for model in models:
                    deleted += int(model.delete())
        return deleted

    @classmethod
    async def destroy_async(cls, identifiers: Sequence[object]) -> int:
        """Asynchronously delete matching models in bounded key batches.

        Args:
            identifiers: Explicit primary-key values selected by application
                code.

        Returns:
            Number of rows found and deleted.
        """
        service = DB.resolve_service()
        deleted = 0
        key_name = cls.primary_key_name()
        async with service.transaction_async(cls.connection):
            for chunk in _chunks(identifiers, _DESTROY_CHUNK_SIZE):
                models = await cls.query().where_in(key_name, chunk).get_async()
                for model in models:
                    deleted += int(await model.delete_async())
        return deleted

    @property
    def exists(self) -> bool:
        """Report whether SQLAlchemy has assigned a non-deleted identity.

        Returns:
            Whether this instance represents a persisted row.
        """
        state = sa_inspect(self)
        return (
            state.identity is not None
            and not state.deleted
            and not was_deleted(self)
        )

    @property
    def was_recently_created(self) -> bool:
        """Report whether the last Titanspan save inserted this instance.

        Returns:
            Whether the latest model save was an insert.
        """
        return recently_created(self)

    @property
    def dirty(self) -> Mapping[str, object]:
        """Expose current dirty column values from SQLAlchemy history.

        Returns:
            An immutable mapping of changed attribute names to current values.
        """
        return MappingProxyType(self._changed_attributes())

    @property
    def changes(self) -> Mapping[str, object]:
        """Return values recorded by the most recent successful model save.

        Returns:
            An immutable snapshot of attributes persisted by that save.
        """
        return MappingProxyType(last_changes(self))

    def was_changed(self, attribute: str | None = None) -> bool:
        """Check whether the last successful save changed a column.

        Args:
            attribute: Optional mapped attribute to check.

        Returns:
            Whether the last save changed any column or the selected one.
        """
        changes = last_changes(self)
        return bool(changes) if attribute is None else attribute in changes

    def original(self) -> Mapping[str, object]:
        """Return loaded values, preferring SQLAlchemy's prior history values.

        Returns:
            An immutable mapping of mapped columns currently loaded in memory.
        """
        state = sa_inspect(self)
        values: dict[str, object] = {}
        for attribute in sa_inspect(type(self)).column_attrs:
            history = state.attrs[attribute.key].history
            if history.deleted:
                values[attribute.key] = history.deleted[0]
                continue
            current = state.attrs[attribute.key].loaded_value
            if current is not NO_VALUE:
                values[attribute.key] = current
        return MappingProxyType(values)

    def fresh(self) -> Self | None:
        """Return a newly loaded instance with this model's current key.

        Returns:
            A detached fresh model or ``None`` if the row no longer exists.
        """
        if not self.exists:
            return None
        return type(self).find(getattr(self, type(self).primary_key_name()))

    async def fresh_async(self) -> Self | None:
        """Asynchronously reload this model as a distinct detached instance.

        Returns:
            A detached fresh model or ``None`` if the row no longer exists.
        """
        if not self.exists:
            return None
        return await type(self).find_async(
            getattr(self, type(self).primary_key_name()),
        )

    def refresh(self) -> Self:
        """Reload this instance's column values from its owning database.

        Returns:
            This refreshed model.

        Raises:
            ModelNotFoundError: If its database row no longer exists.
        """
        if not self.exists:
            raise ModelNotFoundError(_MODEL_NOT_FOUND_MESSAGE)
        service = DB.resolve_service()
        with service.session(type(self).connection) as session:
            self._ensure_session_owner(service, session)
            if object_session(self) is None:
                session.add(self)
            try:
                session.refresh(self)
            except ObjectDeletedError as error:
                raise ModelNotFoundError(_MODEL_NOT_FOUND_MESSAGE) from error
            remember_service(self, service)
        return self

    async def refresh_async(self) -> Self:
        """Asynchronously reload this instance from its owning database.

        Returns:
            This refreshed model.

        Raises:
            ModelNotFoundError: If its database row no longer exists.
        """
        if not self.exists:
            raise ModelNotFoundError(_MODEL_NOT_FOUND_MESSAGE)
        service = DB.resolve_service()
        async with service.session_async(type(self).connection) as session:
            self._ensure_session_owner(service, session)
            if object_session(self) is None:
                session.add(self)
            try:
                await session.refresh(self)
            except ObjectDeletedError as error:
                raise ModelNotFoundError(_MODEL_NOT_FOUND_MESSAGE) from error
            remember_service(self, service)
        return self

    def touch(self) -> bool:
        """Update the mapped timestamp columns and save this model.

        Returns:
            ``True`` after the update succeeds.
        """
        return self.save()

    async def touch_async(self) -> bool:
        """Asynchronously update mapped timestamp columns and save the model.

        Returns:
            ``True`` after the update succeeds.
        """
        return await self.save_async()

    def replicate(self) -> Self:
        """Create an unsaved copy excluding keys and automatic timestamps.

        Returns:
            A new transient model with the remaining loaded column values.
        """
        mapper = sa_inspect(type(self))
        excluded = {
            type(self).primary_key_name(),
            type(self).created_at_name,
            type(self).updated_at_name,
        }
        values = {
            attribute.key: getattr(self, attribute.key)
            for attribute in mapper.column_attrs
            if attribute.key not in excluded
            and state_loaded(self, attribute.key)
        }
        return type(self)().force_fill(values)

    def to_dict(self) -> dict[str, object]:
        """Serialize loaded columns and relationships without lazy I/O.

        Returns:
            A safe dictionary excluding hidden and unloaded attributes.
        """
        state = sa_inspect(self)
        mapped = sa_inspect(type(self))
        allowed = set(type(self).visible) if type(self).visible else None
        hidden = set(type(self).hidden)
        values: dict[str, object] = {}
        for attribute in mapped.column_attrs:
            name = attribute.key
            if name in hidden or (allowed is not None and name not in allowed):
                continue
            current = state.attrs[name].loaded_value
            if current is not NO_VALUE:
                values[name] = _serialize(current)
        for relationship in mapped.relationships:
            name = relationship.key
            if name in hidden or (allowed is not None and name not in allowed):
                continue
            current = state.attrs[name].loaded_value
            if current is not NO_VALUE:
                values[name] = _serialize(current)
        for name in type(self).appends:
            if name not in hidden and (allowed is None or name in allowed):
                values[name] = _serialize(getattr(self, name))
        return values

    def to_json(self) -> str:
        """Serialize this model to JSON without loading relationships.

        Returns:
            A JSON string generated from :meth:`to_dict`.
        """
        return json.dumps(self.to_dict(), separators=(",", ":"))

    def __repr__(self) -> str:
        """Return a representation that respects hidden model attributes.

        Returns:
            A class-named representation of the safe serialized values.
        """
        return f"{type(self).__name__}({self.to_dict()!r})"

    def _assign_attributes(
        self,
        attributes: Mapping[str, object],
        *,
        force: bool,
    ) -> list[str]:
        """Assign mapped columns and return keys rejected by the policy.

        Args:
            attributes: Candidate values.
            force: Whether to bypass the configured fillable and guarded sets.

        Returns:
            Rejected keys without their values.
        """
        column_names = {
            attribute.key for attribute in sa_inspect(type(self)).column_attrs
        }
        rejected: list[str] = []
        raw_attributes = cast(
            "Mapping[object, object]",
            attributes,
        )
        for raw_name, value in raw_attributes.items():
            if not isinstance(raw_name, str):
                rejected.append(str(raw_name))
                continue
            name = raw_name
            if name not in column_names:
                rejected.append(str(name))
                continue
            permitted = (
                force
                or _unguarded_context_is_active()
                or self._is_fillable(name)
            )
            if not permitted:
                rejected.append(name)
                continue
            setattr(self, name, value)
        return rejected

    def _is_fillable(self, name: str) -> bool:
        """Apply the model's explicit fillable and guarded declarations.

        Args:
            name: Mapped column attribute name.

        Returns:
            Whether normal mass assignment permits this column.
        """
        if type(self).fillable:
            return name in type(self).fillable
        guarded = type(self).guarded
        return "*" not in guarded and name not in guarded

    def _changed_attributes(self) -> dict[str, object]:
        """Read current dirty values from SQLAlchemy attribute history.

        Returns:
            Changed mapped column values without maintaining a parallel tracker.
        """
        state = sa_inspect(self)
        changes: dict[str, object] = {}
        for attribute in sa_inspect(type(self)).column_attrs:
            history = state.attrs[attribute.key].history
            if history.has_changes() and history.added:
                changes[attribute.key] = history.added[-1]
        return changes

    def _set_timestamps(self, *, created: bool) -> None:
        """Set enabled timestamp columns using one timezone-aware UTC instant.

        Args:
            created: Whether this operation is preparing an insert.
        """
        if not type(self).timestamps:
            return
        mapped_names = {
            attribute.key for attribute in sa_inspect(type(self)).column_attrs
        }
        now = datetime.now(UTC)
        created_name = type(self).created_at_name
        updated_name = type(self).updated_at_name
        if (
            created
            and created_name in mapped_names
            and getattr(self, created_name) is None
        ):
            setattr(self, created_name, now)
        if updated_name in mapped_names:
            setattr(self, updated_name, now)

    def _ensure_session_owner(
        self,
        service: DatabaseService,
        session: object,
    ) -> None:
        """Validate app ownership and reject attachment to another Session.

        Args:
            service: Current application database service.
            session: Current SQLAlchemy session from that service.

        Raises:
            DatabaseTransactionOwnershipError: If service or Session ownership
                does not match.
        """
        require_service(self, service)
        attached = object_session(self)
        owner_session = (
            session.sync_session
            if isinstance(session, AsyncSession)
            else session
        )
        if attached is not None and attached is not owner_session:
            msg = "The model is attached to a different database session."
            raise DatabaseTransactionOwnershipError(msg)

    def _numeric_attribute(self, column_name: str) -> int | float | Decimal:
        """Read a loaded numeric column without triggering deferred I/O.

        Args:
            column_name: Mapped numeric column name.

        Returns:
            The loaded numeric value.

        Raises:
            DatabaseQueryError: If the value is missing, unloaded, or not
                numeric.
        """
        mapper = sa_inspect(type(self))
        if column_name not in mapper.column_attrs:
            msg = "Model increments require a mapped numeric column."
            raise DatabaseQueryError(msg)
        current = sa_inspect(self).attrs[column_name].loaded_value
        if (
            current is NO_VALUE
            or isinstance(current, bool)
            or not isinstance(current, (int, float, Decimal))
        ):
            msg = "Model increments require a loaded numeric column."
            raise DatabaseQueryError(msg)
        return current

    def _delete_sync(self) -> bool:
        """Delete a persisted model synchronously and mark its state.

        Returns:
            Whether the instance had an identity to delete.
        """
        if not self.exists:
            return False
        if not _dispatch_cancellable_events((ModelDeleting(self),)):
            return False
        service = DB.resolve_service()
        with service.session(type(self).connection) as session:
            self._ensure_session_owner(service, session)
            if object_session(self) is None:
                session.add(self)
            session.delete(self)
            session.flush()

            def after_commit() -> None:
                """Record deletion and dispatch its committed event.

                A rollback discards this callback with the row removal.
                """
                remember_deleted(self)
                Event.dispatch(ModelDeleted(self))

            service.after_commit(after_commit, type(self).connection)
        return True

    async def _delete_async(self) -> bool:
        """Asynchronously delete a persisted model and record the outcome.

        Returns:
            Whether the instance had an identity to delete.
        """
        if not self.exists:
            return False
        if not await _dispatch_cancellable_events_async(
            (ModelDeleting(self),),
        ):
            return False
        service = DB.resolve_service()
        async with service.session_async(type(self).connection) as session:
            self._ensure_session_owner(service, session)
            if object_session(self) is None:
                session.add(self)
            await session.delete(self)
            await session.flush()

            async def after_commit() -> None:
                """Record deletion and await committed delete listeners.

                A rollback discards this callback with the row removal.
                """
                remember_deleted(self)
                await Event.dispatch_async(ModelDeleted(self))

            await service.after_commit_async(
                after_commit,
                type(self).connection,
            )
        return True


def _snake_case(name: str) -> str:
    """Convert a class name into conventional lowercase snake case.

    Args:
        name: Python class name.

    Returns:
        A lowercase underscore-separated name.
    """
    separated = _SNAKE_CASE_ACRONYM.sub(r"\1_\2", name)
    return _SNAKE_CASE_BOUNDARY.sub(r"\1_\2", separated).casefold()


def _current_task_id() -> int | None:
    """Return the current AnyIO task identity when async execution is active.

    Returns:
        The task identifier or ``None`` in a synchronous thread.
    """
    try:
        return anyio.get_current_task().id
    except anyio.NoEventLoopError:
        return None


def _numeric_column(
    model_type: type[Model],
    column_name: str,
) -> Column[object]:
    """Resolve a mapped SQL numeric column without reading its stale value.

    Args:
        model_type: Declaratively mapped model class.
        column_name: Mapped attribute name selected for atomic arithmetic.

    Returns:
        The SQLAlchemy column used by the model attribute.

    Raises:
        DatabaseQueryError: If the attribute is not a supported number.
    """
    mapper = sa_inspect(model_type)
    if column_name not in mapper.column_attrs:
        msg = "Model increments require a mapped numeric column."
        raise DatabaseQueryError(msg)
    attribute = mapper.column_attrs[column_name]
    column = cast("Column[object]", attribute.columns[0])
    if not isinstance(column.type, (Integer, Float, Numeric)):
        msg = "Model increments require a mapped numeric column."
        raise DatabaseQueryError(msg)
    return column


def _identity_values(
    instance: Model,
) -> tuple[tuple[Column[object], object], ...]:
    """Pair the mapped primary key columns with this model's identity.

    Args:
        instance: Persistent SQLAlchemy model instance.

    Returns:
        Mapped key columns and their identity-map values.

    Raises:
        DatabaseQueryError: If the model has no persistent identity.
    """
    state = sa_inspect(instance)
    identity = state.identity
    primary_key = state.mapper.primary_key
    if identity is None or len(identity) != len(primary_key):
        msg = "Atomic model updates require a persistent primary key."
        raise DatabaseQueryError(msg)
    return tuple(
        (cast("Column[object]", column), value)
        for column, value in zip(primary_key, identity, strict=True)
    )


def _updated_at_column(
    model_type: type[Model],
) -> Column[object] | None:
    """Resolve the configured update timestamp for an atomic row update.

    Args:
        model_type: Declaratively mapped model class.

    Returns:
        The mapped update timestamp column, if timestamping is enabled.
    """
    if not model_type.timestamps:
        return None
    name = model_type.updated_at_name
    mapper = sa_inspect(model_type)
    if name not in mapper.column_attrs:
        return None
    return cast("Column[object]", mapper.column_attrs[name].columns[0])


def _unguarded_context_is_active() -> bool:
    """Check whether a temporary guard bypass still owns this execution.

    Returns:
        Whether the current thread, task, and application scope match the
        context that entered ``Model.unguarded()``.
    """
    owner = _MASS_ASSIGNMENT_UNGUARDED.get()
    if owner is None:
        return False
    active = active_application_context()
    application = active.application if active is not None else None
    container = active.container if active is not None else None
    scope = active.scope if active is not None else None
    return (
        owner.thread_id == threading.get_ident()
        and owner.task_id == _current_task_id()
        and owner.application is application
        and owner.container is container
        and owner.scope is scope
    )


def _discard_cancelled_save(
    instance: Model,
    session: Session,
) -> None:
    """Restore rejected mapped changes before an automatic Unit of Work flush.

    SQLAlchemy's attribute history remains authoritative. Known old scalar
    values are restored as committed state. Attributes without loaded history
    are expired and refreshed through the owning Session.

    Args:
        instance: Model whose cancellable save was rejected.
        session: Synchronous SQLAlchemy session owning the operation.
    """
    state = sa_inspect(instance)
    relationship_names = set(state.mapper.relationships.keys())
    changed_names = tuple(
        name
        for name, attribute in state.attrs.items()
        if attribute.history.has_changes()
    )
    added_related = _pending_related_models(
        instance,
        session,
        changed_names,
        relationship_names,
    )

    if state.pending:
        _expunge_pending(added_related, session)
        session.expunge(instance)
        return
    if not state.persistent:
        return

    refresh_names: list[str] = []
    for name in changed_names:
        history = state.attrs[name].history
        if name in relationship_names:
            refresh_names.append(name)
        elif history.deleted:
            set_committed_value(instance, name, history.deleted[0])
        else:
            refresh_names.append(name)

    _expunge_pending(added_related, session)
    if refresh_names:
        session.expire(instance, attribute_names=refresh_names)
        session.refresh(instance, attribute_names=refresh_names)


async def _discard_cancelled_save_async(
    instance: Model,
    session: AsyncSession,
) -> None:
    """Restore rejected async ORM changes before later autoflush operations.

    Args:
        instance: Model whose cancellable save was rejected.
        session: Task-owned SQLAlchemy async session.
    """
    state = sa_inspect(instance)
    sync_session = session.sync_session
    relationship_names = set(state.mapper.relationships.keys())
    changed_names = tuple(
        name
        for name, attribute in state.attrs.items()
        if attribute.history.has_changes()
    )
    added_related = _pending_related_models(
        instance,
        sync_session,
        changed_names,
        relationship_names,
    )

    if state.pending:
        _expunge_pending(added_related, sync_session)
        sync_session.expunge(instance)
        return
    if not state.persistent:
        return

    refresh_names: list[str] = []
    for name in changed_names:
        history = state.attrs[name].history
        if name in relationship_names:
            refresh_names.append(name)
        elif history.deleted:
            set_committed_value(instance, name, history.deleted[0])
        else:
            refresh_names.append(name)

    _expunge_pending(added_related, sync_session)
    if refresh_names:
        sync_session.expire(instance, attribute_names=refresh_names)
        await session.refresh(instance, attribute_names=refresh_names)


def _pending_related_models(
    instance: Model,
    session: Session,
    changed_names: tuple[str, ...],
    relationship_names: set[str],
) -> tuple[Model, ...]:
    """Find new related models introduced by the rejected relationship edit.

    Args:
        instance: Model whose relationship change was rejected.
        session: Owning synchronous session, including the async adapter.
        changed_names: Mapped attributes with pending SQLAlchemy history.
        relationship_names: Relationship attributes mapped on the instance.

    Returns:
        Pending related Titanspan models that were cascaded into this session.
    """
    return tuple(
        value
        for name in changed_names
        if name in relationship_names
        for value in sa_inspect(instance).attrs[name].history.added
        if isinstance(value, Model)
        and object_session(value) is session
        and sa_inspect(value).pending
    )


def _expunge_pending(
    instances: tuple[Model, ...],
    session: Session,
) -> None:
    """Remove cascaded new related instances from a rejected Unit of Work.

    Args:
        instances: Related models captured from changed relationships.
        session: Synchronous SQLAlchemy session owning the Unit of Work.
    """
    for instance in instances:
        if object_session(instance) is session and sa_inspect(instance).pending:
            session.expunge(instance)


def _dispatch_cancellable_events[ModelT](
    events: Sequence[ModelEvent[ModelT]],
) -> bool:
    """Dispatch synchronous pre-persistence events in order.

    Args:
        events: Event objects whose listeners may reject the operation.

    Returns:
        Whether every event allowed persistence to continue.
    """
    for event in events:
        Event.dispatch(event)
        if event.cancelled:
            return False
    return True


async def _dispatch_cancellable_events_async[ModelT](
    events: Sequence[ModelEvent[ModelT]],
) -> bool:
    """Await pre-persistence events and check explicit cancellation.

    Args:
        events: Event objects whose sync or async listeners may reject work.

    Returns:
        Whether every event allowed persistence to continue.
    """
    for event in events:
        await Event.dispatch_async(event)
        if event.cancelled:
            return False
    return True


def _dispatch_saved_events(model: Model, created: bool) -> None:
    """Dispatch model events after its transaction successfully commits.

    Args:
        model: Model whose insert or update is durable.
        created: Whether the committed operation inserted a new row.
    """
    Event.dispatch(ModelCreated(model) if created else ModelUpdated(model))
    Event.dispatch(ModelSaved(model))


async def _dispatch_saved_events_async(
    model: Model,
    created: bool,
) -> None:
    """Await committed model events through the async dispatcher.

    Args:
        model: Model whose insert or update is durable.
        created: Whether the committed operation inserted a new row.
    """
    await Event.dispatch_async(
        ModelCreated(model) if created else ModelUpdated(model),
    )
    await Event.dispatch_async(ModelSaved(model))


def _observer_listener[ModelT: Model](
    model_type: type[ModelT],
    observer_type: type[object],
    method_name: str,
    method: object,
) -> (
    Callable[[ModelEvent[object]], object]
    | Callable[[ModelEvent[object]], Awaitable[object]]
):
    """Adapt one observer hook to the active model-event dispatcher.

    Args:
        model_type: Model class whose instances the observer accepts.
        observer_type: Trusted observer resolved for each lifecycle dispatch.
        method_name: Name of the observer hook to invoke.
        method: Class-level hook used to select sync or async dispatch.

    Returns:
        A synchronous or asynchronous event listener matching the hook.
    """
    if iscoroutinefunction(method):

        async def listen_async(event: ModelEvent[object]) -> object:
            """Invoke an async observer only for its model class.

            Args:
                event: Lifecycle event selected by the dispatcher.

            Returns:
                The observer hook result, if it returned one.
            """
            if not isinstance(event.model, model_type):
                return None
            observer = Event.active_container().make(observer_type)
            callback = cast(
                "Callable[[ModelT], Awaitable[object]]",
                getattr(observer, method_name),
            )
            result = await callback(event.model)
            if result is False:
                event.cancel()
            return result

        return listen_async

    def listen(event: ModelEvent[object]) -> object:
        """Invoke a sync observer only for its model class.

        Args:
            event: Lifecycle event selected by the dispatcher.

        Returns:
            The observer hook result, if it returned one.
        """
        if not isinstance(event.model, model_type):
            return None
        observer = Event.active_container().make(observer_type)
        callback = cast(
            "Callable[[ModelT], object]",
            getattr(observer, method_name),
        )
        result = callback(event.model)
        if result is False:
            event.cancel()
        return result

    return listen


def _pluralize(name: str) -> str:
    """Apply deterministic English plural conventions to a table stem.

    Args:
        name: Snake-case model name.

    Returns:
        A conventional plural table name; irregular nouns need an override.
    """
    if name.endswith(("s", "x", "z", "ch", "sh")):
        return f"{name}es"
    if len(name) > 1 and name.endswith("y") and name[-2] not in "aeiou":
        return f"{name[:-1]}ies"
    return f"{name}s"


def _serialize(value: object) -> object:
    """Convert supported Python values and loaded models recursively.

    Args:
        value: Loaded model field or relationship value.

    Returns:
        A JSON-compatible value that contains no SQLAlchemy internals.
    """
    if isinstance(value, Model):
        return value.to_dict()
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {str(key): _serialize(item) for key, item in mapping.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_serialize(item) for item in cast("Iterable[object]", value)]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return _serialize(value.value)
    if isinstance(value, UUID):
        return str(value)
    return value


def _creation_values(
    attributes: Mapping[str, object],
    values: Mapping[str, object] | None,
) -> dict[str, object]:
    """Merge creation values while preserving lookup attributes.

    Args:
        attributes: Values that identify the row and take precedence.
        values: Additional defaults for a newly created row.

    Returns:
        New values without mutating either caller-owned mapping.
    """
    return {**dict(values or {}), **attributes}


def _chunks[T](values: Sequence[T], size: int) -> Iterable[Sequence[T]]:
    """Yield bounded slices from a finite identifier sequence.

    Args:
        values: Caller-provided sequence that remains unmodified.
        size: Maximum values included in each SQL ``IN`` operation.

    Yields:
        Non-empty slices in their original order.
    """
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _is_unique_constraint_violation(error: BaseException) -> bool:
    """Recognize supported driver codes for duplicate-key violations.

    Args:
        error: Native transaction error with chained SQLAlchemy causes.

    Returns:
        Whether a chained IntegrityError identifies a unique constraint.
    """
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, IntegrityError):
            original = current.orig
            if isinstance(original, sqlite3.IntegrityError):
                return original.sqlite_errorcode in {
                    sqlite3.SQLITE_CONSTRAINT_UNIQUE,
                    sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY,
                }
            if (
                getattr(original, "sqlstate", None) == "23505"
                or getattr(original, "pgcode", None) == "23505"
            ):
                return True
            arguments = getattr(original, "args", ())
            if (
                isinstance(arguments, tuple)
                and arguments
                and arguments[0] == _MYSQL_DUPLICATE_ENTRY_CODE
            ):
                return True
        current = current.__cause__
    return False


def state_loaded(instance: Model, attribute: str) -> bool:
    """Check SQLAlchemy inspection state without triggering deferred loading.

    Args:
        instance: Mapped model instance.
        attribute: Mapped attribute name to inspect.

    Returns:
        Whether SQLAlchemy has loaded the mapped value.
    """
    state = sa_inspect(instance)
    return state.attrs[attribute].loaded_value is not NO_VALUE


__all__ = ["Model"]
