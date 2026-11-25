"""Verify forwarding mixin delegation and error behavior.

Exercise the original target method, decorated fluent calls, and missing
method handling without mocking the behavior under test.
"""

from __future__ import annotations

import pytest

from titanspan.support import ForwardsCalls

pytestmark = pytest.mark.unit

_TARGET_METHOD_ERROR = "failure from target method"
_TARGET_DESCRIPTOR_ERROR = "failure from target descriptor"


class _Target:
    """Provide real methods for forwarding contract tests.

    The target methods cover ordinary returns and raised attribute errors.
    """

    def combine(self, left: str, right: str) -> str:
        """Combine values to verify positional argument forwarding.

        Args:
            left: The first text value.
            right: The second text value.

        Returns:
            Both values separated by a colon.
        """
        return f"{left}:{right}"

    def fluent(self) -> _Target:
        """Return this target to exercise decorated forwarding.

        Returns:
            This target instance.
        """
        return self

    def fail_with_attribute_error(self) -> None:
        """Raise from an existing method without masking the failure.

        Raises:
            AttributeError: Always, with a stable test diagnostic.
        """
        raise AttributeError(_TARGET_METHOD_ERROR)

    @property
    def broken(self) -> str:
        """Raise while resolving a real descriptor.

        Raises:
            AttributeError: Always, with a stable test diagnostic.
        """
        raise AttributeError(_TARGET_DESCRIPTOR_ERROR)


class _Wrapper(ForwardsCalls):
    """Expose mixin methods through a small delegating object.

    The wrapper keeps target selection explicit so tests exercise forwarding
    without relying on arbitrary dynamic attribute dispatch.
    """

    def call(self, target: object, method: str, *args: object) -> object:
        """Forward positional values to the selected target method.

        Args:
            target: The object receiving the delegated method call.
            method: The method name to resolve on the target.
            *args: Positional arguments forwarded to the target method.

        Returns:
            The result returned by the target method.
        """
        return self.forward_call_to(target, method, args)

    def decorated_call(
        self,
        target: object,
        method: str,
        *args: object,
    ) -> object:
        """Forward a call while replacing target-self with this wrapper.

        Args:
            target: The object receiving the delegated method call.
            method: The method name to resolve on the target.
            *args: Positional arguments forwarded to the target method.

        Returns:
            The wrapper for target-self results, or the original result.
        """
        return self.forward_decorated_call_to(target, method, args)


def test_forward_call_passes_arguments_and_returns_the_target_result() -> None:
    """Delegate positional arguments and preserve the method result.

    This covers the base forwarding operation against a real target method.
    """
    assert _Wrapper().call(_Target(), "combine", "hello", "world") == (
        "hello:world"
    )


def test_nested_forwarding_preserves_arguments_and_result() -> None:
    """Delegate through two wrappers to the underlying method.

    Each wrapper receives the same argument sequence and final return value.
    """
    outer = _Wrapper()
    inner = _Wrapper()

    assert (
        outer.call(
            inner,
            "call",
            _Target(),
            "combine",
            "hello",
            "nested",
        )
        == "hello:nested"
    )


def test_forward_decorated_call_returns_wrapper_for_target_self() -> None:
    """Return the wrapper when the delegated method returns its target.

    This preserves fluent chaining across an object wrapper boundary.
    """
    wrapper = _Wrapper()

    assert wrapper.decorated_call(_Target(), "fluent") is wrapper


def test_forward_decorated_call_preserves_other_results() -> None:
    """Preserve values that are not the delegated target instance.

    Non-fluent results pass through without being wrapped or transformed.
    """
    wrapper = _Wrapper()

    assert (
        wrapper.decorated_call(
            _Target(),
            "combine",
            "one",
            "two",
        )
        == "one:two"
    )


@pytest.mark.parametrize("method", ["missing", "this1_shouldWork_too"])
def test_missing_method_raises_an_attribute_error_for_wrapper_class(
    method: str,
) -> None:
    """Report a missing forwarded method using Python's attribute error.

    Args:
        method: The absent method name requested through the wrapper.
    """
    with pytest.raises(
        AttributeError,
        match=rf"Call to undefined method _Wrapper::{method}\(\)",
    ):
        _Wrapper().call(_Target(), method)


def test_target_method_attribute_error_is_not_rewritten() -> None:
    """Preserve an AttributeError raised after a real method was found.

    Forwarding only translates lookup failure, not errors from method bodies.
    """
    with pytest.raises(
        AttributeError,
        match="failure from target method",
    ):
        _Wrapper().call(_Target(), "fail_with_attribute_error")


def test_target_descriptor_attribute_error_is_not_rewritten() -> None:
    """Preserve AttributeError raised by a real target descriptor.

    Static lookup distinguishes an existing descriptor from a missing name.
    """
    with pytest.raises(
        AttributeError,
        match="failure from target descriptor",
    ):
        _Wrapper().call(_Target(), "broken")


def test_non_callable_target_attribute_raises_type_error() -> None:
    """Reject a present attribute that cannot be invoked as a method.

    Python distinguishes a missing method from a non-callable member.
    """

    class TargetWithValue:
        """Provide a regular value under a requested method name.

        The value lets the test verify non-callable lookup behavior.
        """

        action = "not callable"

    with pytest.raises(TypeError, match="not callable"):
        _Wrapper().call(TargetWithValue(), "action")


def test_camel_case_aliases_delegate_to_python_methods() -> None:
    """Keep Illuminate method aliases behaviorally identical.

    Both source-compatible aliases reach the same forwarding implementations.
    """
    wrapper = _Wrapper()
    target = _Target()

    assert wrapper.forwardCallTo(target, "combine", ["a", "b"]) == "a:b"
    assert wrapper.forwardDecoratedCallTo(target, "fluent", []) is wrapper


def test_bad_method_exception_alias_names_the_consuming_class() -> None:
    """Expose the source-compatible static error helper.

    The diagnostic names the consuming wrapper class rather than the mixin.
    """
    with pytest.raises(
        AttributeError,
        match=r"Call to undefined method _Wrapper::missing\(\)",
    ):
        _Wrapper.throwBadMethodCallException("missing")
