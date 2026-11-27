"""Define actionable errors for native Queue and Bus operations.

Public errors avoid rendering job payloads, credentials, or backend details.
"""


class QueueError(RuntimeError):
    """Report a failure in native job registration or execution.
    """  # fmt: skip


class QueueConfigurationError(QueueError, ValueError):
    """Report invalid queue configuration or trusted driver registration.
    """  # fmt: skip


class QueueCapabilityError(QueueError):
    """Report a queue operation unsupported by the selected backend.
    """  # fmt: skip


class QueueDispatchError(QueueError):
    """Report that a job could not be safely accepted for delivery.
    """  # fmt: skip


class QueueSerializationError(QueueError, ValueError):
    """Report an invalid, oversized, or unsupported job message.
    """  # fmt: skip


class UnknownJobError(QueueSerializationError):
    """Report a message type absent from the trusted job registry.
    """  # fmt: skip


class QueueResultError(QueueError):
    """Report invalid Queue result access or timing options.
    """  # fmt: skip


class QueueResultUnavailableError(QueueResultError):
    """Report a pending, expired, or missing retained result.
    """  # fmt: skip


class QueueResultTimeoutError(QueueResultError, TimeoutError):
    """Report that a job result did not become ready before its deadline.
    """  # fmt: skip


__all__ = [
    "QueueCapabilityError",
    "QueueConfigurationError",
    "QueueDispatchError",
    "QueueError",
    "QueueResultError",
    "QueueResultTimeoutError",
    "QueueResultUnavailableError",
    "QueueSerializationError",
    "UnknownJobError",
]
