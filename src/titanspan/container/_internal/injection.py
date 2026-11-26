"""Select dependency sources from contextual and annotation metadata.

The helpers centralize precedence across native resolution entry points.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from typing import TYPE_CHECKING, Annotated, Literal, get_args, get_origin

from titanspan.container.contextual_binding import (
    ContextualBinding,
    ContextualKind,
)
from titanspan.container.exceptions import BindingError
from titanspan.container.injection import FromConfig, Inject, Named, Tagged
from titanspan.contracts.config import ConfigReader, TypedConfigReader

_INJECTION_MARKER_CONFLICT_ERROR = (
    "A dependency annotation may contain only one injection marker."
)
_CONFIG_COLLECTION_ERROR = (
    "Configuration value for key [{key}] must be {expected}; {actual} found."
)

if TYPE_CHECKING:
    from collections.abc import Sequence


def split_annotation(
    annotation: object,
) -> tuple[object, tuple[object, ...]]:
    """Separate the base type and ordered metadata from an annotation.

    Args:
        annotation: Evaluated or runtime Python annotation.

    Returns:
        The underlying type and metadata tuple for ``Annotated`` values.
    """
    if get_origin(annotation) is not Annotated:
        return annotation, ()
    arguments = get_args(annotation)
    return arguments[0], tuple(arguments[1:])


def read_config_value(
    repository: ConfigReader,
    key: str,
    annotation: object,
) -> object:
    """Read a typed configuration value through its native capability.

    Args:
        repository: Configuration reader with optional typed accessors.
        key: Dotted configuration path selected by injection metadata.
        annotation: Parameter annotation, including optional metadata.

    Returns:
        The value validated by the matching typed configuration accessor.

    Raises:
        BindingError: If the reader lacks typed accessors or the annotation
            has no supported accessor.
        TypeError: If the stored configuration value is missing or has an
            incompatible type.
    """
    base, _metadata = split_annotation(annotation)
    if not isinstance(repository, TypedConfigReader):
        message = (
            "Configuration injection requires a ConfigReader that "
            "implements TypedConfigReader."
        )
        raise BindingError(message)
    if base is str:
        return repository.string(key)
    if base is int:
        return repository.integer(key)
    if base is float:
        return repository.float(key)
    if base is bool:
        return repository.boolean(key)
    origin = get_origin(base)
    if base is list or origin is list:
        return _read_config_collection(repository, key, "list")
    if base is dict or origin is dict:
        return _read_config_collection(repository, key, "dictionary")
    if base is Mapping or origin is Mapping:
        return _read_config_collection(repository, key, "mapping")
    message = (
        "FromConfig requires str, int, float, bool, dict, list, or "
        "Mapping annotations."
    )
    raise BindingError(message)


def _read_config_collection(
    repository: TypedConfigReader,
    key: str,
    expected: Literal["list", "dictionary", "mapping"],
) -> object:
    """Narrow the config array capability to the requested outer type.

    Args:
        repository: Typed configuration reader selected by the container.
        key: Dotted configuration path selected by injection metadata.
        expected: Collection shape required by the parameter annotation.

    Returns:
        The array value after its outer type matches the annotation.

    Raises:
        TypeError: If the array value has another outer collection type.
    """
    value = repository.array(key)
    if expected == "list" and isinstance(value, list):
        return value
    if expected == "dictionary" and isinstance(value, dict):
        return value
    if expected == "mapping" and isinstance(value, Mapping):
        return value

    expected_name = {
        "list": "a list",
        "dictionary": "a dictionary",
        "mapping": "a mapping",
    }[expected]
    message = _CONFIG_COLLECTION_ERROR.format(
        key=key,
        expected=expected_name,
        actual=type(value).__name__,
    )
    raise TypeError(message)


def select_dependency_source(
    consumers: Sequence[type[object]],
    name: str,
    annotation: object,
    contextual: Mapping[
        tuple[type[object], Hashable],
        ContextualBinding,
    ],
) -> tuple[ContextualKind, object] | None:
    """Select a dependency source using native precedence rules.

    Contextual rules take priority over ``Annotated`` markers. Explicit call
    values are applied by the public callable layer before this selector.

    Args:
        consumers: Service contracts and implementation types to match.
        name: Exact constructor or callable parameter name.
        annotation: Evaluated annotation, including optional metadata.
        contextual: Rules indexed by consumer and dependency selector.

    Returns:
        Source category and value, or ``None`` for ordinary service lookup.

    Raises:
        BindingError: If the annotation contains conflicting metadata.
    """
    base, metadata = split_annotation(annotation)
    for consumer in consumers:
        for selector in (base, annotation, name):
            if isinstance(selector, Hashable):
                binding = contextual.get((consumer, selector))
                if binding is not None:
                    return binding.kind, binding.value
    markers = tuple(
        marker
        for marker in metadata
        if isinstance(marker, (Inject, FromConfig, Named, Tagged))
    )
    if len(markers) > 1:
        raise BindingError(_INJECTION_MARKER_CONFLICT_ERROR)
    if not markers:
        return None
    marker = markers[0]
    if isinstance(marker, Inject):
        return ContextualKind.IMPLEMENTATION, marker.implementation
    if isinstance(marker, FromConfig):
        return ContextualKind.CONFIG, marker.key
    if isinstance(marker, Named):
        return ContextualKind.NAMED, marker.name
    return ContextualKind.TAGGED, marker.name
