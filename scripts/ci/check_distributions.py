"""Validate built wheel and source archive contents.

Distribution inspection runs without importing the package or executing
archive code. Repository-specific development instructions stay out of both
published artifact formats.
"""

from __future__ import annotations

import argparse
import sys
import tarfile
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

WHEEL_REQUIRED_SUFFIXES = (
    "/METADATA",
    "/entry_points.txt",
    "/licenses/LICENSE",
    "/licenses/THIRD_PARTY_NOTICES.md",
)
SDIST_REQUIRED_SUFFIXES = (
    "/pyproject.toml",
    "/src/titanspan/__init__.py",
    "/LICENSE",
    "/THIRD_PARTY_NOTICES.md",
)
FORBIDDEN_PARTS = {
    ".agents",
    ".github",
    "AGENTS.md",
    ".env",
    ".cache",
    "__pycache__",
}
CI_PATH_PART_COUNT = 2

__all__ = [
    "main",
    "validate_distribution_directory",
    "validate_sdist",
    "validate_wheel",
]


def _contains_forbidden_content(members: list[str]) -> list[str]:
    """Report development-only instruction and cache paths in an archive.

    Args:
        members: POSIX paths read from an archive without extraction.

    Returns:
        Diagnostics for forbidden development-only archive members.
    """
    errors: list[str] = []
    for member in members:
        parts = PurePosixPath(member).parts
        if any(part in FORBIDDEN_PARTS for part in parts):
            errors.append(
                f"development-only path must not be packaged: {member}"
            )
        if len(parts) >= CI_PATH_PART_COUNT and parts[:CI_PATH_PART_COUNT] == (
            "scripts",
            "ci",
        ):
            errors.append(
                f"CI validation script must not be packaged: {member}"
            )
        if any(part.startswith(".coverage") for part in parts):
            errors.append(f"coverage artifact must not be packaged: {member}")
    return errors


def validate_wheel(
    members: list[str],
    metadata: str,
    entry_points: str,
) -> list[str]:
    """Validate runtime metadata, typing, CLI, and development-file policy.

    Args:
        members: Wheel archive member paths.
        metadata: Contents of the unique wheel METADATA file.
        entry_points: Contents of the unique wheel entry-points file.

    Returns:
        Missing or invalid package contract diagnostics.
    """
    errors = _contains_forbidden_content(members)
    if "titanspan/py.typed" not in members:
        errors.append("wheel is missing titanspan/py.typed")
    for suffix in WHEEL_REQUIRED_SUFFIXES:
        if not any(member.endswith(suffix) for member in members):
            errors.append(f"wheel is missing required file ending {suffix}")
    if "Name: titanspan\n" not in metadata:
        errors.append("wheel metadata must declare Name: titanspan")
    if "Requires-Python: >=3.12" not in metadata:
        errors.append("wheel metadata must require Python 3.12 or later")
    if "[console_scripts]" not in entry_points:
        errors.append("wheel entry points must declare console_scripts")
    if "titanspan = titanspan.console.cli:main" not in entry_points:
        errors.append("wheel must expose the titanspan CLI entry point")
    return errors


def validate_sdist(members: list[str]) -> list[str]:
    """Validate source build inputs and exclude development governance files.

    Args:
        members: Source archive member paths.

    Returns:
        Missing build input or forbidden development-file diagnostics.

    Raises:
        ValueError: If archive inspection yields no members.
    """
    if not members:
        reason = "source distribution inventory must not be empty"
        raise ValueError(reason)

    errors = _contains_forbidden_content(members)
    for suffix in SDIST_REQUIRED_SUFFIXES:
        if not any(member.endswith(suffix) for member in members):
            errors.append(f"source distribution is missing {suffix}")
    return errors


def validate_distribution_directory(path: Path) -> list[str]:
    """Inspect exactly one wheel and one source archive in a build directory.

    Args:
        path: Directory containing the build artifacts.

    Returns:
        Artifact content and inventory diagnostics.
    """
    wheels = sorted(path.glob("*.whl"))
    source_archives = sorted(path.glob("*.tar.gz"))
    if len(wheels) != 1 or len(source_archives) != 1:
        return [
            "distribution directory must contain exactly one wheel and "
            "one .tar.gz source archive"
        ]

    errors: list[str] = []
    try:
        with ZipFile(wheels[0]) as wheel:
            members = wheel.namelist()
            metadata_paths = [
                item for item in members if item.endswith(".dist-info/METADATA")
            ]
            entry_paths = [
                item
                for item in members
                if item.endswith(".dist-info/entry_points.txt")
            ]
            if len(metadata_paths) != 1:
                errors.append("wheel must contain exactly one METADATA file")
            if len(entry_paths) != 1:
                errors.append(
                    "wheel must contain exactly one entry_points.txt file"
                )
            metadata = (
                wheel.read(metadata_paths[0]).decode("utf-8")
                if len(metadata_paths) == 1
                else ""
            )
            entry_points = (
                wheel.read(entry_paths[0]).decode("utf-8")
                if len(entry_paths) == 1
                else ""
            )
            errors.extend(validate_wheel(members, metadata, entry_points))
    except (BadZipFile, OSError, UnicodeError) as exc:
        errors.append(f"cannot inspect wheel {wheels[0]}: {exc}")

    try:
        with tarfile.open(source_archives[0], mode="r:gz") as archive:
            errors.extend(validate_sdist(archive.getnames()))
    except (OSError, tarfile.TarError, ValueError) as exc:
        errors.append(
            f"cannot inspect source archive {source_archives[0]}: {exc}"
        )
    return errors


def main() -> int:
    """Validate built artifacts and report distribution violations.

    Return a nonzero process status when either archive violates the
    installable package contract.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?", default=Path("dist"))
    args = parser.parse_args()

    errors = validate_distribution_directory(args.directory)
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    sys.stdout.write("Wheel and source archive contents passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
