"""Require rationale comments around selected high-risk Python operations.

Tokenization distinguishes real comments from strings. The check targets
explicit task, subprocess, and dynamic-code operations instead of imposing
an arbitrary comment-density rule.
"""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

RISK_CALLS = {
    "create_task": "task creation",
    "gather": "task fan-out",
    "run": "subprocess execution",
    "Popen": "subprocess execution",
    "call": "subprocess execution",
    "eval": "dynamic code execution",
    "exec": "dynamic code execution",
    "load": "unsafe deserialization",
    "loads": "unsafe deserialization",
    "basicConfig": "global logging configuration",
}
COMMENT_DIRECTIVES = (
    "noqa",
    "type:",
    "pyright:",
    "pragma:",
)
MINIMUM_COMMENT_WORDS = 5
WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z'-]*")

__all__ = ["main", "validate_source"]


def _source_comments(source: str) -> list[tuple[int, str]]:
    """Return actual comment tokens with their one-based source lines.

    Args:
        source: Python source to tokenize.

    Returns:
        Comment text and source line pairs.

    Raises:
        SyntaxError: If the tokenizer cannot read malformed input.
    """
    reader = io.StringIO(source).readline
    return [
        (token.start[0], token.string[1:].strip())
        for token in tokenize.generate_tokens(reader)
        if token.type == tokenize.COMMENT
    ]


def _is_explanatory(comment: str) -> bool:
    """Check whether a comment has enough prose to explain a decision.

    Args:
        comment: Comment body without its leading hash marker.

    Returns:
        Whether the comment contains at least five non-directive words.
    """
    normalized = comment.casefold()
    if any(directive in normalized for directive in COMMENT_DIRECTIVES):
        return False
    return len(WORD_PATTERN.findall(comment)) >= MINIMUM_COMMENT_WORDS


def _risk_labels(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Identify selected risky operations from call nodes, not string text.

    Args:
        node: Function or method implementation under review.

    Returns:
        Distinct operation labels requiring an explanatory comment.
    """
    labels: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            name = child.func.id
        elif isinstance(child.func, ast.Attribute):
            name = child.func.attr
        else:
            name = ""
        label = RISK_CALLS.get(name)
        if label == "subprocess execution" and not (
            isinstance(child.func, ast.Attribute)
            and isinstance(child.func.value, ast.Name)
            and child.func.value.id == "subprocess"
        ):
            label = None
        if label == "unsafe deserialization" and not (
            isinstance(child.func, ast.Attribute)
            and isinstance(child.func.value, ast.Name)
            and child.func.value.id == "pickle"
        ):
            label = None
        if label is not None:
            labels.add(label)
        for keyword in child.keywords:
            if (
                keyword.arg == "shell"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
            ):
                labels.add("shell execution")
    return sorted(labels)


def validate_source(path: Path, source: str) -> list[str]:
    """Find high-risk operations without a nearby explanatory comment.

    Args:
        path: Source path used in diagnostics.
        source: Python source text to inspect.

    Returns:
        One diagnostic for each uncovered high-risk implementation block.
    """
    try:
        tree = ast.parse(source, filename=str(path))
        comments = _source_comments(source)
    except (SyntaxError, tokenize.TokenError) as exc:
        line_number = getattr(exc, "lineno", None) or 1
        return [f"{path}:{line_number}: cannot analyze comments: {exc}"]

    errors: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end_line = node.end_lineno or node.lineno
        risks = _risk_labels(node)
        if not risks:
            continue

        first_relevant_line = max(1, node.lineno - 2)
        explanatory = any(
            first_relevant_line <= line_number <= end_line
            and _is_explanatory(comment)
            for line_number, comment in comments
        )
        if not explanatory:
            labels = ", ".join(risks)
            errors.append(
                f"{path}:{node.lineno}: {node.name} uses {labels} without "
                "a nearby explanatory comment"
            )
    return errors


def _python_files(root: Path) -> list[Path]:
    """Return maintained Python files from first-party project areas.

    Args:
        root: Repository root.

    Returns:
        Sorted source, test, example, benchmark, script, and stub files.
    """
    directories = (
        "src",
        "tests",
        "examples",
        "benchmarks",
        "scripts",
        "stubs",
    )
    return sorted(
        path
        for directory in directories
        for path in (root / directory).rglob("*.py")
        if path.is_file() and "__pycache__" not in path.parts
    )


def validate_repository(root: Path) -> list[str]:
    """Validate explanatory comments across maintained Python code.

    Args:
        root: Repository root containing first-party code directories.

    Returns:
        All high-risk comment-policy violations found.
    """
    errors: list[str] = []
    for path in _python_files(root):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{path}: cannot read source: {exc}")
            continue
        errors.extend(validate_source(path, source))
    return errors


def main() -> int:
    """Run the comment-policy check and print actionable diagnostics.

    The validator checks only source-maintained implementation files and
    returns a non-zero status for malformed or undocumented risky code.
    """
    root = Path(__file__).resolve().parents[2]
    errors = validate_repository(root)
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    sys.stdout.write("Risk-focused implementation comment check passed.\n")
    return 0
