"""Verify secure random string generation and its scoped test controls.

The tests cover native generation methods, deterministic factory overrides,
and isolation between copied execution contexts.
"""

from collections.abc import Callable, Iterator
from contextvars import copy_context
from string import ascii_letters, digits, punctuation
from typing import cast

import pytest

from titanspan.support import Str

_ALPHANUMERIC = ascii_letters + digits
_DEFAULT_RANDOM_LENGTH = 16
_DEFAULT_PASSWORD_LENGTH = 32
_DIGITS_ONLY_PASSWORD_LENGTH = 24
_SEQUENCE_RANDOM_LENGTH = 8
_FALLBACK_ERROR_MESSAGE = "random sequence exhausted"
RandomStringFactory = Callable[[int], str]


@pytest.fixture(autouse=True)
def reset_random_string_factory() -> Iterator[None]:
    """Restore secure generation before and after each test.

    Yields:
        Control to the test with no active factory override.
    """
    Str.create_random_strings_normally()
    try:
        yield
    finally:
        Str.create_random_strings_normally()


@pytest.mark.unit
@pytest.mark.parametrize("length", [0, 1, 16, 63])
def test_random_returns_requested_alphanumeric_length(length: int) -> None:
    """Generate the requested number of ASCII letters and digits.

    Args:
        length: Number of characters requested from the generator.
    """
    result = Str.random(length)

    assert isinstance(result, str)
    assert len(result) == length
    assert set(result) <= set(_ALPHANUMERIC)


@pytest.mark.unit
def test_random_defaults_to_sixteen_characters() -> None:
    """Use the documented default length when the caller omits it.

    Returns:
        None.
    """
    assert len(Str.random()) == _DEFAULT_RANDOM_LENGTH


@pytest.mark.unit
def test_random_with_negative_length_returns_an_empty_string() -> None:
    """Return an empty result for a negative requested length.

    Returns:
        None.
    """
    assert Str.random(-1) == ""


@pytest.mark.unit
def test_password_includes_each_enabled_character_class() -> None:
    """Generate passwords with letters, digits, and symbols by default.

    Returns:
        None.
    """
    password = Str.password()

    assert len(password) == _DEFAULT_PASSWORD_LENGTH
    assert any(character in ascii_letters for character in password)
    assert any(character in digits for character in password)
    assert any(character in punctuation for character in password)


@pytest.mark.unit
def test_password_can_restrict_the_enabled_character_classes() -> None:
    """Keep all generated characters within the explicitly enabled class.

    Returns:
        None.
    """
    password = Str.password(
        _DIGITS_ONLY_PASSWORD_LENGTH,
        letters=False,
        numbers=True,
        symbols=False,
    )

    assert len(password) == _DIGITS_ONLY_PASSWORD_LENGTH
    assert set(password) <= set(digits)


@pytest.mark.unit
@pytest.mark.parametrize("length", [0, 1, 2])
def test_password_requires_space_for_each_enabled_class(length: int) -> None:
    """Reject lengths too short to include every enabled character class.

    Args:
        length: The requested length below the three enabled classes.
    """
    with pytest.raises(ValueError, match="length must be at least"):
        Str.password(length)


@pytest.mark.unit
def test_password_requires_at_least_one_enabled_character_class() -> None:
    """Reject a password configuration with an empty character alphabet.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="at least one character class"):
        Str.password(12, letters=False, numbers=False, symbols=False)


@pytest.mark.unit
def test_password_rejects_boolean_lengths() -> None:
    """Do not treat Python booleans as integer password lengths.

    Returns:
        None.
    """
    with pytest.raises(TypeError, match="length must be an integer"):
        Str.password(True)


@pytest.mark.unit
def test_random_uses_the_active_context_factory_override() -> None:
    """Use an injected factory for deterministic random strings.

    Returns:
        None.
    """
    Str.create_random_strings_using(lambda length: f"size:{length}")

    assert Str.random(7) == "size:7"


@pytest.mark.unit
def test_factory_override_isolated_to_copied_context() -> None:
    """Keep factory changes in an execution context separate from its parent.

    Returns:
        None.
    """
    Str.create_random_strings_using(lambda length: f"parent:{length}")
    child_context = copy_context()
    child_context.run(
        Str.create_random_strings_using,
        lambda length: f"child:{length}",
    )

    assert child_context.run(Str.random, 4) == "child:4"
    assert Str.random(4) == "parent:4"


@pytest.mark.unit
def test_none_factory_restores_secure_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restore the secure generator when a factory is cleared.

    Args:
        monkeypatch: Pytest helper for replacing the secure choice boundary.
    """
    Str.create_random_strings_using(lambda _length: "override")

    def choose_first(alphabet: str) -> str:
        """Return a deterministic member of the supplied alphabet.

        Args:
            alphabet: The allowed random characters.

        Returns:
            The first allowed character.
        """
        assert set(alphabet) == set(_ALPHANUMERIC)
        return alphabet[0]

    monkeypatch.setattr("titanspan.support.str.secrets.choice", choose_first)
    Str.create_random_strings_using(None)

    assert Str.random(4) == "aaaa"


@pytest.mark.unit
def test_factory_must_return_a_string() -> None:
    """Reject invalid custom factory results at the integration boundary.

    Returns:
        None.
    """

    def invalid_factory(_length: int) -> str:
        """Return an invalid runtime value through the declared contract.

        Args:
            _length: Requested size, unused by this invalid test callback.

        Returns:
            A non-string value cast to the factory's declared return type.
        """
        return cast("str", 4)

    Str.create_random_strings_using(invalid_factory)

    with pytest.raises(TypeError, match="must return a string"):
        Str.random(1)


@pytest.mark.unit
def test_sequence_factory_uses_values_then_secure_fallback() -> None:
    """Consume a fixed sequence and generate normally when it is exhausted.

    Returns:
        None.
    """
    Str.create_random_strings_using_sequence(["first", "second"])

    assert Str.random(_SEQUENCE_RANDOM_LENGTH) == "first"
    assert Str.random(_SEQUENCE_RANDOM_LENGTH) == "second"
    assert len(Str.random(_SEQUENCE_RANDOM_LENGTH)) == _SEQUENCE_RANDOM_LENGTH


@pytest.mark.unit
def test_sequence_factory_uses_custom_fallback_for_missing_values() -> None:
    """Pass requested lengths to the configured sequence fallback.

    Returns:
        None.
    """
    received_lengths: list[int] = []

    def fallback(length: int) -> str:
        """Record the request and return a stable test value.

        Args:
            length: The requested random string length.

        Returns:
            A deterministic string derived from ``length``.
        """
        received_lengths.append(length)
        return f"fallback:{length}"

    Str.create_random_strings_using_sequence(["first"], fallback)

    assert Str.random(4) == "first"
    assert Str.random(9) == "fallback:9"
    assert received_lengths == [9]


@pytest.mark.unit
def test_sequence_consumption_is_local_to_each_copied_context() -> None:
    """Copying a context preserves its sequence position independently.

    Returns:
        None.
    """
    Str.create_random_strings_using_sequence(["first", "second"])
    child_context = copy_context()

    assert Str.random() == "first"
    assert child_context.run(Str.random) == "first"
    assert Str.random() == "second"
    assert child_context.run(Str.random) == "second"


@pytest.mark.unit
def test_sequence_factory_propagates_custom_fallback_errors() -> None:
    """Preserve exceptions raised by a caller-provided fallback.

    Returns:
        None.
    """

    def fallback(_length: int) -> str:
        """Raise a deterministic error after the sequence is exhausted.

        Args:
            _length: The requested length, unused by this fallback.

        Raises:
            LookupError: Always, to make fallback failure observable.
        """
        raise LookupError(_FALLBACK_ERROR_MESSAGE)

    Str.create_random_strings_using_sequence(["only"], fallback)

    assert Str.random(1) == "only"
    with pytest.raises(LookupError, match="sequence exhausted"):
        Str.random(1)


@pytest.mark.unit
@pytest.mark.parametrize("factory", ["not callable", 42])
def test_factory_registration_rejects_non_callable_values(
    factory: object,
) -> None:
    """Reject values that cannot provide generated strings.

    Args:
        factory: An invalid value passed through the untyped boundary.
    """
    invalid_factory = cast("RandomStringFactory", factory)

    with pytest.raises(TypeError):
        Str.create_random_strings_using(invalid_factory)


@pytest.mark.unit
def test_sequence_registration_rejects_non_string_values() -> None:
    """Reject sequence entries that cannot satisfy the string contract.

    Returns:
        None.
    """
    invalid_sequence = cast("list[str]", ["valid", 2])

    with pytest.raises(TypeError):
        Str.create_random_strings_using_sequence(invalid_sequence)


@pytest.mark.unit
def test_sequence_registration_rejects_non_iterables() -> None:
    """Reject values that cannot provide an ordered sequence.

    Returns:
        None.
    """
    invalid_sequence = cast("list[str]", 5)

    with pytest.raises(TypeError, match="must be iterable"):
        Str.create_random_strings_using_sequence(invalid_sequence)


@pytest.mark.unit
def test_sequence_registration_rejects_non_callable_fallbacks() -> None:
    """Reject a fallback that cannot create a value after exhaustion.

    Returns:
        None.
    """
    invalid_fallback = cast("RandomStringFactory", "fallback")

    with pytest.raises(TypeError, match="fallback must be callable"):
        Str.create_random_strings_using_sequence([], invalid_fallback)
