"""Define errors raised by the native logging component.

These exceptions keep application code independent of backend-specific error
types and identify configuration, resolution, and delivery failures.
"""


class LoggingError(RuntimeError):
    """Base class for Titanspan logging failures.

    Raise this type when a logging operation cannot honor its configured
    behavior and a more specific public error is not available.
    """


class LogConfigurationError(LoggingError, ValueError):
    """Report invalid logging configuration before channel use.

    The manager raises this error for missing references, unsupported driver
    names, recursive stacks, and incompatible driver options.
    """


class LogChannelNotFoundError(LoggingError, KeyError):
    """Report attempts to resolve an undeclared channel.

    This error includes the unresolved channel name and never falls back to a
    different configured destination.
    """


class LogDeliveryError(LoggingError):
    """Report a failure while delivering a record to a configured driver.

    Args:
        channel: The channel whose driver failed.
        message: A concise diagnostic without record payload contents.
    """

    def __init__(self, channel: str, message: str) -> None:
        """Initialize the delivery error with a safe channel identifier.

        Args:
            channel: The channel whose driver failed.
            message: A diagnostic that does not include log context.
        """
        super().__init__(f"Log delivery failed for {channel!r}: {message}")
        self.channel = channel


class LogQueueFullError(LogDeliveryError):
    """Report bounded log-buffer saturation without losing the record.

    The exception is raised only by policies configured to reject a write.
    Drop and fallback policies instead return an explicit delivery status.
    """

    def __init__(self, channel: str, message: str) -> None:
        """Describe the saturated channel and configured failure policy.

        Args:
            channel: The channel whose background queue is full.
            message: A safe explanation that omits log payload contents.
        """
        super().__init__(channel, message)


class LogContextError(LoggingError):
    """Report facade use without an explicitly active manager.

    Bind a manager with the facade's context manager before using its
    class-level convenience methods.
    """


class LogLifecycleError(LoggingError):
    """Report logging operations attempted outside an owned lifecycle.

    Use this error for closed managers, channels, and drivers rather than
    exposing backend-specific shutdown exceptions.
    """


class LogBackendError(LoggingError):
    """Report invalid events crossing a private backend boundary.

    This error prevents internal adapter failures from being represented as
    third-party exception types in the public logging API.
    """


class LogEventError(LoggingError):
    """Report a listener failure after a record reached its destination.

    Attributes:
        channel: The channel whose event listener failed.

    The original listener exception remains available as the chained cause.
    """

    def __init__(self, channel: str, listener_error: str) -> None:
        """Describe the channel and safe exception type.

        Args:
            channel: The channel whose event listener failed.
            listener_error: The listener exception class name.
        """
        message = f"Log event listener failed for {channel!r}: {listener_error}"
        super().__init__(message)
        self.channel = channel


class InvalidLogLevelError(ValueError):
    """Report a severity value that cannot be mapped to RFC 5424.

    This is a ``ValueError`` so it remains familiar in configuration parsing.
    """


class InvalidLogContextError(TypeError):
    """Report context values that violate the native record contract.

    Context keys must be strings and values must fit bounded normalization.
    """


class LogAssertionError(AssertionError):
    """Report an unmet logging assertion in application tests.

    It remains an ``AssertionError`` for compatibility with test frameworks.
    """
