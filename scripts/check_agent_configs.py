"""Validate Titanspan's repository-local agent instructions and skills."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from zipfile import BadZipFile, ZipFile

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
}


def _parse_frontmatter(path: Path) -> tuple[dict[str, str], str, list[str]]:
    """Read scalar YAML frontmatter used by repository instruction files."""
    errors: list[str] = []
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, "", [f"{path}: cannot read file: {exc}"]

    if not contents.startswith("---\n"):
        return {}, "", [f"{path}: missing YAML frontmatter opener"]

    closing = contents.find("\n---\n", 4)
    if closing < 0:
        return {}, "", [f"{path}: missing YAML frontmatter closer"]

    metadata: dict[str, str] = {}
    frontmatter = contents[4:closing]
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
        value = raw_value.strip()
        if value.startswith('"'):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                errors.append(f"{path}:{line_number}: invalid quoted value")
                continue
            if not isinstance(decoded, str):
                errors.append(f"{path}:{line_number}: expected a string value")
                continue
            value = decoded
        elif value.startswith("'"):
            if not value.endswith("'") or len(value) < 2:
                errors.append(f"{path}:{line_number}: invalid quoted value")
                continue
            value = value[1:-1]
        metadata[key] = value

    return metadata, contents[closing + 5 :], errors


def validate_skill(path: Path) -> list[str]:
    """Check skill metadata, naming, and required workflow sections."""
    metadata, body, errors = _parse_frontmatter(path)
    name = metadata.get("name", "")
    description = metadata.get("description", "")

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        errors.append(f"{path}: skill name must be lowercase kebab-case")
    if len(name) > 64:
        errors.append(f"{path}: skill name exceeds 64 characters")
    if name and path.parent.name != name:
        errors.append(f"{path}: name must match its skill directory")
    if not description.strip() or len(description) > 1024:
        errors.append(f"{path}: description must contain 1 to 1024 characters")

    for section in REQUIRED_SKILL_SECTIONS:
        if section not in body:
            errors.append(f"{path}: missing section {section!r}")

    return errors


def _validate_profile(path: Path, root: Path) -> list[str]:
    """Check Copilot profile metadata and least-privilege role settings."""
    metadata, body, errors = _parse_frontmatter(path)
    if not metadata.get("name"):
        errors.append(f"{path}: profile name is required")
    if not metadata.get("description"):
        errors.append(f"{path}: profile description is required")
    if metadata.get("infer") != "false":
        errors.append(f"{path}: explicit profiles must set infer: false")
    if metadata.get("include-custom-instructions") != "true":
        errors.append(
            f"{path}: subagents must include canonical project instructions"
        )
    if "model" in metadata:
        errors.append(f"{path}: model identifiers are not allowed")

    tools_value = metadata.get("tools", "")
    try:
        tools = json.loads(tools_value)
    except json.JSONDecodeError:
        tools = None
    if not isinstance(tools, list) or not all(
        isinstance(tool, str) for tool in tools
    ):
        errors.append(f"{path}: tools must be a JSON-compatible YAML list")
    elif path.as_posix().replace(root.as_posix() + "/", "") in (
        READ_ONLY_PROFILES
    ) and tools != ["read", "search"]:
        errors.append(f"{path}: review-only profile must be read-only")

    if "AGENTS.md" not in body:
        errors.append(f"{path}: profile must reference canonical AGENTS.md")
    return errors


def _validate_adapter(root: Path, relative_path: str, marker: str) -> list[str]:
    """Check that a harness adapter exists and points to canonical guidance."""
    path = root / relative_path
    if not path.is_file():
        return [f"{relative_path}: required adapter is missing"]

    if relative_path == ".gemini/settings.json":
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return [f"{relative_path}: invalid JSON settings: {exc}"]
        file_names = settings.get("context", {}).get("fileName", [])
        if "AGENTS.md" not in file_names:
            return [f"{relative_path}: context.fileName must include AGENTS.md"]
        return []

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{relative_path}: cannot read adapter: {exc}"]

    if marker not in content:
        return [f"{relative_path}: adapter must reference {marker!r}"]

    if relative_path == ".continue/rules/titanspan.md":
        if "alwaysApply: true" not in content:
            return [f"{relative_path}: Continue rule must be always applied"]
    elif relative_path == ".trae/rules/titanspan.md":
        if "alwaysApply: true" not in content:
            return [f"{relative_path}: Trae rule must be always applied"]
    elif (
        relative_path == ".aiassistant/rules/titanspan.md"
        and "Always" not in content
    ):
        return [f"{relative_path}: manual rule activation must be documented"]

    return []


def validate_packaging_config(path: Path) -> list[str]:
    """Require scoped agent instructions to stay out of built wheels."""
    try:
        configuration = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"{path}: cannot validate TOML packaging settings: {exc}"]

    backend = (
        configuration.get("tool", {}).get("uv", {}).get("build-backend", {})
    )
    exclusions = backend.get("wheel-exclude", [])
    if "**/AGENTS.md" not in exclusions:
        return [f"{path}: wheel-exclude must include **/AGENTS.md"]
    return []


def validate_wheel(path: Path) -> list[str]:
    """Reject development agent files from a built runtime wheel."""
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


def validate_repository(root: Path) -> list[str]:
    """Validate required references, scoped instructions, skills, and profiles.

    Args:
        root: Repository directory to inspect.

    Returns:
        Validation errors, or an empty list when all checks pass.
    """
    root = root.resolve()
    errors: list[str] = []
    required_files = (
        "AGENTS.md",
        "ARCHITECTURE.md",
        "ROADMAP.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "docs/development/standards.md",
        "docs/development/agent-workflow.md",
        "docs/development/agent-compatibility.md",
        "Makefile",
        "pyproject.toml",
    )
    errors.extend(
        f"{relative_path}: required file is missing"
        for relative_path in required_files
        if not (root / relative_path).is_file()
    )

    for relative_path in SCOPED_INSTRUCTIONS:
        path = root / relative_path
        if not path.is_file():
            errors.append(f"{relative_path}: scoped instructions are missing")
            continue
        if relative_path != "src/titanspan/AGENTS.md":
            content = path.read_text(encoding="utf-8")
            if "AGENTS.md" not in content:
                errors.append(
                    f"{relative_path}: scoped guidance must defer to root rules"
                )

    skill_paths = sorted((root / ".agents/skills").glob("*/SKILL.md"))
    if not skill_paths:
        errors.append(".agents/skills: no shared skills were found")
    for path in skill_paths:
        errors.extend(validate_skill(path))

    for relative_path, marker in ADAPTERS.items():
        errors.extend(_validate_adapter(root, relative_path, marker))
    errors.extend(_validate_adapter(root, ".gemini/settings.json", "AGENTS.md"))
    errors.extend(validate_packaging_config(root / "pyproject.toml"))

    for relative_path in COPILOT_PROFILES:
        errors.extend(_validate_profile(root / relative_path, root))

    makefile_path = root / "Makefile"
    if makefile_path.is_file():
        makefile = makefile_path.read_text(encoding="utf-8")
        if "agents-check:" not in makefile:
            errors.append("Makefile: add the read-only agents-check target")
        if "check: " not in makefile or "agents-check" not in makefile:
            errors.append("Makefile: include agents-check in make check")
        if "check_agent_configs.py --wheel" not in makefile:
            errors.append("Makefile: audit the wheel in make build")

    package_root = root / "src/titanspan"
    if (package_root / ".agents").exists():
        errors.append(
            "src/titanspan/.agents: development skills are not runtime"
        )

    return errors


def main() -> int:
    """Run repository checks and return a process status."""
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
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Agent configuration checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
