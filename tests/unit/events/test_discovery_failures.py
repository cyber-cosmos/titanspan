"""Verify discovery rejects unsafe and stale manifest inputs.

The tests use trusted real modules and temporary JSON files.
"""

from __future__ import annotations

import hashlib
import json
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import cast

import anyio
import pytest

from titanspan.events import EventDiscoveryError, NativeEventDispatcher
from titanspan.events.discovery import (
    DiscoveryEntry,
    cache_events,
    clear_event_cache,
    discover_events,
    inspect_events,
    write_event_manifest,
)

pytestmark = pytest.mark.unit
_MODULE = "tests.unit.events._discovery_fixture"
_REPLACEMENT_ERROR = "replacement failed"
_MANIFEST_TYPE_ERROR = "Expected a manifest mapping."


class ExternalEvent:
    """Identify a class outside the explicitly trusted discovery modules.

    Manifest creation rejects this selector before it writes a cache.
    """


def test_discovery_rejects_relative_and_unimportable_modules() -> None:
    """Require configured discovery names to be absolute and importable.

    Only explicitly trusted modules reach Python's import system.
    """
    with pytest.raises(EventDiscoveryError, match="absolute trusted"):
        inspect_events([".relative"])
    with pytest.raises(EventDiscoveryError, match="Unable to import"):
        inspect_events(["titanspan.missing_event_module"])


def test_listener_annotation_failure_is_actionable() -> None:
    """Reject forward references that trusted discovery cannot resolve.

    Import and annotation failures remain visible to application startup.
    """
    with pytest.raises(EventDiscoveryError, match="listener annotation"):
        inspect_events(["tests.unit.events._invalid_discovery_fixture"])


def test_manifest_rejects_each_top_level_validation_failure(
    tmp_path: Path,
) -> None:
    """Reject malformed, stale, and incompatible manifest documents.

    Each document reaches the real loader after independent JSON parsing.
    """
    path = tmp_path / "events.json"
    cache_events([_MODULE], path)
    original = json.loads(path.read_text(encoding="utf-8"))
    cases: list[tuple[object, bool]] = [
        ([], False),
        ({"version": 1, "entries": []}, False),
        ({**original, "sha256": "invalid"}, False),
        ({**original, "version": 99}, True),
        ({**original, "modules": []}, True),
        ({**original, "entries": {}}, True),
    ]

    for document, sign in cases:
        encoded = _signed_document(document) if sign else document
        path.write_text(json.dumps(encoded), encoding="utf-8")
        with pytest.raises(EventDiscoveryError, match="invalid or stale"):
            _run_discovery(path)

    path.write_text("not json", encoding="utf-8")
    with pytest.raises(EventDiscoveryError, match="invalid or stale"):
        _run_discovery(path)


def test_manifest_rejects_invalid_descriptors_and_selectors(
    tmp_path: Path,
) -> None:
    """Validate descriptor fields before resolving trusted module members.

    JSON selector names cannot import or execute unrelated Python objects.
    """
    path = tmp_path / "events.json"
    cache_events([_MODULE], path)
    cases: list[object] = [
        [7],
        [{"module": _MODULE}],
        [
            {
                "module": _MODULE,
                "qualname": "FixtureEvent",
                "method": "",
                "subscriber": False,
                "selectors": [7],
            },
        ],
        [
            {
                "module": _MODULE,
                "qualname": "FixtureEvent",
                "method": "",
                "subscriber": False,
                "selectors": [
                    {"module": "untrusted.package", "qualname": "Event"},
                ],
            },
        ],
        [
            {
                "module": _MODULE,
                "qualname": "FixtureEvent",
                "method": "",
                "subscriber": False,
                "selectors": [
                    {"module": _MODULE, "qualname": "function_listener"},
                ],
            },
        ],
        [
            {
                "module": _MODULE,
                "qualname": "FixtureEvent",
                "method": "",
                "subscriber": False,
                "selectors": [],
            },
        ],
        [
            {
                "module": _MODULE,
                "qualname": "MissingMember",
                "method": "",
                "subscriber": False,
                "selectors": [],
            },
        ],
    ]

    for entries in cases:
        document = json.loads(path.read_text(encoding="utf-8"))
        document["entries"] = entries
        path.write_text(
            json.dumps(_signed_document(document)),
            encoding="utf-8",
        )
        with pytest.raises(EventDiscoveryError, match="invalid or stale"):
            _run_discovery(path)


def test_manifest_rejects_local_members_and_untrusted_type_selectors(
    tmp_path: Path,
) -> None:
    """Reject local-only targets and selectors outside configured modules.

    Manifests resolve names only inside modules trusted by configuration.
    """
    path = tmp_path / "events.json"
    cache_events([_MODULE], path)
    document = json.loads(path.read_text(encoding="utf-8"))
    invalid_descriptor: dict[str, object] = {
        "module": _MODULE,
        "qualname": "<locals>.Listener",
        "method": "",
        "subscriber": False,
        "selectors": [],
    }
    document["entries"] = [invalid_descriptor]
    path.write_text(
        json.dumps(_signed_document(document)),
        encoding="utf-8",
    )
    with pytest.raises(EventDiscoveryError, match="invalid or stale"):
        _run_discovery(path)

    module = import_module(_MODULE)
    discovered_entry = DiscoveryEntry(
        _MODULE,
        "FixtureEvent",
        None,
        (ExternalEvent,),
    )
    with pytest.raises(EventDiscoveryError, match="trusted modules"):
        write_event_manifest(
            path,
            [_MODULE],
            [discovered_entry],
            {_MODULE: module},
        )


def test_module_hash_requires_readable_source_files(tmp_path: Path) -> None:
    """Reject trusted modules without available source bytes.

    Cache validation depends on deterministic source hashes.
    """
    missing_source = ModuleType("missing_source")
    with pytest.raises(EventDiscoveryError, match="source files"):
        write_event_manifest(
            tmp_path / "missing.json",
            ["missing_source"],
            [],
            {"missing_source": missing_source},
        )

    unreadable_source = ModuleType("unreadable_source")
    unreadable_source.__file__ = str(tmp_path / "missing.py")
    with pytest.raises(EventDiscoveryError, match="Unable to hash"):
        write_event_manifest(
            tmp_path / "unreadable.json",
            ["unreadable_source"],
            [],
            {"unreadable_source": unreadable_source},
        )


def test_cache_clear_and_write_failures_use_native_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report filesystem failures while cleaning temporary cache files.

    Atomic writes leave no temporary file after replacement fails.
    """
    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(EventDiscoveryError, match="clear the event cache"):
        clear_event_cache(directory)

    blocked_parent = tmp_path / "blocked"
    blocked_parent.write_text("file", encoding="utf-8")
    with pytest.raises(EventDiscoveryError, match="write the event cache"):
        cache_events([_MODULE], blocked_parent / "events.json")

    path = tmp_path / "atomic.json"

    def fail_replace(self: Path, target: Path) -> Path:
        """Raise as the destination when atomic replacement is attempted.

        Args:
            self: Temporary manifest path created by the writer.
            target: Requested final destination path.

        Returns:
            A Path result that the injected failure never reaches.
        """
        _ = self, target
        raise OSError(_REPLACEMENT_ERROR)

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(EventDiscoveryError, match="write the event cache"):
        cache_events([_MODULE], path)
    assert list(tmp_path.glob(".atomic.json.*.tmp")) == []


def _signed_document(document: object) -> dict[str, object]:
    """Recalculate the manifest checksum after a controlled test mutation.

    Args:
        document: Mapping-like JSON value produced by the cache writer.

    Returns:
        A shallow copy with its valid body checksum attached.
    """
    if not isinstance(document, dict):
        raise TypeError(_MANIFEST_TYPE_ERROR)
    manifest = cast("dict[str, object]", document)
    body = {key: value for key, value in manifest.items() if key != "sha256"}
    serialized = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    body["sha256"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return body


def _run_discovery(path: Path) -> None:
    """Load a cached descriptor through the public discovery operation.

    Args:
        path: Manifest being checked against the trusted module.
    """

    async def load() -> None:
        """Load this path through asynchronous listener discovery.

        The enclosing test owns the temporary manifest lifecycle.
        """
        await discover_events(
            NativeEventDispatcher(),
            [_MODULE],
            manifest_path=path,
        )

    anyio.run(load)
