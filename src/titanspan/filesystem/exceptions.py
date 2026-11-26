"""Define native errors for storage configuration and disk selection.

Operational failures preserve standard ``OSError`` subclasses from the
selected backend whenever possible.
"""


class FilesystemError(Exception):
    """Report a filesystem component error without backend-specific details.

    The original backend exception remains available through exception
    chaining when the component adds context.
    """


class FilesystemConfigurationError(FilesystemError, ValueError):
    """Report invalid filesystem configuration or custom driver settings.

    Configuration failures identify the invalid setting without echoing
    unrelated application configuration values.
    """


class FilesystemDiskError(FilesystemError):
    """Report an unknown disk, driver, or invalid registration operation.

    The error avoids exposing backend credentials or configuration values.
    """


class UnknownFilesystemDiskError(FilesystemDiskError, KeyError):
    """Report a disk name that is not registered by the active manager.

    The unknown name is available through the public ``disk_name`` field.
    """

    def __init__(self, disk_name: str) -> None:
        """Retain the missing disk name and build a safe error message.

        Args:
            disk_name: Name requested from the application-owned manager.
        """
        self.disk_name = disk_name
        message = f"Filesystem disk {disk_name!r} is not configured."
        super().__init__(message)


class UnsafeStoragePathError(FilesystemError, ValueError):
    """Report a path that escapes or violates a configured disk root.

    Invalid input is never suppressed by a disk's operation error policy.
    """


class StorageFakeContextError(FilesystemError, RuntimeError):
    """Report a storage assertion requested outside an active fake context.

    The exception message contains no path content or stored file bytes.
    """


__all__ = [
    "FilesystemConfigurationError",
    "FilesystemDiskError",
    "FilesystemError",
    "StorageFakeContextError",
    "UnknownFilesystemDiskError",
    "UnsafeStoragePathError",
]
