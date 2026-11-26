"""Verify route discovery validates configuration and trusted imports.

The cases exercise the provider-owned route loader without a second bootstrap.
"""

import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

import pytest

import titanspan.routing.discovery as discovery_module
from titanspan.config import Repository
from titanspan.routing import RouteDiscoveryError, Router
from titanspan.routing.discovery import RouteDiscovery

pytestmark = pytest.mark.unit
_REGISTRATION_FAILURE = "registration failed"


def application_endpoint() -> str:
    """Return a value for asynchronous module registration metadata.

    Returns:
        A stable route result not invoked by this configuration test.
    """
    return "async"


@pytest.mark.parametrize(
    ("settings", "error", "message"),
    [
        ({"path": 1}, TypeError, "directory path"),
        ({"modules": "application.routes"}, TypeError, "dotted Python"),
        ({"modules": ("bad-name",)}, ValueError, "dotted Python"),
        (
            {"modules": ("application.routes", "application.routes")},
            ValueError,
            "more than once",
        ),
        ({"discover": 1}, TypeError, "must be a boolean"),
    ],
)
def test_route_discovery_rejects_invalid_configuration(
    settings: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    """Reject malformed route roots, module names, and discovery flags.

    Configuration errors surface before any route module is imported.
    """
    with pytest.raises(error, match=message):
        RouteDiscovery.from_configuration(Repository({"routing": settings}))


@pytest.mark.anyio
async def test_route_discovery_skips_missing_root_when_disabled(
    tmp_path: Path,
) -> None:
    """Disable conventional imports without requiring a project route root.

    Explicit discovery remains independent from default file scanning.
    """
    policy = RouteDiscovery.from_configuration(
        Repository(
            {
                "routing": {
                    "path": str(tmp_path / "missing"),
                    "discover": False,
                },
            },
        ),
    )
    router = Router()

    await policy.register(router)

    assert router.routes.all() == ()


@pytest.mark.anyio
async def test_route_discovery_requires_existing_conventional_root(
    tmp_path: Path,
) -> None:
    """Fail clearly when conventional route discovery has no trusted root.

    The error identifies the missing configured project directory.
    """
    policy = RouteDiscovery.from_configuration(
        Repository({"routing": {"path": str(tmp_path / "missing")}}),
    )

    with pytest.raises(RouteDiscoveryError, match="does not exist"):
        await policy.register(Router())


@pytest.mark.anyio
async def test_explicit_route_module_requires_a_registration_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject imported modules that do not provide the native hook.

    The loader never scans module globals for arbitrary callables.
    """
    module_name = "titanspan_test_missing_route_hook"
    monkeypatch.setitem(sys.modules, module_name, ModuleType(module_name))
    policy = RouteDiscovery.from_configuration(
        Repository(
            {
                "routing": {
                    "discover": False,
                    "modules": (module_name,),
                },
            },
        ),
    )

    with pytest.raises(RouteDiscoveryError, match="register_routes"):
        await policy.register(Router())


@pytest.mark.anyio
async def test_explicit_route_module_wraps_registration_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve module failures as causes of a native discovery error.

    The explicit module remains the source reported to the application.
    """
    module_name = "titanspan_test_failing_route_hook"
    module = ModuleType(module_name)

    def fail_registration(router: Router) -> None:
        """Raise a fixture error from an otherwise valid registration hook.

        Args:
            router: Native application router supplied by the loader.
        """
        _ = router
        raise RuntimeError(_REGISTRATION_FAILURE)

    module.__dict__["register_routes"] = fail_registration
    monkeypatch.setitem(sys.modules, module_name, module)
    policy = RouteDiscovery.from_configuration(
        Repository(
            {
                "routing": {
                    "discover": False,
                    "modules": (module_name,),
                },
            },
        ),
    )

    with pytest.raises(
        RouteDiscoveryError,
        match="registration failed",
    ) as error:
        await policy.register(Router())

    assert isinstance(error.value.__cause__, RuntimeError)


@pytest.mark.anyio
async def test_explicit_route_module_preserves_native_discovery_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep deliberate discovery failures from being wrapped a second time.

    Module hooks can raise a native error with their own useful context.
    """
    module_name = "titanspan_test_native_route_error"
    module = ModuleType(module_name)

    def fail_registration(router: Router) -> None:
        """Raise a native discovery error from a module hook.

        Args:
            router: Native application router supplied by discovery.
        """
        _ = router
        raise RouteDiscoveryError(_REGISTRATION_FAILURE)

    module.__dict__["register_routes"] = fail_registration
    monkeypatch.setitem(sys.modules, module_name, module)
    policy = RouteDiscovery.from_configuration(
        Repository(
            {
                "routing": {
                    "discover": False,
                    "modules": (module_name,),
                },
            },
        ),
    )

    with pytest.raises(RouteDiscoveryError, match=_REGISTRATION_FAILURE):
        await policy.register(Router())


@pytest.mark.anyio
async def test_explicit_route_module_accepts_async_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Await asynchronous route registration through the startup provider.

    Async hooks share the same application-owned route catalog as sync hooks.
    """
    module_name = "titanspan_test_async_route_hook"
    module = ModuleType(module_name)

    async def register_routes(router: Router) -> None:
        """Register a route after the provider awaits this hook.

        Args:
            router: Native application router supplied by discovery.
        """
        router.get("/async-hook", application_endpoint)

    module.__dict__["register_routes"] = register_routes
    monkeypatch.setitem(sys.modules, module_name, module)
    policy = RouteDiscovery.from_configuration(
        Repository(
            {
                "routing": {
                    "discover": False,
                    "modules": (module_name,),
                },
            },
        ),
    )
    router = Router()

    await policy.register(router)

    assert router.routes.all()[0].path == "/async-hook"


@pytest.mark.anyio
async def test_conventional_route_file_reports_missing_import_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail clearly when Python cannot create a spec for a trusted route file.

    A missing loader does not leave temporary package entries behind.
    """
    route_directory = tmp_path / "routes"
    route_directory.mkdir()
    (route_directory / "web.py").write_text("VALUE = 1\n", encoding="utf-8")

    def no_spec(name: str, location: str) -> ModuleSpec | None:
        """Report that the Python import system cannot load this file.

        Args:
            name: Temporary package-qualified module name.
            location: Trusted route file location.

        Returns:
            No import specification for this test case.
        """
        _ = name, location
        return None

    monkeypatch.setattr(
        discovery_module.importlib.util,
        "spec_from_file_location",
        no_spec,
    )
    policy = RouteDiscovery.from_configuration(
        Repository({"routing": {"path": str(tmp_path)}}),
    )
    previous_names = {
        name for name in sys.modules if name.startswith("_titanspan_routes_")
    }

    with pytest.raises(RouteDiscoveryError, match="conventional route file"):
        await policy.register(Router())

    current_names = {
        name for name in sys.modules if name.startswith("_titanspan_routes_")
    }
    assert current_names == previous_names


@pytest.mark.anyio
async def test_conventional_route_file_cannot_escape_trusted_root(
    tmp_path: Path,
) -> None:
    """Reject symlinked route files that resolve outside the application root.

    Trusted import boundaries use resolved paths rather than file names.
    """
    route_directory = tmp_path / "routes"
    route_directory.mkdir()
    external_file = tmp_path.parent / f"{tmp_path.name}-outside.py"
    external_file.write_text(
        "def register_routes(router):\n"
        "    router.get('/outside', lambda: 'outside')\n",
        encoding="utf-8",
    )
    (route_directory / "web.py").symlink_to(external_file)
    policy = RouteDiscovery.from_configuration(
        Repository({"routing": {"path": str(tmp_path)}}),
    )

    with pytest.raises(RouteDiscoveryError, match="conventional route file"):
        await policy.register(Router())


@pytest.mark.anyio
async def test_conventional_route_import_error_is_wrapped_and_cleaned(
    tmp_path: Path,
) -> None:
    """Wrap module execution failures and remove its temporary namespace.

    Subsequent application startups cannot inherit partial import state.
    """
    route_directory = tmp_path / "routes"
    route_directory.mkdir()
    (route_directory / "web.py").write_text(
        "raise RuntimeError('broken route file')\n",
        encoding="utf-8",
    )
    policy = RouteDiscovery.from_configuration(
        Repository({"routing": {"path": str(tmp_path)}}),
    )
    previous_names = {
        name for name in sys.modules if name.startswith("_titanspan_routes_")
    }

    with pytest.raises(RouteDiscoveryError, match="conventional route file"):
        await policy.register(Router())

    current_names = {
        name for name in sys.modules if name.startswith("_titanspan_routes_")
    }
    assert current_names == previous_names
