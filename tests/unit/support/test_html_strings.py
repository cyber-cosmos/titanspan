"""Verify trusted and encoded HTML string behavior.

The cases test escaping, context-local encoder isolation, and Python
HTML-rendering interoperability.
"""

from __future__ import annotations

from enum import Enum

import anyio
import pytest

from titanspan.support import EncodedHtmlString, HtmlString, e

EXPECTED_ESCAPED = "&lt;script&gt;alert(&#039;x&#039;) &amp;"


class HtmlToken(str, Enum):
    """Provide a string-backed value for encoding tests.

    The member emulates an enum with a scalar backing value.
    """

    VALUE = "<token>"


class StructuredHtmlToken(Enum):
    """Represent an enum without a scalar value.

    This value exercises the Python-specific fallback for arbitrary enums.
    """

    VALUE = ("<structured>",)


class DeferredHtmlValue:
    """Defer display rendering until an HTML string is requested.

    The class returns trusted HTML through the native display-value protocol
    without coupling the runtime to a template engine.
    """

    def resolve_displayable_value(self) -> HtmlString:
        """Return trusted HTML at the time of rendering.

        Returns:
            The resolved trusted HTML value.
        """
        return HtmlString("<em>deferred</em>")


class CustomHtmlValue:
    """Expose the trusted HTML protocol from an application class.

    This fixture verifies that the runtime accepts structural implementations.
    """

    def to_html(self) -> str:
        """Return explicitly trusted markup.

        Returns:
            The trusted HTML representation.
        """
        return "<strong>custom</strong>"


class CustomDeferredText:
    """Expose deferred display behavior from an application class.

    This fixture verifies structural protocol use without a base class.
    """

    def resolve_displayable_value(self) -> str:
        """Resolve plain text when the value is rendered.

        Returns:
            Plain text requiring HTML escaping.
        """
        return "<strong>delayed</strong>"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("<h1>foo</h1>", "<h1>foo</h1>"),
        ("   <h1> foo </h1>   ", "   <h1> foo </h1>   "),
        ("", ""),
        (None, ""),
        ("foo bar", "foo bar"),
    ],
)
def test_html_string_preserves_trusted_content(
    value: str | None,
    expected: str,
) -> None:
    """Preserve trusted HTML and map a null value to empty text.

    Args:
        value: The trusted source text.
        expected: The expected HTML string.
    """
    html = HtmlString(value)

    assert html.to_html() == expected
    assert html.to_html() == expected
    assert html.__html__() == expected
    assert str(html) == expected
    assert html.is_empty() is (expected == "")
    assert html.is_not_empty() is (expected != "")


@pytest.mark.unit
def test_encoded_html_escapes_untrusted_text_and_supports_safe_entities() -> (
    None
):
    """Escape HTML delimiters and preserve valid entities when requested.

    Returns:
        None.
    """
    untrusted = EncodedHtmlString("<script>alert('x') &")
    encoded = EncodedHtmlString("&amp; <b>", double_encode=False)

    assert untrusted.to_html() == EXPECTED_ESCAPED
    assert str(untrusted) == EXPECTED_ESCAPED
    assert encoded.to_html() == "&amp; &lt;b&gt;"
    assert EncodedHtmlString.convert(None) == ""
    assert EncodedHtmlString.convert('"quoted"', with_quote=False) == (
        '"quoted"'
    )
    assert EncodedHtmlString(HtmlToken.VALUE).to_html() == "&lt;token&gt;"
    assert EncodedHtmlString(StructuredHtmlToken.VALUE).to_html() == ("VALUE")
    assert EncodedHtmlString(True).to_html() == "1"
    assert EncodedHtmlString(False).to_html() == ""
    assert EncodedHtmlString(2.5).to_html() == "2.5"
    assert EncodedHtmlString(None).to_html() == ""


@pytest.mark.unit
def test_encoded_html_preserves_empty_value_semantics() -> None:
    """Match the wrapped source value when checking emptiness.

    Returns:
        None.
    """
    assert EncodedHtmlString(None).is_empty()
    assert EncodedHtmlString("").is_empty()
    assert not EncodedHtmlString(False).is_empty()
    assert EncodedHtmlString("value").is_not_empty()


@pytest.mark.unit
def test_encoded_html_does_not_escape_trusted_htmlable_values() -> None:
    """Avoid encoding an explicitly trusted HTML value a second time.

    Returns:
        None.
    """
    trusted = HtmlString("<em>safe</em>")

    assert EncodedHtmlString(trusted).to_html() == "<em>safe</em>"


@pytest.mark.unit
def test_encoded_html_resolves_deferred_display_values() -> None:
    """Resolve a display value before deciding whether to escape it.

    Returns:
        None.
    """
    assert EncodedHtmlString(DeferredHtmlValue()).to_html() == (
        "<em>deferred</em>"
    )
    assert EncodedHtmlString(CustomDeferredText()).to_html() == (
        "&lt;strong&gt;delayed&lt;/strong&gt;"
    )
    assert EncodedHtmlString(CustomHtmlValue()).to_html() == (
        "<strong>custom</strong>"
    )
    assert e(CustomDeferredText()) == "&lt;strong&gt;delayed&lt;/strong&gt;"
    assert e(CustomHtmlValue()) == "<strong>custom</strong>"


@pytest.mark.unit
def test_custom_html_encoders_are_isolated_between_async_tasks() -> None:
    """Keep custom encoder overrides within the active async context.

    Returns:
        None.
    """
    results: dict[str, str] = {}

    async def custom_encoder() -> None:
        """Set a context-local encoder and render one value.

        Returns:
            None.
        """
        EncodedHtmlString.encode_using(lambda value, _double: f"custom:{value}")
        await anyio.lowlevel.checkpoint()
        results["custom"] = EncodedHtmlString("value").to_html()

    async def default_encoder() -> None:
        """Render with the default encoder in a separate task context.

        Returns:
            None.
        """
        await anyio.lowlevel.checkpoint()
        results["default"] = EncodedHtmlString("<value>").to_html()

    async def run_tasks() -> None:
        """Run custom and default encoders concurrently.

        Returns:
            None.
        """
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(custom_encoder)
            task_group.start_soon(default_encoder)

    try:
        anyio.run(run_tasks)
        assert results == {
            "custom": "custom:value",
            "default": "&lt;value&gt;",
        }
        assert EncodedHtmlString("<value>").to_html() == "&lt;value&gt;"
    finally:
        EncodedHtmlString.flush_state()
