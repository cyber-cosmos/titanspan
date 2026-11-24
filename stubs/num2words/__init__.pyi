"""Describe the narrow num2words API used at the Support boundary."""

def num2words(
    number: int | float,
    ordinal: bool = False,
    lang: str = "en",
    to: str = "cardinal",
) -> str:
    """Convert one numeric value to cardinal or ordinal words."""
