"""Resolve application-owned storage through the active context.

Storage fakes use a context-local overlay while production disks remain owned
by the canonical FilesystemManager registration.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType
from typing import TYPE_CHECKING

from titanspan.contracts.filesystem import StorageDisk, StorageManager
from titanspan.facades.base import Facade
from titanspan.filesystem._backends import create_memory_filesystem
from titanspan.filesystem.configuration import FilesystemDiskConfiguration
from titanspan.filesystem.disk import FilesystemDisk
from titanspan.filesystem.exceptions import StorageFakeContextError
from titanspan.filesystem.fake import FilesystemFake
from titanspan.filesystem.manager import FilesystemManager

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping
    from contextvars import Token

    from titanspan.contracts.container import ServiceContainer

_ACTIVE_FAKES: ContextVar[Mapping[tuple[int, str], FilesystemFake]] = (
    ContextVar(
        "titanspan_filesystem_fakes",
        default=MappingProxyType({}),
    )
)
_FAKE_DISK = "memory"


class Storage(Facade[StorageManager]):
    """Expose named disks and test fakes from the active application.

    Production manager resolution always uses the canonical container. Fake
    selection overlays only the named disk in the current execution context.
    """

    service_contract = StorageManager

    @classmethod
    def resolve_from_container(
        cls,
        container: ServiceContainer,
    ) -> StorageManager:
        """Resolve the canonical manager contract from one app container.

        Args:
            container: Active application's service registry.

        Returns:
            The application's registered StorageManager.
        """
        return container.make(StorageManager)

    @classmethod
    def manager(cls) -> StorageManager:
        """Return the manager registered by the active application.

        Returns:
            Canonical app-owned StorageManager contract.
        """
        return cls.resolve_service()

    @classmethod
    def disk(cls, name: str | None = None) -> StorageDisk:
        """Resolve a configured disk or its active context-local fake.

        Args:
            name: Configured disk name, or ``None`` for the default disk.

        Returns:
            The selected production or fake storage disk.
        """
        manager = cls.manager()
        disk_name = manager.default_disk if name is None else name
        fake = _ACTIVE_FAKES.get().get((id(manager), disk_name))
        if fake is not None:
            return fake.disk
        return manager.disk(disk_name)

    @classmethod
    @contextmanager
    def fake(
        cls,
        name: str | None = None,
    ) -> Generator[FilesystemFake, None, None]:
        """Replace one configured disk with a private memory store.

        Args:
            name: Disk to replace, or the application default disk.

        Yields:
            The fake disk and its storage assertions.

        Notes:
            The overlay is task-local and restores any enclosing fake scope.
        """
        manager = cls.manager()
        disk_name = manager.default_disk if name is None else name
        if (
            not isinstance(manager, FilesystemManager)
            or disk_name not in manager.disk_names
        ):
            manager.disk(disk_name)
        settings = FilesystemDiskConfiguration(driver=_FAKE_DISK)
        filesystem = create_memory_filesystem(settings)
        fake_disk = FilesystemDisk(filesystem)
        fake = FilesystemFake(fake_disk)
        overlay = dict(_ACTIVE_FAKES.get())
        overlay[(id(manager), disk_name)] = fake
        token: Token[Mapping[tuple[int, str], FilesystemFake]] = (
            _ACTIVE_FAKES.set(MappingProxyType(overlay))
        )
        try:
            yield fake
        finally:
            _ACTIVE_FAKES.reset(token)

    @classmethod
    def assert_exists(cls, path: str, *, disk: str | None = None) -> None:
        """Assert a path exists in the active fake disk.

        Args:
            path: Disk-relative path to verify.
            disk: Fake disk name, defaulting to the app default.

        Raises:
            StorageFakeContextError: If the selected disk is not faked.
            AssertionError: If the path is absent.
        """
        cls._fake(disk).assert_exists(path)

    @classmethod
    def assert_missing(cls, path: str, *, disk: str | None = None) -> None:
        """Assert a path is absent from the active fake disk.

        Args:
            path: Disk-relative path to verify.
            disk: Fake disk name, defaulting to the app default.

        Raises:
            StorageFakeContextError: If the selected disk is not faked.
            AssertionError: If the path exists.
        """
        cls._fake(disk).assert_missing(path)

    @classmethod
    def assert_stored(
        cls,
        path: str,
        content: str | bytes | None = None,
        *,
        disk: str | None = None,
        encoding: str = "utf-8",
    ) -> None:
        """Assert that a file is present in the active fake disk.

        Args:
            path: Disk-relative file path.
            content: Optional expected text or bytes.
            disk: Fake disk name, defaulting to the app default.
            encoding: Encoding used for expected text content.

        Raises:
            StorageFakeContextError: If the selected disk is not faked.
            AssertionError: If content is missing or differs.
        """
        cls._fake(disk).assert_stored(path, content, encoding=encoding)

    @classmethod
    def assert_not_stored(cls, path: str, *, disk: str | None = None) -> None:
        """Assert that a file is absent from the active fake disk.

        Args:
            path: Disk-relative path.
            disk: Fake disk name, defaulting to the app default.

        Raises:
            StorageFakeContextError: If the selected disk is not faked.
            AssertionError: If the path exists.
        """
        cls._fake(disk).assert_not_stored(path)

    @classmethod
    def _fake(cls, name: str | None) -> FilesystemFake:
        """Return the fake bound to the current application and execution.

        Args:
            name: Optional configured disk name.

        Returns:
            The active fake for that named disk.

        Raises:
            StorageFakeContextError: If no matching fake scope is active.
        """
        manager = cls.manager()
        disk_name = manager.default_disk if name is None else name
        fake = _ACTIVE_FAKES.get().get((id(manager), disk_name))
        if fake is None:
            raise StorageFakeContextError(_FAKE_CONTEXT_ERROR)
        return fake


_FAKE_CONTEXT_ERROR = "Use Storage.fake() before making storage assertions."


__all__ = ["Storage"]
