"""Store small Database ownership facts on SQLAlchemy instrumented models.

Dirty values and persistence state stay owned by SQLAlchemy's mapper. The
adapter records only application identity and the most recent save outcome.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqlalchemy import inspect as sa_inspect

from titanspan.database.exceptions import DatabaseTransactionOwnershipError

if TYPE_CHECKING:
    from sqlalchemy.orm.state import InstanceState

    from titanspan.contracts.database import DatabaseService

_SERVICE_ID = "titanspan_database_service_id"
_RECENTLY_CREATED = "titanspan_recently_created"
_LAST_CHANGES = "titanspan_last_changes"
_DELETED = "titanspan_deleted"


def remember_service(instance: object, service: DatabaseService) -> None:
    """Associate a detached model with the service that loaded or saved it.

    Args:
        instance: SQLAlchemy-instrumented model instance.
        service: Current application Database service.
    """
    _state(instance).info[_SERVICE_ID] = id(service)


def require_service(instance: object, service: DatabaseService) -> None:
    """Reject a model that is being reused with another application service.

    Args:
        instance: SQLAlchemy-instrumented model instance.
        service: Current application Database service.

    Raises:
        DatabaseTransactionOwnershipError: If another app owns the model.
    """
    selected = _state(instance).info.get(_SERVICE_ID)
    if selected is not None and selected != id(service):
        msg = "The model belongs to a different application database service."
        raise DatabaseTransactionOwnershipError(msg)


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
    state.info[_SERVICE_ID] = id(service)
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


__all__ = [
    "last_changes",
    "recently_created",
    "remember_deleted",
    "remember_save",
    "remember_service",
    "require_service",
    "was_deleted",
]
