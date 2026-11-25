"""Enforce line length and multiline documentation in Python sources.

The check applies to runtime code, tests, examples, benchmarks, and
repository-local development scripts without adding a runtime dependency.
"""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from pathlib import Path
from typing import cast

PYTHON_DIRECTORIES = (
    "src",
    "tests",
    "benchmarks",
    "examples",
    "scripts",
    "stubs",
)
REQUIRED_LINE_LENGTH = 80

__all__ = [
    "PythonStandardsConfigurationError",
    "main",
    "validate_python_file",
    "validate_repository",
]


class PythonStandardsConfigurationError(Exception):
    """Describe invalid project configuration for the source checker.

    The exception centralizes the diagnostic format so validation sites can
    provide a path and reason without constructing inconsistent messages.
    """

    def __init__(self, path: Path, reason: str) -> None:
        """Store the affected configuration path and validation reason.

        Args:
            path: Project configuration file that could not be validated.
            reason: Concise diagnostic explaining the invalid configuration.
        """
        message = f"{path}: {reason}"
        super().__init__(message)


def _string_mapping(value: object) -> dict[str, object] | None:
    """Narrow an untrusted parser object to a string-keyed dictionary.

    Args:
        value: TOML parser output or a nested value from its tables.

    Returns:
        A string-keyed dictionary, or ``None`` for another shape.
    """
    if not isinstance(value, dict):
        return None

    # tomllib exposes Any values; confine that typing gap to this checked
    # parser boundary before the rest of the script uses typed objects.
    raw_mapping = cast("dict[object, object]", value)
    result: dict[str, object] = {}
    for key, item in raw_mapping.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def _docstring_expression(body: list[ast.stmt]) -> ast.Expr | None:
    """Return the literal expression used as a declaration's docstring.

    Args:
        body: Statements belonging to a module, class, or function.

    Inspect the AST source span so an escaped newline inside a one-line
    literal cannot satisfy the repository documentation policy.
    """
    if not body or not isinstance(body[0], ast.Expr):
        return None

    expression = body[0]
    if not isinstance(expression.value, ast.Constant):
        return None
    if not isinstance(expression.value.value, str):
        return None

    return expression


def _declarations(
    tree: ast.Module,
) -> list[tuple[str, str, int, list[ast.stmt]]]:
    """Collect a module and every class or function body in source order.

    Args:
        tree: Parsed Python module.

    Nested functions and methods are included because their contracts need
    documentation just as module-level functions do.
    """
    declarations = [("module", "module", 1, tree.body)]
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            declarations.append(("class", node.name, node.lineno, node.body))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            declarations.append(("function", node.name, node.lineno, node.body))
    return declarations


def validate_python_file(
    path: Path,
    *,
    max_line_length: int = 80,
    check_line_length: bool = True,
    check_docstrings: bool = True,
    check_syntax: bool = True,
) -> list[str]:
    """Return selected source-standard violations for one Python file.

    Args:
        path: Python source file to inspect.
        max_line_length: Maximum number of Unicode code points per line.
        check_line_length: Whether to enforce the physical line-length cap.
        check_docstrings: Whether declarations need multiline docstrings.
        check_syntax: Whether the source must parse as Python.

    Returns:
        Human-readable violations for enabled checks.
    """
    errors: list[str] = []
    try:
        source_bytes = path.read_bytes()
        source = source_bytes.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{path}: cannot read UTF-8 source: {exc}"]

    if check_line_length:
        errors.extend(
            f"{path}:{line_number}: line exceeds "
            f"{max_line_length} characters ({len(line)})"
            for line_number, line in enumerate(source.splitlines(), start=1)
            if len(line) > max_line_length
        )
    if (check_line_length or check_docstrings) and "\r" in source:
        errors.append(f"{path}: line endings must be LF")

    if not check_syntax and not check_docstrings:
        return errors

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        errors.append(f"{path}:{exc.lineno}: invalid Python syntax: {exc.msg}")
        return errors

    if not check_docstrings:
        return errors

    for kind, name, line_number, body in _declarations(tree):
        description = "module" if kind == "module" else f"{kind} {name}"
        expression = _docstring_expression(body)
        if expression is None:
            errors.append(
                f"{path}:{line_number}: {description} missing docstring"
            )
            continue
        end_line = expression.end_lineno
        if end_line is None or end_line <= expression.lineno:
            errors.append(
                f"{path}:{line_number}: {description} docstring must "
                "span multiple lines"
            )

    return errors


def _configured_line_length(root: Path) -> int:
    """Read Ruff's line length so source validation has one policy value.

    Args:
        root: Repository root containing pyproject.toml.

    Fail closed when configuration is missing or malformed rather than
    silently reverting to a weaker default.
    """
    configuration_path = root / "pyproject.toml"
    try:
        configuration_value = tomllib.loads(
            configuration_path.read_text(encoding="utf-8")
        )
    except (OSError, tomllib.TOMLDecodeError) as exc:
        reason = f"cannot read project configuration: {exc}"
        raise PythonStandardsConfigurationError(
            configuration_path,
            reason,
        ) from exc

    configuration = _string_mapping(cast("object", configuration_value))
    if configuration is None:
        raise PythonStandardsConfigurationError(
            configuration_path,
            "expected a TOML table",
        )
    tool = _string_mapping(configuration.get("tool"))
    if tool is None:
        raise PythonStandardsConfigurationError(
            configuration_path,
            "missing [tool] section",
        )
    ruff = _string_mapping(tool.get("ruff"))
    if ruff is None:
        raise PythonStandardsConfigurationError(
            configuration_path,
            "missing [tool.ruff]",
        )
    line_length = ruff.get("line-length")
    if (
        not isinstance(line_length, int)
        or isinstance(line_length, bool)
        or line_length < 1
    ):
        raise PythonStandardsConfigurationError(
            configuration_path,
            "tool.ruff.line-length must be positive",
        )
    if line_length != REQUIRED_LINE_LENGTH:
        raise PythonStandardsConfigurationError(
            configuration_path,
            f"tool.ruff.line-length must remain {REQUIRED_LINE_LENGTH}",
        )
    return line_length


def validate_repository(
    root: Path,
    *,
    check_line_length: bool = True,
    check_docstrings: bool = True,
    check_syntax: bool = True,
) -> list[str]:
    """Check every maintained Python file under configured project areas.

    Args:
        root: Repository root containing pyproject.toml and source folders.
        check_line_length: Whether to enforce the physical line-length cap.
        check_docstrings: Whether declarations need multiline docstrings.
        check_syntax: Whether maintained source files must parse.

    Returns:
        Violations from all discovered Python files.
    """
    line_length = _configured_line_length(root)
    files = sorted(
        path
        for directory in PYTHON_DIRECTORIES
        for path in (root / directory).rglob("*.py")
        if path.is_file() and "__pycache__" not in path.parts
    )
    return [
        error
        for path in files
        for error in validate_python_file(
            path,
            max_line_length=line_length,
            check_line_length=check_line_length,
            check_docstrings=check_docstrings,
            check_syntax=check_syntax,
        )
    ]


def main() -> int:
    """Run repository Python checks and return a process status.

    The command is read-only and writes diagnostics to terminal streams.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root to validate",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--docblocks-only",
        action="store_true",
        help="check multiline documentation and Python syntax",
    )
    modes.add_argument(
        "--line-length-only",
        action="store_true",
        help="check strict physical line length and LF endings",
    )
    modes.add_argument(
        "--syntax-only",
        action="store_true",
        help="parse maintained Python files without importing them",
    )
    args = parser.parse_args()

    try:
        errors = validate_repository(
            args.root,
            check_line_length=not args.docblocks_only and not args.syntax_only,
            check_docstrings=not args.line_length_only and not args.syntax_only,
            check_syntax=not args.line_length_only,
        )
    except PythonStandardsConfigurationError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1

    sys.stdout.write("Python source standards passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
