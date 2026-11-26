"""Verify Filesystem application registration and facade cohesion.

Tests resolve configured disks from real Titanspan application containers.
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi import Request  # noqa: TC002 - FastAPI resolves the annotation.
from fastapi.testclient import TestClient

from titanspan import Application
from titanspan.contracts.filesystem import StorageManager
from titanspan.facades import Storage
from titanspan.filesystem import (
    FilesystemManager,
    FilesystemServiceProvider,
    StorageFakeContextError,
    UnknownFilesystemDiskError,
)

pytestmark = pytest.mark.integration

if TYPE_CHECKING:
    from pathlib import Path


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
