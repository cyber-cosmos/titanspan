"""Define native Foundation errors with actionable diagnostics.

These errors describe provider discovery and application lifecycle failures.
"""


class ProviderDiscoveryError(ImportError):
    """Report a configured application provider that cannot be loaded.

    The message identifies the entry point and failure type without exposing
    provider configuration values or an implementation traceback.
    """

    def __init__(self, name: str, reason: str) -> None:
        """Create an error for one trusted provider entry point.

        Args:
            name: Entry-point name selected by the application builder.
            reason: Safe failure category or conformance detail.
        """
        self.name = name
        self.reason = reason
        super().__init__(
            f"Could not load application provider [{name}]: {reason}."
        )


class ApplicationLifecycleError(RuntimeError):
    """Report a lifecycle operation that conflicts with app state.

    Attributes:
        operation: Lifecycle operation that was rejected.
    """

    def __init__(self, operation: str, reason: str) -> None:
        """Create an application lifecycle diagnostic.

        Args:
            operation: Startup, shutdown, or registration operation.
            reason: Safe explanation of the current lifecycle state.
        """
        self.operation = operation
        super().__init__(f"Cannot {operation}: {reason}.")


__all__ = ["ApplicationLifecycleError", "ProviderDiscoveryError"]
