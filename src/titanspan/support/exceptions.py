"""Define errors raised by Titanspan Support utilities.

The exceptions preserve stable operation categories while carrying
Python-specific messages and structured details for callers.
"""

from __future__ import annotations


class UriContextError(RuntimeError):
    """Report URI operations that require absent application services.

    URI parsing remains available without an Application. Route factories and
    native redirects need an explicitly active application context.
    """


class ArrayValueError(ValueError):
    """Report a value that does not satisfy a typed array accessor.

    The error remains a ``ValueError`` so callers can handle invalid values
    using standard Python exception conventions.
    """

    def __init__(
        self,
        key: object,
        expected: str,
        actual: object,
    ) -> None:
        """Create an error describing the mismatched value type.

        Args:
            key: The nested key used to retrieve the value.
            expected: A human-readable expected type description.
            actual: The returned value that failed validation.
        """
        self.key = key
        self.expected = expected
        self.actual_type = type(actual).__name__
        message = (
            f"Array value for key [{key}] must be {expected}, "
            f"{self.actual_type} found."
        )
        super().__init__(message)


class ArrayConversionError(ValueError):
    """Report an object that cannot be converted to array data.

    The exception gives ``Arr.from_`` callers one stable failure category
    without exposing serializer implementation details.
    """

    def __init__(self) -> None:
        """Create the standard conversion failure error.

        The message identifies the supported conversion boundary.
        """
        message = "The input cannot be represented as keyed data."
        super().__init__(message)


class ArrayMutationError(TypeError):
    """Report an invalid mutable array target.

    Mutation helpers raise this exception when their target cannot be
    changed through Python's mutable mapping or sequence protocols.
    """

    def __init__(self) -> None:
        """Create the standard mutation failure error.

        The message names the supported mutation boundary so callers can
        correct the input without depending on an implementation detail.
        """
        message = "The selected value must be a mutable sequence."
        super().__init__(message)


class InvalidSortCriterionError(TypeError):
    """Report an unsupported value passed to a sorting helper.

    Sort helpers accept field paths, callables, or supported selector
    sequences. Other values are rejected before sorting begins.
    """

    def __init__(self) -> None:
        """Create the standard sort-criterion validation error.

        The message describes selector forms supported by the public API.
        """
        message = "Sort criteria must be paths or one-argument callables."
        super().__init__(message)


class RandomSelectionError(ValueError):
    """Report a random selection larger than its source collection.

    The exception records both counts to let callers handle undersized
    sources without parsing the diagnostic message.
    """

    def __init__(self, requested: int, available: int) -> None:
        """Create a selection error with requested and available counts.

        Args:
            requested: The requested number of selected values.
            available: The number of available source values.
        """
        self.requested = requested
        self.available = available
        message = f"Requested {requested} items from {available} available."
        super().__init__(message)


class NoMatchingArrayItemError(LookupError):
    """Report that no value matched a requested array selection.

    This error is raised by strict single-item retrieval when the input
    contains no value satisfying the requested predicate.
    """

    def __init__(self) -> None:
        """Create the standard empty-selection error.

        The message identifies the failed exactly-one selection contract.
        """
        message = "No matching item was found."
        super().__init__(message)


class MultipleMatchingArrayItemsError(ValueError):
    """Report that an operation expected exactly one matching value.

    The exception records the number of matches to support structured
    handling of zero-or-many selection failures.
    """

    def __init__(self, count: int) -> None:
        """Create an error containing the number of matching values.

        Args:
            count: The number of matching values found.
        """
        self.count = count
        message = f"Expected one item, found {count}."
        super().__init__(message)


class MacroNotFoundError(LookupError):
    """Report that a macro registry cannot resolve a requested name.

    The exception records the target class and name to support reliable
    diagnostics without parsing the human-readable message.
    """

    def __init__(self, class_name: str, name: str) -> None:
        """Create an error identifying the unresolved class macro.

        Args:
            class_name: The type whose macro registry was searched.
            name: The missing macro name.
        """
        self.class_name = class_name
        self.name = name
        super().__init__(f"unknown macro [{name}] on [{class_name}].")


class InvalidMacroNameError(ValueError):
    """Report a macro registration with an empty name.

    Macro names are explicit API identifiers and cannot be empty or consist
    only of whitespace.
    """

    def __init__(self) -> None:
        """Create the standard invalid macro name error.

        The diagnostic remains stable for both class and mixin registration.
        """
        super().__init__("Macro name must not be empty.")


class InvalidMacroCallbackError(TypeError):
    """Report invalid macro callback registration data.

    This error covers non-callable registrations and mixin factories that
    return values the macro registry cannot invoke.
    """

    def __init__(self, name: str, *, factory: bool = False) -> None:
        """Create an error describing the invalid callback boundary.

        Args:
            name: The macro or mixin factory name.
            factory: Whether the invalid value came from a mixin factory.
        """
        if factory:
            message = f"Mixin factory [{name}] must return a callable."
        else:
            message = "Macro callback must be callable."
        super().__init__(message)


class AsyncCallbackUsageError(TypeError):
    """Report an awaitable returned through a synchronous API.

    Explicit async counterparts prevent accidental execution of callbacks
    without an await point.
    """

    def __init__(
        self,
        source: str,
        async_api: str = "an explicit async API",
    ) -> None:
        """Create a diagnostic directing callers to the async API.

        Args:
            source: The synchronous operation that received an awaitable.
            async_api: The recommended asynchronous counterpart.
        """
        message = (
            f"Synchronous {source} returned an awaitable; use {async_api}."
        )
        super().__init__(message)


class InvalidRetryConfigurationError(ValueError):
    """Report an invalid retry count or delay value.

    The exception distinguishes invalid configuration values from errors
    raised by the operation being retried.
    """

    def __init__(self, parameter: str, requirement: str) -> None:
        """Describe the rejected retry parameter.

        Args:
            parameter: The retry argument that failed validation.
            requirement: The value constraint that was violated.
        """
        message = f"{parameter} must be {requirement}."
        super().__init__(message)


class InvalidRetryConfigurationTypeError(TypeError):
    """Report a retry argument with an unsupported value type.

    The exception separates argument type errors from invalid numeric values
    and from failures raised by the operation itself.
    """

    def __init__(self, parameter: str, expected: str) -> None:
        """Describe the expected type for a retry argument.

        Args:
            parameter: The retry argument with an unsupported type.
            expected: The supported type or types.
        """
        message = f"{parameter} must be {expected}."
        super().__init__(message)


class InvalidNumberValueError(TypeError):
    """Report a boolean passed where a numeric value is required.

    Python treats booleans as integer subclasses, so numeric accessors
    reject booleans explicitly.
    """

    def __init__(self) -> None:
        """Create the standard invalid number type error.

        The message describes the supported built-in numeric types.
        """
        super().__init__("number must be an integer or float")


class InvalidNumberParseTypeError(ValueError):
    """Reject parser result modes outside the supported ICU values.

    Integer modes and the floating-point mode use the numeric values exposed
    by ``NumberParseType``.
    """

    def __init__(self) -> None:
        """Create an error naming the accepted parser mode values.

        The stable message lets callers diagnose an invalid mode without
        depending on Babel's parser exceptions.
        """
        super().__init__("type must be 0, 1, or 2")


class InvalidNumberPrecisionError(ValueError):
    """Report a precision value outside the supported digit range.

    The exception records the parameter name and its expected requirement so
    callers can distinguish invalid precision settings.
    """

    def __init__(self, parameter: str, requirement: str) -> None:
        """Identify the precision argument and its required value range.

        Args:
            parameter: The precision argument that failed validation.
            requirement: A concise description of the accepted values.
        """
        super().__init__(f"{parameter} must be {requirement}")


class InvalidNumberPrecisionTypeError(TypeError):
    """Report a fraction digit setting that is not an integer.

    Booleans are rejected even though Python defines them as integer
    subclasses.
    """

    def __init__(self, parameter: str) -> None:
        """Name the precision argument with its invalid runtime type.

        Args:
            parameter: The precision argument that failed validation.
        """
        super().__init__(f"{parameter} must be an integer")


class InvalidNumberStepError(ValueError):
    """Report a zero step supplied to ``Number.pairs``.

    A zero step cannot advance the lower boundary and would otherwise make
    range generation non-terminating.
    """

    def __init__(self) -> None:
        """Create the standard zero-step validation error.

        The message points to the public ``by`` argument used by
        ``Number.pairs``.
        """
        super().__init__("The by argument must not be zero.")


class NonAdvancingNumberRangeError(ValueError):
    """Report a floating-point step that cannot advance the range.

    This protects range generation when floating-point precision absorbs the
    requested increment.
    """

    def __init__(self) -> None:
        """Create the standard non-advancing range error.

        The message lets callers adjust the step or use integer boundaries.
        """
        super().__init__("by is too small to advance the range.")


class MissingNumberDependencyError(ImportError):
    """Report an unavailable package required by a Number operation.

    Formatting and word spelling use optional dependencies so applications
    that do not need them can keep the base installation small.
    """

    def __init__(self, package: str) -> None:
        """Explain which optional extra provides the required package.

        Args:
            package: The missing package import name.
        """
        self.package = package
        super().__init__(
            f"{package} is required for this operation; "
            "install the titanspan[numbers] extra."
        )


__all__ = [
    "ArrayConversionError",
    "ArrayMutationError",
    "ArrayValueError",
    "AsyncCallbackUsageError",
    "InvalidMacroCallbackError",
    "InvalidMacroNameError",
    "InvalidNumberParseTypeError",
    "InvalidNumberPrecisionError",
    "InvalidNumberPrecisionTypeError",
    "InvalidNumberStepError",
    "InvalidNumberValueError",
    "InvalidRetryConfigurationError",
    "InvalidRetryConfigurationTypeError",
    "InvalidSortCriterionError",
    "MacroNotFoundError",
    "MissingNumberDependencyError",
    "MultipleMatchingArrayItemsError",
    "NoMatchingArrayItemError",
    "NonAdvancingNumberRangeError",
    "RandomSelectionError",
    "UriContextError",
]
