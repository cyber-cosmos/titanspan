"""Test CI report summaries and required coverage artifact aggregation.

The report helpers reject incomplete data so summaries cannot turn missing
test or coverage evidence into an apparent success.
"""

from pathlib import Path

import pytest
from coverage import CoverageData
from scripts.ci.collect_coverage import collect_coverage_artifacts
from scripts.ci.summarize_junit import parse_junit_report, render_summary

pytestmark = pytest.mark.unit
EXPECTED_COVERAGE_ARTIFACTS = 2


def _write_branch_coverage(path: Path) -> None:
    """Write a minimal valid branch-coverage database for artifact tests.

    The collector checks actual Coverage.py data rather than accepting any
    non-empty file with a matching name.
    """
    data = CoverageData(basename=str(path))
    data.add_arcs({"sample.py": {(-1, 1), (1, -1)}})
    data.write()


def test_junit_report_counts_results_from_a_suite(tmp_path: Path) -> None:
    """Parse actual tests, failures, errors, and skipped cases.

    The resulting totals are suitable for an Actions job summary.
    """
    report = tmp_path / "report.xml"
    report.write_text(
        '<testsuite tests="5" failures="1" errors="1" skipped="1">'
        "</testsuite>\n",
        encoding="utf-8",
    )

    result = parse_junit_report(report)

    assert result == {
        "tests": 5,
        "failures": 1,
        "errors": 1,
        "skipped": 1,
        "passed": 2,
    }
    assert "2 passed" in render_summary(result)


def test_junit_report_rejects_missing_or_empty_suites(tmp_path: Path) -> None:
    """Reject absent reports and reports that collected no tests.

    A passing empty test selection must never be summarized as useful CI.
    """
    missing = tmp_path / "missing.xml"
    with pytest.raises(ValueError, match="cannot read JUnit"):
        parse_junit_report(missing)

    empty = tmp_path / "empty.xml"
    empty.write_text('<testsuite tests="0"/>', encoding="utf-8")
    with pytest.raises(ValueError, match="no tests"):
        parse_junit_report(empty)


def test_coverage_collection_requires_each_named_artifact(
    tmp_path: Path,
) -> None:
    """Copy each required coverage payload under a unique data-file name.

    The aggregate stage cannot silently omit a failed or missing test job.
    """
    categories = ("unit", "integration")
    for category in categories:
        artifact = tmp_path / "downloads" / f"coverage-{category}"
        artifact.mkdir(parents=True)
        _write_branch_coverage(artifact / ".coverage")

    output = tmp_path / "combined"
    collected = collect_coverage_artifacts(
        tmp_path / "downloads",
        output,
        expected_categories=categories,
    )

    assert collected == EXPECTED_COVERAGE_ARTIFACTS
    assert (output / ".coverage.unit").stat().st_size > 0
    assert (output / ".coverage.integration").stat().st_size > 0


def test_coverage_collection_rejects_missing_and_unexpected_artifacts(
    tmp_path: Path,
) -> None:
    """Fail closed when artifact folders do not match the required matrix.

    An extra test category requires an explicit update to the collector's
    expected inventory.
    """
    downloads = tmp_path / "downloads"
    (downloads / "coverage-unit").mkdir(parents=True)
    _write_branch_coverage(downloads / "coverage-unit" / ".coverage")
    (downloads / "coverage-extra").mkdir()

    with pytest.raises(ValueError, match="artifact inventory"):
        collect_coverage_artifacts(
            downloads,
            tmp_path / "combined",
            expected_categories=("unit", "integration"),
        )


def test_coverage_collection_rejects_invalid_category_names(
    tmp_path: Path,
) -> None:
    """Reject category names that could escape the aggregate directory.

    Artifact labels become filenames and must stay path-safe.
    """
    with pytest.raises(ValueError, match="invalid coverage category"):
        collect_coverage_artifacts(
            tmp_path,
            tmp_path / "combined",
            expected_categories=("../unit",),
        )
