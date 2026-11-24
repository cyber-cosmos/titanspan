"""Test independent line and branch coverage enforcement.

Coverage thresholds must fail independently rather than hide a weak metric
inside an aggregate percentage.
"""

from pathlib import Path

import pytest
from scripts.check_coverage import read_coverage_policy, validate_coverage

EXPECTED_COVERAGE_METRIC_COUNT = 2

pytestmark = pytest.mark.unit
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.security
def test_repository_keeps_independent_coverage_thresholds() -> None:
    """Keep coverage policy at 95 percent lines and 90 percent branches.

    The configured values must not be lowered as a workaround for weak tests.
    """
    assert read_coverage_policy(REPOSITORY_ROOT / "pyproject.toml") == (
        95.0,
        90.0,
    )


def test_coverage_policy_checks_lines_and_branches_separately() -> None:
    """Reject a report that misses the branch threshold only.

    Line coverage cannot compensate for an inadequately exercised branch.
    """
    totals: dict[str, object] = {
        "percent_statements_covered": 99.0,
        "percent_branches_covered": 89.0,
    }

    errors = validate_coverage(
        totals,
        minimum_line_coverage=95.0,
        minimum_branch_coverage=90.0,
    )

    assert len(errors) == 1
    assert "branch coverage" in errors[0]


def test_coverage_policy_accepts_both_thresholds() -> None:
    """Accept reports that meet both configured independent thresholds.

    The values are percentages emitted by coverage.py's JSON report.
    """
    totals: dict[str, object] = {
        "percent_statements_covered": 95.0,
        "percent_branches_covered": 90.0,
    }

    assert (
        validate_coverage(
            totals,
            minimum_line_coverage=95.0,
            minimum_branch_coverage=90.0,
        )
        == []
    )


def test_coverage_policy_rejects_missing_metrics() -> None:
    """Fail closed when a coverage report omits a required metric.

    Missing values must not be treated as zero errors or successful coverage.
    """
    errors = validate_coverage(
        {},
        minimum_line_coverage=95.0,
        minimum_branch_coverage=90.0,
    )

    assert len(errors) == EXPECTED_COVERAGE_METRIC_COUNT
