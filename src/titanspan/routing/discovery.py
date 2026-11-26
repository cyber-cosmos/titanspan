"""Load trusted route modules during the native application startup phase.

Modules contribute route declarations through one explicit registration hook.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import inspect
import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import TYPE_CHECKING, cast

from titanspan.routing.exceptions import (
    DuplicateRouteError,
    RouteDiscoveryError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import ModuleType

    from titanspan.contracts.config import ConfigRepository
    from titanspan.routing.router import Router

_DEFAULT_ROUTE_FILES = ("web.py", "api.py")
_REGISTER_HOOK = "register_routes"
_INVALID_ROUTE_ROOT_ERROR = "routing.path must be a directory path."
_INVALID_MODULES_ERROR = (
    "routing.modules must contain dotted Python module names."
)
_INVALID_DISCOVERY_FLAG_ERROR = "routing.discover must be a boolean."
_MISSING_REGISTER_HOOK_ERROR = (
    "Route modules must define register_routes(router)"
)
_DUPLICATE_MODULE_ERROR = "A route module is configured more than once."
_MODULE_IMPORT_ERROR = "Unable to import configured route module"
_MODULE_REGISTRATION_ERROR = "Route module registration failed"
_ROUTE_FILE_ERROR = "Unable to load a conventional route file"
_ROUTE_ROOT_MISSING_ERROR = "The configured route root does not exist."


class RouteDiscovery:
    """Register explicit modules and conventional application route files.

    Discovery runs from a provider's startup callback, after all services are
    registered and before Foundation freezes route metadata.
    """

    def __init__(
        self,
        root: Path,
        modules: tuple[str, ...],
        *,
        conventional: bool,
    ) -> None:
        """Retain validated route discovery settings for one application.

        Args:
            root: Trusted project root containing the conventional routes dir.
            modules: Explicit import names registered in declared order.
            conventional: Whether ``routes/web.py`` and ``routes/api.py`` load.
        """
        self._root = root
        self._modules = modules
        self._conventional = conventional

    @classmethod
    def from_configuration(
        cls,
        configuration: ConfigRepository,
    ) -> RouteDiscovery:
        """Build discovery policy from the application's routing settings.

        Args:
            configuration: Canonical application configuration repository.

        Returns:
            Validated module and conventional route loading settings.

        Raises:
            TypeError: If a route setting has an unsupported value type.
            ValueError: If a module name or route root is invalid.
        """
        raw_root = configuration.get("routing.path", str(Path.cwd()))
        if not isinstance(raw_root, (str, Path)):
            raise TypeError(_INVALID_ROUTE_ROOT_ERROR)
        root = Path(raw_root).expanduser().resolve()
        raw_modules = configuration.get("routing.modules", ())
        if isinstance(raw_modules, str) or not isinstance(
            raw_modules,
            (tuple, list),
        ):
            raise TypeError(_INVALID_MODULES_ERROR)
        module_values = cast("Sequence[object]", raw_modules)
        modules = tuple(module_values)
        if any(not _valid_module_name(item) for item in modules):
            raise ValueError(_INVALID_MODULES_ERROR)
        module_names = cast("tuple[str, ...]", modules)
        if len(set(module_names)) != len(module_names):
            raise ValueError(_DUPLICATE_MODULE_ERROR)
        conventional = configuration.get("routing.discover", True)
        if not isinstance(conventional, bool):
            raise TypeError(_INVALID_DISCOVERY_FLAG_ERROR)
        return cls(root, module_names, conventional=conventional)

    async def register(self, router: Router) -> None:
        """Import and register modules in deterministic startup order.

        Args:
            router: Canonical application router receiving registrations.

        Raises:
            RouteDiscoveryError: If a module is invalid or cannot load.
            DuplicateRouteError: If route declarations conflict.
        """
        if self._conventional and not self._root.is_dir():
            raise RouteDiscoveryError(_ROUTE_ROOT_MISSING_ERROR)
        for module_name in self._modules:
            await self._register_imported(module_name, router)
        if not self._conventional:
            return
        route_directory = self._root / "routes"
        for filename in _DEFAULT_ROUTE_FILES:
            candidate = route_directory / filename
            if candidate.is_file():
                await self._register_file(candidate, router)

    async def _register_imported(
        self,
        module_name: str,
        router: Router,
    ) -> None:
        """Import an explicitly trusted module and invoke its hook.

        Args:
            module_name: Configured dotted module name.
            router: Canonical router receiving route declarations.

        Raises:
            RouteDiscoveryError: If import or registration fails.
            DuplicateRouteError: If route metadata collides.
        """
        try:
            module = importlib.import_module(module_name)
        except Exception as error:
            raise RouteDiscoveryError(
                _MODULE_IMPORT_ERROR,
                source=module_name,
            ) from error
        await _register_module(module, module_name, router)

    async def _register_file(
        self,
        candidate: Path,
        router: Router,
    ) -> None:
        """Load one conventional file inside the configured project root.

        Args:
            candidate: ``web.py`` or ``api.py`` route module path.
            router: Canonical router receiving route declarations.

        Raises:
            RouteDiscoveryError: If path resolution, import, or registration
                fails.
            DuplicateRouteError: If route metadata collides.
        """
        root = self._root.resolve()
        try:
            route_file = candidate.resolve(strict=True)
            route_file.relative_to(root)
        except (OSError, ValueError) as error:
            raise RouteDiscoveryError(_ROUTE_FILE_ERROR) from error
        prefix = _package_name(route_file.parent, router)
        _route_package(prefix, route_file.parent)
        module_name = f"{prefix}.{route_file.stem}"
        try:
            module_spec = importlib.util.spec_from_file_location(
                module_name,
                route_file,
            )
        except Exception as error:
            _remove_route_package(prefix)
            raise RouteDiscoveryError(
                _ROUTE_FILE_ERROR,
                source=route_file.name,
            ) from error
        if module_spec is None or module_spec.loader is None:
            _remove_route_package(prefix)
            raise RouteDiscoveryError(
                _ROUTE_FILE_ERROR,
                source=route_file.name,
            )
        try:
            module = importlib.util.module_from_spec(module_spec)
            sys.modules[module_name] = module
            module_spec.loader.exec_module(module)
            await _register_module(module, str(route_file), router)
        except DuplicateRouteError:
            raise
        except RouteDiscoveryError:
            raise
        except Exception as error:
            raise RouteDiscoveryError(
                _ROUTE_FILE_ERROR,
                source=route_file.name,
            ) from error
        finally:
            _remove_route_package(prefix)


async def _register_module(
    module: ModuleType,
    identity: str,
    router: Router,
) -> None:
    """Invoke one module's required sync or async route registration hook.

    Args:
        module: Imported trusted route module.
        identity: Module name or conventional relative file label.
        router: Canonical router receiving route declarations.

    Raises:
        RouteDiscoveryError: If the hook is absent or raises.
        DuplicateRouteError: If a declaration collides with another route.
    """
    callback = getattr(module, _REGISTER_HOOK, None)
    if not callable(callback):
        raise RouteDiscoveryError(
            _MISSING_REGISTER_HOOK_ERROR,
            source=identity,
        )
    try:
        result = callback(router)
        if inspect.isawaitable(result):
            await result
    except (DuplicateRouteError, RouteDiscoveryError):
        raise
    except Exception as error:
        raise RouteDiscoveryError(
            _MODULE_REGISTRATION_ERROR,
            source=identity,
        ) from error


def _route_package(name: str, directory: Path) -> ModuleType:
    """Install one temporary namespace package for relative imports.

    Args:
        name: Unique package prefix for this application and route root.
        directory: Trusted directory containing route modules.

    Returns:
        The temporary namespace package inserted into ``sys.modules``.
    """
    package_spec = ModuleSpec(name, loader=None, is_package=True)
    package_spec.submodule_search_locations = [str(directory)]
    package = importlib.util.module_from_spec(package_spec)
    sys.modules[name] = package
    return package


def _remove_route_package(name: str) -> None:
    """Remove one temporary import namespace and all loaded children.

    Args:
        name: Unique prefix installed for a trusted route directory.

    The route hook retains its own callable globals after the import namespace
    is removed, so this cleanup does not alter registered route identities.
    """
    prefix_names = tuple(
        module_name
        for module_name in sys.modules
        if module_name == name or module_name.startswith(f"{name}.")
    )
    for module_name in prefix_names:
        sys.modules.pop(module_name, None)


def _package_name(directory: Path, router: Router) -> str:
    """Return a process-unique temporary package name for one Router.

    Args:
        directory: Trusted route module directory.
        router: Application router that owns the imported module objects.

    Returns:
        Stable name for this router and root within its startup lifecycle.
    """
    identity = f"{directory}:{id(router)}".encode()
    digest = hashlib.sha256(identity).hexdigest()[:16]
    return f"_titanspan_routes_{digest}"


def _valid_module_name(value: object) -> bool:
    """Check one configured dotted module path without importing it.

    Args:
        value: Untrusted configuration entry.

    Returns:
        True for a non-empty dotted sequence of Python identifiers.
    """
    return isinstance(value, str) and all(
        part.isidentifier() for part in value.split(".")
    )


__all__ = ["RouteDiscovery"]
