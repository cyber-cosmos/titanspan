"""Manage native hooks around public service resolution requests.

Callbacks run for public root requests, including cached values. Nested
dependencies built internally by the backend are not separately announced.
"""

from __future__ import annotations

from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Coroutine,
)
from contextvars import ContextVar, Token
from inspect import (
    isasyncgenfunction,
    isawaitable,
    iscoroutine,
    iscoroutinefunction,
    signature,
    unwrap,
)
from typing import get_args, get_origin, get_type_hints

from titanspan.container.exceptions import (
    AsyncResolutionRequiredError,
    BindingResolutionError,
)

type BeforeResolutionCallback = Callable[[type[object]], object]
type ResolutionCallback = Callable[[object], object]

_ASYNC_CALLBACK_ERROR = (
    "An asynchronous resolution callback requires make_async()."
)
_RECURSIVE_CALLBACK_ERROR = (
    "A resolution callback recursively requested the same service."
)


class ResolutionCallbacks:
    """Store and execute ordered callbacks for resolution boundaries.

    Callback registries are application-owned. Their recursion guard uses a
    context variable so concurrent tasks do not share mutable callback state.
    """

    def __init__(self) -> None:
        """Create an empty registry with task-local recursion tracking.

        All callback lists preserve registration order and are read-only while
        the container is resolving application services.
        """
        self._before: dict[
            type[object] | None,
            list[BeforeResolutionCallback],
        ] = {}
        self._resolving: dict[
            type[object] | None,
            list[ResolutionCallback],
        ] = {}
        self._after: dict[
            type[object] | None,
            list[ResolutionCallback],
        ] = {}
        self._active: ContextVar[frozenset[type[object]]] = ContextVar(
            f"titanspan_resolution_callbacks_{id(self)}",
            default=frozenset(),
        )

    def before_resolving(
        self,
        service: type[object] | None,
        callback: BeforeResolutionCallback,
    ) -> None:
        """Register a callback before each matching public request.

        Args:
            service: Exact service key, or ``None`` for every root request.
            callback: Function receiving the canonical requested type.
        """
        self._before.setdefault(service, []).append(callback)

    def resolving(
        self,
        service: type[object] | None,
        callback: ResolutionCallback,
    ) -> None:
        """Register a callback after a matching value is obtained.

        Args:
            service: Exact service key, or ``None`` for every root request.
            callback: Function receiving the resolved service instance.
        """
        self._resolving.setdefault(service, []).append(callback)

    def after_resolving(
        self,
        service: type[object] | None,
        callback: ResolutionCallback,
    ) -> None:
        """Register a callback after all ``resolving`` hooks complete.

        Args:
            service: Exact service key, or ``None`` for every root request.
            callback: Function receiving the resolved service instance.
        """
        self._after.setdefault(service, []).append(callback)

    def clone(self) -> ResolutionCallbacks:
        """Copy callback policy into an isolated temporary registry.

        Returns:
            A registry with the same callbacks and a fresh recursion context.
        """
        copied = ResolutionCallbacks()
        copied._before = {
            service: list(callbacks)
            for service, callbacks in self._before.items()
        }
        copied._resolving = {
            service: list(callbacks)
            for service, callbacks in self._resolving.items()
        }
        copied._after = {
            service: list(callbacks)
            for service, callbacks in self._after.items()
        }
        return copied

    def run_sync[ServiceT](
        self,
        service: type[object],
        resolver: Callable[[], ServiceT],
    ) -> ServiceT:
        """Run callbacks around one immediate dependency lookup.

        Args:
            service: Canonical service key requested by the caller.
            resolver: Synchronous container resolution operation.

        Returns:
            The resolver result after synchronous hooks complete.

        Raises:
            AsyncResolutionRequiredError: If any callback requires awaiting.
            BindingResolutionError: If a callback recursively resolves itself.
        """
        self._ensure_sync_callbacks(service)
        token = self._enter(service)
        try:
            for callback in self._callbacks(self._before, service):
                self._invoke_sync(callback, service)
            value = resolver()
            for callback in self._callbacks(self._resolving, service):
                self._invoke_sync(callback, value)
            for callback in self._callbacks(self._after, service):
                self._invoke_sync(callback, value)
            return value
        finally:
            self._active.reset(token)

    def _ensure_sync_callbacks(self, service: type[object]) -> None:
        """Reject declared asynchronous hooks before service construction.

        Args:
            service: Canonical key whose callbacks will surround resolution.

        Raises:
            AsyncResolutionRequiredError: If a matching callback is async.
        """
        before_callbacks = self._callbacks(self._before, service)
        value_callbacks = (
            *self._callbacks(self._resolving, service),
            *self._callbacks(self._after, service),
        )
        for callback in before_callbacks:
            if _callback_requires_async(callback):
                raise AsyncResolutionRequiredError(_ASYNC_CALLBACK_ERROR)
        for callback in value_callbacks:
            if _callback_requires_async(callback):
                raise AsyncResolutionRequiredError(_ASYNC_CALLBACK_ERROR)

    async def run_async[ServiceT](
        self,
        service: type[object],
        resolver: Callable[[], Awaitable[ServiceT]],
    ) -> ServiceT:
        """Await a dependency and each callback in deterministic order.

        Args:
            service: Canonical service key requested by the caller.
            resolver: Asynchronous container resolution operation.

        Returns:
            The resolver result after all asynchronous hooks complete.

        Raises:
            BindingResolutionError: If a callback recursively resolves itself.
        """
        token = self._enter(service)
        try:
            for callback in self._callbacks(self._before, service):
                await self._invoke_async(callback, service)
            value = await resolver()
            for callback in self._callbacks(self._resolving, service):
                await self._invoke_async(callback, value)
            for callback in self._callbacks(self._after, service):
                await self._invoke_async(callback, value)
            return value
        finally:
            self._active.reset(token)

    def _enter(self, service: type[object]) -> Token[frozenset[type[object]]]:
        """Guard callback and resolver execution against direct recursion.

        Args:
            service: Canonical key at this public resolution boundary.

        Returns:
            Context token restored after the operation finishes.

        Raises:
            BindingResolutionError: If this task already resolves the service.
        """
        active = self._active.get()
        if service in active:
            raise BindingResolutionError(_RECURSIVE_CALLBACK_ERROR)
        return self._active.set(active | {service})

    @staticmethod
    def _callbacks[CallbackT](
        registry: dict[
            type[object] | None,
            list[CallbackT],
        ],
        service: type[object],
    ) -> tuple[CallbackT, ...]:
        """Return global callbacks followed by service-specific callbacks.

        Args:
            registry: One phase's ordered callback mapping.
            service: Canonical service key being resolved.

        Returns:
            Immutable callback sequence in invocation order.
        """
        return tuple(registry.get(None, ())) + tuple(registry.get(service, ()))

    @staticmethod
    def _invoke_sync[ValueT](
        callback: Callable[[ValueT], object],
        value: ValueT,
    ) -> None:
        """Invoke one synchronous hook and reject awaitable results.

        Args:
            callback: Callback selected for the current resolution phase.
            value: Service type or resolved object passed to the callback.

        Raises:
            AsyncResolutionRequiredError: If the callback is asynchronous.
        """
        result = callback(value)
        if isawaitable(result):
            if iscoroutine(result):
                result.close()
            raise AsyncResolutionRequiredError(_ASYNC_CALLBACK_ERROR)

    @staticmethod
    async def _invoke_async[ValueT](
        callback: Callable[[ValueT], object],
        value: ValueT,
    ) -> None:
        """Invoke a hook and await it when it returns an awaitable.

        Args:
            callback: Callback selected for the current resolution phase.
            value: Service type or resolved object passed to the callback.
        """
        result = callback(value)
        if isawaitable(result):
            await result


def _callback_requires_async(callback: Callable[..., object]) -> bool:
    """Inspect callback shape and return annotation without invoking it.

    Args:
        callback: Resolution hook selected for the current service request.

    Returns:
        Whether the callback is declared async or returns an awaitable value.
    """
    unwrapped = unwrap(callback)
    if iscoroutinefunction(unwrapped) or isasyncgenfunction(unwrapped):
        return True
    if callable(unwrapped) and (
        iscoroutinefunction(type(unwrapped).__call__)
        or isasyncgenfunction(type(unwrapped).__call__)
    ):
        return True
    try:
        result = get_type_hints(callback, include_extras=True).get(
            "return",
            signature(callback).return_annotation,
        )
    except (NameError, TypeError, ValueError):
        return False
    origin = get_origin(result)
    if origin in {Awaitable, Coroutine, AsyncIterator, AsyncGenerator}:
        return True
    return any(
        get_origin(argument)
        in {Awaitable, Coroutine, AsyncIterator, AsyncGenerator}
        for argument in get_args(result)
    )


__all__ = [
    "BeforeResolutionCallback",
    "ResolutionCallback",
    "ResolutionCallbacks",
]
