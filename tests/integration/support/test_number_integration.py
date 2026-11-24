"""Verify Number behavior across the real optional number libraries.

The tests exercise the locale and spelling boundaries with installed packages.
"""

from __future__ import annotations

import pytest

from titanspan.support import Number


@pytest.mark.integration
def test_number_uses_babel_locale_data_for_formatting_and_parsing() -> None:
    """Use Babel's installed CLDR data for formatting and decimal parsing.

    Returns:
        None.
    """
    assert Number.format(123_456_789, locale="de") == "123.456.789"
    assert Number.parse("1.234,56", locale="de") == 1234.56
    assert Number.currency(1, "EUR", locale="de") == "1,00\u00a0€"


@pytest.mark.integration
def test_number_uses_num2words_for_cardinal_and_ordinal_text() -> None:
    """Delegate word spelling to the installed num2words implementation.

    Returns:
        None.
    """
    assert Number.spell(10) == "ten"
    assert Number.spell(3, locale="fr") == "trois"
    assert Number.ordinal(3) == "3rd"
    assert Number.spell_ordinal(3) == "third"
