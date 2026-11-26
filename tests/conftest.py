"""Provide shared pytest configuration for the repository test suite.

Fixtures are introduced here only when multiple tests need the same behavior.
"""

import pytest
from scripts.ci.test_classification import unclassified_test_ids


def pytest_collection_modifyitems(
    session: pytest.Session,
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Require a recognized category on each collected runtime test.

    Args:
        session: Pytest session that owns the collected tests.
        config: Active pytest configuration.
        items: Runtime tests collected from the configured test paths.

    Raises:
        pytest.UsageError: If a test is invisible to focused CI selectors.
    """
    _ = session, config
    tests: list[tuple[str, tuple[str, ...]]] = [
        (
            item.nodeid,
            tuple(marker.name for marker in item.iter_markers()),
        )
        for item in items
    ]
    unclassified = unclassified_test_ids(tests)
    if unclassified:
        examples = "\n".join(f"  - {node_id}" for node_id in unclassified)
        message = (
            "Every runtime test needs a category marker from architecture, "
            "benchmark, concurrency, feature, integration, regression, "
            "security, stress, or unit. Unclassified tests:\n"
            f"{examples}"
        )
        raise pytest.UsageError(message)
