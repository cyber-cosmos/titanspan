"""Validate repository-local agent instructions and package boundaries.

This checker uses the Python standard library so development governance does
not add a framework runtime dependency.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from contextlib import suppress
from pathlib import Path
from typing import TypeGuard, cast
from zipfile import BadZipFile, ZipFile

SKILL_NAME_MAX_LENGTH = 64
SKILL_DESCRIPTION_MAX_LENGTH = 1024
FRONTMATTER_OPENING = "---\n"
FRONTMATTER_CLOSING = "\n---\n"
MINIMUM_QUOTED_SCALAR_LENGTH = 2

REQUIRED_SKILL_SECTIONS = (
    "## When to use",
    "## References",
    "## Procedure",
    "## Failure modes",
    "## Validation",
    "## Completion criteria",
)

SCOPED_INSTRUCTIONS = (
    "src/titanspan/AGENTS.md",
    "src/titanspan/foundation/AGENTS.md",
    "src/titanspan/container/AGENTS.md",
    "src/titanspan/config/AGENTS.md",
    "src/titanspan/console/AGENTS.md",
    "tests/AGENTS.md",
    "benchmarks/AGENTS.md",
    "docs/AGENTS.md",
    "examples/AGENTS.md",
    ".github/AGENTS.md",
)

COPILOT_PROFILES = (
    ".github/agents/architect.agent.md",
    ".github/agents/implementer.agent.md",
    ".github/agents/reviewer.agent.md",
    ".github/agents/async-safety-reviewer.agent.md",
    ".github/agents/security-reviewer.agent.md",
    ".github/agents/performance-engineer.agent.md",
    ".github/agents/test-engineer.agent.md",
    ".github/agents/documentation-engineer.agent.md",
)

READ_ONLY_PROFILES = {
    ".github/agents/architect.agent.md",
    ".github/agents/reviewer.agent.md",
    ".github/agents/async-safety-reviewer.agent.md",
    ".github/agents/security-reviewer.agent.md",
    ".github/agents/performance-engineer.agent.md",
}

DEVELOPMENT_CONFIG_DIRECTORIES = {
    ".agents",
    ".amazonq",
    ".aiassistant",
    ".claude",
    ".continue",
    ".gemini",
    ".github",
    ".tabnine",
    ".trae",
}

ADAPTERS = {
    "CLAUDE.md": "@AGENTS.md",
    ".aider.conf.yml": "AGENTS.md",
    ".continue/rules/titanspan.md": "AGENTS.md",
    ".amazonq/rules/titanspan.md": "AGENTS.md",
    ".aiassistant/rules/titanspan.md": "AGENTS.md",
    ".trae/rules/titanspan.md": "AGENTS.md",
    ".tabnine/guidelines/titanspan.md": "AGENTS.md",
    ".github/copilot-instructions.md": "AGENTS.md",
}

REQUIRED_FILES = (
    "AGENTS.md",
    "ARCHITECTURE.md",
    "ROADMAP.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "docs/src/content/docs/development/standards.md",
    "docs/src/content/docs/development/agent-workflow.md",
    "docs/src/content/docs/development/agent-compatibility.md",
    "docs/src/content/docs/development/writing-standards.md",
    "docs/src/content/docs/development/glossary.md",
    "scripts/check_python_standards.py",
    "scripts/check_coverage.py",
    ".pre-commit-config.yaml",
    ".yamllint",
    ".secrets.baseline",
    ".github/copilot-instructions.md",
    "Makefile",
    "pyproject.toml",
)

__all__ = [
    "main",
    "validate_packaging_config",
    "validate_repository",
    "validate_skill",
    "validate_wheel",
]


def _string_mapping(value: object) -> dict[str, object] | None:
    """Return a mapping with string keys or ``None`` for invalid data.

    JSON and TOML parsers expose loosely typed values; validate the boundary
    once before reading configuration fields.
    """
    if not isinstance(value, dict):
        return None

    # Parser outputs are untrusted and typed as Any; cast only after the
    # runtime dict check, then validate each key before using the mapping.
    raw_mapping = cast("dict[object, object]", value)
    result: dict[str, object] = {}
    for key, item in raw_mapping.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def _is_string_list(value: object) -> TypeGuard[list[str]]:
    """Check and narrow a parsed JSON array to string values.

    Args:
        value: Untrusted value parsed from profile frontmatter.

    Returns:
        Whether the value is a list containing only strings.
    """
    if not isinstance(value, list):
        return False
    values = cast("list[object]", value)
    return all(isinstance(item, str) for item in values)


def _parse_scalar(
    value: str,
    path: Path,
    line_number: int,
    errors: list[str],
) -> str | None:
    """Decode a plain, single-quoted, or JSON-compatible string scalar.

    Args:
        value: Scalar text from the constrained YAML metadata block.
        path: Source file used in diagnostics.
        line_number: One-based source line for the value.
        errors: Mutable error list populated for malformed quoting.

    Returns:
        The decoded scalar or ``None`` when quoting is invalid.
    """
    if value.startswith('"'):
        try:
            decoded: object = json.loads(value)
        except json.JSONDecodeError:
            errors.append(f"{path}:{line_number}: invalid quoted value")
            return None
        if not isinstance(decoded, str):
            errors.append(f"{path}:{line_number}: expected a string value")
            return None
        return decoded

    if value.startswith("'"):
        if len(value) < MINIMUM_QUOTED_SCALAR_LENGTH or not value.endswith("'"):
            errors.append(f"{path}:{line_number}: invalid quoted value")
            return None
        return value[1:-1]

    return value


def _parse_frontmatter(
    path: Path,
) -> tuple[dict[str, str], str, list[str]]:
    """Read the scalar YAML subset used by skills and agent profiles.

    Args:
        path: Markdown file containing YAML frontmatter.

    Returns:
        Parsed string metadata, Markdown body, and validation errors.

    Notes:
        The repository uses only scalar metadata, so this boundary parser
        avoids introducing a YAML runtime dependency into development checks.
    """
    errors: list[str] = []
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, "", [f"{path}: cannot read file: {exc}"]

    if not contents.startswith(FRONTMATTER_OPENING):
        return {}, "", [f"{path}: missing YAML frontmatter opener"]

    closing = contents.find(FRONTMATTER_CLOSING, len(FRONTMATTER_OPENING))
    if closing < 0:
        return {}, "", [f"{path}: missing YAML frontmatter closer"]

    metadata: dict[str, str] = {}
    frontmatter = contents[len(FRONTMATTER_OPENING) : closing]
    for line_number, line in enumerate(frontmatter.splitlines(), start=2):
        if not line.strip():
            continue
        key, separator, raw_value = line.partition(":")
        if not separator or not re.fullmatch(r"[a-z][a-z0-9-]*", key):
            errors.append(f"{path}:{line_number}: invalid metadata line")
            continue
        if key in metadata:
            errors.append(f"{path}:{line_number}: duplicate field {key!r}")
            continue

        value = _parse_scalar(raw_value.strip(), path, line_number, errors)
        if value is not None:
            metadata[key] = value

    body_start = closing + len(FRONTMATTER_CLOSING)
    return metadata, contents[body_start:], errors


def validate_skill(path: Path) -> list[str]:
    """Check Agent Skills metadata, directory naming, and required sections.

    Args:
        path: Skill Markdown file to validate.

    Returns:
        Validation errors, or an empty list when the skill is valid.
    """
    metadata, body, errors = _parse_frontmatter(path)
    name = metadata.get("name", "")
    description = metadata.get("description", "")

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        errors.append(f"{path}: skill name must be lowercase kebab-case")
    if len(name) > SKILL_NAME_MAX_LENGTH:
        errors.append(
            f"{path}: skill name exceeds {SKILL_NAME_MAX_LENGTH} characters"
        )
    if name and path.parent.name != name:
        errors.append(f"{path}: name must match its skill directory")
    description_is_invalid = (
        not description.strip()
        or len(description) > SKILL_DESCRIPTION_MAX_LENGTH
    )
    if description_is_invalid:
        errors.append(
            f"{path}: description must contain 1 to "
            f"{SKILL_DESCRIPTION_MAX_LENGTH} characters"
        )

    for section in REQUIRED_SKILL_SECTIONS:
        if section not in body:
            errors.append(f"{path}: missing section {section!r}")
    return errors


def _validate_profile(path: Path, root: Path) -> list[str]:
    """Check Copilot profile metadata, tool scope, and canonical guidance.

    Args:
        path: Custom agent profile Markdown file.
        root: Repository root used to identify review-only profiles.

    Returns:
        Validation errors, or an empty list when the profile is valid.
    """
    metadata, body, errors = _parse_frontmatter(path)
    if not metadata.get("name"):
        errors.append(f"{path}: profile name is required")
    if not metadata.get("description"):
        errors.append(f"{path}: profile description is required")
    if metadata.get("infer") != "false":
        errors.append(f"{path}: explicit profiles must set infer: false")
    if metadata.get("include-custom-instructions") != "true":
        errors.append(
            f"{path}: profiles must include canonical project instructions"
        )
    if "model" in metadata:
        errors.append(f"{path}: model identifiers are not allowed")

    raw_tools: object = None
    with suppress(json.JSONDecodeError):
        raw_tools = json.loads(metadata.get("tools", ""))
    if not _is_string_list(raw_tools):
        errors.append(f"{path}: tools must be a JSON-compatible YAML list")
    else:
        relative_path = path.relative_to(root).as_posix()
        is_read_only_profile = relative_path in READ_ONLY_PROFILES
        if is_read_only_profile and raw_tools != ["read", "search"]:
            errors.append(f"{path}: review-only profile must be read-only")

    if "AGENTS.md" not in body:
        errors.append(f"{path}: profile must reference canonical AGENTS.md")
    return errors


def _validate_gemini_adapter(path: Path) -> list[str]:
    """Check Gemini CLI's JSON context discovery setting.

    Args:
        path: Gemini settings file.

    Returns:
        Validation errors, or an empty list when canonical context is loaded.
    """
    try:
        settings_value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: invalid JSON settings: {exc}"]

    settings = _string_mapping(settings_value)
    context = _string_mapping(settings.get("context")) if settings else None
    names = context.get("fileName") if context else None
    if not _is_string_list(names) or "AGENTS.md" not in names:
        return [f"{path}: context.fileName must include AGENTS.md"]
    return []


def _validate_text_adapter(
    path: Path,
    relative_path: str,
    marker: str,
) -> list[str]:
    """Check a text adapter references the canonical project instructions.

    Args:
        path: Adapter file to inspect.
        relative_path: Repository-relative adapter path.
        marker: Required canonical guidance reference.

    Returns:
        Validation errors from the shared and harness-specific requirements.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{relative_path}: cannot read adapter: {exc}"]

    errors: list[str] = []
    if marker not in content:
        errors.append(f"{relative_path}: adapter must reference {marker!r}")
    if (
        relative_path
        in {
            ".continue/rules/titanspan.md",
            ".trae/rules/titanspan.md",
        }
        and "alwaysApply: true" not in content
    ):
        errors.append(f"{relative_path}: rule must be always applied")
    if (
        relative_path == ".aiassistant/rules/titanspan.md"
        and "Always" not in content
    ):
        errors.append(f"{relative_path}: manual rule activation must be noted")
    return errors


def _validate_adapter(
    root: Path,
    relative_path: str,
    marker: str,
) -> list[str]:
    """Check that a configured harness adapter exists and is linked.

    Args:
        root: Repository root.
        relative_path: Repository-relative adapter path.
        marker: Required canonical instruction reference.

    Returns:
        Validation errors, or an empty list when the adapter is valid.
    """
    path = root / relative_path
    if not path.is_file():
        return [f"{relative_path}: required adapter is missing"]
    if relative_path == ".gemini/settings.json":
        return _validate_gemini_adapter(path)
    return _validate_text_adapter(path, relative_path, marker)


def validate_packaging_config(path: Path) -> list[str]:
    """Require scoped agent instructions to stay out of built wheels.

    Args:
        path: Project TOML configuration path.

    Returns:
        Validation errors, or an empty list when wheel exclusion is present.
    """
    try:
        configuration_value: object = tomllib.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"{path}: cannot validate TOML packaging settings: {exc}"]

    configuration = _string_mapping(configuration_value)
    tool = _string_mapping(configuration.get("tool")) if configuration else None
    uv = _string_mapping(tool.get("uv")) if tool else None
    backend = _string_mapping(uv.get("build-backend")) if uv else None
    exclusions = backend.get("wheel-exclude") if backend else None
    if not _is_string_list(exclusions) or "**/AGENTS.md" not in exclusions:
        return [f"{path}: wheel-exclude must include **/AGENTS.md"]
    return []


def validate_wheel(path: Path) -> list[str]:
    """Reject development agent files and scripts from a runtime wheel.

    Args:
        path: Wheel archive to inspect.

    Returns:
        Packaging violations, or an empty list for runtime-only contents.
    """
    try:
        with ZipFile(path) as wheel:
            members = wheel.namelist()
    except (BadZipFile, OSError) as exc:
        return [f"{path}: cannot read wheel archive: {exc}"]

    errors: list[str] = []
    for member in members:
        parts = Path(member).parts
        if Path(member).name in {"AGENTS.md", "CLAUDE.md"}:
            errors.append(f"{path}: development instruction included: {member}")
        elif DEVELOPMENT_CONFIG_DIRECTORIES.intersection(parts):
            errors.append(f"{path}: agent configuration included: {member}")
        elif "scripts" in parts:
            errors.append(f"{path}: development script included: {member}")
    return errors


def _validate_required_files(root: Path) -> list[str]:
    """Find missing project governance and architecture documents.

    Args:
        root: Repository root.

    Returns:
        A diagnostic for every missing required file.
    """
    return [
        f"{relative_path}: required file is missing"
        for relative_path in REQUIRED_FILES
        if not (root / relative_path).is_file()
    ]


def _validate_scoped_instructions(root: Path) -> list[str]:
    """Check scoped instruction files defer to root project policy.

    Args:
        root: Repository root.

    Returns:
        Missing-file and missing-reference diagnostics.
    """
    errors: list[str] = []
    for relative_path in SCOPED_INSTRUCTIONS:
        path = root / relative_path
        if not path.is_file():
            errors.append(f"{relative_path}: scoped instructions are missing")
            continue
        if relative_path == "src/titanspan/AGENTS.md":
            continue
        content = path.read_text(encoding="utf-8")
        if "AGENTS.md" not in content:
            errors.append(
                f"{relative_path}: scoped guidance must defer to root rules"
            )
    return errors


def _validate_skills(root: Path) -> list[str]:
    """Check all shared skill files and require at least one reusable skill.

    Args:
        root: Repository root.

    Returns:
        Skill validation errors.
    """
    paths = sorted((root / ".agents/skills").glob("*/SKILL.md"))
    if not paths:
        return [".agents/skills: no shared skills were found"]
    return [error for path in paths for error in validate_skill(path)]


def _validate_profiles(root: Path) -> list[str]:
    """Check every configured optional Copilot specialist profile.

    Args:
        root: Repository root.

    Returns:
        Profile validation errors.
    """
    return [
        error
        for relative_path in COPILOT_PROFILES
        for error in _validate_profile(root / relative_path, root)
    ]


def _validate_adapters(root: Path) -> list[str]:
    """Check configured harness adapters reference canonical instructions.

    Args:
        root: Repository root.

    Returns:
        Adapter validation errors.
    """
    errors = [
        error
        for relative_path, marker in ADAPTERS.items()
        for error in _validate_adapter(root, relative_path, marker)
    ]
    gemini_errors = _validate_adapter(
        root,
        ".gemini/settings.json",
        "AGENTS.md",
    )
    return errors + gemini_errors


def _validate_makefile(root: Path) -> list[str]:
    """Require all mandatory checks and wheel auditing in Make targets.

    Args:
        root: Repository root.

    Returns:
        Makefile contract errors.
    """
    path = root / "Makefile"
    if not path.is_file():
        return []
    contents = path.read_text(encoding="utf-8")
    errors: list[str] = []
    check_match = re.search(
        r"(?m)^check:(?:[^\\\n]|\\\n[ \t]*)*",
        contents,
    )
    check_target = check_match.group(0) if check_match else ""
    required_checks = (
        "lint",
        "format-check",
        "python-standards",
        "types",
        "yaml-check",
        "lock-check",
        "architecture-check",
        "agents-check",
        "prose-check",
        "terminology-check",
        "prose-test",
        "coverage",
    )
    missing_checks = [
        target for target in required_checks if target not in check_target
    ]
    if "agents-check:" not in contents:
        errors.append("Makefile: add the read-only agents-check target")
    if "check: " not in contents or "agents-check" not in contents:
        errors.append("Makefile: include agents-check in make check")
    if missing_checks:
        errors.append(
            "Makefile: make check must include " + ", ".join(missing_checks)
        )
    if "check_agent_configs.py --wheel" not in contents:
        errors.append("Makefile: audit the wheel in make build")
    return errors


def _validate_package_layout(root: Path) -> list[str]:
    """Ensure development skills remain outside the runtime package.

    Args:
        root: Repository root.

    Returns:
        A diagnostic when agent assets appear inside the package tree.
    """
    package_skills = root / "src/titanspan/.agents"
    if package_skills.exists():
        return ["src/titanspan/.agents: development skills are not runtime"]
    return []


def validate_repository(root: Path) -> list[str]:
    """Validate instructions, adapters, skills, profiles, and packaging.

    Args:
        root: Repository directory to inspect.

    Returns:
        Validation errors, or an empty list when the repository is valid.
    """
    root = root.resolve()
    validators = (
        _validate_required_files,
        _validate_scoped_instructions,
        _validate_skills,
        _validate_profiles,
        _validate_adapters,
        _validate_makefile,
        _validate_package_layout,
    )
    errors = [error for validate in validators for error in validate(root)]
    errors.extend(validate_packaging_config(root / "pyproject.toml"))
    return errors


def main() -> int:
    """Run repository checks and return a process status.

    The command is read-only and writes diagnostics to standard output.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root to validate",
    )
    parser.add_argument(
        "--wheel",
        type=Path,
        help="built wheel to inspect for development-only files",
    )
    args = parser.parse_args()

    errors = validate_repository(args.root)
    if args.wheel is not None:
        errors.extend(validate_wheel(args.wheel))
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1

    sys.stdout.write("Agent configuration checks passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
