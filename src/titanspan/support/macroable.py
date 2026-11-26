"""Provide explicit, typed macro registration for support classes.

The API uses Python callables and explicit invocation methods instead of
magic attribute lookup.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from threading import RLock
from types import MethodType
from typing import ClassVar, cast
from weakref import WeakKeyDictionary

from titanspan.support.exceptions import (
    InvalidMacroCallbackError,
    InvalidMacroNameError,
    MacroNotFoundError,
)

type Macro = Callable[..., object]
type MacroEntry = tuple[Macro, bool]


class Macroable:
    """Register and explicitly invoke class- and instance-level macros.

    Macro definitions are scoped to each class and inherited through the
    class hierarchy. A registered plain function is bound to the active
    object by ``call_macro``; ``invoke_macro`` calls it without an instance.

    Attributes:
        macro: Register or replace a callback on the receiving class.
        has_macro: Check whether a class or a parent registered a callback.

    Notes:
        Python does not expose dynamically registered methods to static
        type checkers. Callers should use the typed invocation methods or
        declare statically typed wrappers around known macros.
    """

    _registries: ClassVar[
        WeakKeyDictionary[type[Macroable], dict[str, MacroEntry]]
    ] = WeakKeyDictionary()
    _registry_lock: ClassVar[RLock] = RLock()

    def __init_subclass__(cls) -> None:
        """Create an isolated registry for a new macro-capable class.

        The weak-key registry avoids retaining dynamically created classes
        after their owners release them.
        """
        super().__init_subclass__()
        with Macroable._registry_lock:
            Macroable._registries.setdefault(cls, {})

    @classmethod
    def macro(cls, name: str, callback: Macro) -> None:
        """Register or replace a class-level macro callback.

        Args:
            name: A non-empty public macro name.
            callback: A callable accepting the invocation arguments.

        Raises:
            TypeError: If ``callback`` is not callable.
            ValueError: If ``name`` is empty or whitespace-only.
        """
        if not name.strip():
            raise InvalidMacroNameError
        if not callable(callback):
            raise InvalidMacroCallbackError(name)

        # Class registries are mutated under one lock because registration
        # may occur while worker threads are starting or tests are isolated.
        with Macroable._registry_lock:
            registry = Macroable._registries.setdefault(cls, {})
            registry[name] = (callback, True)

    @classmethod
    def has_macro(cls, name: str) -> bool:
        """Check for a local or inherited macro registration.

        Args:
            name: The macro identifier to check.

        Returns:
            Whether this class can resolve the named macro.
        """
        return cls.resolve_macro(name) is not None

    @classmethod
    def resolve_macro(cls, name: str) -> MacroEntry | None:
        """Return the callback entry visible to this class.

        Args:
            name: The macro identifier to find.

        Returns:
            A callback and binding flag, or ``None`` when absent.

        Notes:
            This method supports static typing for code that needs to inspect
            a macro without relying on dynamic attribute dispatch.
        """
        with Macroable._registry_lock:
            for candidate in cls.__mro__:
                registry = Macroable._registries.get(candidate)
                if registry is not None and name in registry:
                    return registry[name]
        return None

    @classmethod
    def mixin(cls, mixin: object, replace: bool = True) -> None:
        """Register callbacks produced by a mixin object's methods.

        Public and protected non-dunder methods are invoked as zero-argument
        factories. Each factory must return a callable. Returned callbacks
        retain their Python closure binding to the mixin instance.

        Args:
            mixin: The object providing callback factories.
            replace: Whether to replace an existing local or inherited name.

        Raises:
            TypeError: If a factory does not return a callable.
        """
        members = inspect.getmembers(mixin, predicate=callable)
        for name, factory in members:
            if name.startswith("__"):
                continue
            if not replace and cls.has_macro(name):
                continue

            callback = factory()
            if not callable(callback):
                raise InvalidMacroCallbackError(name, factory=True)
            cls._register_mixin_macro(name, callback)

    @classmethod
    def _register_mixin_macro(cls, name: str, callback: object) -> None:
        """Store a mixin callback without rebinding its closure.

        Args:
            name: The method name exposed by the mixin.
            callback: A callable created by the mixin factory.
        """
        # Mixin closures close over their source object and should not receive
        # the target as an extra first argument during instance invocation.
        with Macroable._registry_lock:
            registry = Macroable._registries.setdefault(cls, {})
            registry[name] = (cast("Macro", callback), False)

    @classmethod
    def flush_macros(cls) -> None:
        """Remove macros registered directly on the receiving class.

        Inherited registrations remain visible until their owning class is
        flushed, matching the class-level inheritance model.
        """
        with Macroable._registry_lock:
            Macroable._registries.setdefault(cls, {}).clear()

    @classmethod
    def invoke_macro(
        cls,
        name: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        """Invoke a registered callback without binding an instance.

        Args:
            name: The registered macro name.
            *args: Positional callback arguments.
            **kwargs: Named callback arguments.

        Returns:
            The callback's result.

        Raises:
            MacroNotFoundError: If no class or parent registered the name.
        """
        entry = cls.resolve_macro(name)
        if entry is None:
            raise MacroNotFoundError(cls.__name__, name)
        callback, _bind_instance = entry
        return callback(*args, **kwargs)

    def call_macro(
        self,
        name: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        """Invoke a registered callback in the current instance context.

        Args:
            name: The registered macro name.
            *args: Positional callback arguments.
            **kwargs: Named callback arguments.

        Returns:
            The callback's result.

        Raises:
            MacroNotFoundError: If no class or parent registered the name.
        """
        entry = type(self).resolve_macro(name)
        if entry is None:
            raise MacroNotFoundError(type(self).__name__, name)
        callback, bind_instance = entry
        if bind_instance and inspect.isfunction(callback):
            callback = cast("Macro", MethodType(callback, self))
        return callback(*args, **kwargs)


__all__ = ["Macro", "Macroable"]
