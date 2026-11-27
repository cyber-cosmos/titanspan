"""Register the canonical Queue manager and job-scoped metadata.

The provider uses Foundation's Container graph and lazy resource lifecycle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator  # noqa: TC003
from typing import TYPE_CHECKING

from titanspan.container import Scope
from titanspan.contracts.config import ConfigRepository  # noqa: TC001
from titanspan.contracts.container import ServiceContainer  # noqa: TC001
from titanspan.contracts.events import EventDispatcher  # noqa: TC001
from titanspan.contracts.foundation import BootableServiceProvider
from titanspan.contracts.logging import LogWriter  # noqa: TC001
from titanspan.contracts.queue import (
    BusDispatcher,
    JobMiddlewareType,
    QueueDispatcher,
)
from titanspan.queue.exceptions import QueueConfigurationError
from titanspan.queue.job import (
    Job,
    JobContext,
    validate_middleware_declarations,
)
from titanspan.queue.manager import QueueBrokerFactory, QueueManager

if TYPE_CHECKING:
    from collections.abc import (
        Awaitable,
        Callable,
        Mapping,
        Sequence,
    )

    from titanspan.contracts.container import ServiceRegistry


class QueueServiceProvider(BootableServiceProvider):
    """Register Queue contracts through one application-owned manager.

    Broker factories remain lazy. Startup freezes trusted job registrations
    without opening any remote connections.
    """

    def __init__(
        self,
        *,
        drivers: Mapping[str, QueueBrokerFactory] | None = None,
        jobs: Sequence[type[Job]] = (),
        middleware: Sequence[JobMiddlewareType] = (),
    ) -> None:
        """Retain trusted application jobs and broker adapters.

        Args:
            drivers: Trusted Taskiq broker factories keyed by driver name.
            jobs: Explicit job classes allowed to execute in this app.
            middleware: Ordered application-wide middleware classes.
        """
        self._drivers = dict(drivers or {})
        self._jobs = tuple(jobs)
        try:
            self._middleware = validate_middleware_declarations(
                tuple(middleware)
            )
        except TypeError as error:
            msg = "Queue middleware declarations must be callable classes."
            raise QueueConfigurationError(msg) from error

    def register(self, container: ServiceRegistry) -> None:
        """Bind QueueManager and QueueDispatcher to the canonical graph.

        Args:
            container: Native registry shared by application providers.
        """

        async def provide_manager(
            repository: ConfigRepository,
            application_container: ServiceContainer,
            events: EventDispatcher,
            logger: LogWriter,
        ) -> AsyncIterator[QueueManager]:
            """Own the manager and its broker cleanup in the app Container.

            Args:
                repository: Canonical Queue configuration source.
                application_container: Existing authoritative service graph.
                events: Canonical metadata event dispatcher.
                logger: Canonical structured application logger.

            Yields:
                One application-specific lazy Queue manager.
            """
            manager = QueueManager.from_repository(
                repository,
                container=application_container,
                drivers=self._drivers,
                jobs=self._jobs,
                events=events,
                logger=logger,
            )
            try:
                manager.register_middleware(self._middleware)
                yield manager
            finally:
                await manager.aclose()

        def provide_dispatcher(manager: QueueManager) -> QueueDispatcher:
            """Expose the manager through the canonical shared contract.

            Args:
                manager: Application-owned Queue manager.

            Returns:
                The same manager injected into application services.
            """
            return manager

        def provide_bus_dispatcher(manager: QueueManager) -> BusDispatcher:
            """Expose the same manager through the native Bus contract.

            Args:
                manager: Application-owned Queue manager.

            Returns:
                The same manager used by Queue and dependency injection.
            """
            return manager

        def provide_job_context(manager: QueueManager) -> JobContext:
            """Resolve metadata only while one native job scope is active.

            Args:
                manager: Canonical application Queue manager.

            Returns:
                Current job metadata for the active execution.
            """
            return manager.current_job_context

        container.singleton(QueueManager, provide_manager)
        container.singleton(QueueDispatcher, provide_dispatcher)
        container.singleton(BusDispatcher, provide_bus_dispatcher)
        container.scoped(
            JobContext,
            provide_job_context,
            scope=Scope.JOB,
        )

    @property
    def boot(self) -> Callable[..., Awaitable[object] | None]:
        """Freeze the registered job catalog after all providers register.

        Returns:
            A provider callback resolved by the native Container.
        """
        return self._boot

    def _boot(self, manager: QueueManager) -> None:
        """Freeze application job types without connecting to a broker.

        Args:
            manager: Lazy application-owned Queue manager.
        """
        manager.freeze()

    _drivers: dict[str, QueueBrokerFactory]
    _jobs: tuple[type[Job], ...]
    _middleware: tuple[JobMiddlewareType, ...]


__all__ = ["QueueServiceProvider"]
