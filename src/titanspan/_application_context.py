"""Hold the active application binding for one execution context.

Foundation installs this context around application work. Facades consult it
instead of maintaining independent production registries.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

    from titanspan.contracts.container import ServiceContainer


class ApplicationContextError(RuntimeError):
    """Report facade use without an active application context.

    Bind an application context before resolving application-owned services.
    """


@dataclass(frozen=True, slots=True)
class ActiveApplicationContext:
    """Identify the application, service container, and current scope.

    Attributes:
        application: Active application object owned by Foundation.
        container: Canonical service container for the application.
        scope: Optional active execution scope, such as a request or job.
    """

    application: object
    container: ServiceContainer
    scope: object | None = None


_ACTIVE_CONTEXT: ContextVar[ActiveApplicationContext | None] = ContextVar(
    "titanspan_active_application_context",
    default=None,
)


@contextmanager
def bind_application_context(
    application: object,
    container: ServiceContainer,
    scope: object | None = None,
) -> Generator[ActiveApplicationContext, None, None]:
    """Bind application services until normal or exceptional scope exit.

    Args:
        application: Application that owns the selected container.
        container: Canonical application service container.
        scope: Optional execution scope owned by that container.

    Yields:
        The context visible to facades during this execution.

    Notes:
        ContextVar tokens isolate concurrent tasks and restore nested bindings.
    """
    active = ActiveApplicationContext(application, container, scope)
    token: Token[ActiveApplicationContext | None] = _ACTIVE_CONTEXT.set(active)
    try:
        yield active
    finally:
        _ACTIVE_CONTEXT.reset(token)


def active_application_context() -> ActiveApplicationContext | None:
    """Return the context bound to the current task or thread.

    Returns:
        The active application context, or ``None`` outside application work.
    """
    return _ACTIVE_CONTEXT.get()


__all__ = [
    "ActiveApplicationContext",
    "ApplicationContextError",
    "active_application_context",
    "bind_application_context",
]
