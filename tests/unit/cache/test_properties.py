"""Check portable cache invariants over generated values and tag groups.
"""  # fmt: skip

import string
from math import ulp

import pytest
from hypothesis import given, settings, strategies

from titanspan.cache import CacheConfiguration, CacheManager
from titanspan.cache._serialization import JSONSerializer
from titanspan.cache.expiration import normalize_ttl

pytestmark = pytest.mark.unit

_SAFE_CHARACTERS = string.ascii_letters + string.digits
_MAX_TTL_ROUNDING_ERROR = 0.001001
_SAFE_TEXT = strategies.text(
    alphabet=strategies.characters(
        blacklist_categories=("Cs",),
    ),
    max_size=20,
)
_JSON_VALUES = strategies.recursive(
    strategies.none()
    | strategies.booleans()
    | strategies.integers()
    | strategies.floats(
        allow_nan=False,
        allow_infinity=False,
        width=64,
    )
    | _SAFE_TEXT,
    lambda children: (
        strategies.lists(children, max_size=4)
        | strategies.dictionaries(_SAFE_TEXT, children, max_size=4)
    ),
    max_leaves=20,
)


@settings(max_examples=100, deadline=None)
@given(value=_JSON_VALUES)
def test_safe_json_values_round_trip(value: object) -> None:
    """Preserve every value in the supported bounded JSON data model.
    """  # fmt: skip
    serializer = JSONSerializer(100_000)

    assert serializer.decode(serializer.encode(value)) == value


@settings(max_examples=100, deadline=None)
@given(
    duration=strategies.floats(
        min_value=0.000001,
        max_value=315_576_000,
        allow_nan=False,
        allow_infinity=False,
        width=64,
    )
)
def test_positive_ttl_rounding_never_shortens_expiration(
    duration: float,
) -> None:
    """Round positive TTLs upward without exceeding one millisecond.
    """  # fmt: skip
    normalized = normalize_ttl(duration)

    assert normalized is not None
    assert normalized >= duration
    assert normalized - duration < _MAX_TTL_ROUNDING_ERROR
    assert abs(normalized * 1000 - round(normalized * 1000)) < 2 * ulp(
        normalized * 1000
    )


@settings(max_examples=60, deadline=None)
@given(
    names=strategies.lists(
        strategies.text(
            alphabet=_SAFE_CHARACTERS,
            min_size=1,
            max_size=12,
        ),
        min_size=1,
        max_size=8,
    )
)
def test_tag_identity_is_order_and_duplicate_independent(
    names: list[str],
) -> None:
    """Invalidate the same group regardless of order or repeated names.
    """  # fmt: skip
    manager = CacheManager(CacheConfiguration(namespace="tag-property"))
    first = manager.store().tags(*names)
    equivalent = manager.store().tags(*reversed(names), *names)

    assert first.put("shared", names)
    assert equivalent.get("shared") == names

    equivalent.flush()

    assert first.missing("shared")
