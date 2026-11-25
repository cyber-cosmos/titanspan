"""Summarize Pytest JUnit XML reports without masking test failures.

The summary reports counts from the generated XML. The pytest step remains
responsible for its own exit status.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import cast
from xml.etree import ElementTree as XmlElementTree

from defusedxml import ElementTree

RESULT_KEYS = ("tests", "failures", "errors", "skipped")

__all__ = ["main", "parse_junit_report", "render_summary"]


def _count_attribute(element: XmlElementTree.Element, name: str) -> int:
    """Read one non-negative integer counter from a JUnit element.

    Args:
        element: Parsed suite or suites root.
        name: Counter attribute to validate.

    Returns:
        A non-negative test count.

    Raises:
        ValueError: If the attribute is absent, malformed, or negative.
    """
    raw_value = element.attrib.get(name)
    if raw_value is None or not raw_value.isdigit():
        reason = f"JUnit report has an invalid {name} counter"
        raise ValueError(reason)
    return int(raw_value)


def parse_junit_report(path: Path) -> dict[str, int]:
    """Read actual Pytest execution counts from a JUnit XML report.

    Args:
        path: Report path created by Pytest.

    Returns:
        Test, failure, error, skipped, and derived passed counts.

    Raises:
        ValueError: If the report is unreadable, malformed, or empty.
    """
    try:
        # defusedxml has no published typing stubs. Keep its parser at this
        # boundary and use the compatible standard-library element types.
        parsed_tree = cast(
            "XmlElementTree.ElementTree[XmlElementTree.Element]",
            ElementTree.parse(path),
        )
        root = parsed_tree.getroot()
    except (OSError, XmlElementTree.ParseError, ValueError) as exc:
        reason = f"cannot read JUnit report {path}: {exc}"
        raise ValueError(reason) from exc
    if root.tag not in {"testsuite", "testsuites"}:
        reason = "JUnit report root must be testsuite or testsuites"
        raise ValueError(reason)

    if root.tag == "testsuite":
        totals = {
            key: int(root.attrib.get(key, "0"))
            if root.attrib.get(key, "0").isdigit()
            else _count_attribute(root, key)
            for key in RESULT_KEYS
        }
    elif all(key in root.attrib for key in RESULT_KEYS):
        totals = {key: _count_attribute(root, key) for key in RESULT_KEYS}
    else:
        suites = [
            element for element in root.iter("testsuite") if element is not root
        ]
        if not suites:
            reason = "JUnit report does not contain a test suite"
            raise ValueError(reason)
        totals = {
            key: sum(_count_attribute(suite, key) for suite in suites)
            for key in RESULT_KEYS
        }

    totals["passed"] = (
        totals["tests"]
        - totals["failures"]
        - totals["errors"]
        - totals["skipped"]
    )
    if totals["tests"] == 0:
        reason = "JUnit report contains no tests"
        raise ValueError(reason)
    if totals["passed"] < 0:
        reason = "JUnit counters exceed the total test count"
        raise ValueError(reason)
    return totals


def render_summary(results: dict[str, int]) -> str:
    """Render test counts as concise Actions job-summary Markdown.

    Args:
        results: Validated report totals from ``parse_junit_report``.

    Returns:
        Markdown containing actual test outcomes.
    """
    return (
        "## Test results\n\n"
        f"- {results['passed']} passed\n"
        f"- {results['failures']} failed\n"
        f"- {results['errors']} errors\n"
        f"- {results['skipped']} skipped\n"
        f"- {results['tests']} total\n"
    )


def main() -> int:
    """Write actual test counts to the job summary.

    Return a nonzero process status when the report is malformed or the
    GitHub summary cannot be written.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    try:
        results = parse_junit_report(args.report)
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    summary = render_summary(results)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with Path(summary_path).open("a", encoding="utf-8") as stream:
                stream.write(summary)
        except OSError as exc:
            sys.stderr.write(f"ERROR: cannot write job summary: {exc}\n")
            return 1
    sys.stdout.write(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
