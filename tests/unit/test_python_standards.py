"""Test the repository's Python source policy validator.

These tests keep line length and documentation enforcement deterministic.
"""

from pathlib import Path

import pytest
from scripts.check_python_standards import (
    PythonStandardsConfigurationError,
    validate_python_file,
    validate_repository,
)

pytestmark = pytest.mark.unit


def test_validator_accepts_multiline_documented_source(
    tmp_path: Path,
) -> None:
    """Accept source with multiline module and symbol documentation.

    The example includes a class method and a module-level function so the
    validator checks nested and top-level declarations.
    """
    source = tmp_path / "valid.py"
    source.write_text(
        '"""Describe the example module.\n\nMore detail follows.\n"""\n'
        "\n"
        "class Example:\n"
        '    """Describe the example class.\n\nMore detail follows.\n'
        '    """\n'
        "\n"
        "    def execute(self) -> None:\n"
        '        """Describe the operation.\n\nExplain its contract.\n'
        '        """\n'
        "\n"
        "def build() -> Example:\n"
        '    """Build the example.\n\nReturn the documented value.\n'
        '    """\n'
        "    return Example()\n",
        encoding="utf-8",
    )

    assert validate_python_file(source) == []


@pytest.mark.regression
def test_validator_rejects_missing_and_single_line_docstrings(
    tmp_path: Path,
) -> None:
    """Reject undocumented declarations and physically one-line docstrings.

    This enforces a consistent documentation shape even when the prose is
    concise.
    """
    source = tmp_path / "undocumented.py"
    source.write_text(
        '"""One-line module description."""\n'
        "\n"
        "def undocumented() -> None:\n"
        "    pass\n"
        "\n"
        "def one_line() -> None:\n"
        '    """One-line function description."""\n'
        "    pass\n",
        encoding="utf-8",
    )

    errors = validate_python_file(source)

    assert any("module docstring must span multiple lines" in e for e in errors)
    assert any("undocumented" in e and "missing docstring" in e for e in errors)
    assert any("one_line" in e and "span multiple lines" in e for e in errors)


def test_validator_rejects_lines_longer_than_eighty_columns(
    tmp_path: Path,
) -> None:
    """Report overlong physical lines without relying on Ruff exemptions.

    URLs and comments receive the same strict limit as ordinary source lines.
    """
    source = tmp_path / "long_line.py"
    long_line = "# " + ("x" * 79)
    source.write_text(
        '"""Describe the example module.\n\nMore detail follows.\n"""\n'
        f"{long_line}\n",
        encoding="utf-8",
    )

    errors = validate_python_file(source)

    assert any(":5: line exceeds 80 characters" in error for error in errors)


def test_validator_can_check_docblocks_without_line_length(
    tmp_path: Path,
) -> None:
    """Report missing documentation while ignoring unrelated long lines.

    The focused CI job can report docstring status independently from the
    separate physical line-length job.
    """
    source = tmp_path / "docblocks.py"
    source.write_text(
        '"""Document the module.\n\nMore detail.\n"""\n'
        "# " + ("x" * 90) + "\n"
        "def undocumented() -> None:\n    pass\n",
        encoding="utf-8",
    )

    errors = validate_python_file(
        source,
        check_line_length=False,
        check_docstrings=True,
        check_syntax=True,
    )

    assert any("undocumented" in error for error in errors)
    assert not any("line exceeds" in error for error in errors)


def test_validator_can_check_line_length_without_docstrings(
    tmp_path: Path,
) -> None:
    """Enforce line endings and length independently of documentation.

    This separation makes line-length failures visible as their own CI
    status while retaining the shared strict source policy.
    """
    source = tmp_path / "lines.py"
    source.write_text(
        "def undocumented() -> None:\n    pass\n",
        encoding="utf-8",
    )

    errors = validate_python_file(
        source,
        check_line_length=True,
        check_docstrings=False,
        check_syntax=False,
    )

    assert errors == []


def test_validator_can_parse_syntax_without_other_policies(
    tmp_path: Path,
) -> None:
    """Reject invalid Python without importing or checking its docstrings.

    Syntax verification is safe for maintained scripts with import side
    effects because the validator only invokes the Python parser.
    """
    source = tmp_path / "syntax.py"
    source.write_text("def broken(:\n    pass\n", encoding="utf-8")

    errors = validate_python_file(
        source,
        check_line_length=False,
        check_docstrings=False,
        check_syntax=True,
    )

    assert any("invalid Python syntax" in error for error in errors)


@pytest.mark.regression
def test_validator_rejects_crlf_line_endings(tmp_path: Path) -> None:
    """Reject CRLF source so repository Python files remain LF-only.

    Git attributes normalize tracked files, while this check catches local
    source files that would otherwise violate the cross-platform policy.
    """
    source = tmp_path / "crlf.py"
    source.write_bytes(
        b'"""Describe the module.\r\n\r\nMore details.\r\n"""\r\n'
    )

    errors = validate_python_file(source)

    assert any("line endings must be LF" in error for error in errors)


@pytest.mark.security
def test_repository_policy_rejects_a_weaker_line_length(
    tmp_path: Path,
) -> None:
    """Prevent Ruff configuration from silently relaxing the 80-column cap.

    Args:
        tmp_path: Isolated directory containing a weakened Ruff setting.
    """
    configuration = tmp_path / "pyproject.toml"
    configuration.write_text(
        "[tool.ruff]\nline-length = 120\n",
        encoding="utf-8",
    )

    with pytest.raises(
        PythonStandardsConfigurationError,
        match="line-length must remain 80",
    ):
        validate_repository(tmp_path)
