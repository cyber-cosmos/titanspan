"""Verify persistent route metadata caches reject unsafe and stale entries.

The cache stores JSON inspection records, never live routes or callables.
"""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from titanspan.config import Repository
from titanspan.contracts.http import (
    HttpRequest,
    HttpResponse,
    MiddlewareDeclaration,
    RequestHandler,
)
from titanspan.routing import RouteCacheError, Router
from titanspan.routing.route_cache import (
    RouteCache,
    StaleRouteCacheError,
    UnsupportedRouteCacheError,
)

pytestmark = pytest.mark.unit
_WRITE_FAILURE = "replacement failed"


def cache_endpoint() -> dict[str, str]:
    """Provide one stable module-level action identity for cache metadata.

    Returns:
        A route body not invoked by cache inspection.
    """
    return {"status": "ok"}


class CacheController:
    """Represent a stable controller identity for route metadata.

    Instances are not created while the cache inspects this declaration.
    """

    def show(self) -> str:
        """Return a stable action value.

        Returns:
            A value that cache inspection never invokes.
        """
        return "show"


class CacheMiddleware:
    """Provide a class identity for cached route middleware metadata.

    The cache records its class path and never creates an instance.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Forward the request through the native HTTP middleware contract.

        Args:
            request: Active request contract.
            next_handler: Remaining handler in the middleware chain.

        Returns:
            The downstream response.
        """
        return await next_handler(request)


def _cache_router() -> Router:
    """Create a router with one stable action for cache format tests.

    Returns:
        An unfrozen Router with an importable endpoint.
    """
    router = Router()
    router.get("/health", cache_endpoint).name("health")
    return router


def test_route_cache_round_trips_metadata_and_preserves_action_identity(
    tmp_path: Path,
) -> None:
    """Read a safe metadata snapshot after writing the canonical catalog.

    The cached record retains registration order and controller identity.
    """
    router = _cache_router()
    cache = RouteCache(tmp_path / "routes.json")

    cache.write(router)
    entries = cache.read(router)

    assert len(entries) == 1
    assert entries[0].path == "/health"
    assert entries[0].methods == ("GET",)
    assert entries[0].name == "health"
    assert entries[0].action == (
        f"callable:{cache_endpoint.__module__}.{cache_endpoint.__qualname__}"
    )


def test_route_cache_clear_is_idempotent(tmp_path: Path) -> None:
    """Remove an existing cache and accept a missing cache file.

    Clearing metadata does not mutate the canonical route collection.
    """
    router = _cache_router()
    cache_path = tmp_path / "routes.json"
    cache = RouteCache(cache_path)
    cache.write(router)

    cache.clear()
    cache.clear()

    assert not cache_path.exists()
    assert router.routes.all()[0].path == "/health"


def test_route_cache_rejects_metadata_changed_after_write(
    tmp_path: Path,
) -> None:
    """Fail clearly when the current catalog no longer matches its snapshot.

    Adding a route invalidates the cache without changing route identities.
    """
    router = _cache_router()
    cache = RouteCache(tmp_path / "routes.json")
    cache.write(router)
    router.get("/ready", cache_endpoint).name("ready")

    with pytest.raises(StaleRouteCacheError, match="stale"):
        cache.read(router)


def test_route_cache_refuses_live_local_callable_identity(
    tmp_path: Path,
) -> None:
    """Reject closures instead of serializing a nonportable live action.

    Unsupported handlers leave no cache file behind.
    """
    router = Router()

    def local_endpoint() -> str:
        """Return a nested callable value that cannot be imported safely.

        RouteCache must reject its nonportable local identity.
        """
        return "local"

    router.get("/local", local_endpoint)
    cache_path = tmp_path / "routes.json"
    cache = RouteCache(cache_path)

    with pytest.raises(UnsupportedRouteCacheError, match="stable identity"):
        cache.write(router)

    assert not cache_path.exists()


def test_route_cache_freezes_nested_json_metadata(tmp_path: Path) -> None:
    """Keep mutable nested defaults immutable in cache records.

    JSON-safe defaults and middleware remain useful to inspection callers.
    """
    router = Router()
    router.get("/items/{item}", cache_endpoint).defaults(
        {"item": {"keys": [1, "two"]}},
    ).middleware(
        (
            "auth",
            CacheMiddleware,
            MiddlewareDeclaration("policy", ("staff", "download")),
        ),
    ).domain("api.example.test")
    cache = RouteCache(tmp_path / "routes.json")

    cache.write(router)
    entry = cache.read(router)[0]

    assert entry.middleware == (
        "alias:auth",
        f"middleware:{CacheMiddleware.__module__}.CacheMiddleware",
        "alias:policy;parameter_count=2",
    )
    cached_text = (tmp_path / "routes.json").read_text(encoding="utf-8")
    assert "staff" not in cached_text
    assert "download" not in cached_text
    assert entry.domain == "api.example.test"
    item_default = entry.defaults["item"]
    assert isinstance(item_default, Mapping)
    assert item_default["keys"] == (1, "two")


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ([], "format is unsupported"),
        ({"version": 2}, "format is unsupported"),
        ({"version": 1}, "could not be read"),
        ({"version": 1, "routes": {}}, "could not be read"),
        ({"version": 1, "routes": [None]}, "could not be read"),
    ],
)
def test_route_cache_rejects_malformed_json_metadata(
    tmp_path: Path,
    document: object,
    message: str,
) -> None:
    """Reject unsupported roots, versions, and route entry shapes.

    Cache contents are untrusted and never construct live routing objects.
    """
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(RouteCacheError, match=message):
        RouteCache(path).read(_cache_router())


@pytest.mark.parametrize("contents", [None, "{"], ids=["missing", "invalid"])
def test_route_cache_reports_missing_or_invalid_files(
    tmp_path: Path,
    contents: str | None,
) -> None:
    """Convert missing files and invalid JSON into the cache contract error.

    File failures do not leak JSON parser or filesystem details.
    """
    path = tmp_path / "routes.json"
    if contents is not None:
        path.write_text(contents, encoding="utf-8")

    with pytest.raises(RouteCacheError, match="could not be read"):
        RouteCache(path).read(_cache_router())


def test_route_cache_rejects_a_stale_fingerprint(tmp_path: Path) -> None:
    """Detect stale metadata even when entries are otherwise well formed.

    The live catalog remains authoritative over the cache fingerprint.
    """
    path = tmp_path / "routes.json"
    path.write_text(
        json.dumps({"version": 1, "fingerprint": "wrong", "routes": []}),
        encoding="utf-8",
    )

    with pytest.raises(StaleRouteCacheError, match="stale"):
        RouteCache(path).read(_cache_router())


def test_route_cache_wraps_write_failures_and_removes_temporary_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translate failed atomic replacement and clean up its temporary file.

    The target catalog remains intact when a filesystem operation fails.
    """
    router = _cache_router()
    cache_path = tmp_path / "routes.json"

    def fail_replace(path: Path, target: Path) -> Path:
        """Raise the filesystem error exercised by the cache boundary.

        Args:
            path: Temporary file selected for replacement.
            target: Final metadata location.

        Raises:
            OSError: Replacement is unavailable in this fixture.
        """
        _ = path, target
        raise OSError(_WRITE_FAILURE)

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(RouteCacheError, match="could not be written"):
        RouteCache(cache_path).write(router)

    assert not cache_path.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_route_cache_wraps_parent_directory_creation_failures(
    tmp_path: Path,
) -> None:
    """Translate an invalid cache parent into the routing cache error.

    Callers receive one stable error type for every filesystem write failure.
    """
    parent = tmp_path / "occupied"
    parent.write_text("not a directory", encoding="utf-8")

    with pytest.raises(RouteCacheError, match="could not be written"):
        RouteCache(parent / "routes.json").write(_cache_router())


@pytest.mark.parametrize(
    "value",
    [float("inf"), {1: "non-string key"}, object()],
    ids=["infinite", "key", "opaque"],
)
def test_route_cache_rejects_non_json_defaults(
    tmp_path: Path,
    value: object,
) -> None:
    """Reject defaults that JSON cannot represent without custom encoders.

    The cache never guesses how application objects should be serialized.
    """
    router = Router()
    router.get("/items/{item}", cache_endpoint).defaults({"item": value})

    with pytest.raises(UnsupportedRouteCacheError, match="JSON-safe"):
        RouteCache(tmp_path / "routes.json").write(router)


def test_route_cache_records_controller_action_identity(
    tmp_path: Path,
) -> None:
    """Record controller and controller-method actions without instances.

    The identities are stable and contain no serialized controller object.
    """
    router = Router()
    router.get("/controller", CacheController)
    router.get("/method", (CacheController, "show"))
    entries = RouteCache(tmp_path / "routes.json").write(router)

    assert entries is None
    cached = RouteCache(tmp_path / "routes.json").read(router)
    assert cached[0].action == (
        f"controller:{CacheController.__module__}.CacheController.__call__"
    )
    assert cached[1].action == (
        f"controller:{CacheController.__module__}.CacheController.show"
    )


def test_route_cache_rejects_stateful_and_local_controller_actions() -> None:
    """Reject bound instances and controller types local to one call.

    Their identities cannot safely refer to importable application code.
    """
    bound_router = Router()
    bound_router.get("/bound", CacheController().show)
    with pytest.raises(UnsupportedRouteCacheError):
        RouteCache(Path("unused.json")).write(bound_router)

    class LocalController:
        """Represent a controller that cannot be imported by module path.

        The class metadata is intentionally local to this test function.
        """

    local_router = Router()
    local_router.get("/local-controller", LocalController)
    with pytest.raises(UnsupportedRouteCacheError):
        RouteCache(Path("unused.json")).write(local_router)


def test_route_cache_reads_json_with_configuration_defaults(
    tmp_path: Path,
) -> None:
    """Exercise the canonical JSON configuration values in one cache read.

    Nested dictionaries and arrays become immutable cache metadata.
    """
    configuration = Repository({"defaults": {"item": ["one", "two"]}})
    router = Router()
    router.get("/items/{item}", cache_endpoint).defaults(
        {"item": configuration.get("defaults")},
    )
    cache = RouteCache(tmp_path / "routes.json")

    cache.write(router)
    entry = cache.read(router)[0]

    item_default = entry.defaults["item"]
    assert isinstance(item_default, Mapping)
    assert item_default["item"] == ("one", "two")
