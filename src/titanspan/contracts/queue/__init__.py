"""Expose dependency-independent Queue and Bus service contracts.

Concrete job execution and broker integration belong to Queue.
"""

from titanspan.contracts.queue.context import JobContext
from titanspan.contracts.queue.dispatch import DispatchReceipt
from titanspan.contracts.queue.dispatcher import (
    BatchBuilder,
    BatchHandle,
    BusDispatcher,
    ChainBuilder,
    PendingDispatch,
    QueueDispatcher,
)
from titanspan.contracts.queue.middleware import (
    JobMiddleware,
    JobMiddlewareType,
    JobNext,
    SyncJobMiddleware,
    SyncJobNext,
)
from titanspan.contracts.queue.result import JobResultHandle, JobResultSnapshot

__all__ = [
    "BatchBuilder",
    "BatchHandle",
    "BusDispatcher",
    "ChainBuilder",
    "DispatchReceipt",
    "JobContext",
    "JobMiddleware",
    "JobMiddlewareType",
    "JobNext",
    "JobResultHandle",
    "JobResultSnapshot",
    "PendingDispatch",
    "QueueDispatcher",
    "SyncJobMiddleware",
    "SyncJobNext",
]
