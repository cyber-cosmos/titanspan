"""Verify trusted discovery and safe JSON manifest behavior.

The enclosing test observes this target through the framework.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, cast

import pytest
from tests.unit.events._discovery_fixture import (
    FixtureEvent,
    FixtureUpdated,
)

from titanspan.events import NativeEventDispatcher
from titanspan.events.discovery import (
    cache_events,
    clear_event_cache,
    discover_events,
    inspect_events,
)
from titanspan.events.exceptions import EventDiscoveryError

if TYPE_CHECKING:
    from pathlib import Path

_MODULE = "tests.unit.events._discovery_fixture"
_EXPECTED_ENTRIES = 8

pytestmark = pytest.mark.unit


def test_inspection_finds_decorated_functions_classes_and_subscribers() -> None:
    """Return stable descriptors without registering process-global state.

    The assertions verify discovery and cache behavior with real modules.
    """
    first = inspect_events([_MODULE])
    second = inspect_events([_MODULE])

    assert first == second
    assert {entry.qualname for entry in first} == {
        "AnnotatedListener",
        "ClassListener",
        "DeclaredClassListener",
        "FixtureSubscriber",
        "MethodShapeListener",
        "UnionListener",
        "function_listener",
        "named_listener",
    }
    assert sum(entry.is_subscriber for entry in first) == 1


@pytest.mark.anyio
async def test_discovery_registers_once_and_uses_union_annotations() -> None:
    """Register deterministic handlers and avoid duplicate scans.

    The assertions verify discovery and cache behavior with real modules.
    """
    dispatcher = NativeEventDispatcher()

    await discover_events(dispatcher, [_MODULE])
    await discover_events(dispatcher, [_MODULE])

    responses = dispatcher.dispatch(FixtureEvent("value"))

    assert responses == [
        "annotated:value",
        "class:value",
        "declared:value",
        "subscriber:value",
        "union:value",
        "function:value",
    ]
    assert dispatcher.dispatch(FixtureUpdated("static")) == [
        "static:static",
        "union:static",
    ]
    assert await dispatcher.dispatch_async(
        "workflow.completed",
        "named",
    ) == ["workflow.completed:named"]


def test_json_manifest_round_trips_and_clears(tmp_path: Path) -> None:
    """Use safe metadata manifests without serializing Python objects.

    The assertions verify discovery and cache behavior with real modules.
    """
    path = tmp_path / "event-manifest.json"

    assert cache_events([_MODULE], path) == path
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["version"] == 1
    assert "pickle" not in path.read_text(encoding="utf-8")

    clear_event_cache(path)

    assert not path.exists()


@pytest.mark.anyio
async def test_manifest_loads_only_current_trusted_metadata(
    tmp_path: Path,
) -> None:
    """Load a validated manifest through its configured module set.

    The assertions verify discovery and cache behavior with real modules.
    """
    path = tmp_path / "events.json"
    cache_events([_MODULE], path)
    dispatcher = NativeEventDispatcher()

    entries = await discover_events(
        dispatcher,
        [_MODULE],
        manifest_path=path,
    )

    assert len(entries) == _EXPECTED_ENTRIES
    assert dispatcher.dispatch(FixtureEvent("cached")) == [
        "annotated:cached",
        "class:cached",
        "declared:cached",
        "subscriber:cached",
        "union:cached",
        "function:cached",
    ]


@pytest.mark.anyio
async def test_malformed_manifest_fails_closed(tmp_path: Path) -> None:
    """Reject corrupted cache data instead of executing serialized objects.

    The assertions verify discovery and cache behavior with real modules.
    """
    path = tmp_path / "events.json"
    cache_events([_MODULE], path)
    path.write_text('{"version": 1, "entries": []}', encoding="utf-8")

    with pytest.raises(EventDiscoveryError, match="invalid or stale"):
        await discover_events(
            NativeEventDispatcher(),
            [_MODULE],
            manifest_path=path,
        )


@pytest.mark.anyio
async def test_stale_module_hash_fails_closed(tmp_path: Path) -> None:
    """Reject cached listener metadata after its source digest changes.

    The assertions verify discovery and cache behavior with real modules.
    """
    path = tmp_path / "events.json"
    cache_events([_MODULE], path)
    _change_source_digest(path)

    with pytest.raises(EventDiscoveryError, match="invalid or stale"):
        await discover_events(
            NativeEventDispatcher(),
            [_MODULE],
            manifest_path=path,
        )


def _change_source_digest(path: Path) -> None:
    """Resign a manifest after changing its trusted-module source digest.

    Args:
        path: Existing manifest changed only for stale-source verification.
    """
    document = cast(
        "dict[str, object]",
        json.loads(path.read_text(encoding="utf-8")),
    )
    modules = cast("list[dict[str, str]]", document["modules"])
    modules[0]["sha256"] = "0" * 64
    body = {key: value for key, value in document.items() if key != "sha256"}
    serialized = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    document["sha256"] = hashlib.sha256(
        serialized.encode("utf-8"),
    ).hexdigest()
    path.write_text(json.dumps(document), encoding="utf-8")
