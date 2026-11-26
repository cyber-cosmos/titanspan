"""Validate pytest markers for runtime test classification.

The coverage suite collects every runtime test. Classification markers keep
each new test visible to the repository's focused CI targets.
"""

from collections.abc import Iterable

TEST_CLASSIFICATIONS = frozenset(
    {
        "architecture",
        "benchmark",
        "concurrency",
        "feature",
        "integration",
        "regression",
        "security",
        "stress",
        "unit",
    }
)


def unclassified_test_ids(
    tests: Iterable[tuple[str, Iterable[str]]],
) -> tuple[str, ...]:
    """Return collected tests without a recognized runtime category.

    Args:
        tests: Pairs of pytest node IDs and their inherited marker names.

    Returns:
        Node IDs that need a unit, integration, or specialized marker.
    """
    unclassified: list[str] = []
    for node_id, markers in tests:
        if not TEST_CLASSIFICATIONS.intersection(markers):
            unclassified.append(node_id)
    return tuple(unclassified)


__all__ = ["TEST_CLASSIFICATIONS", "unclassified_test_ids"]
