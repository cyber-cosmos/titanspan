"""Provide application lifecycle helpers for real framework tests.

The helpers compose the production Application and existing ASGI clients.
"""

from __future__ import annotations

from contextlib import AsyncExitStack, ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

import anyio

from titanspan.foundation import Application
from titanspan.testing._backends.asgi import (
    AsyncTestClient,
    SyncTestClient,
    create_async_client,
    create_sync_client,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from types import TracebackType
    from typing import Self

    from titanspan.config import Settings
    from titanspan.contracts.foundation import ServiceProvider
    from titanspan.contracts.http import HttpMiddleware

from titanspan.contracts.config import ConfigRepository
from titanspan.contracts.container import (
    AsyncServiceContainer,
    ServiceContainer,
    ServiceRegistry,
)
from titanspan.contracts.foundation import ApplicationPaths

_TEST_ROOT_PREFIX = "titanspan-test-"
_ROUTES_DIRECTORY = "routes"
_CONTEXT_REENTRY_ERROR = "An application test context cannot be re-entered."
_CONTEXT_INACTIVE_ERROR = "Enter the application test context first."
_COMPOSITION_SERVICE_ERROR = (
    "Replace configuration through config= and keep application path and "
    "container contracts owned by Foundation."
)
_COMPOSITION_SERVICES = frozenset(
    {
        ConfigRepository,
        ApplicationPaths,
        AsyncServiceContainer,
        ServiceContainer,
        ServiceRegistry,
    }
)


class _ServiceReplacementProvider:
    """Register per-test service instances in the application graph.

    Foundation owns these values through the normal provider lifecycle.
    """

    def __init__(self, replacements: Mapping[type[object], object]) -> None:
        """Snapshot the replacements before Container composition.

        Args:
            replacements: Contract keys mapped to test-owned values.
        """
        self._replacements = dict(replacements)

    def register(self, container: ServiceRegistry) -> None:
        """Bind test values through the canonical application registry.

        Args:
            container: Service registry composed by Foundation.
        """
        for service, value in self._replacements.items():
            container.instance(service, value)

    _replacements: dict[type[object], object]


class _ApplicationTestState:
    """Create one isolated root and its production Application instance.

    Temporary resources belong to this state until context exit.
    """

    def __init__(
        self,
        *,
        base_path: str | Path | None,
        config: Mapping[str, object] | None,
        settings: Settings | None,
        service_providers: Sequence[ServiceProvider],
        http_middleware: Sequence[type[HttpMiddleware]],
        replacements: Mapping[type[object], object],
    ) -> None:
        """Build the selected application and retain owned temporary storage.

        Args:
            base_path: Explicit root or None for an isolated temporary root.
            config: Application configuration overrides.
            settings: Optional typed configuration settings.
            service_providers: Native application providers.
            http_middleware: Native application middleware classes.
            replacements: Service values registered for this test application.
        """
        if _COMPOSITION_SERVICES.intersection(replacements):
            raise ValueError(_COMPOSITION_SERVICE_ERROR)
        self._temporary_root = (
            TemporaryDirectory(prefix=_TEST_ROOT_PREFIX)
            if base_path is None
            else None
        )
        if base_path is None:
            temporary_root = self._temporary_root
            if temporary_root is None:
                raise RuntimeError(_CONTEXT_INACTIVE_ERROR)
            selected_path = Path(temporary_root.name)
        else:
            selected_path = Path(base_path)
        selected_path = selected_path.resolve()
        self.base_path = selected_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        (self.base_path / _ROUTES_DIRECTORY).mkdir(exist_ok=True)
        providers = tuple(service_providers)
        if replacements:
            providers = (*providers, _ServiceReplacementProvider(replacements))
        builder = (
            Application.builder()
            .with_base_path(self.base_path)
            .discover_providers()
        )
        if config is not None:
            builder.with_config(config)
        if settings is not None:
            builder.with_settings(settings)
        if http_middleware:
            builder.with_http_middleware(*http_middleware)
        for provider in providers:
            builder.with_service_provider(provider)
        self.application = builder.build()

    def cleanup(self) -> None:
        """Remove a temporary root owned by this test context.

        Explicit application roots remain under caller ownership.
        """
        if self._temporary_root is not None:
            self._temporary_root.cleanup()
            self._temporary_root = None

    base_path: Path
    application: Application
    _temporary_root: TemporaryDirectory[str] | None


class ApplicationTest:
    """Run a real Application through the in-process ASGI test client.

    The ASGI client owns application lifespan. Service replacements register
    through the production Container before its graph is composed.
    """

    def __init__(
        self,
        *,
        base_path: str | Path | None = None,
        config: Mapping[str, object] | None = None,
        settings: Settings | None = None,
        service_providers: Sequence[ServiceProvider] = (),
        http_middleware: Sequence[type[HttpMiddleware]] = (),
        replacements: Mapping[type[object], object] | None = None,
    ) -> None:
        """Create a test Application without starting its lifecycle.

        Args:
            base_path: Explicit application root or an owned temporary root.
            config: Application values layered over loaded configuration.
            settings: Optional typed settings for environment isolation.
            service_providers: Providers registered through Foundation.
            http_middleware: Middleware classes registered with HTTP.
            replacements: Application-owned service values for this test.
        """
        self._state = _ApplicationTestState(
            base_path=base_path,
            config=config,
            settings=settings,
            service_providers=service_providers,
            http_middleware=http_middleware,
            replacements={} if replacements is None else replacements,
        )
        self._stack: ExitStack | None = None
        self._client: SyncTestClient | None = None
        self._finished = False

    def __enter__(self) -> Self:
        """Start the application and expose its in-process client.

        Returns:
            This context with client ready to issue requests.

        Raises:
            RuntimeError: If the test context is re-entered.
        """
        if self._finished or self._stack is not None:
            raise RuntimeError(_CONTEXT_REENTRY_ERROR)
        stack = ExitStack()
        stack.callback(self._state.cleanup)
        try:
            client = create_sync_client(self.application.asgi)
            stack.enter_context(client)
        except BaseException:
            stack.close()
            self._finished = True
            raise
        self._stack = stack
        self._client = client
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """Close the client, application, overrides, and owned root.

        Args:
            exception_type: Active exception class, if any.
            exception: Active exception instance, if any.
            traceback: Active traceback associated with the exception.

        Returns:
            Whether the context handled the active exception.

        Raises:
            RuntimeError: If the context was not entered.
        """
        stack = self._stack
        if stack is None:
            raise RuntimeError(_CONTEXT_INACTIVE_ERROR)
        self._stack = None
        self._client = None
        self._finished = True
        return stack.__exit__(exception_type, exception, traceback)

    @property
    def application(self) -> Application:
        """Return the production Application before or during the context.

        Returns:
            The application composed by the native Foundation component.
        """
        return self._state.application

    @property
    def client(self) -> SyncTestClient:
        """Return the active synchronous ASGI client.

        Raises:
            RuntimeError: If the application test context is inactive.
        """
        client = self._client
        if client is None:
            raise RuntimeError(_CONTEXT_INACTIVE_ERROR)
        return client

    @property
    def base_path(self) -> Path:
        """Return the effective root selected for this test application.

        Returns:
            The resolved temporary or explicit application path.
        """
        return self._state.base_path

    _state: _ApplicationTestState
    _stack: ExitStack | None
    _client: SyncTestClient | None
    _finished: bool


class AsyncApplicationTest:
    """Run a real Application through the asynchronous ASGI transport.

    Foundation startup and shutdown remain explicit. ASGI requests create
    their own application and request contexts through normal middleware.
    """

    def __init__(
        self,
        *,
        base_path: str | Path | None = None,
        config: Mapping[str, object] | None = None,
        settings: Settings | None = None,
        service_providers: Sequence[ServiceProvider] = (),
        http_middleware: Sequence[type[HttpMiddleware]] = (),
        replacements: Mapping[type[object], object] | None = None,
    ) -> None:
        """Create an asynchronous test Application.

        Args:
            base_path: Explicit application root or an owned temporary root.
            config: Application values layered over loaded configuration.
            settings: Optional typed settings for environment isolation.
            service_providers: Providers registered through Foundation.
            http_middleware: Middleware classes registered with HTTP.
            replacements: Application-owned service values for this test.
        """
        self._state = _ApplicationTestState(
            base_path=base_path,
            config=config,
            settings=settings,
            service_providers=service_providers,
            http_middleware=http_middleware,
            replacements={} if replacements is None else replacements,
        )
        self._stack: AsyncExitStack | None = None
        self._client: AsyncTestClient | None = None
        self._finished = False

    async def __aenter__(self) -> Self:
        """Start the application and expose its asynchronous ASGI client.

        Returns:
            This context with client ready to issue requests.

        Raises:
            RuntimeError: If the test context is re-entered.
        """
        if self._finished or self._stack is not None:
            raise RuntimeError(_CONTEXT_REENTRY_ERROR)
        stack = AsyncExitStack()
        stack.callback(self._state.cleanup)
        try:
            await self.application.startup()
            stack.push_async_callback(self.application.shutdown)
            client = create_async_client(self.application.asgi)
            await stack.enter_async_context(client)
        except BaseException:
            with anyio.CancelScope(shield=True):
                await stack.aclose()
            self._finished = True
            raise
        self._stack = stack
        self._client = client
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """Close the client, application, overrides, and owned root.

        Args:
            exception_type: Active exception class, if any.
            exception: Active exception instance, if any.
            traceback: Active traceback associated with the exception.

        Returns:
            Whether the context handled the active exception.

        Raises:
            RuntimeError: If the context was not entered.
        """
        stack = self._stack
        if stack is None:
            raise RuntimeError(_CONTEXT_INACTIVE_ERROR)
        self._stack = None
        self._client = None
        self._finished = True
        with anyio.CancelScope(shield=True):
            return await stack.__aexit__(exception_type, exception, traceback)

    @property
    def application(self) -> Application:
        """Return the production Application before or during the context.

        Returns:
            The application composed by the native Foundation component.
        """
        return self._state.application

    @property
    def client(self) -> AsyncTestClient:
        """Return the active asynchronous ASGI client.

        Raises:
            RuntimeError: If the application test context is inactive.
        """
        client = self._client
        if client is None:
            raise RuntimeError(_CONTEXT_INACTIVE_ERROR)
        return client

    @property
    def base_path(self) -> Path:
        """Return the effective root selected for this test application.

        Returns:
            The resolved temporary or explicit application path.
        """
        return self._state.base_path

    _state: _ApplicationTestState
    _stack: AsyncExitStack | None
    _client: AsyncTestClient | None
    _finished: bool


__all__ = ["ApplicationTest", "AsyncApplicationTest"]
