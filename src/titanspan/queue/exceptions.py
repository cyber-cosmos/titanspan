"""Define actionable errors for native Queue and Bus operations.

Public errors avoid rendering job payloads, credentials, or backend details.
"""


class QueueError(RuntimeError):
    """Report a failure in native job registration or execution."""


class QueueConfigurationError(QueueError, ValueError):
    """Report invalid queue configuration or trusted driver registration."""


class QueueCapabilityError(QueueError):
    """Report a queue operation unsupported by the selected backend."""


class QueueDispatchError(QueueError):
    """Report that a job could not be safely accepted for delivery."""


class QueueSerializationError(QueueError, ValueError):
    """Report an invalid, oversized, or unsupported job message."""


class UnknownJobError(QueueSerializationError):
    """Report a message type absent from the trusted job registry."""


__all__ = [
    "QueueCapabilityError",
    "QueueConfigurationError",
    "QueueDispatchError",
    "QueueError",
    "QueueSerializationError",
    "UnknownJobError",
]
