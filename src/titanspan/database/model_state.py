"""Store small Database ownership facts on SQLAlchemy instrumented models.

Dirty values and persistence state stay owned by SQLAlchemy's mapper. The
adapter records only application identity and the most recent save outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import InstanceState
from sqlalchemy.orm.base import NO_VALUE

from titanspan.database.exceptions import DatabaseTransactionOwnershipError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from titanspan.contracts.database import DatabaseService

_DATABASE_OWNER = "titanspan_database_owner"
_RECENTLY_CREATED = "titanspan_recently_created"
_LAST_CHANGES = "titanspan_last_changes"
_DELETED = "titanspan_deleted"


@dataclass(frozen=True, slots=True, eq=False)
class _DatabaseOwnership:
    """Retain the stable service and connection that own one model.

    Equality uses object identity for the service. Keeping the service
    reference prevents integer object identifiers from being reused while a
    model still carries ownership metadata.
    """

    service: DatabaseService
    connection_name: str

    def __eq__(self, other: object) -> bool:
        """Compare both application service and logical connection.

        Args:
            other: Candidate ownership record.

        Returns:
            Whether both records refer to the same service object and name.
        """
        return (
            isinstance(other, _DatabaseOwnership)
            and self.service is other.service
            and self.connection_name == other.connection_name
        )

    def __hash__(self) -> int:
        """Hash the identity pair while retaining its service object.

        Returns:
            A hash consistent with identity-based equality.
        """
        return hash((id(self.service), self.connection_name))


def remember_service(
    instance: object,
    service: DatabaseService,
    connection_name: str | None = None,
) -> None:
    """Associate a model with its application service and logical connection.

    Args:
        instance: SQLAlchemy-instrumented model instance.
        service: Current application Database service.
        connection_name: Actual logical connection used for this model.
    """
    _state(instance).info[_DATABASE_OWNER] = _ownership(
        instance,
        service,
        connection_name,
    )


def require_service(
    instance: object,
    service: DatabaseService,
    connection_name: str | None = None,
) -> None:
    """Reject reuse through another app service or logical connection.

    Args:
        instance: SQLAlchemy-instrumented model instance.
        service: Current application Database service.
        connection_name: Logical connection requested by this operation.

    Raises:
        DatabaseTransactionOwnershipError: If another app or connection owns
            the model.
    """
    selected = database_ownership(instance)
    requested = _ownership(instance, service, connection_name)
    if selected is not None and selected != requested:
        msg = "The model belongs to a different app or database connection."
        raise DatabaseTransactionOwnershipError(msg)


def database_ownership(instance: object) -> _DatabaseOwnership | None:
    """Return the stored stable owner for one mapped model.

    Args:
        instance: SQLAlchemy-instrumented model instance.

    Returns:
        The application service and logical connection, if previously loaded
        or persisted through Titanspan.
    """
    selected = _state(instance).info.get(_DATABASE_OWNER)
    if isinstance(selected, _DatabaseOwnership):
        return selected
    return None


def remember_service_graph(
    instance: object,
    service: DatabaseService,
    connection_name: str | None = None,
) -> None:
    """Record ownership for one model and its already-loaded relations.

    The traversal reads SQLAlchemy's loaded attribute state and never invokes
    relationship descriptors, so ownership tagging cannot issue hidden I/O.

    Args:
        instance: Root SQLAlchemy-instrumented model.
        service: Application Database service that executed the query.
        connection_name: Actual logical connection used for the query.
    """
    selected_connection = _ownership(
        instance,
        service,
        connection_name,
    ).connection_name
    pending = [instance]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        marker = id(current)
        if marker in visited:
            continue
        visited.add(marker)
        remember_service(current, service, selected_connection)
        state = _state(current)
        for relationship in state.mapper.relationships:
            value = state.attrs[relationship.key].loaded_value
            if value is NO_VALUE:
                continue
            related_values = (
                cast("Iterable[object]", value)
                if relationship.uselist
                else (value,)
            )
            for related in related_values:
                if related is None:
                    continue
                related_state = sa_inspect(related, raiseerr=False)
                if isinstance(related_state, InstanceState):
                    pending.append(related)


def remember_save(
    instance: object,
    service: DatabaseService,
    *,
    created: bool,
    changes: dict[str, object],
) -> None:
    """Record the application service and latest successful flush outcome.

    Args:
        instance: SQLAlchemy-instrumented model instance.
        service: Current application Database service.
        created: Whether the Unit of Work inserted this model.
        changes: Instrumentation-derived values changed before the flush.
    """
    state = _state(instance)
    remember_service(instance, service)
    state.info[_RECENTLY_CREATED] = created
    state.info[_LAST_CHANGES] = changes.copy()
    state.info[_DELETED] = False


def remember_deleted(instance: object) -> None:
    """Mark a model as deleted after SQLAlchemy flushes its deletion.

    Args:
        instance: SQLAlchemy-instrumented model instance.
    """
    _state(instance).info[_DELETED] = True


def recently_created(instance: object) -> bool:
    """Report whether this instance was most recently inserted by Titanspan.

    Args:
        instance: SQLAlchemy-instrumented model instance.

    Returns:
        Whether the last model save created the database row.
    """
    return bool(_state(instance).info.get(_RECENTLY_CREATED, False))


def last_changes(instance: object) -> dict[str, object]:
    """Return a copy of the attributes changed by the last successful save.

    Args:
        instance: SQLAlchemy-instrumented model instance.

    Returns:
        A detached mapping of attribute names to persisted values.
    """
    return cast(
        "dict[str, object]",
        _state(instance).info.get(_LAST_CHANGES, {}),
    ).copy()


def was_deleted(instance: object) -> bool:
    """Report whether this instance was deleted through Titanspan.

    Args:
        instance: SQLAlchemy-instrumented model instance.

    Returns:
        Whether a successful model delete was recorded.
    """
    return bool(_state(instance).info.get(_DELETED, False))


def _state(instance: object) -> InstanceState[object]:
    """Inspect a mapped instance through SQLAlchemy's public API.

    Args:
        instance: SQLAlchemy-instrumented model instance.

    Returns:
        Instrumented state with SQLAlchemy-owned lifecycle information.
    """
    return cast("InstanceState[object]", sa_inspect(instance))


def _ownership(
    instance: object,
    service: DatabaseService,
    connection_name: str | None,
) -> _DatabaseOwnership:
    """Build an ownership record using the service's canonical name.

    Args:
        instance: Mapped model selecting a default connection when omitted.
        service: Application Database service.
        connection_name: Requested connection or ``None`` for model default.

    Returns:
        A stable service identity paired with the resolved connection name.
    """
    selected_name = connection_name
    if selected_name is None:
        selected_name = cast(
            "str | None",
            getattr(type(instance), "connection", None),
        )
    connection = service.connection(selected_name)
    return _DatabaseOwnership(service, connection.name)


__all__ = [
    "database_ownership",
    "last_changes",
    "recently_created",
    "remember_deleted",
    "remember_save",
    "remember_service",
    "remember_service_graph",
    "require_service",
    "was_deleted",
]
