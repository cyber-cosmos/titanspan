"""Delegate wrapper method calls to a composed object.

The mixin uses Python method lookup and exception conventions.
"""

from __future__ import annotations

from inspect import getattr_static
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from collections.abc import Sequence


class ForwardsCalls:
    """Forward selected method calls from a wrapper to its delegate.

    Use this mixin when a wrapper exposes methods implemented by a composed
    object. Decorated forwarding returns the wrapper when the delegate's
    method returns that delegate, preserving fluent wrapper chains.

    Notes:
        Dynamic lookup is isolated at the delegation boundary. A missing
        method raises ``AttributeError``; exceptions raised inside an
        existing descriptor or method retain their original identity.
    """

    def forward_call_to(
        self,
        target: object,
        method: str,
        parameters: Sequence[object],
    ) -> object:
        """Invoke a method on the delegate and return its result.

        Args:
            target: The object that owns the delegated method.
            method: The method name to resolve on the target.
            parameters: Positional arguments passed to that method.

        Returns:
            The result returned by the delegated method.

        Raises:
            AttributeError: If the target has no matching method.
            TypeError: If the resolved target attribute is not callable.
            Exception: Any exception raised by the target method.

        Notes:
            Attribute lookup and invocation are separated so an
            ``AttributeError`` raised by a real descriptor or method is not
            mistaken for a missing method.
        """
        try:
            candidate = getattr(target, method)
        except AttributeError:
            try:
                getattr_static(target, method)
            except AttributeError:
                type(self).throw_bad_method_call_exception(method)
            raise

        if not callable(candidate):
            message = (
                f"Forwarded attribute [{method}] on "
                f"[{type(target).__name__}] is not callable."
            )
            raise TypeError(message)

        return candidate(*parameters)

    def forward_decorated_call_to(
        self,
        target: object,
        method: str,
        parameters: Sequence[object],
    ) -> object:
        """Forward a call and preserve fluent wrapper identity.

        Args:
            target: The object that owns the delegated method.
            method: The method name to resolve on the target.
            parameters: Positional arguments passed to that method.

        Returns:
            This wrapper if the target method returns its target; otherwise,
            the target method's result.

        Raises:
            AttributeError: If the target has no matching method.
            TypeError: If the resolved target attribute is not callable.
            Exception: Any exception raised by the target method.
        """
        result: object = self.forward_call_to(target, method, parameters)
        return self if result is target else result

    @classmethod
    def throw_bad_method_call_exception(cls, method: str) -> NoReturn:
        """Raise Python's attribute error for an unknown delegated method.

        Args:
            method: The method name requested by the wrapper.

        Raises:
            AttributeError: Always, naming the wrapper and missing method.
        """
        message = f"{cls.__qualname__} has no delegated method {method!r}"
        raise AttributeError(message)


__all__ = ["ForwardsCalls"]
