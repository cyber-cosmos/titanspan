"""Validate GitHub Actions job graphs and immutable external action pins.

The primary workflow has a fixed mandatory-job inventory. This checker
ensures every job is visible, bounded by a timeout, and included in the
fail-closed gate.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from typing import cast

import yaml

from scripts.ci.check_gate import EXPECTED_JOBS

GATE_JOB_ID = "ci-gate"
PYTHON_MATRIX = ("3.12", "3.13", "3.14", "3.15")
PLATFORM_MATRIX = ("macos-latest", "windows-latest")
COVERAGE_INPUT_JOBS = (
    "unit-tests",
    "integration-tests",
    "feature-tests",
    "regression-tests",
    "concurrency-tests",
    "security-tests",
    "compatibility-tests",
    "public-api",
)
JOB_UNVISITED = 0
JOB_VISITING = 1
JOB_VISITED = 2
ACTION_LINE = re.compile(r"^\s*uses:\s*([^\s#]+)(?:\s+#\s*(.*))?\s*$")
IMMUTABLE_ACTION = re.compile(r"^[^/@]+/[^@]+@([0-9a-f]{40})$")
VERSION_ANNOTATION = re.compile(r"^v[0-9][A-Za-z0-9_.+-]*$")

__all__ = [
    "main",
    "validate_action_references",
    "validate_ci_workflow",
    "validate_repository",
]


def _string_mapping(value: object) -> dict[str, object] | None:
    """Narrow a parsed YAML object to a dictionary with string keys.

    Args:
        value: YAML parser output from a workflow document.

    Returns:
        A string-keyed mapping, or ``None`` when the value is malformed.
    """
    if not isinstance(value, dict):
        return None

    raw_mapping = cast("dict[object, object]", value)
    result: dict[str, object] = {}
    for key, item in raw_mapping.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def _string_list(value: object) -> list[str] | None:
    """Narrow a parsed YAML sequence to a list of strings.

    Args:
        value: YAML parser output expected to contain job identifiers.

    Returns:
        String list, or ``None`` when the sequence has invalid values.
    """
    if not isinstance(value, list):
        return None
    raw_values = cast("list[object]", value)
    if not all(isinstance(item, str) for item in raw_values):
        return None
    return cast("list[str]", raw_values)


def _is_positive_integer(value: object) -> bool:
    """Check a parsed numeric timeout without accepting booleans.

    Args:
        value: Parsed YAML scalar.

    Returns:
        Whether the value is a positive integer or decimal digit string.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value > 0
    return isinstance(value, str) and value.isdigit() and int(value) > 0


def _has_gate_validator(steps_value: object) -> bool:
    """Check that the gate passes its complete needs object to the validator.

    Args:
        steps_value: Parsed list of steps from the final gate.

    Returns:
        Whether a step invokes the validator with CI_NEEDS_JSON.
    """
    if not isinstance(steps_value, list):
        return False
    steps = cast("list[object]", steps_value)
    for value in steps:
        step = _string_mapping(value)
        if step is None:
            continue
        environment = _string_mapping(step.get("env"))
        if (
            "scripts.ci.check_gate" in str(step.get("run", ""))
            and environment is not None
            and "CI_NEEDS_JSON" in environment
        ):
            return True
    return False


def validate_action_references(workflow_text: str) -> list[str]:
    """Require external GitHub Actions to use SHA pins and release comments.

    Args:
        workflow_text: Raw workflow or composite action YAML.

    Returns:
        Diagnostics for mutable, malformed, or unannotated action references.
    """
    errors: list[str] = []
    for line_number, line in enumerate(workflow_text.splitlines(), start=1):
        if not re.match(r"^\s*uses:\s*", line):
            continue
        match = ACTION_LINE.match(line)
        if match is None:
            errors.append(f"line {line_number}: malformed uses reference")
            continue

        reference, annotation = match.groups()
        if reference.startswith("./"):
            continue
        immutable = IMMUTABLE_ACTION.fullmatch(reference)
        if immutable is None:
            errors.append(
                f"line {line_number}: action must use a full immutable SHA"
            )
            continue
        if annotation is None or not VERSION_ANNOTATION.fullmatch(
            annotation.strip()
        ):
            errors.append(
                f"line {line_number}: pinned action needs a release comment"
            )
    return errors


def _job_dependencies(job: object) -> list[str] | None:
    """Read and validate one job's optional ``needs`` field.

    Args:
        job: Parsed job mapping.

    Returns:
        Its dependency identifiers, or ``None`` for invalid data.
    """
    mapping = _string_mapping(job)
    if mapping is None:
        return None
    needs = mapping.get("needs", [])
    if isinstance(needs, str):
        return [needs]
    values = _string_list(needs)
    if values is None:
        return None
    if len(values) != len(set(values)):
        return None
    return values


def _find_dependency_cycles(
    jobs: dict[str, object],
) -> list[str]:
    """Find cycles in the workflow's explicit job dependency graph.

    Args:
        jobs: Parsed map of job identifiers to job configurations.

    Returns:
        One diagnostic for each dependency cycle discovered.
    """
    errors: list[str] = []
    job_ids = set(jobs)
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(job_id: str) -> None:
        """Walk dependencies and record a cycle when a node repeats.

        Args:
            job_id: Job being visited in depth-first order.
        """
        current_state = state.get(job_id, JOB_UNVISITED)
        if current_state == JOB_VISITED:
            return
        if current_state == JOB_VISITING:
            cycle_start = stack.index(job_id)
            cycle = " -> ".join([*stack[cycle_start:], job_id])
            errors.append(f"workflow dependency cycle: {cycle}")
            return

        state[job_id] = JOB_VISITING
        stack.append(job_id)
        dependencies = _job_dependencies(jobs[job_id])
        if dependencies is not None:
            for dependency in dependencies:
                if dependency in job_ids:
                    visit(dependency)
        stack.pop()
        state[job_id] = JOB_VISITED

    for job_id in sorted(job_ids):
        visit(job_id)
    return errors


def _validate_ci_root(root: dict[str, object]) -> list[str]:
    """Validate primary workflow triggers, permissions, and concurrency.

    Args:
        root: Parsed primary workflow mapping.

    Returns:
        Root-level policy violations.
    """
    errors: list[str] = []
    permissions = _string_mapping(root.get("permissions"))
    if permissions is None or permissions.get("contents") != "read":
        errors.append("workflow permissions must default contents to read")

    triggers = _string_mapping(root.get("on"))
    required_triggers = {"push", "pull_request", "workflow_dispatch"}
    if triggers is None or not required_triggers.issubset(triggers):
        errors.append("workflow is missing a required CI trigger")
    elif "merge_group" not in triggers:
        errors.append("workflow must support merge_group checks")
    if triggers is not None:
        for event_name in ("push", "pull_request"):
            event = _string_mapping(triggers.get(event_name))
            if event is not None and {
                "paths",
                "paths-ignore",
            }.intersection(event):
                errors.append(
                    f"primary CI must not use {event_name} path filters"
                )

    concurrency = _string_mapping(root.get("concurrency"))
    if concurrency is None or concurrency.get("cancel-in-progress") != (
        "${{ github.event_name == 'pull_request' }}"
    ):
        errors.append("CI concurrency may cancel superseded pull requests only")
    return errors


def _validate_job_inventory(jobs: dict[str, object]) -> list[str]:
    """Validate job identifiers, timeouts, dependencies, and graph cycles.

    Args:
        jobs: Parsed map of job identifiers to configurations.

    Returns:
        Job inventory and dependency-policy violations.
    """
    expected_jobs = {*EXPECTED_JOBS, GATE_JOB_ID}
    actual_jobs = set(jobs)
    errors = [
        f"primary workflow is missing job: {job_id}"
        for job_id in sorted(expected_jobs - actual_jobs)
    ]
    errors.extend(
        f"unexpected primary workflow job: {job_id}"
        for job_id in sorted(actual_jobs - expected_jobs)
    )

    for job_id, job in jobs.items():
        mapping = _string_mapping(job)
        if mapping is None:
            errors.append(f"job {job_id} must be a mapping")
            continue
        if not _is_positive_integer(mapping.get("timeout-minutes")):
            errors.append(f"job {job_id} must set a positive timeout-minutes")
        if mapping.get("continue-on-error") in (True, "true"):
            errors.append(
                f"mandatory job {job_id} must not use continue-on-error"
            )
        dependencies = _job_dependencies(job)
        if dependencies is None:
            errors.append(f"job {job_id} has malformed needs dependencies")
            continue
        errors.extend(
            f"job {job_id} needs unknown job: {dependency}"
            for dependency in dependencies
            if dependency not in jobs
        )

    errors.extend(_find_dependency_cycles(jobs))
    return errors


def _validate_job_matrices(jobs: dict[str, object]) -> list[str]:
    """Verify complete Python and platform matrices without fail-fast.

    Args:
        jobs: Parsed primary workflow job mapping.

    Returns:
        Diagnostics for incomplete or canceling compatibility matrices.
    """
    errors: list[str] = []
    expected_matrices = {
        "unit-tests": ("python-version", PYTHON_MATRIX),
        "integration-tests": ("python-version", PYTHON_MATRIX),
        "platform-smoke": ("os", PLATFORM_MATRIX),
    }
    for job_id, (matrix_key, expected_values) in expected_matrices.items():
        job = _string_mapping(jobs.get(job_id))
        strategy = _string_mapping(job.get("strategy")) if job else None
        matrix = _string_mapping(strategy.get("matrix")) if strategy else None
        actual_values = _string_list(matrix.get(matrix_key)) if matrix else None
        if actual_values is None or tuple(actual_values) != expected_values:
            errors.append(
                f"job {job_id} matrix must contain {list(expected_values)}"
            )
        if strategy is None or strategy.get("fail-fast") is not False:
            errors.append(f"job {job_id} matrix must set fail-fast: false")
    return errors


def _validate_coverage_job(jobs: dict[str, object]) -> list[str]:
    """Require aggregate and changed-source coverage enforcement.

    Args:
        jobs: Parsed primary workflow job mapping.

    Returns:
        Diagnostics for incomplete coverage aggregation or thresholds.
    """
    coverage = _string_mapping(jobs.get("coverage"))
    if coverage is None:
        return ["primary workflow must define a coverage job"]

    errors: list[str] = []
    if "always()" not in str(coverage.get("if", "")):
        errors.append("coverage job must run after unsuccessful test jobs")
    dependencies = _job_dependencies(coverage)
    if dependencies is None or set(dependencies) != set(COVERAGE_INPUT_JOBS):
        errors.append("coverage job needs must match all coverage inputs")

    steps_value = coverage.get("steps")
    steps = (
        cast("list[object]", steps_value)
        if isinstance(
            steps_value,
            list,
        )
        else []
    )
    diff_coverage_runs: list[str] = []
    for step_value in steps:
        step = _string_mapping(step_value)
        if step is None:
            continue
        command = step.get("run")
        if isinstance(command, str) and "diff-cover coverage.xml" in command:
            diff_coverage_runs.append(command)

    required_tokens = (
        "--include",
        "src/titanspan/**",
        "--fail-under=95",
        "--markdown-report=diff-coverage.md",
    )
    if not any(
        all(token in command for token in required_tokens)
        for command in diff_coverage_runs
    ):
        errors.append(
            "coverage job must enforce 95% changed source line coverage"
        )
    return errors


def _validate_gate(jobs: dict[str, object]) -> list[str]:
    """Require the final gate to check every mandatory result fail-closed.

    Args:
        jobs: Parsed primary workflow job mapping.

    Returns:
        Gate configuration violations.
    """
    gate = _string_mapping(jobs.get(GATE_JOB_ID))
    if gate is None:
        return ["primary workflow must define a ci-gate job"]

    errors: list[str] = []
    if gate.get("name") != "Gate: All mandatory CI checks":
        errors.append("ci-gate must use the stable mandatory gate name")
    if "always()" not in str(gate.get("if", "")):
        errors.append("ci-gate must use if: always()")
    gate_needs = _string_list(gate.get("needs"))
    if gate_needs is None or set(gate_needs) != set(EXPECTED_JOBS):
        errors.append(
            "ci-gate needs must exactly match the mandatory job inventory"
        )
    continue_on_error = gate.get("continue-on-error")
    if continue_on_error is True or continue_on_error == "true":
        errors.append("ci-gate must not use continue-on-error")
    if not _has_gate_validator(gate.get("steps")):
        errors.append("ci-gate must run the checked job-result validator")
    return errors


def validate_ci_workflow(workflow: object) -> list[str]:
    """Check mandatory jobs, bounded execution, and a fail-closed CI gate.

    Args:
        workflow: Parsed YAML mapping from the primary CI workflow.

    Returns:
        Diagnostics for missing jobs, invalid dependencies, or unsafe policy.
    """
    root = _string_mapping(workflow)
    if root is None:
        return ["primary workflow must be a YAML mapping"]

    errors = _validate_ci_root(root)
    jobs = _string_mapping(root.get("jobs"))
    if jobs is None:
        return [*errors, "workflow must define a jobs mapping"]
    errors.extend(_validate_job_inventory(jobs))
    errors.extend(_validate_job_matrices(jobs))
    errors.extend(_validate_coverage_job(jobs))
    errors.extend(_validate_gate(jobs))
    return errors


def _read_python_versions(root: dict[str, object]) -> set[str]:
    """Read Python minor versions declared by project classifiers.

    Args:
        root: Parsed pyproject TOML document.

    Returns:
        Declared supported Python versions from project classifiers.
    """
    project = _string_mapping(root.get("project"))
    if project is None:
        return set()
    classifiers = _string_list(project.get("classifiers"))
    if classifiers is None:
        return set()
    prefix = "Programming Language :: Python :: "
    return {
        classifier.removeprefix(prefix)
        for classifier in classifiers
        if classifier.startswith(prefix)
        and classifier.removeprefix(prefix).count(".") == 1
    }


def _validate_timeouts(workflow: object, path: Path) -> list[str]:
    """Require explicit timeouts on every job in a workflow document.

    Args:
        workflow: Parsed workflow root mapping.
        path: Workflow path used in diagnostics.

    Returns:
        Diagnostics for jobs without a positive timeout.
    """
    root = _string_mapping(workflow)
    if root is None:
        return [f"{path}: workflow must be a mapping"]
    jobs = _string_mapping(root.get("jobs"))
    if jobs is None:
        return [f"{path}: workflow must define jobs"]

    errors: list[str] = []
    for job_id, job in jobs.items():
        mapping = _string_mapping(job)
        timeout = mapping.get("timeout-minutes") if mapping else None
        if not _is_positive_integer(timeout):
            errors.append(f"{path}: job {job_id} needs a positive timeout")
    return errors


def _load_yaml(path: Path) -> tuple[object | None, list[str]]:
    """Parse a GitHub YAML file while preserving YAML 1.2 key spellings.

    Args:
        path: Workflow or composite action file.

    Returns:
        Parsed data and diagnostics. YAML tags cannot construct Python objects.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, [f"{path}: cannot read UTF-8 YAML: {exc}"]
    try:
        value: object = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, [f"{path}: invalid YAML: {exc}"]
    if isinstance(value, dict):
        raw_mapping = cast("dict[object, object]", value)
        normalized: dict[object, object] = {}
        for key, item in raw_mapping.items():
            normalized["on" if key is True else key] = item
        value = normalized
    return value, validate_action_references(text)


def validate_repository(root: Path) -> list[str]:
    """Validate every workflow and the primary CI job graph.

    Args:
        root: Repository root containing ``.github`` and ``pyproject.toml``.

    Returns:
        Workflow syntax-policy and graph diagnostics.
    """
    github_root = root / ".github"
    workflow_paths = sorted((github_root / "workflows").glob("*.yml"))
    workflow_paths.extend(sorted((github_root / "workflows").glob("*.yaml")))
    action_paths = sorted((github_root / "actions").rglob("action.yml"))
    action_paths.extend(sorted((github_root / "actions").rglob("action.yaml")))
    if not workflow_paths:
        return [".github/workflows contains no YAML workflows"]

    errors: list[str] = []
    for path in [*workflow_paths, *action_paths]:
        parsed, action_errors = _load_yaml(path)
        errors.extend(f"{path}: {error}" for error in action_errors)
        if parsed is None:
            continue
        if path.parent.name == "workflows":
            errors.extend(_validate_timeouts(parsed, path))
            mapping = _string_mapping(parsed)
            permissions = (
                _string_mapping(mapping.get("permissions")) if mapping else None
            )
            if permissions is None or permissions.get("contents") != "read":
                errors.append(
                    f"{path}: workflow permissions must default "
                    "contents to read"
                )
            if path.name == "ci.yml":
                errors.extend(validate_ci_workflow(parsed))

    try:
        project_value = tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8")
        )
    except (OSError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"pyproject.toml: cannot read supported versions: {exc}")
        return errors
    project = cast("dict[str, object]", project_value)
    declared = _read_python_versions(project)
    if declared != set(PYTHON_MATRIX):
        errors.append(
            "workflow Python matrix must match declared support: "
            f"{sorted(declared)} != {list(PYTHON_MATRIX)}"
        )
    return errors


def main() -> int:
    """Run workflow policy checks and print diagnostics.

    Action syntax validation is run separately by the pinned actionlint tool
    after this structural policy check succeeds.
    """
    root = Path(__file__).resolve().parents[2]
    errors = validate_repository(root)
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    sys.stdout.write("Workflow structural policy passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
