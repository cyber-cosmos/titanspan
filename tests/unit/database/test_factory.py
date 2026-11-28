"""Verify factories reject invalid sizes and sequences.

These cases cover validation before any persistence occurs.
"""

from __future__ import annotations

import pytest

from titanspan.database import (
    DatabaseFactoryError,
    FactoryBatch,
    Model,
)

pytestmark = pytest.mark.unit


def test_factory_rejects_invalid_batch_sizes() -> None:
    """Require a non-negative integer before creating a factory batch.

    Invalid values must fail before a model is instantiated.
    """
    factory = Model.factory()

    with pytest.raises(DatabaseFactoryError, match="non-negative integer"):
        factory.count(-1)
    with pytest.raises(DatabaseFactoryError, match="non-negative integer"):
        factory.count(True)
    with pytest.raises(DatabaseFactoryError, match="non-negative integer"):
        FactoryBatch(factory, -1)


def test_factory_requires_sequence_values() -> None:
    """Reject an empty sequence instead of silently disabling it.

    A sequence must provide a value for every requested item.
    """
    with pytest.raises(DatabaseFactoryError, match="at least one value"):
        Model.factory().sequence()


def test_factory_rejects_invalid_raw_attribute_indices() -> None:
    """Require a non-negative integer for raw value resolution.

    Index callables use the same zero-based ordering as factory batches.
    """
    factory = Model.factory()

    with pytest.raises(DatabaseFactoryError, match="attribute index"):
        factory.raw_attributes(index=-1)
    with pytest.raises(DatabaseFactoryError, match="attribute index"):
        factory.raw_attributes(index=True)
