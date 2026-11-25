"""Test structural enforcement of comments at high-risk code paths.

The validator checks comments around selected concurrency, security, and
resource-lifecycle operations without imposing a comment-density target.
"""

from pathlib import Path

import pytest
from scripts.ci.check_comments import validate_source

pytestmark = pytest.mark.unit


def test_comment_check_requires_rationale_for_task_creation() -> None:
    """Require an explanatory comment near unmanaged task creation.

    The operation affects task ownership and cancellation semantics.
    """
    source = (
        '"""Module documentation.\n\nMore detail.\n"""\n'
        "\n"
        "async def start() -> None:\n"
        '    """Start work.\n\nReturn after scheduling.\n"""\n'
        "    asyncio.create_task(run())\n"
    )

    errors = validate_source(Path("sample.py"), source)

    assert len(errors) == 1
    assert "task creation" in errors[0]


def test_comment_check_accepts_a_reasoned_task_ownership_comment() -> None:
    """Accept a nearby comment explaining why an owned task is created.

    A rationale comment is allowed before the operation or inside its body.
    """
    source = (
        '"""Module documentation.\n\nMore detail.\n"""\n'
        "\n"
        "async def start() -> None:\n"
        '    """Start work.\n\nReturn after scheduling.\n"""\n'
        "    # The scope owns this task and propagates cancellation safely.\n"
        "    asyncio.create_task(run())\n"
    )

    assert validate_source(Path("sample.py"), source) == []


def test_comment_check_does_not_count_comment_text_inside_strings() -> None:
    """Ignore comment-looking text embedded in a Python string literal.

    Tokenization must distinguish actual source comments from data strings.
    """
    source = (
        '"""Module documentation.\n\nMore detail.\n"""\n'
        "\n"
        "async def start() -> None:\n"
        '    """Start work.\n\nReturn after scheduling.\n"""\n'
        '    note = "# this is data, not a rationale"\n'
        "    asyncio.create_task(run())\n"
    )

    assert validate_source(Path("sample.py"), source)


def test_comment_check_ignores_ordinary_pure_functions() -> None:
    """Avoid requiring explanatory comments for ordinary pure code.

    The policy targets explicit risk patterns rather than comment density.
    """
    source = (
        '"""Module documentation.\n\nMore detail.\n"""\n'
        "\n"
        "def double(value: int) -> int:\n"
        '    """Return a doubled integer.\n\nPreserve integer semantics.\n"""\n'
        "    return value * 2\n"
    )

    assert validate_source(Path("sample.py"), source) == []
