"""Verify test collection categories match focused repository targets.

The root pytest hook uses this policy before every test run.
"""

import pytest
from scripts.ci.test_classification import unclassified_test_ids

pytestmark = pytest.mark.unit


def test_classification_accepts_unit_and_specialized_markers() -> None:
    """Accept all established categories used by Make targets.

    A test can carry more than one category when it serves multiple suites.
    """
    cases = (
        ("tests/unit/test_one.py::test_one", ("unit",)),
        (
            "tests/integration/test_two.py::test_two",
            ("integration", "architecture"),
        ),
        ("benchmarks/test_three.py::test_three", ("benchmark",)),
    )

    assert unclassified_test_ids(cases) == ()


def test_classification_rejects_missing_and_non_category_markers() -> None:
    """Report tests that focused test selectors would otherwise omit.

    The slow marker describes duration and does not replace a test category.
    """
    cases = (
        ("tests/unit/test_one.py::test_one", ("unit",)),
        ("tests/test_two.py::test_two", ()),
        ("tests/test_three.py::test_three", ("slow",)),
    )

    assert unclassified_test_ids(cases) == (
        "tests/test_two.py::test_two",
        "tests/test_three.py::test_three",
    )
