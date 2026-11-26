"""Validate repository prose with the pinned Vale executable.

The runner delegates parsing and style rules to Vale. It filters the corpus
to maintained Markdown and Python source, then applies the repository's
error-only blocking policy.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
HARD_RULES = frozenset(
    {
        "Titanspan.Capitalization",
        "Titanspan.Terminology",
        "Titanspan.ProhibitedExpressions",
    }
)
TERMINOLOGY_RULES = frozenset(
    {
        "Titanspan.Capitalization",
        "Titanspan.Terminology",
    }
)
LEGAL_FILES = frozenset({"THIRD_PARTY_NOTICES.md"})
EXCLUDED_PREFIXES = (
    ".vale/",
    ".cache/",
    ".venv/",
    "build/",
    "dist/",
    "docs/.astro/",
    "docs/dist/",
    "docs/node_modules/",
    "node_modules/",
    "test-results/",
    "tests/prose/fixtures/",
)


@dataclass(frozen=True, slots=True)
class Alert:
    """Store the Vale fields needed for a concise repository report.

    Attributes:
        path: Repository-relative source path.
        line: One-based source line.
        check: Vale rule identifier.
        severity: Vale alert level.
        message: Rule-specific diagnostic.
    """

    path: str
    line: int
    check: str
    severity: str
    message: str


class ProseCheckError(RuntimeError):
    """Report failures in the prose tooling integration.

    The exception gives each Make target one concise error path for missing
    binaries, invalid output, and failed Vale commands.
    """


def _string_mapping(value: object) -> dict[str, object] | None:
    """Narrow JSON values to dictionaries with string keys.

    Args:
        value: Parsed JSON value.

    Returns:
        A string-keyed dictionary or ``None`` for another shape.
    """
    if not isinstance(value, dict):
        return None

    raw_mapping = cast("dict[object, object]", value)
    mapping: dict[str, object] = {}
    for key, item in raw_mapping.items():
        if not isinstance(key, str):
            return None
        mapping[key] = item
    return mapping


def _vale_executable() -> str:
    """Find the pinned Vale binary in the environment or project cache.

    Returns:
        A command path that can run Vale.

    Raises:
        ProseCheckError: If Vale is missing or its version does not match.
    """
    configured = os.environ.get("VALE")
    on_path = shutil.which("vale")
    cached = ROOT / ".cache" / "tools" / "vale" / _version() / "vale"
    homebrew_paths = (
        Path("/opt/homebrew/bin/vale"),
        Path("/usr/local/bin/vale"),
    )
    expected = f"vale version {_version()}"
    candidates = [configured] if configured else []
    candidates.extend([on_path] if on_path else [])
    candidates.extend(str(path) for path in homebrew_paths if path.is_file())
    candidates.extend([str(cached)] if cached.is_file() else [])
    for executable in candidates:
        try:
            # The candidates are explicit paths, and Vale receives no shell.
            result = subprocess.run(  # noqa: S603
                [executable, "--version"],
                cwd=ROOT,
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError:
            if configured:
                reason = (
                    f"Could not run VALE={configured}; "
                    f"install Vale {_version()}."
                )
                raise ProseCheckError(reason) from None
            continue
        if result.returncode == 0 and result.stdout.strip() == expected:
            return executable

    reason = f"Vale {_version()} is required; run `make vale-install`."
    raise ProseCheckError(reason)


def _version() -> str:
    """Read the repository's pinned Vale version.

    Returns:
        The exact Vale release version.
    """
    return (ROOT / ".vale-version").read_text(encoding="utf-8").strip()


def _maintained_prose_files() -> list[str]:
    """List first-party Markdown and Python files tracked by Git.

    Returns:
        Relative paths to maintained documents and source files.

    Raises:
        ProseCheckError: If Git cannot provide the repository file list.
    """
    git = shutil.which("git")
    if git is None:
        reason = "Git is required to list repository source files."
        raise ProseCheckError(reason)

    # Git and its fixed arguments are resolved locally without shell parsing.
    result = subprocess.run(  # noqa: S603
        [
            git,
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        reason = "Git could not list repository source files."
        raise ProseCheckError(reason)

    filenames = result.stdout.decode("utf-8").split("\0")
    selected: list[str] = []
    for filename in filenames:
        if not filename or filename in LEGAL_FILES:
            continue
        if filename.startswith(EXCLUDED_PREFIXES):
            continue
        if Path(filename).suffix.lower() not in {".md", ".markdown", ".py"}:
            continue
        if (ROOT / filename).is_file():
            selected.append(filename)
    return sorted(selected)


def _alerts_from_json(payload: str) -> list[Alert]:
    """Validate Vale's JSON output and convert supported alert fields.

    Args:
        payload: Vale JSON output for one or more source files.

    Returns:
        Alerts with repository-relative paths and source lines.

    Raises:
        ProseCheckError: If Vale returns malformed or unsupported JSON.
    """
    try:
        value: object = json.loads(payload)
    except json.JSONDecodeError as exc:
        reason = "Vale returned malformed JSON output."
        raise ProseCheckError(reason) from exc

    files = _string_mapping(value)
    if files is None:
        reason = "Vale JSON output must map file paths to alerts."
        raise ProseCheckError(reason)

    alerts: list[Alert] = []
    for path, entries in files.items():
        if not isinstance(entries, list):
            reason = f"Vale returned invalid alerts for {path}."
            raise ProseCheckError(reason)
        for entry in cast("list[object]", entries):
            alert = _string_mapping(entry)
            if alert is None:
                reason = f"Vale returned an invalid alert for {path}."
                raise ProseCheckError(reason)
            check = alert.get("Check")
            line = alert.get("Line")
            severity = alert.get("Severity")
            message = alert.get("Message")
            if (
                not isinstance(check, str)
                or not isinstance(line, int)
                or isinstance(line, bool)
                or not isinstance(severity, str)
                or not isinstance(message, str)
            ):
                reason = f"Vale returned an incomplete alert for {path}."
                raise ProseCheckError(reason)
            if severity not in {"suggestion", "warning", "error"}:
                reason = (
                    f"Vale returned an unknown severity for {check}: "
                    f"{severity}."
                )
                raise ProseCheckError(reason)
            alerts.append(Alert(path, line, check, severity, message))
    return alerts


def _run_vale(
    executable: str,
    arguments: list[str],
) -> subprocess.CompletedProcess[str]:
    """Run Vale without masking configuration or parsing failures.

    Args:
        executable: Pinned Vale binary path.
        arguments: Vale subcommand and arguments.

    Returns:
        The completed Vale process result.

    Raises:
        ProseCheckError: If Vale cannot start.
    """
    try:
        # The pinned Vale path is executed directly, without shell parsing.
        return subprocess.run(  # noqa: S603
            [executable, *arguments],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as exc:
        reason = f"Could not start Vale: {exc}"
        raise ProseCheckError(reason) from exc


def _validate_config(executable: str) -> None:
    """Ask Vale to parse the repository configuration before linting.

    Args:
        executable: Pinned Vale binary path.

    Raises:
        ProseCheckError: If Vale rejects the configuration.
    """
    result = _run_vale(executable, ["ls-config"])
    if result.returncode != 0:
        diagnostic = result.stderr.strip() or result.stdout.strip()
        reason = f"Vale configuration is invalid:\n{diagnostic}"
        raise ProseCheckError(reason)


def _lint_repository(executable: str) -> list[Alert]:
    """Lint the maintained prose corpus using the active repository config.

    Args:
        executable: Pinned Vale binary path.

    Returns:
        All warnings, suggestions, and errors from Vale.

    Raises:
        ProseCheckError: If there are no files or Vale fails to run.
    """
    filenames = _maintained_prose_files()
    if not filenames:
        reason = "No maintained Markdown or Python files were found."
        raise ProseCheckError(reason)
    result = _run_vale(
        executable,
        ["--no-exit", "--output=JSON", *filenames],
    )
    if result.returncode != 0:
        diagnostic = result.stderr.strip() or result.stdout.strip()
        reason = f"Vale failed while linting prose:\n{diagnostic}"
        raise ProseCheckError(reason)
    return _alerts_from_json(result.stdout)


def _report(alerts: list[Alert], *, terminology_only: bool) -> bool:
    """Print findings and return whether blocking errors were found.

    Args:
        alerts: Parsed alerts from Vale.
        terminology_only: Whether to report only canonical terminology rules.

    Returns:
        Whether the selected alerts contain an error-level finding.
    """
    selected = [
        alert
        for alert in alerts
        if not terminology_only or alert.check in TERMINOLOGY_RULES
    ]
    errors = [alert for alert in selected if alert.severity == "error"]
    advisory = [alert for alert in selected if alert.severity != "error"]
    for alert in errors:
        sys.stdout.write(
            f"{alert.path}:{alert.line}: error: "
            f"{alert.check}: {alert.message}\n"
        )

    counts = Counter((alert.severity, alert.check) for alert in advisory)
    if counts:
        sys.stdout.write("Advisory prose findings:\n")
        for (severity, check), count in sorted(counts.items()):
            sys.stdout.write(f"  {severity}: {check}: {count}\n")
            examples = [
                alert
                for alert in advisory
                if alert.severity == severity and alert.check == check
            ][:2]
            for alert in examples:
                sys.stdout.write(
                    f"    {alert.path}:{alert.line}: {alert.message}\n"
                )

    if not errors:
        sys.stdout.write("No blocking prose findings.\n")
    return bool(errors)


def _test_invalid_config(executable: str) -> None:
    """Verify Vale fails closed when a setting has an invalid value.

    Args:
        executable: Pinned Vale binary path.

    Raises:
        ProseCheckError: If Vale accepts invalid configuration.
    """
    with TemporaryDirectory(prefix="titanspan-vale-test-") as directory:
        config = Path(directory) / ".vale.ini"
        config.write_text(
            "MinAlertLevel = impossible\n",
            encoding="utf-8",
        )
        result = _run_vale(
            executable,
            [f"--config={config}", "ls-config"],
        )
    if result.returncode == 0 or "MinAlertLevel" not in result.stderr:
        reason = (
            "Vale did not reject the invalid configuration regression case."
        )
        raise ProseCheckError(reason)
    sys.stdout.write("Vale rejects invalid configuration values.\n")


def _run_rule_tests(executable: str) -> None:
    """Run native Vale rule coverage and repository configuration cases.

    Args:
        executable: Pinned Vale binary path.

    Raises:
        ProseCheckError: If config validation or a rule test fails.
    """
    _validate_config(executable)
    result = _run_vale(
        executable,
        [
            "test",
            "--coverage",
            ".vale/styles/Titanspan",
            "tests/prose",
        ],
    )
    if result.returncode != 0:
        diagnostic = result.stdout.strip() or result.stderr.strip()
        reason = (
            "Vale rule tests failed; run `make vale-sync` first if its "
            f"styles or Python grammar are missing:\n{diagnostic}"
        )
        raise ProseCheckError(reason)
    if result.stdout:
        sys.stdout.write(f"{result.stdout.strip()}\n")
    _test_invalid_config(executable)


def main() -> int:
    """Run one read-only Vale operation selected by the Makefile.

    Returns:
        Process status for the requested operation.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("sync", "prose", "terminology", "test"),
    )
    options = parser.parse_args()

    try:
        executable = _vale_executable()
        if options.command == "sync":
            result = _run_vale(executable, ["sync"])
            if result.stdout:
                sys.stdout.write(result.stdout)
            if result.stderr:
                sys.stderr.write(result.stderr)
            return result.returncode
        if options.command == "test":
            _run_rule_tests(executable)
            return 0

        _validate_config(executable)
        alerts = _lint_repository(executable)
        failed = _report(
            alerts,
            terminology_only=options.command == "terminology",
        )
        return int(failed)
    except (OSError, ProseCheckError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
