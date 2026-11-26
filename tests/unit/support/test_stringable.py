"""Verify immutable fluent strings and Python string interoperability.

The tests check chaining, return types, immutability,
condition callbacks, macro invocation, and Python string interoperability.
"""

from __future__ import annotations

import pytest

from titanspan.support import Str, Stringable

EXPECTED_TEXT_LENGTH = 19
EXPECTED_REPEATED_WORDS = "ha ha"
EXPECTED_UUID = "550e8400-e29b-41d4-a716-446655440000"
EXPECTED_ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
EXPECTED_POSITION = 2
EXPECTED_WORD_COUNT = 3


def append_marker(value: Stringable, _condition: object) -> Stringable:
    """Return a fluent value with a marker appended.

    Args:
        value: The callback's current Stringable value.
        _condition: The predicate result passed by Conditionable.

    Returns:
        A new Stringable value ending in an exclamation mark.
    """
    return value.append("!")


def append_default(value: Stringable, _condition: object) -> Stringable:
    """Return a fallback fluent value with a question mark appended.

    Args:
        value: The callback's current Stringable value.
        _condition: The predicate result passed by Conditionable.

    Returns:
        A new Stringable value ending in a question mark.
    """
    return value.append("?")


@pytest.mark.unit
def test_stringable_chains_transformations_and_keeps_original_value() -> None:
    """Chain transformations while keeping instances immutable.

    Returns:
        None.
    """
    original = Str.of("  Hello World  ")
    result = original.trim().lower().replace(" ", "-").append("-framework")

    assert isinstance(original, Stringable)
    assert original.to_string() == "  Hello World  "
    assert original.value() == original.to_string()
    assert len(original) == len(original.value())
    assert result.to_string() == "hello-world-framework"
    assert str(result) == "hello-world-framework"


@pytest.mark.unit
def test_stringable_preserves_native_result_types() -> None:
    """Return strings, predicates, and numeric values from their own APIs.

    Returns:
        None.
    """
    value = Str.of("Titanspan Framework")

    assert value.contains("Framework") is True
    assert value.length() == EXPECTED_TEXT_LENGTH
    assert value.match(r"Titan\w+").to_string() == "Titanspan"
    assert value.to_base64().from_base64().to_string() == (
        "Titanspan Framework"
    )


@pytest.mark.unit
def test_stringable_supports_chained_path_transformations() -> None:
    """Apply path-oriented transformations with the fluent interface.

    Returns:
        None.
    """
    value = Stringable("path/to/report.csv")

    assert value.after_last("/").before_last(".").to_string() == "report"
    assert value.starts_with("path")
    assert value.ends_with(".csv")


@pytest.mark.unit
def test_stringable_conditional_operations_delegate_to_conditionable() -> None:
    """Apply conditional string operations with fluent results.

    Returns:
        None.
    """
    matched = [
        Stringable("Titanspan").when_contains("Titan", append_marker),
        Stringable("Titanspan").when_contains_all(
            ["Titan", "span"],
            append_marker,
        ),
        Stringable("").when_empty(append_marker),
        Stringable("Titanspan").when_not_empty(append_marker),
        Stringable("Titanspan").when_ends_with("span", append_marker),
        Stringable("Titanspan").when_doesnt_end_with("other", append_marker),
        Stringable("Titanspan").when_exactly(
            Stringable("Titanspan"),
            append_marker,
        ),
        Stringable("Titanspan").when_not_exactly("other", append_marker),
        Stringable("Titanspan").when_is("Titan*", append_marker),
        Stringable("Titanspan").when_is_ascii(append_marker),
        Stringable(EXPECTED_UUID).when_is_uuid(append_marker),
        Stringable(EXPECTED_ULID).when_is_ulid(append_marker),
        Stringable("Titanspan").when_starts_with("Titan", append_marker),
        Stringable("Titanspan").when_doesnt_start_with("other", append_marker),
        Stringable("Titanspan").when_test("Titan.*", append_marker),
    ]

    assert [
        result.to_string()
        for result in matched
        if isinstance(result, Stringable)
    ] == [
        "Titanspan!",
        "Titanspan!",
        "!",
        "Titanspan!",
        "Titanspan!",
        "Titanspan!",
        "Titanspan!",
        "Titanspan!",
        "Titanspan!",
        "Titanspan!",
        f"{EXPECTED_UUID}!",
        f"{EXPECTED_ULID}!",
        "Titanspan!",
        "Titanspan!",
        "Titanspan!",
    ]

    fallback = Stringable("Titanspan").when_contains(
        "missing",
        append_marker,
        append_default,
    )
    assert isinstance(fallback, Stringable)
    assert fallback.to_string() == "Titanspan?"
    camel_case = [
        Stringable("Titanspan").when_contains("Titan", append_marker),
        Stringable("Titanspan").when_contains_all(
            ["Titan", "span"],
            append_marker,
        ),
        Stringable("").when_empty(append_marker),
        Stringable("Titanspan").when_not_empty(append_marker),
        Stringable("Titanspan").when_ends_with("span", append_marker),
        Stringable("Titanspan").when_doesnt_end_with("other", append_marker),
        Stringable("Titanspan").when_exactly(
            "Titanspan",
            append_marker,
        ),
        Stringable("Titanspan").when_not_exactly("other", append_marker),
        Stringable("Titanspan").when_is("Titan*", append_marker),
        Stringable("Titanspan").when_is_ascii(append_marker),
        Stringable(EXPECTED_UUID).when_is_uuid(append_marker),
        Stringable(EXPECTED_ULID).when_is_ulid(append_marker),
        Stringable("Titanspan").when_starts_with("Titan", append_marker),
        Stringable("Titanspan").when_doesnt_start_with(
            "other",
            append_marker,
        ),
        Stringable("Titanspan").when_test("Titan.*", append_marker),
    ]
    assert [str(result) for result in camel_case] == [
        "Titanspan!",
        "Titanspan!",
        "!",
        "Titanspan!",
        "Titanspan!",
        "Titanspan!",
        "Titanspan!",
        "Titanspan!",
        "Titanspan!",
        "Titanspan!",
        f"{EXPECTED_UUID}!",
        f"{EXPECTED_ULID}!",
        "Titanspan!",
        "Titanspan!",
        "Titanspan!",
    ]


@pytest.mark.unit
def test_stringable_supports_delimiter_and_case_transformations() -> None:
    """Delegate common delimiter and case operations to Str.

    Returns:
        None.
    """
    value = Stringable("[hello_world]")

    assert value.between("[", "]").camel().to_string() == "helloWorld"
    assert value.between_first("[", "]").kebab().to_string() == ("hello-world")
    assert value.before_last("_").after("[").to_string() == "hello"
    assert value.after_last("_").before("]").to_string() == "world"
    assert Stringable("hello-world").studly().to_string() == "HelloWorld"
    assert Stringable("hello-world").snake().to_string() == "hello_world"
    assert Stringable("hello-world").pascal().to_string() == "HelloWorld"
    assert Stringable("Crème brûlée").ascii().slug().to_string() == (
        "creme-brulee"
    )
    assert Stringable("prefix value").chop_start("prefix ").to_string() == (
        "value"
    )
    assert Stringable("value.csv").chop_end(".csv").to_string() == "value"


@pytest.mark.unit
def test_stringable_exposes_string_predicates_and_native_results() -> None:
    """Return native booleans and extracted values for predicates.

    Returns:
        None.
    """
    value = Stringable("Titanspan Framework")

    assert value.contains_all(["Titan", "Framework"])
    assert value.doesnt_contain("Django")
    assert value.starts_with("Titan")
    assert value.doesnt_start_with("Django")
    assert value.ends_with("Framework")
    assert value.doesnt_end_with("Django")
    assert value.is_("Titan*")
    assert value.is_match(r"Framework$")
    assert value.test(r"^Titan")
    assert value.is_ascii()
    assert Stringable('{"enabled": true}').is_json()
    assert Stringable("https://example.com").is_url()
    assert Stringable(EXPECTED_UUID).is_uuid(4)
    assert Stringable(EXPECTED_ULID).is_ulid()
    assert Stringable("").is_empty()
    assert value.is_not_empty()
    assert Stringable(" \t\n").is_blank()
    assert value.is_not_blank()
    assert value.length() == EXPECTED_TEXT_LENGTH
    assert Stringable("Titan🙂").char_at(-1) == "🙂"
    with pytest.raises(IndexError):
        Stringable("x").char_at(10)


@pytest.mark.unit
def test_stringable_handles_padding_search_and_replacements() -> None:
    """Delegate search, replacement, and padding operations to Str.

    Returns:
        None.
    """
    value = Stringable("a/b/c")

    assert value.replace("/", "-").to_string() == "a-b-c"
    assert value.replace_array("/", ["one", "two"]).to_string() == ("aonebtwoc")
    assert value.replace_first("/", "-").to_string() == "a-b/c"
    assert value.replace_last("/", "-").to_string() == "a/b-c"
    assert value.replace_start("a", "x").to_string() == "x/b/c"
    assert value.replace_end("c", "x").to_string() == "a/b/x"
    assert value.replace_matches(r"/", "-").to_string() == "a-b-c"
    assert value.remove(["/", "b"]).to_string() == "ac"
    assert value.swap({"/": "-", "a": "x"}).to_string() == "x-b-c"
    assert value.position("b") == EXPECTED_POSITION
    assert Stringable("Handler@run").parse_callback() == (
        "Handler",
        "run",
    )
    assert Stringable("x").pad_left(3, "0").to_string() == "00x"
    assert Stringable("x").pad_right(3, "0").to_string() == "x00"
    assert Stringable("x").pad_both(3, "0").to_string() == "0x0"


@pytest.mark.unit
def test_stringable_handles_unicode_limits_and_whitespace() -> None:
    """Preserve Unicode code points through slicing and normalization.

    Returns:
        None.
    """
    value = Stringable("  one   two three  ")

    assert value.squish().to_string() == "one two three"
    assert value.trim().to_string() == "one   two three"
    assert Stringable("--value--").trim("-").to_string() == "value"
    assert Stringable("  value  ").ltrim().to_string() == "value  "
    assert Stringable("  value  ").rtrim().to_string() == "  value"
    assert (
        Stringable("one two three")
        .limit(
            7,
            preserve_words=True,
        )
        .to_string()
        == "one..."
    )
    assert value.words(2).to_string() == "  one   two..."
    assert value.word_count() == EXPECTED_WORD_COUNT
    assert value.word_count("-") == EXPECTED_WORD_COUNT
    assert value.word_wrap(7).to_string() == "  one\ntwo\nthree"
    assert Stringable("hello").substr(1, 3).to_string() == "ell"
    assert Stringable("ababa").substr_count("a") == EXPECTED_WORD_COUNT
    assert Stringable("hello").substr_replace("X", 1, 2).to_string() == ("hXlo")
    assert Stringable("Titanspan").take(-4).to_string() == "span"


@pytest.mark.unit
def test_stringable_formats_and_encodes_strings() -> None:
    """Keep fluent transformations and formatting return types distinct.

    Returns:
        None.
    """
    value = Stringable("hello_world")

    assert value.convert_case(1).to_string() == "hello_world"
    assert value.deduplicate("_").to_string() == "hello_world"
    assert value.headline().to_string() == "Hello World"
    assert value.initials().to_string() == "h"
    assert Stringable("hello world").initials(True).to_string() == "HW"
    assert value.lcfirst().to_string() == "hello_world"
    assert value.ucfirst().to_string() == "Hello_world"
    assert value.ucwords().to_string() == "Hello_world"
    assert value.upper().to_string() == "HELLO_WORLD"
    assert Stringable("hello world").title().to_string() == "Hello World"
    assert Stringable("S/N: 12").numbers().to_string() == "12"
    assert Stringable("one").append(" ", "two").to_string() == "one two"
    assert Stringable("two").prepend("one", " ").to_string() == "one two"
    assert Stringable("line").new_line(2).to_string() == "line\n\n"
    assert Stringable("ha ").repeat(2).to_string() == (
        EXPECTED_REPEATED_WORDS + " "
    )
    assert Stringable("xx").reverse().to_string() == "xx"
    assert Stringable("api///").finish("/").to_string() == "api/"
    assert Stringable("///api").start("/").to_string() == "/api"
    assert Stringable("<value>").unwrap("<", ">").to_string() == "value"
    assert Stringable("value").wrap("<", ">").to_string() == "<value>"
    encoded = Stringable("Titanspan").to_base64()
    assert encoded.from_base64().to_string() == "Titanspan"
    assert encoded.to_string() == str(encoded)
    assert Stringable("VALUE").to_string() == "VALUE"
    assert Stringable("<b>safe</b>").to_html_string().to_html() == (
        "<b>safe</b>"
    )


@pytest.mark.unit
def test_stringable_checks_errors_and_mutable_offset_boundaries() -> None:
    """Reject invalid offsets and transformation arguments explicitly.

    Returns:
        None.
    """
    value = Stringable("abc")

    with pytest.raises(IndexError):
        _ = value[3]
    with pytest.raises(TypeError):
        _ = value[True]
    with pytest.raises(IndexError):
        value[3] = "x"
    with pytest.raises(TypeError):
        value[True] = "x"
    with pytest.raises(ValueError, match="one code point"):
        value[0] = "xy"
    with pytest.raises(IndexError):
        del value[-4]
    with pytest.raises(ValueError, match="count must be non-negative"):
        Stringable("x").new_line(-1)
    with pytest.raises(ValueError, match="times must be non-negative"):
        Stringable("x").repeat(-1)
    assert not Stringable("").offset_exists(0)
    assert not Stringable("x").offset_exists(True)
    assert Stringable("x").__repr__() == "Stringable('x')"


@pytest.mark.unit
def test_stringable_supports_indexing_and_offset_mutation() -> None:
    """Expose native Python indexing and immutable string behavior.

    Returns:
        None.
    """
    value = Stringable("Titanspan")

    assert value[0] == "T"
    assert value[-4:] == "span"
    assert value.offset_exists(0)
    assert value.offset_exists(-1)
    assert not value.offset_exists(20)
    value[0] = "t"
    assert str(value) == "titanspan"
    del value[0]
    assert str(value) == "itanspan"


@pytest.mark.unit
def test_stringable_composes_conditionable_and_macroable_behaviour() -> None:
    """Reuse shared conditional and macro mixins without dynamic lookup.

    Returns:
        None.
    """

    def append_suffix(value: Stringable, suffix: str) -> Stringable:
        """Append a suffix through a registered macro.

        Args:
            value: The fluent string receiving the suffix.
            suffix: The text appended to the value.

        Returns:
            A new fluent string.
        """
        return value.append(suffix)

    Stringable.macro("appendSuffix", append_suffix)
    source = Stringable("Titanspan")
    result = source.when(
        lambda current: current.starts_with("Titan"),
        lambda current, _condition: current.call_macro(
            "appendSuffix",
            " Framework",
        ),
    )

    try:
        assert isinstance(result, Stringable)
        assert result.to_string() == "Titanspan Framework"
        assert Stringable.has_macro("appendSuffix")
    finally:
        Stringable.flush_macros()
