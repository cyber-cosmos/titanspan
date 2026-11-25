"""Define native errors raised by configuration services.

The exception types avoid leaking implementation-specific validation errors
or configured secret values through ordinary application diagnostics.
"""


class ConfigurationError(RuntimeError):
    """Report a failure while loading or using application configuration.

    The base class provides a stable Titanspan error boundary for loaders,
    settings, cache files, and facade lifecycle failures.
    """


class ConfigValueError(TypeError):
    """Report a stored value that does not satisfy a typed accessor.

    Only the key name, expected type, and actual type are retained. The
    underlying value is never included because configuration may be secret.

    Attributes:
        key: Configuration path that failed validation.
        expected: Human-readable expected type.
        actual_type: Name of the observed Python type.
    """

    def __init__(self, key: str, expected: str, value: object) -> None:
        """Create a safe diagnostic for a type mismatch.

        Args:
            key: Configuration path being read.
            expected: Description of the expected Python type.
            value: Rejected value, retained only through its type name.
        """
        self.key = key
        self.expected = expected
        self.actual_type = type(value).__name__
        super().__init__(
            f"Configuration value for key [{key}] must be {expected}; "
            f"{self.actual_type} found."
        )


class ConfigurationLoadError(ConfigurationError):
    """Report a trusted configuration source that could not be loaded.

    Attributes:
        source: The configuration filename or source identifier.
        cause_type: Exception class name from the private parser boundary.
    """

    def __init__(self, source: str, cause_type: str) -> None:
        """Create a source diagnostic without including source contents.

        Args:
            source: Path or logical name of the failed source.
            cause_type: Name of the internal exception class.
        """
        self.source = source
        self.cause_type = cause_type
        super().__init__(
            f"Could not load configuration source [{source}] ({cause_type})."
        )


class ConfigurationCacheError(ConfigurationError):
    """Report an invalid or unsafe configuration cache operation.

    Attributes:
        path: The cache path associated with the failure.
    """

    def __init__(self, path: str, reason: str) -> None:
        """Create a diagnostic that does not expose cached values.

        Args:
            path: Cache file path.
            reason: Safe explanation of the rejected cache operation.
        """
        self.path = path
        super().__init__(f"Configuration cache [{path}]: {reason}")


class ConfigContextError(ConfigurationError):
    """Report facade access without an active application repository.

    The facade requires explicit application or test context and never
    silently creates a process-global configuration repository.
    """


class SettingsValidationError(ConfigurationError):
    """Report invalid typed settings without exposing backend error objects.

    Attributes:
        fields: Names of the settings fields that failed validation.
    """

    def __init__(self, fields: tuple[str, ...]) -> None:
        """Create a validation diagnostic containing field names only.

        Args:
            fields: Settings field names reported by validation.
        """
        self.fields = fields
        labels = ", ".join(fields) if fields else "unknown fields"
        super().__init__(f"Invalid application settings: {labels}.")


__all__ = [
    "ConfigContextError",
    "ConfigValueError",
    "ConfigurationCacheError",
    "ConfigurationError",
    "ConfigurationLoadError",
    "SettingsValidationError",
]
