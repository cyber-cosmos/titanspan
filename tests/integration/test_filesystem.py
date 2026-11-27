"""Verify Filesystem application registration and facade cohesion.

Tests resolve configured disks from real Titanspan application containers.
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import TYPE_CHECKING

import fsspec.implementations.memory as _memory  # pyright: ignore
import pytest
from fastapi import Request  # noqa: TC002 - FastAPI resolves the annotation.
from fastapi.testclient import TestClient

from titanspan import Application
from titanspan.contracts.filesystem import StorageDisk, StorageManager
from titanspan.facades import Storage
from titanspan.filesystem import (
    FilesystemDiskConfiguration,
    FilesystemManager,
    FilesystemServiceProvider,
    StorageFakeContextError,
    UnknownFilesystemDiskError,
)
from titanspan.filesystem._backends import (
    create_local_filesystem,
    create_memory_filesystem,
)

pytestmark = pytest.mark.integration
_UNEXPECTED_CUSTOM_DISK_ERROR = "Unexpected custom disk resolution"
_CLOSE_FAILED_ERROR = "Filesystem closed unexpectedly"

if TYPE_CHECKING:
    from pathlib import Path

    from titanspan.filesystem._types import FsspecFilesystem


def _application(root: Path) -> Application:
    """Build one application with a configured local disk provider.

    Args:
        root: Temporary directory trusted as the disk root.

    Returns:
        Application with native filesystem services registered.
    """
    return Application(
        config={
            "filesystem": {
                "default": "local",
                "disks": {
                    "local": {
                        "driver": "local",
                        "root": str(root),
                    },
                },
            },
        },
        service_providers=(FilesystemServiceProvider(),),
    )


class _InjectedStorageWriter:
    """Write files through an injected application storage manager.

    This helper exercises the same contract used by production services.
    """

    def __init__(self, manager: StorageManager) -> None:
        """Retain the canonical manager resolved by the app Container.

        Args:
            manager: Application-owned storage service.
        """
        self._manager = manager

    def write(self, path: str, content: str) -> bool:
        """Write content through the injected manager.

        Args:
            path: Disk-relative destination.
            content: Text content to store.

        Returns:
            Whether the selected disk accepted the write.
        """
        return self._manager.disk().put(path, content)

    _manager: StorageManager


class _StorageManagerWithoutOverrides:
    """Represent a valid custom manager without fake support.

    The optional override capability has a clear failure policy.
    """

    @property
    def default_disk(self) -> str:
        """Return the test manager's configured disk name.

        Returns:
            The configured disk identifier.
        """
        return "custom"

    def disk(self, name: str | None = None) -> StorageDisk:
        """Reject disk construction because the test must not resolve it.

        Args:
            name: Optional configured disk identifier.

        Returns:
            No value; this manager is only used to test fake policy.

        Raises:
            AssertionError: Always, because fake selection must fail first.
        """
        _ = name
        raise AssertionError(_UNEXPECTED_CUSTOM_DISK_ERROR)


class _ClosableMemoryFileSystem(
    _memory.MemoryFileSystem,  # pyright: ignore[reportUnknownBaseType]
):
    """Track manager finalization on a real fsspec memory filesystem.

    The locked fsspec release does not publish complete typing stubs.
    """

    def __init__(self, closed: list[bool]) -> None:
        """Create an isolated backend and retain close evidence.

        Args:
            closed: List updated when the manager finalizes this filesystem.
        """
        super().__init__(  # pyright: ignore[reportUnknownMemberType]
            global_store=False,
            skip_instance_cache=True,
        )
        self._closed = closed

    def close(self) -> None:
        """Record backend finalization for the lifecycle assertion.

        Returns:
            None.
        """
        self._closed.append(True)

    _closed: list[bool]


class _FailAfterFilesystemResolution:
    """Resolve a disk during provider boot, then simulate startup failure.

    The application must still finalize the backend that boot created.
    """

    def register(self, container: object) -> None:
        """Keep the provider registration phase empty.

        Args:
            container: Shared registry, unused by this test provider.
        """
        del container

    async def boot(self, manager: StorageManager) -> None:
        """Open a disk and fail after resource ownership is established.

        Args:
            manager: Canonical manager injected from the application graph.
        """
        manager.disk().put("startup.txt", "created")
        raise RuntimeError(_CLOSE_FAILED_ERROR)


def test_provider_facade_and_injected_contract_share_one_manager(
    tmp_path: Path,
) -> None:
    """Resolve one app-owned manager through injection and the facade.

    The provider reads final settings from the canonical Config repository.
    """
    application = _application(tmp_path)

    with application.context():
        manager = application.container.make(FilesystemManager)
        contract = application.container.make(StorageManager)

        assert contract is manager
        assert Storage.manager() is manager
        assert Storage.disk() is manager.disk("local")
        assert Storage.disk().put("reports/annual.txt", "verified")
        assert Storage.disk().get("reports/annual.txt") == "verified"


def test_custom_backend_closes_after_partial_application_startup() -> None:
    """Finalize a lazily created backend when a later provider fails.

    Provider cleanup must run before the Container closes its graph.
    """
    closed: list[bool] = []

    def create_filesystem(
        configuration: FilesystemDiskConfiguration,
    ) -> FsspecFilesystem:
        """Create an isolated fsspec backend with observable cleanup.

        Args:
            configuration: Configured disk settings.

        Returns:
            A real in-memory filesystem with a close observer.
        """
        _ = configuration
        return _ClosableMemoryFileSystem(
            closed,
        )  # pyright: ignore[reportReturnType]

    application = Application(
        config={
            "filesystem": {
                "default": "ephemeral",
                "disks": {
                    "ephemeral": {
                        "driver": "tracked-memory",
                        "root": "documents",
                    },
                },
            },
        },
        service_providers=(
            FilesystemServiceProvider(
                drivers={"tracked-memory": create_filesystem},
            ),
            _FailAfterFilesystemResolution(),
        ),
    )

    async def start() -> None:
        """Run startup and preserve the original provider failure.

        Raises:
            RuntimeError: The later provider's expected startup failure.
        """
        with pytest.raises(RuntimeError, match=_CLOSE_FAILED_ERROR):
            await application.startup()

    asyncio.run(start())

    assert closed == [True]


def test_shutdown_does_not_construct_an_unused_filesystem() -> None:
    """Leave unused configured backend factories lazy through shutdown.

    Provider cleanup inspects existing ownership without creating a disk.
    """
    factory_calls: list[bool] = []

    def create_filesystem(
        configuration: FilesystemDiskConfiguration,
    ) -> FsspecFilesystem:
        """Record construction before returning a real memory backend.

        Args:
            configuration: Configured disk settings.

        Returns:
            An isolated fsspec memory filesystem.
        """
        factory_calls.append(True)
        return create_memory_filesystem(configuration)

    application = Application(
        config={
            "filesystem": {
                "disks": {
                    "memory": {
                        "driver": "tracked-memory",
                        "root": "",
                    },
                },
            },
        },
        service_providers=(
            FilesystemServiceProvider(
                drivers={"tracked-memory": create_filesystem},
            ),
        ),
    )

    async def start_and_stop() -> None:
        """Start and stop an application that never opens its disk.

        Shutdown must not construct the configured backend.
        """
        await application.startup()
        await application.shutdown()

    asyncio.run(start_and_stop())

    assert factory_calls == []


def test_storage_fake_is_nested_and_context_local(tmp_path: Path) -> None:
    """Restore nested fakes and isolate parallel execution contexts.

    Each fake owns a separate fsspec memory filesystem and keeps production
    disk state outside the fake overlay.
    """
    application = _application(tmp_path)

    with application.context():
        with pytest.raises(StorageFakeContextError):
            Storage.assert_stored("missing.txt")

        with Storage.fake() as outer:
            Storage.disk().put("outer.txt", "outer")
            outer.assert_stored("outer.txt", "outer")
            Storage.assert_exists("outer.txt")
            Storage.assert_missing("missing.txt")
            with pytest.raises(AssertionError):
                Storage.assert_exists("missing.txt")
            with pytest.raises(AssertionError):
                Storage.assert_missing("outer.txt")
            with Storage.fake() as inner:
                Storage.disk().put("inner.txt", "inner")
                inner.assert_stored("inner.txt", "inner")
                inner.assert_missing("outer.txt")
            Storage.assert_stored("outer.txt", "outer")
            Storage.assert_not_stored("inner.txt")
        assert (
            not application.container.make(FilesystemManager)
            .disk()
            .exists(
                "outer.txt",
            )
        )
        with (
            pytest.raises(UnknownFilesystemDiskError),
            Storage.fake("not-configured"),
        ):
            pytest.fail("An unknown disk entered a fake scope.")

        async def run_fake(value: str) -> str:
            """Store and read one value in an independent child context.

            Args:
                value: Unique content identifying one execution.

            Returns:
                Content read from that execution's fake disk.
            """
            with Storage.fake():
                await Storage.disk().put_async("parallel.txt", value)
                return await Storage.disk().get_async("parallel.txt")

        async def run_fake_contexts() -> tuple[str, str]:
            """Run both fake scopes as sibling tasks.

            Returns:
                Content observed through each task-local fake disk.
            """
            return await asyncio.gather(
                run_fake("first"),
                run_fake("second"),
            )

        first, second = asyncio.run(run_fake_contexts())
        assert (first, second) == ("first", "second")


def test_applications_own_independent_memory_disks() -> None:
    """Keep fsspec memory stores isolated across application managers.

    The backend defaults to a process-global store, so Titanspan disables it.
    """
    configuration = {
        "filesystem": {
            "default": "memory",
            "disks": {
                "memory": {
                    "driver": "memory",
                    "root": "shared-looking-prefix",
                },
            },
        },
    }
    first = Application(
        config=configuration,
        service_providers=(FilesystemServiceProvider(),),
    )
    second = Application(
        config=configuration,
        service_providers=(FilesystemServiceProvider(),),
    )

    with first.context():
        assert Storage.disk().put("private.txt", "first")
    with second.context():
        assert not Storage.disk().exists("private.txt")


def test_storage_fake_does_not_initialize_optional_backend() -> None:
    """Allow tests to fake an optional disk without loading its adapter.

    The configured disk identity is validated without resolving its factory.
    """
    application = Application(
        config={
            "filesystem": {
                "default": "remote",
                "disks": {
                    "remote": {
                        "driver": "optional-remote",
                        "root": "bucket/prefix",
                    },
                },
            },
        },
        service_providers=(FilesystemServiceProvider(),),
    )

    with application.context(), Storage.fake() as fake:
        assert Storage.disk().put("fake.txt", "isolated")
        fake.assert_stored("fake.txt", "isolated")


def test_storage_fake_replaces_the_injected_manager_disk(
    tmp_path: Path,
) -> None:
    """Route injected disk access to the active fake without backend access.

    The production driver call count proves fake setup does not initialize
    or touch the configured disk.
    """
    production_factory_calls: list[FilesystemDiskConfiguration] = []

    def make_local_filesystem(
        configuration: FilesystemDiskConfiguration,
    ) -> FsspecFilesystem:
        """Record production disk construction and return its local backend.

        Args:
            configuration: Trusted local disk settings.

        Returns:
            The real fsspec local filesystem used by the application.
        """
        production_factory_calls.append(configuration)
        return create_local_filesystem(configuration)

    application = Application(
        config={
            "filesystem": {
                "default": "local",
                "disks": {
                    "local": {
                        "driver": "tracked-local",
                        "root": str(tmp_path),
                    },
                },
            },
        },
        service_providers=(
            FilesystemServiceProvider(
                drivers={"tracked-local": make_local_filesystem},
            ),
        ),
    )

    with application.context(), Storage.fake() as fake:
        writer = application.container.make(_InjectedStorageWriter)
        assert writer.write("through-manager.txt", "isolated")
        fake.assert_stored("through-manager.txt", "isolated")
        assert production_factory_calls == []

    assert not (tmp_path / "through-manager.txt").exists()


def test_custom_manager_without_override_capability_fails_explicitly(
    tmp_path: Path,
) -> None:
    """Require custom managers to opt in to scoped storage substitution.

    The error occurs before disk construction or fake execution.
    """
    application = _application(tmp_path)

    with (
        application.context(),
        Storage.use(_StorageManagerWithoutOverrides()),
        pytest.raises(
            StorageFakeContextError,
            match="StorageDiskOverride",
        ),
        Storage.fake(),
    ):
        pytest.fail("Unsupported storage fake was activated.")


def test_relative_disk_roots_follow_each_application_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anchor relative local disks to their owning application roots.

    Changing the ambient working directory after app construction must not
    redirect either application's storage operations.
    """
    roots = (tmp_path / "first-app", tmp_path / "second-app")
    applications = tuple(
        Application(
            base_path=root,
            config={
                "filesystem": {
                    "disks": {
                        "local": {
                            "driver": "local",
                            "root": "storage/app",
                        },
                    },
                },
            },
            service_providers=(FilesystemServiceProvider(),),
        )
        for root in roots
    )
    ambient = tmp_path / "ambient"
    ambient.mkdir()
    monkeypatch.chdir(ambient)

    for index, application in enumerate(applications):
        with application.context():
            assert Storage.disk().put(f"app-{index}.txt", str(index))

    for index, root in enumerate(roots):
        assert (root / "storage/app" / f"app-{index}.txt").read_text() == str(
            index,
        )
    assert not (ambient / "storage/app").exists()


def test_http_request_stream_writes_to_a_configured_disk(
    tmp_path: Path,
) -> None:
    """Stream an incoming ASGI request into the application storage disk.

    The route passes Starlette's async body iterator directly to Filesystem.
    """
    application = _application(tmp_path)

    @application.asgi.post("/uploads")
    async def store_upload(request: Request) -> dict[str, bool]:
        """Persist request chunks without buffering the complete body.

        Args:
            request: Incoming Starlette request handled by Titanspan ASGI.

        Returns:
            Whether the configured storage backend accepted the stream.
        """
        stored = await Storage.disk().write_stream_async(
            "uploads/generated-object.bin",
            request.stream(),
        )
        return {"stored": stored}

    disk = application.container.make(FilesystemManager).disk()
    with TestClient(application.asgi) as client:
        response = client.post(
            "/uploads",
            content=b"first part, second part",
        )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"stored": True}
    assert disk.get_bytes("uploads/generated-object.bin") == (
        b"first part, second part"
    )
