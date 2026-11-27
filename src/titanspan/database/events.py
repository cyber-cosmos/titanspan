"""Define Active Record events delivered by the native Events component.

Database dispatches mutation events through the active application's
dispatcher and keeps post-persistence events behind transaction commits.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ModelEvent[ModelT]:
    """Carry one model through a database lifecycle boundary.

    Pre-persistence listeners may call :meth:`cancel` to reject the
    operation before SQLAlchemy flushes it.
    """

    model: ModelT
    cancelled: bool = False

    def cancel(self) -> None:
        """Reject the pending operation before SQLAlchemy flushes it.

        The owning model operation returns ``False`` without writing a row.
        """
        self.cancelled = True


@dataclass(slots=True)
class ModelSaving[ModelT](ModelEvent[ModelT]):
    """Signal that a model save is about to be flushed.

    This event precedes the more specific create or update event.
    """


@dataclass(slots=True)
class ModelSaved[ModelT](ModelEvent[ModelT]):
    """Signal that a model save transaction has committed.

    This event follows the create or update event after commit.
    """


@dataclass(slots=True)
class ModelCreating[ModelT](ModelEvent[ModelT]):
    """Signal that a new model insert is about to be flushed.

    A listener can cancel the insert before the Unit of Work flushes.
    """


@dataclass(slots=True)
class ModelCreated[ModelT](ModelEvent[ModelT]):
    """Signal that a new model insert transaction has committed.

    Listeners observe only inserts whose owning transaction committed.
    """


@dataclass(slots=True)
class ModelUpdating[ModelT](ModelEvent[ModelT]):
    """Signal that a persistent model update is about to be flushed.

    A listener can cancel the update before the Unit of Work flushes.
    """


@dataclass(slots=True)
class ModelUpdated[ModelT](ModelEvent[ModelT]):
    """Signal that a model update transaction has committed.

    Listeners observe only updates whose owning transaction committed.
    """


@dataclass(slots=True)
class ModelDeleting[ModelT](ModelEvent[ModelT]):
    """Signal that a model delete is about to be flushed.

    A listener can cancel the deletion before SQLAlchemy flushes it.
    """


@dataclass(slots=True)
class ModelDeleted[ModelT](ModelEvent[ModelT]):
    """Signal that a model deletion transaction has committed.

    Listeners observe only deletions whose owning transaction committed.
    """


__all__ = [
    "ModelCreated",
    "ModelCreating",
    "ModelDeleted",
    "ModelDeleting",
    "ModelEvent",
    "ModelSaved",
    "ModelSaving",
    "ModelUpdated",
    "ModelUpdating",
]
