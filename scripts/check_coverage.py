"""Enforce separate minimum line and branch coverage percentages.

The line threshold is read from coverage.py configuration, while the branch
threshold is read from the Titanspan quality policy in pyproject.toml.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tomllib
from pathlib import Path
from typing import TypeGuard, cast

MINIMUM_COVERAGE_PERCENTAGE = 0.0
MAXIMUM_COVERAGE_PERCENTAGE = 100.0

__all__ = [
    "main",
    "read_coverage_policy",
    "render_coverage_summary",
    "validate_coverage",
]


class CoveragePolicyError(Exception):
    """Describe invalid coverage configuration or report data.

    The exception centralizes coverage diagnostics while preserving the input
    path that needs correction.
    """

    def __init__(self, path: Path, reason: str) -> None:
        """Store the path and concise validation reason.

        Args:
            path: Project configuration or generated report being checked.
            reason: Explanation of the invalid input or configuration.
        """
        message = f"{path}: {reason}"
        super().__init__(message)


def _string_mapping(value: object) -> dict[str, object] | None:
    """Narrow an untrusted parser object to a string-keyed dictionary.

    Args:
        value: TOML or JSON parser output, or a nested table value.

    Returns:
        A string-keyed dictionary, or ``None`` for another shape.
    """
    if not isinstance(value, dict):
        return None

    # Parser outputs carry Any values; validate keys before using table data.
    raw_mapping = cast("dict[object, object]", value)
    result: dict[str, object] = {}
    for key, item in raw_mapping.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def validate_coverage(
    totals: dict[str, object],
    *,
    minimum_line_coverage: float,
    minimum_branch_coverage: float,
) -> list[str]:
    """Check line and branch coverage independently.

    Args:
        totals: The ``totals`` object from a coverage.py JSON report.
        minimum_line_coverage: Required statement coverage percentage.
        minimum_branch_coverage: Required branch coverage percentage.

    Returns:
        A diagnostic for each absent or under-threshold metric.
    """
    errors: list[str] = []
    metrics = (
        (
            "percent_statements_covered",
            "line coverage",
            minimum_line_coverage,
        ),
        (
            "percent_branches_covered",
            "branch coverage",
            minimum_branch_coverage,
        ),
    )
    for key, label, threshold in metrics:
        value = totals.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            errors.append(f"coverage report is missing a valid {label} metric")
        elif value < threshold:
            errors.append(
                f"{label} is {value:.2f}%; minimum is {threshold:.2f}%"
            )
    return errors


def render_coverage_summary(
    totals: dict[str, object],
    *,
    minimum_line_coverage: float,
    minimum_branch_coverage: float,
) -> str:
    """Render measured coverage values and policy thresholds for CI.

    Args:
        totals: Coverage.py totals object from the combined report.
        minimum_line_coverage: Required statement coverage percentage.
        minimum_branch_coverage: Required branch coverage percentage.

    Returns:
        A Markdown table populated from the actual report metrics.

    Raises:
        ValueError: If either coverage metric is missing or invalid.
    """
    line = totals.get("percent_statements_covered")
    branch = totals.get("percent_branches_covered")
    if not _is_coverage_percentage(line):
        reason = "coverage report is missing a valid line metric"
        raise ValueError(reason)
    if not _is_coverage_percentage(branch):
        reason = "coverage report is missing a valid branch metric"
        raise ValueError(reason)

    line_status = "Passed" if line >= minimum_line_coverage else "Failed"
    branch_status = "Passed" if branch >= minimum_branch_coverage else "Failed"
    return (
        "| Metric | Measured | Minimum | Result |\n"
        "|---|---:|---:|---|\n"
        f"| Line coverage | {line:.2f}% | "
        f"{minimum_line_coverage:.2f}% | {line_status} |\n"
        f"| Branch coverage | {branch:.2f}% | "
        f"{minimum_branch_coverage:.2f}% | {branch_status} |\n"
    )


def read_coverage_policy(path: Path) -> tuple[float, float]:
    """Read coverage thresholds from the repository's TOML configuration.

    Args:
        path: Repository pyproject.toml path.

    Returns:
        The configured line and branch coverage thresholds.

    Raises:
        CoveragePolicyError: If configuration is missing or malformed.
    """
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        reason = f"cannot read project configuration: {exc}"
        raise CoveragePolicyError(path, reason) from exc

    configuration = _string_mapping(cast("object", parsed))
    if configuration is None:
        raise CoveragePolicyError(path, "expected a TOML table")
    tool = _string_mapping(configuration.get("tool"))
    if tool is None:
        raise CoveragePolicyError(path, "missing [tool] configuration")

    coverage = _string_mapping(tool.get("coverage"))
    if coverage is None:
        raise CoveragePolicyError(path, "missing [tool.coverage] configuration")
    report = _string_mapping(coverage.get("report"))
    titanspan = _string_mapping(tool.get("titanspan"))
    quality = _string_mapping(titanspan.get("quality")) if titanspan else None
    if report is None or quality is None:
        raise CoveragePolicyError(path, "missing coverage threshold settings")

    line_threshold = report.get("fail_under")
    branch_threshold = quality.get("minimum-branch-coverage")
    if not _is_coverage_percentage(line_threshold):
        raise CoveragePolicyError(path, "invalid line coverage threshold")
    if not _is_coverage_percentage(branch_threshold):
        raise CoveragePolicyError(path, "invalid branch coverage threshold")
    return float(line_threshold), float(branch_threshold)


def _is_coverage_percentage(value: object) -> TypeGuard[int | float]:
    """Check that a configured threshold is a finite percentage.

    Args:
        value: Parsed coverage threshold from project configuration.

    Returns:
        Whether the value is numeric and lies within percentage bounds.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return (
        MINIMUM_COVERAGE_PERCENTAGE <= value <= MAXIMUM_COVERAGE_PERCENTAGE
        and math.isfinite(value)
    )


def _load_totals(path: Path) -> dict[str, object]:
    """Load and validate totals from a coverage.py JSON report.

    Args:
        path: Coverage JSON report path.

    Returns:
        A string-keyed totals mapping.

    Raises:
        CoveragePolicyError: If the report cannot be parsed or lacks totals.
    """
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        reason = f"cannot read coverage report: {exc}"
        raise CoveragePolicyError(path, reason) from exc

    report = _string_mapping(cast("object", parsed))
    if report is None:
        raise CoveragePolicyError(path, "expected a JSON object")
    totals = _string_mapping(report.get("totals"))
    if totals is None:
        raise CoveragePolicyError(path, "missing totals object")
    return totals


def main() -> int:
    """Validate generated coverage against repository policy.

    The command reports measured values and exits nonzero on invalid or
    insufficient coverage.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "report",
        type=Path,
        nargs="?",
        default=Path("coverage.json"),
        help="coverage.py JSON report path",
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("pyproject.toml"),
        help="project configuration path",
    )
    args = parser.parse_args()

    try:
        minimum_line, minimum_branch = read_coverage_policy(args.pyproject)
        totals = _load_totals(args.report)
    except CoveragePolicyError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    errors = validate_coverage(
        totals,
        minimum_line_coverage=minimum_line,
        minimum_branch_coverage=minimum_branch,
    )
    try:
        summary = render_coverage_summary(
            totals,
            minimum_line_coverage=minimum_line,
            minimum_branch_coverage=minimum_branch,
        )
        github_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if github_summary:
            with Path(github_summary).open("a", encoding="utf-8") as stream:
                stream.write(summary)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"ERROR: cannot write coverage summary: {exc}\n")
        return 1
    sys.stdout.write(summary)
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1

    sys.stdout.write(
        f"Coverage passed: lines {totals['percent_statements_covered']}%, "
        f"branches {totals['percent_branches_covered']}%.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
