"""Verify string transformations and text utility behavior.

The tests cover deterministic string transformations, Unicode handling,
matching, replacement, and both public naming conventions.
"""

import re

import pytest
from hypothesis import given, strategies

from titanspan.support import Str

EXPECTED_CODE_POINT_COUNT = 3
EXPECTED_MATCH_COUNT = 2
EXPECTED_WORD_COUNT = 3
EXPECTED_CHARACTER_INDEX = 1
EXPECTED_HYPHENATED_WORDS = 2
EXPECTED_LAST_MATCH_POSITION = 4
EXPECTED_TWO_WORDS = 2


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "search", "expected"),
    [
        ("hannah", "han", "nah"),
        ("hannah", "missing", "hannah"),
        ("hannah", "", "hannah"),
        ("café au café", "café", " au café"),
    ],
)
def test_after_uses_first_unicode_occurrence(
    subject: str,
    search: str,
    expected: str,
) -> None:
    """Return the text after the first matching substring.

    Args:
        subject: The full input string.
        search: The substring to locate.
        expected: The expected remainder.
    """
    assert Str.after(subject, search) == expected


@pytest.mark.unit
def test_before_last_and_between_extract_delimited_text() -> None:
    """Extract string portions using first and last delimiters.

    Returns:
        None.
    """
    assert Str.before_last("titanspan framework docs", " ") == (
        "titanspan framework"
    )
    assert Str.between("[section] value", "[", "]") == "section"
    assert Str.between_first("[a][b]", "[", "]") == "a"
    assert Str.after_last("/a/b", "/") == "b"


@pytest.mark.unit
def test_prefix_suffix_and_containment_support_multiple_needles() -> None:
    """Match any provided needle and keep empty needles non-matching.

    Returns:
        None.
    """
    assert Str.starts_with("Titanspan", ["Titan", "Tita"])
    assert Str.ends_with("report.csv", [".json", ".csv"])
    assert Str.contains("Titanspan Framework", ["AI", "Framework"])
    assert Str.contains_all("Titanspan Framework", ["Titan", "Framework"])
    assert Str.doesnt_contain("Titanspan", "framework")
    assert not Str.starts_with("Titanspan", "")
    assert not Str.ends_with("", "")


@pytest.mark.unit
def test_string_operations_cover_common_transformations() -> None:
    """Exercise string operations across common transformation groups.

    Returns:
        None.
    """
    assert Str.after_last("a/b", "/") == "b"
    assert Str.before_last("a/b/c", "/") == "a/b"
    assert Str.between_first("[a][b]", "[", "]") == "a"
    assert Str.char_at("Titanspan", 0) == "T"
    assert Str.chop_start("prefix", "pre") == "fix"
    assert Str.chop_end("file.csv", ".csv") == "file"
    assert Str.contains_all("Titanspan", ["Titan", "span"])
    assert Str.doesnt_contain("Titanspan", "Django")
    assert Str.ends_with("report.csv", ".csv")
    assert Str.doesnt_end_with("report.csv", ".json")
    assert Str.is_json('{"ok": true}')
    assert Str.is_ascii("plain")
    assert Str.is_url("https://example.com")
    assert Str.is_uuid("550e8400-e29b-41d4-a716-446655440000", 4)
    assert Str.is_ulid("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert Str.pad_both("x", 3) == " x "
    assert Str.pad_left("x", 2) == " x"
    assert Str.pad_right("x", 2) == "x "
    assert Str.replace_array(":", ["one"], "a:b") == "aoneb"
    assert Str.replace_first("a", "x", "a") == "x"
    assert Str.replace_start("a", "x", "a") == "x"
    assert Str.replace_last("a", "x", "a") == "x"
    assert Str.replace_end("a", "x", "a") == "x"
    assert Str.replace_matches(r"a", "x", "a") == "x"
    assert Str.doesnt_start_with("Titanspan", "Django")
    assert Str.starts_with("Titanspan", "Titan")
    assert Str.substr_count("aba", "a") == EXPECTED_MATCH_COUNT
    assert Str.substr_replace("abc", "X", 1, 1) == "aXc"
    assert Str.to_base64("Titanspan") == Str.to_base64("Titanspan")
    assert Str.word_count("one two") == EXPECTED_TWO_WORDS
    assert Str.word_wrap("one two", 3) == "one\ntwo"
    assert Str.is_match("dog", "a dog")


@pytest.mark.unit
def test_is_uses_glob_patterns_with_explicit_case_option() -> None:
    """Match whole strings with asterisk glob patterns.

    Returns:
        None.
    """
    assert Str.is_("routes/*", "routes/api/v1")
    assert Str.is_("TITAN*", "titanspan", ignore_case=True)
    assert not Str.is_("TITAN*", "titanspan")
    assert not Str.is_([], "anything")


@pytest.mark.unit
def test_case_conversion_handles_acronyms_and_separators() -> None:
    """Convert common identifier forms without losing word boundaries.

    Returns:
        None.
    """
    assert Str.snake("TitanspanHTTPFramework") == "titanspan_http_framework"
    assert Str.camel("hello_world") == "helloWorld"
    assert Str.kebab("Titanspan Python Framework") == (
        "titanspan-python-framework"
    )
    assert Str.studly("hello_world") == "HelloWorld"
    assert Str.pascal("hello-world") == "HelloWorld"
    assert Str.headline("titanspan_http-framework") == (
        "Titanspan Http Framework"
    )


@pytest.mark.unit
def test_slug_and_unicode_operations_use_python_code_points() -> None:
    """Normalize text and count Unicode code points consistently.

    Returns:
        None.
    """
    assert Str.slug("Crème brûlée & AI", dictionary={"&": "and"}) == (
        "creme-brulee-and-ai"
    )
    assert Str.length("你好🙂") == EXPECTED_CODE_POINT_COUNT
    assert Str.char_at("café", -1) == "é"
    with pytest.raises(IndexError):
        Str.char_at("café", 9)
    assert Str.reverse("你好") == "好你"


@pytest.mark.unit
def test_limit_words_and_substring_are_unicode_aware() -> None:
    """Truncate text by Python code points and preserve requested words.

    Returns:
        None.
    """
    assert Str.limit("Titanspan is a framework", 10) == "Titanspan..."
    assert Str.limit("Titanspan is a framework", 15, preserve_words=True) == (
        "Titanspan is..."
    )
    assert Str.words("one two three", 2) == "one two..."
    assert Str.substr("Titanspan", -4, 4) == "span"
    assert Str.substr_count("ééé", "é", 1) == EXPECTED_MATCH_COUNT
    assert Str.take("Titanspan", -4) == "span"


@pytest.mark.unit
def test_replace_family_uses_literal_substrings_and_python_regex() -> None:
    """Replace selected occurrences without interpreting literal text.

    Returns:
        None.
    """
    assert Str.replace_first("a.b", "x", "a.b a.b") == "x a.b"
    assert Str.replace_last("a.b", "x", "a.b a.b") == "a.b x"
    assert Str.replace_start("pre", "new", "prefix") == "newfix"
    assert Str.replace_end("fix", "done", "prefix") == "predone"
    assert Str.replace_matches(r"(\d+)", r"[\1]", "a12b") == "a[12]b"
    assert (
        Str.remove([" ", "-"], "Titan-span Framework") == "TitanspanFramework"
    )


@pytest.mark.unit
def test_string_wrappers_and_whitespace_helpers() -> None:
    """Normalize delimiters and whitespace using explicit operations.

    Returns:
        None.
    """
    assert Str.finish("api////", "/") == "api/"
    assert Str.start("////api", "/") == "/api"
    assert Str.wrap("api", "<") == "<api<"
    assert Str.unwrap("<api>", "<", ">") == "api"
    assert Str.squish("  Titanspan\n  Framework  ") == "Titanspan Framework"
    assert Str.deduplicate("one---two", "-") == "one-two"
    assert Str.trim("***titanspan***", "*") == "titanspan"


@pytest.mark.unit
def test_ascii_json_uuid_and_base64_helpers() -> None:
    """Expose safe standard-library encodings and validators.

    Returns:
        None.
    """
    assert Str.ascii("Crème") == "Creme"
    assert Str.is_json('{"ok": true}')
    assert not Str.is_json("not json")
    assert Str.is_uuid("550e8400-e29b-41d4-a716-446655440000", 4)
    assert not Str.is_uuid("not-a-uuid")
    assert Str.from_base64(Str.to_base64("Titanspan")) == "Titanspan"


@pytest.mark.unit
def test_regex_errors_are_not_silently_swallowed() -> None:
    """Surface invalid regular expressions to the caller.

    Raises:
        re.error: If the supplied regular expression is invalid.
    """
    with pytest.raises(re.error):
        Str.match("(", "value")


@pytest.mark.unit
@given(strategies.text(max_size=40))
def test_trim_is_idempotent(value: str) -> None:
    """Preserve a general invariant across Unicode and control characters.

    Args:
        value: Any generated Unicode string.
    """
    trimmed = Str.trim(value)
    assert Str.trim(trimmed) == trimmed


@pytest.mark.unit
def test_delimiter_helpers_and_empty_patterns() -> None:
    """Handle absent delimiters, empty patterns, and ordered candidates.

    Returns:
        None.
    """
    assert Str.before("hannah", "nah") == "han"
    assert Str.before("hannah", "missing") == "hannah"
    assert Str.before("hannah", "") == "hannah"
    assert Str.after_last("yvette", "tte") == ""
    assert Str.after_last("yvette", "") == "yvette"
    assert Str.between("unmatched", "[", "]") == "unmatched"
    assert Str.between("value", "", "]") == "value"
    assert Str.between_first("value", "[", "") == "value"
    assert Str.before_last("value", "") == "value"
    assert Str.chop_start("prefix-value", ["pre", "prefix-"]) == "fix-value"
    assert Str.chop_end("value.json", [".txt", ".json"]) == "value"
    assert Str.chop_start("value", "") == "value"
    assert Str.chop_end("value", "") == "value"
    assert Str.deduplicate("---", ["", "-"]) == "-"


@pytest.mark.unit
def test_containment_and_prefix_helpers_cover_negative_cases() -> None:
    """Exercise case folding, empty candidates, and negative predicates.

    Returns:
        None.
    """
    assert Str.contains("Titanspan", "TITAN", ignore_case=True)
    assert not Str.contains("Titanspan", "")
    assert not Str.contains("Titanspan", [])
    assert not Str.contains_all("Titanspan", [])
    assert not Str.contains_all("Titanspan", ["Titan", "absent"])
    assert Str.doesnt_end_with("file.csv", ".json")
    assert Str.doesnt_start_with("Titanspan", "Python")
    assert Str.starts_with("Titanspan", "Titan")
    assert Str.doesnt_start_with("Titanspan", "Python")


@pytest.mark.unit
def test_globs_ascii_and_url_validation_cover_boundaries() -> None:
    """Validate patterns and URLs without implying network safety.

    Returns:
        None.
    """
    assert not Str.is_("", "value")
    assert Str.is_("*", "value")
    assert Str.is_ascii("plain")
    assert not Str.is_ascii("café")
    assert Str.is_url("https://localhost:8000/path")
    assert Str.is_url("mailto:hello@example.com")
    assert Str.is_url("https://[::1]/")
    assert not Str.is_url("http://.")
    assert not Str.is_url("https://example.com:invalid")
    assert not Str.is_url("https://example.com", protocols=("http",))
    assert not Str.is_url("https://:8000")
    assert not Str.is_url("https://example.com/path with space")
    assert not Str.is_url(None)
    assert not Str.is_url("https://\ud800")


@pytest.mark.unit
def test_uuid_ulid_and_json_validators_reject_malformed_values() -> None:
    """Reject malformed identifiers and Python-only JSON constants.

    Returns:
        None.
    """
    assert not Str.is_uuid("550e8400-e29b-41d4-a716-446655440000", 1)
    assert not Str.is_uuid(None)
    assert Str.is_ulid("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert Str.is_ulid("01arz3ndektsv4rrffq69g5fav")
    assert not Str.is_ulid("81ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert not Str.is_ulid("invalid")
    assert Str.is_json("null")
    assert not Str.is_json("NaN")
    assert not Str.is_json(1)


@pytest.mark.unit
def test_ascii_case_and_slug_helpers_cover_empty_and_custom_inputs() -> None:
    """Handle empty strings, Unicode decomposition, and slug dictionaries.

    Returns:
        None.
    """
    assert Str.ascii("") == ""
    assert Str.ascii("Straße") == "Strasse"
    assert Str.camel("") == ""
    assert Str.kebab("") == ""
    assert Str.snake("", delimiter=".") == ""
    assert Str.pascal("CBOR", normalize=True) == "Cbor"
    assert Str.studly("http_server") == "HttpServer"
    assert Str.slug("", dictionary={}) == ""
    assert Str.slug("hello @example", dictionary={"@": "at"}) == (
        "hello-at-example"
    )
    assert Str.title("hello world") == "Hello World"
    assert Str.upper("hello") == "HELLO"
    assert Str.lower("HELLO") == "hello"
    assert Str.headline("HELLO_world") == "Hello World"
    assert Str.initials("ada lovelace", capitalize=True) == "AL"
    assert Str.initials("") == ""


@pytest.mark.unit
def test_truncation_mask_and_padding_validate_ranges() -> None:
    """Exercise string boundary operations and their invalid inputs.

    Returns:
        None.
    """
    assert Str.limit("short", 10) == "short"
    assert Str.limit("long string", 4, "", preserve_words=True) == "long"
    assert Str.mask("123456", "*", -3, 2) == "123**6"
    assert Str.mask("123", "", 0) == "123"
    assert Str.mask("123", "*", 8) == "123"
    assert Str.pad_both("x", 4, "ab") == "axab"
    assert Str.pad_left("x", 3, "ab") == "abx"
    assert Str.pad_right("x", 3, "ab") == "xab"
    assert Str.pad_right("long", 2) == "long"
    assert Str.finish("already/", "/") == "already/"
    assert Str.finish("text", "") == "text"
    assert Str.start("/text", "/") == "/text"
    assert Str.start("text", "") == "text"
    assert Str.unwrap("plain", "<", ">") == "plain"
    with pytest.raises(ValueError, match="padding string"):
        Str.pad_left("x", 2, "")
    with pytest.raises(ValueError, match="non-negative"):
        Str.limit("text", -1)
    with pytest.raises(ValueError, match="non-negative"):
        Str.words("text", -1)
    assert Str.words("", 0) == ""
    assert Str.words("one two", 0) == "..."


@pytest.mark.unit
def test_match_and_regex_utilities_preserve_python_errors() -> None:
    """Return capture groups and enforce regular-expression limits.

    Returns:
        None.
    """
    assert Str.match(r"id=(\d+)", "id=42") == "42"
    assert Str.match(r"missing", "value") == ""
    assert Str.is_match([r"cat", r"dog"], "a dog")
    assert not Str.is_match([], "anything")
    assert Str.match_all(r"(\w+)", "one two") == ["one", "two"]
    assert Str.match_all(r"(a)(b)", "ab") == ["a"]
    assert Str.replace_matches(
        r"\d", "x", "123", limit=EXPECTED_CHARACTER_INDEX
    ) == ("x23")


@pytest.mark.unit
def test_replacement_encoding_and_substring_edges() -> None:
    """Cover replacement modes, offsets, and Base64 decode failures.

    Returns:
        None.
    """
    assert Str.replace("TITAN", "Framework", "titan", case_sensitive=False) == (
        "Framework"
    )
    assert Str.replace(["", "absent"], "x", "text") == "text"
    assert Str.replace_first("", "x", "text") == "text"
    assert Str.replace_start("missing", "x", "text") == "text"
    assert Str.replace_end("missing", "x", "text") == "text"
    assert Str.replace_array(":", ["one"], "a:b:c") == "aoneb:c"
    assert Str.replace_array("", [], "text") == "text"
    assert Str.remove("T", "Titanspan", case_sensitive=False) == "ianspan"
    assert Str.numbers("phone: 555") == "555"
    assert Str.position("abcabc", "bc", offset=-3) == (
        EXPECTED_LAST_MATCH_POSITION
    )
    assert Str.position("abc", "z") is None
    assert Str.substr("abcdef", 1, -1) == "bcde"
    assert Str.substr("abc", -10) == "abc"
    assert Str.substr_count("abcabc", "a", -3, EXPECTED_CHARACTER_INDEX) == (
        EXPECTED_CHARACTER_INDEX
    )
    with pytest.raises(ValueError, match="needle"):
        Str.substr_count("abc", "")
    assert Str.substr_replace("abcdef", "X", 1, 2) == "aXdef"
    assert Str.substr_replace("abcdef", "X", -2, -1) == "abcdXf"
    assert Str.take("text", 0) == ""
    assert Str.repeat("x", 0) == ""
    with pytest.raises(ValueError, match="non-negative"):
        Str.repeat("x", -1)
    assert Str.from_base64("!!!", strict=True) is False
    assert Str.from_base64("%%%") == ""
    assert Str.numbers(["tel: 555", "id-9"]) == ["555", "9"]


@pytest.mark.unit
def test_whitespace_case_split_and_word_helpers() -> None:
    """Test explicit separators and Unicode word processing behavior.

    Returns:
        None.
    """
    assert Str.trim("** value **", "*") == " value "
    assert Str.ltrim("...value", ".") == "value"
    assert Str.rtrim("value...", ".") == "value"
    assert Str.squish("   ") == ""
    assert Str.ucfirst("hello") == "Hello"
    assert Str.ucfirst("") == ""
    assert Str.lcfirst("Hello") == "hello"
    assert Str.ucwords("hello-world", "-") == "Hello-World"
    assert Str.ucsplit("TitanspanFramework") == ["Titanspan", "Framework"]
    assert Str.ucsplit("") == []
    assert Str.word_count("hello-world") == EXPECTED_HYPHENATED_WORDS
    assert Str.word_count("foo-bar", "-") == EXPECTED_CHARACTER_INDEX
    assert Str.word_wrap("one two", 3, "|", True) == "one|two"
    assert Str.word_wrap("extraordinary", 4, "|", True) == "extr|aord|inar|y"
    with pytest.raises(ValueError, match="positive"):
        Str.word_wrap("text", 0)


@pytest.mark.unit
def test_callback_parsing_and_keyword_swapping() -> None:
    """Parse callback labels and replace longest mapped terms first.

    Returns:
        None.
    """
    assert Str.parse_callback("Service@run") == ("Service", "run")
    assert Str.parse_callback("Service", "handle") == ("Service", "handle")
    assert Str.parse_callback("Class@anonymous\0file.py@run") == (
        "Class@anonymous\0file.py",
        "run",
    )
    assert Str.parse_callback("Class@anonymous\0file.py") == (
        "Class@anonymous\0file.py",
        None,
    )
    assert Str.swap({"Titan": "T", "Titanspan": "Framework"}, "Titanspan") == (
        "Framework"
    )
    assert Str.swap({}, "Titanspan") == "Titanspan"


@pytest.mark.unit
def test_case_modes_and_contextual_excerpts() -> None:
    """Convert text using named modes and excerpt context.

    Returns:
        None.
    """
    assert Str.convert_case("hello", 0) == "HELLO"
    assert Str.convert_case("HELLO", 1) == "hello"
    assert Str.convert_case("Straße", 3) == "strasse"
    assert Str.convert_case("hello WORLD", 2) == "Hello World"
    assert (
        Str.excerpt(
            "This is a beautiful morning",
            "beautiful",
            {"radius": 5},
        )
        == "...is a beautiful morn..."
    )
    assert Str.excerpt("This is a beautiful morning", "day") is None
    assert Str.excerpt("abc", "b", {"radius": 1}) == "abc"
    assert Str.excerpt("abc", "b", {"radius": 0}) == "...b..."
    with pytest.raises(ValueError, match="mode"):
        Str.convert_case("text", 99)
    with pytest.raises(ValueError, match="radius"):
        Str.excerpt("text", "text", {"radius": -1})
    with pytest.raises(TypeError, match="omission"):
        Str.excerpt("text", "text", {"omission": 1})
