"""Construct supported fsspec filesystem instances.

Built-in disk factories keep fsspec ownership inside the Filesystem component.
"""

from typing import cast

from fsspec import (  # pyright: ignore[reportMissingTypeStubs]
    filesystem,  # pyright: ignore[reportUnknownVariableType]
)

from titanspan.filesystem._types import FsspecFilesystem
from titanspan.filesystem.configuration import FilesystemDiskConfiguration
from titanspan.filesystem.exceptions import FilesystemConfigurationError

_INVALID_LOCAL_OPTION_ERROR = "The local filesystem options are invalid."
_INVALID_MEMORY_OPTION_ERROR = "The memory filesystem options are invalid."


def create_local_filesystem(
    configuration: FilesystemDiskConfiguration,
) -> FsspecFilesystem:
    """Create an isolated local fsspec filesystem.

    Args:
        configuration: Named disk settings for the local backend.

    Returns:
        A new fsspec LocalFileSystem instance.

    Raises:
        FilesystemConfigurationError: If reserved fsspec options are supplied.
    """
    options = dict(configuration.options)
    if "skip_instance_cache" in options or "protocol" in options:
        raise FilesystemConfigurationError(_INVALID_LOCAL_OPTION_ERROR)
    return cast(
        "FsspecFilesystem",
        filesystem(
            "file",
            auto_mkdir=True,
            skip_instance_cache=True,
            **options,
        ),
    )


def create_memory_filesystem(
    configuration: FilesystemDiskConfiguration,
) -> FsspecFilesystem:
    """Create an isolated, non-global fsspec memory filesystem.

    Args:
        configuration: Named disk settings for the memory backend.

    Returns:
        A new fsspec MemoryFileSystem instance with its own store.

    Raises:
        FilesystemConfigurationError: If isolation options are overridden.
    """
    options = dict(configuration.options)
    if any(
        name in options
        for name in ("global_store", "skip_instance_cache", "protocol")
    ):
        raise FilesystemConfigurationError(_INVALID_MEMORY_OPTION_ERROR)
    return cast(
        "FsspecFilesystem",
        filesystem(
            "memory",
            global_store=False,
            skip_instance_cache=True,
            **options,
        ),
    )


__all__ = ["create_local_filesystem", "create_memory_filesystem"]
