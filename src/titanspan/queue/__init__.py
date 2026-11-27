"""Expose the native application Queue and job execution services.

Taskiq transports remain private infrastructure adapters.
"""

from titanspan.queue.batch import BatchHandle, BatchSnapshot, PendingBatch
from titanspan.queue.chain import PendingChain
from titanspan.queue.configuration import (
    QueueConfiguration,
    QueueConnectionConfiguration,
)
from titanspan.queue.events import (
    JobDispatched,
    JobDispatching,
    JobFailed,
    JobProcessed,
    JobProcessing,
    QueueEvent,
)
from titanspan.queue.exceptions import (
    QueueCapabilityError,
    QueueConfigurationError,
    QueueDispatchError,
    QueueError,
    QueueResultError,
    QueueResultTimeoutError,
    QueueResultUnavailableError,
    QueueSerializationError,
    UnknownJobError,
)
from titanspan.queue.job import Job, JobContext
from titanspan.queue.manager import (
    PendingDispatch,
    QueueBrokerFactory,
    QueueDispatchRecord,
    QueueFake,
    QueueFakeScope,
    QueueManager,
)
from titanspan.queue.results import QueueResultHandle
from titanspan.queue.service_provider import QueueServiceProvider

__all__ = [
    "BatchHandle",
    "BatchSnapshot",
    "Job",
    "JobContext",
    "JobDispatched",
    "JobDispatching",
    "JobFailed",
    "JobProcessed",
    "JobProcessing",
    "PendingBatch",
    "PendingChain",
    "PendingDispatch",
    "QueueBrokerFactory",
    "QueueCapabilityError",
    "QueueConfiguration",
    "QueueConfigurationError",
    "QueueConnectionConfiguration",
    "QueueDispatchError",
    "QueueDispatchRecord",
    "QueueError",
    "QueueEvent",
    "QueueFake",
    "QueueFakeScope",
    "QueueManager",
    "QueueResultError",
    "QueueResultHandle",
    "QueueResultTimeoutError",
    "QueueResultUnavailableError",
    "QueueSerializationError",
    "QueueServiceProvider",
    "UnknownJobError",
]
