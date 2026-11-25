"""Collect one compatible coverage artifact from each mandatory test job.

Artifacts are expected from Linux and the canonical Python runtime only, so
their source paths and coverage database versions remain compatible.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from shutil import copyfile

from coverage import CoverageData
from coverage.exceptions import CoverageException

COVERAGE_CATEGORIES = (
    "unit",
    "integration",
    "feature",
    "regression",
    "concurrency",
    "security",
    "compatibility",
    "public-api",
)
CATEGORY_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

__all__ = [
    "COVERAGE_CATEGORIES",
    "collect_coverage_artifacts",
    "main",
]


def _valid_coverage_file(path: Path) -> bool:
    """Check that one artifact is readable branch coverage with measured files.

    Args:
        path: Coverage.py SQLite data file.

    Returns:
        Whether data can be read and contains branches and measured files.
    """
    try:
        data = CoverageData(basename=str(path))
        data.read()
    except CoverageException:
        return False
    return data.has_arcs() and bool(data.measured_files())


def _read_coverage_sources(
    download_root: Path,
    categories: tuple[str, ...],
) -> dict[str, Path]:
    """Validate every required artifact directory and branch-data file.

    Args:
        download_root: Directory populated by Actions artifact download.
        categories: Validated coverage category labels.

    Returns:
        A category-to-source-file mapping.

    Raises:
        ValueError: If directories or data files are missing or invalid.
    """
    expected_directories = {f"coverage-{category}" for category in categories}
    try:
        actual_directories = {
            path.name for path in download_root.iterdir() if path.is_dir()
        }
    except OSError as exc:
        reason = f"cannot read coverage artifact directory: {exc}"
        raise ValueError(reason) from exc
    if actual_directories != expected_directories:
        reason = (
            "coverage artifact inventory mismatch: "
            f"expected {sorted(expected_directories)}, "
            f"received {sorted(actual_directories)}"
        )
        raise ValueError(reason)

    sources: dict[str, Path] = {}
    for category in categories:
        source = download_root / f"coverage-{category}" / ".coverage"
        if not source.is_file() or source.stat().st_size == 0:
            reason = f"missing or empty coverage artifact for {category}"
            raise ValueError(reason)
        if not _valid_coverage_file(source):
            reason = f"invalid branch coverage artifact for {category}"
            raise ValueError(reason)
        sources[category] = source
    return sources


def _copy_coverage_sources(
    sources: dict[str, Path],
    output_directory: Path,
) -> int:
    """Copy validated coverage files to unique data-file names.

    Args:
        sources: Category-to-coverage-file mapping already validated.
        output_directory: New location for aggregate input data.

    Returns:
        Number of copied coverage databases.

    Raises:
        ValueError: If the destination already contains coverage data.
    """
    if output_directory.exists():
        existing = list(output_directory.glob(".coverage.*"))
        if existing:
            reason = "coverage output directory already contains data files"
            raise ValueError(reason)
    output_directory.mkdir(parents=True, exist_ok=True)
    for category, source in sources.items():
        copyfile(source, output_directory / f".coverage.{category}")
    return len(sources)


def collect_coverage_artifacts(
    download_root: Path,
    output_directory: Path,
    *,
    expected_categories: tuple[str, ...] = COVERAGE_CATEGORIES,
) -> int:
    """Validate and copy one branch-coverage file per required test category.

    Args:
        download_root: Directory populated by Actions artifact download.
        output_directory: New directory for uniquely named coverage files.
        expected_categories: Required artifact category labels.

    Returns:
        Number of verified artifacts copied into the output directory.

    Raises:
        ValueError: If inventory, data files, or destination are invalid.
    """
    if not expected_categories or any(
        CATEGORY_PATTERN.fullmatch(category) is None
        for category in expected_categories
    ):
        reason = "invalid coverage category inventory"
        raise ValueError(reason)
    if len(expected_categories) != len(set(expected_categories)):
        reason = "coverage categories must be unique"
        raise ValueError(reason)

    sources = _read_coverage_sources(download_root, expected_categories)
    return _copy_coverage_sources(sources, output_directory)


def main() -> int:
    """Collect verified artifacts and report the category count.

    Return a nonzero process status when a required job artifact is missing
    or contains invalid coverage data.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("download_root", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()

    try:
        count = collect_coverage_artifacts(
            args.download_root,
            args.output_directory,
        )
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1
    sys.stdout.write(f"Collected {count} coverage artifacts.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
