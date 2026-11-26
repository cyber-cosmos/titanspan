"""Verify Collections against real Support values and callbacks.

The tests use no Application or Container because collections are plain values.
"""

from __future__ import annotations

from titanspan.collections import collect
from titanspan.support import Fluent


def test_collection_map_reads_real_fluent_nested_attributes() -> None:
    """Use a real Fluent value through a typed Collection callback.

    Returns:
        None.
    """
    users = collect(
        [
            Fluent[str, object]({"profile": {"name": "Ada"}}),
            Fluent[str, object]({"profile": {"name": "Lin"}}),
        ]
    )

    names = users.map(lambda user: user.get("profile.name"))

    assert names.all() == ["Ada", "Lin"]


def test_collection_tap_reuses_support_and_preserves_identity() -> None:
    """Run a Support tap callback without changing the collection instance.

    Returns:
        None.
    """
    values = collect([1, 2])
    observed: list[int] = []

    assert (
        values.tap(lambda collection: observed.extend(collection.all()))
        is values
    )
    assert observed == [1, 2]
