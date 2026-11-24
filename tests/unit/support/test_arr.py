"""Verify Laravel-compatible array utility contracts.

The cases focus on nested paths, explicit ``None`` values, mutation behavior,
and stable key handling across Titanspan's Python representations.
"""

import locale
from collections.abc import Hashable, Iterator, Mapping, Sequence
from typing import cast

import pytest
from hypothesis import given, strategies

from titanspan.support import (
    Arr,
    ArrayConversionError,
    ArrayMutationError,
    ArrayValueError,
    InvalidSortCriterionError,
)

EXPECTED_COUNT = 3
EXPECTED_RATIO = 1.5
LAST_MATCH_BOUNDARY = 3
EXPECTED_LAST_MATCH = 2
FOURTH_VALUE = 4
SINGLE_VALUE = 7
SECOND_VALUE = 2
UNREADABLE_LOOKUP_ERROR = "Lookup is unavailable."


@pytest.mark.unit
def test_get_and_has_distinguish_missing_from_none() -> None:
    """Resolve nested keys without confusing missing values with ``None``.

    Returns:
        None.
    """
    data: dict[str, object] = {"user": {"name": None}}

    assert Arr.get(data, "user.name", "fallback") is None
    assert Arr.get(data, "user.email", "fallback") == "fallback"
    assert Arr.has(data, "user.name")
    assert not Arr.has(data, "user.email")


@pytest.mark.unit
def test_get_evaluates_callable_default_only_when_missing() -> None:
    """Evaluate callable defaults lazily for absent paths.

    Returns:
        None.
    """
    calls = 0

    def fallback() -> str:
        """Count evaluation and provide a fallback value.

        Returns:
            The fallback value.
        """
        nonlocal calls
        calls += 1
        return "fallback"

    assert Arr.get({"present": "value"}, "present", fallback) == "value"
    assert calls == 0
    assert Arr.get({}, "missing", fallback) == "fallback"
    assert calls == 1


@pytest.mark.unit
def test_set_and_forget_mutate_nested_mapping() -> None:
    """Set and remove dot-addressed values on a mutable mapping.

    Returns:
        None.
    """
    data: dict[str, object] = {}

    Arr.set(data, "account.profile.name", "Titanspan")
    assert data == {"account": {"profile": {"name": "Titanspan"}}}

    Arr.forget(data, "account.profile.name")
    assert data == {"account": {"profile": {}}}


@pytest.mark.unit
def test_pull_returns_present_none_and_removes_only_requested_key() -> None:
    """Pull a key while preserving explicit null semantics.

    Returns:
        None.
    """
    data: dict[str, object] = {"nested": {"value": None}, "keep": True}

    assert Arr.pull(data, "nested.value", "fallback") is None
    assert data == {"nested": {}, "keep": True}


@pytest.mark.unit
def test_dot_undot_round_trip_nested_mappings() -> None:
    """Flatten and restore non-empty nested mappings.

    Returns:
        None.
    """
    data = {"user": {"name": "Ada", "active": True}, "empty": {}}

    dotted = Arr.dot(data)

    assert dotted == {"user.name": "Ada", "user.active": True, "empty": {}}
    assert Arr.undot(dotted) == data


@pytest.mark.unit
def test_flatten_respects_depth_and_discards_mapping_keys() -> None:
    """Flatten nested values to the requested depth.

    Returns:
        None.
    """
    data = [{"one": 1, "two": {"three": 3}}]

    assert Arr.flatten(data, 1) == [1, {"three": 3}]
    assert Arr.flatten(data) == [1, 3]


@pytest.mark.unit
def test_typed_accessors_validate_values() -> None:
    """Return values of the requested type and reject mismatches.

    Raises:
        ValueError: If a retrieved value has the wrong type.
    """
    data: dict[str, object] = {
        "active": True,
        "count": EXPECTED_COUNT,
        "ratio": EXPECTED_RATIO,
        "name": "Ada",
        "items": [1, 2],
    }

    assert Arr.boolean(data, "active") is True
    assert Arr.integer(data, "count") == EXPECTED_COUNT
    assert Arr.float(data, "ratio") == EXPECTED_RATIO
    assert Arr.string(data, "name") == "Ada"
    assert Arr.array(data, "items") == [1, 2]

    with pytest.raises(ValueError, match="must be a boolean"):
        Arr.boolean(data, "count")


@pytest.mark.unit
def test_compatibility_aliases_share_the_python_implementation() -> None:
    """Expose camelCase names without duplicating implementation logic.

    Returns:
        None.
    """
    data = {"first_name": "Ada"}

    assert Arr.has_all(data, ["first_name"])
    assert Arr.hasAll(data, ["first_name"])
    assert Arr.is_assoc({"first_name": "Ada"})
    assert Arr.isAssoc({"first_name": "Ada"})
    assert Arr.crossJoin([1], ["a"]) == [[1, "a"]]
    assert Arr.exceptValues({"number": 1}, 1) == {}
    assert Arr.is_list(["first", "second"])
    assert Arr.isList(["first", "second"])
    assert not Arr.is_list({0: "first", 2: "second"})
    assert Arr.keyBy([{"id": 1}], "id") == {1: {"id": 1}}
    assert Arr.onlyValues({"one": 1, "two": 2}, 2) == {"two": 2}
    assert Arr.sortRecursive({"b": 2, "a": 1}) == {"a": 1, "b": 2}


@pytest.mark.unit
def test_every_laravel_arr_method_has_a_python_entry_point() -> None:
    """Keep the pinned Arr method inventory visible in Python APIs.

    Returns:
        None.
    """
    method_names = (
        "accessible",
        "arrayable",
        "add",
        "array",
        "boolean",
        "collapse",
        "crossJoin",
        "divide",
        "dot",
        "undot",
        "except",
        "exceptValues",
        "exists",
        "first",
        "last",
        "take",
        "flatten",
        "float",
        "forget",
        "from",
        "get",
        "has",
        "hasAll",
        "hasAny",
        "every",
        "some",
        "integer",
        "isAssoc",
        "isList",
        "join",
        "keyBy",
        "prependKeysWith",
        "only",
        "onlyValues",
        "select",
        "pluck",
        "map",
        "mapWithKeys",
        "mapSpread",
        "prepend",
        "pull",
        "query",
        "random",
        "set",
        "push",
        "shuffle",
        "sole",
        "sort",
        "sortDesc",
        "sortRecursive",
        "sortRecursiveDesc",
        "string",
        "toCssClasses",
        "toCssStyles",
        "where",
        "reject",
        "partition",
        "whereNotNull",
        "wrap",
    )

    def python_name(name: str) -> str:
        """Map pinned Laravel reserved words to legal Python names.

        Args:
            name: The upstream public method name.

        Returns:
            The corresponding Titanspan snake_case name.
        """
        aliases = {"except": "except_", "from": "from_"}
        if name in aliases:
            return aliases[name]
        output: list[str] = []
        for character in name:
            if character.isupper():
                output.extend(("_", character.lower()))
            else:
                output.append(character)
        return "".join(output).lstrip("_")

    for name in method_names:
        python_api = python_name(name)
        assert callable(getattr(Arr, python_api))
        if name not in {"except", "from"}:
            assert callable(getattr(Arr, name, None))


@pytest.mark.unit
def test_cross_join_and_partition_preserve_values() -> None:
    """Build products and partition entries without losing keys.

    Returns:
        None.
    """
    products = Arr.cross_join([1, 2], ["a", "b"])

    assert products == [[1, "a"], [1, "b"], [2, "a"], [2, "b"]]

    def is_one(value: object, _: Hashable) -> bool:
        """Recognize the selected integer partition value.

        Args:
            value: The value being inspected.
            _: The item's key, which is irrelevant to this predicate.

        Returns:
            Whether the value is integer one.
        """
        return isinstance(value, int) and value == 1

    assert Arr.partition({"a": 1, "b": 2}, is_one) == (
        {"a": 1},
        {"b": 2},
    )


@pytest.mark.unit
def test_key_by_pluck_and_select_support_nested_data() -> None:
    """Project nested values while preserving explicit result keys.

    Returns:
        None.
    """
    users: list[dict[str, object]] = [
        {"id": "u1", "profile": {"name": "Ada", "active": True}},
        {"id": "u2", "profile": {"name": "Lin", "active": False}},
    ]

    assert Arr.key_by(users, "id") == {"u1": users[0], "u2": users[1]}
    assert Arr.pluck(users, "profile.name") == ["Ada", "Lin"]
    assert Arr.select(users, ["id"]) == [{"id": "u1"}, {"id": "u2"}]


@pytest.mark.unit
def test_map_and_map_with_keys_keep_expected_order() -> None:
    """Map values and re-key entries in their original iteration order.

    Returns:
        None.
    """
    data = {"a": 1, "b": 2}

    assert Arr.map(data, lambda value, key: f"{key}{value}") == {
        "a": "a1",
        "b": "b2",
    }
    assert Arr.map_with_keys(data, lambda value, key: {key.upper(): value}) == {
        "A": 1,
        "B": 2,
    }


@pytest.mark.unit
def test_predicates_and_filters_follow_callback_results() -> None:
    """Apply keyed callbacks consistently to predicate and filter helpers.

    Returns:
        None.
    """
    data = {"a": 1, "b": 2, "c": None}

    def positive(value: object, _: Hashable) -> bool:
        """Check that an item is a positive integer.

        Args:
            value: The value being inspected.
            _: The item's key, which is irrelevant to this predicate.

        Returns:
            Whether the value is a positive integer.
        """
        return (
            isinstance(value, int) and not isinstance(value, bool) and value > 0
        )

    assert Arr.every({"a": 1}, positive)
    assert Arr.some(data, positive)
    assert Arr.where(data, positive) == {"a": 1, "b": 2}
    assert Arr.reject(data, positive) == {"c": None}
    assert Arr.where_not_null(data) == {"a": 1, "b": 2}


@pytest.mark.unit
def test_collection_helpers_cover_empty_and_negative_boundaries() -> None:
    """Handle empty inputs, defaults, negative limits, and CSS values.

    Returns:
        None.
    """
    assert Arr.first([], default="empty") == "empty"

    def below_three(value: object, _: Hashable) -> bool:
        """Select values below the named boundary.

        Args:
            value: The value being inspected.
            _: The item's positional key.

        Returns:
            Whether the value is below three.
        """
        return isinstance(value, int) and value < LAST_MATCH_BOUNDARY

    assert (
        Arr.last([1, EXPECTED_LAST_MATCH, LAST_MATCH_BOUNDARY], below_three)
        == EXPECTED_LAST_MATCH
    )
    assert Arr.take([1, 2, LAST_MATCH_BOUNDARY], -2) == [
        EXPECTED_LAST_MATCH,
        LAST_MATCH_BOUNDARY,
    ]
    assert Arr.wrap(None) == []
    assert Arr.join(["one", "two", "three"], ", ", " and ") == (
        "one, two and three"
    )
    assert Arr.to_css_classes({"active": True, "hidden": False}) == "active"
    assert Arr.to_css_styles(["color:red", "display:none;"]) == (
        "color:red; display:none;"
    )


@pytest.mark.unit
def test_query_and_random_helpers_validate_requested_count() -> None:
    """Serialize query data and reject impossible random selections.

    Raises:
        ValueError: If more items are requested than exist.
    """
    data = {"q": "a b", "page": 2}

    assert Arr.query(data) == "q=a%20b&page=2"
    assert Arr.random(data) in {"a b", 2}

    with pytest.raises(ValueError, match="Requested 3 items"):
        Arr.random(data, 3)


@pytest.mark.unit
def test_only_and_except_accept_iterables_of_keys() -> None:
    """Select and exclude keys while preserving source mapping order.

    Returns:
        None.
    """
    data = {"a": 1, "b": 2, "c": 3}

    assert Arr.only(data, ["c", "a"]) == {"a": 1, "c": 3}
    assert Arr.except_(data, ["b"]) == {"a": 1, "c": 3}


@pytest.mark.unit
def test_mapping_operations_cover_upstream_contracts() -> None:
    """Check core mapping classification and composition operations.

    Returns:
        None.
    """
    assert Arr.accessible({})
    assert Arr.accessible(("a", "b"))
    assert not Arr.accessible("text")
    assert Arr.arrayable(iter((1, 2)))
    assert not Arr.arrayable("text")
    assert Arr.divide({"first": 1, "second": 2}) == (
        ["first", "second"],
        [1, 2],
    )
    assert Arr.collapse([[1, 2], [3]]) == [1, 2, 3]
    assert Arr.collapse([{"a": 1}, {"a": 2, "b": 3}]) == {
        "a": 2,
        "b": 3,
    }


@pytest.mark.unit
def test_add_except_values_and_direct_existence() -> None:
    """Add absent nested values and filter mapping entries by value.

    Returns:
        None.
    """
    source: dict[str, object] = {"present": None, "enabled": True}

    assert Arr.add(source, "new.value", 1) is source
    assert Arr.add(source, "present", "filled") is source
    assert source["present"] == "filled"
    assert Arr.exists(source, "enabled")
    assert not Arr.exists(source, "missing")
    assert Arr.except_values({"int": 1, "bool": True}, 1) == {}
    assert Arr.except_values(
        {"int": 1, "bool": True},
        1,
        strict=True,
    ) == {"bool": True}


@pytest.mark.unit
def test_lazy_first_and_iterable_last_consume_expected_items() -> None:
    """Avoid exhausting generators when finding a first matching item.

    Returns:
        None.
    """
    visited: list[int] = []

    def values() -> object:
        """Yield values while recording iteration.

        Returns:
            The source generator.
        """
        for value in range(5):
            visited.append(value)
            yield value

    assert Arr.first(values()) == 0
    assert visited == [0]


@pytest.mark.unit
def test_mapping_reads_and_paths_cover_missing_and_invalid_boundaries() -> None:
    """Handle broken mapping access and invalid nested mutations safely.

    Returns:
        None.
    """

    class UnreadableMapping(Mapping[str, object]):
        """Expose a mapping whose lookup deliberately fails with TypeError.

        Iteration remains valid so the implementation reaches the read
        boundary through the standard Mapping protocol.
        """

        def __getitem__(self, key: str) -> object:
            """Reject item access to exercise guarded mapping reads.

            Args:
                key: The requested key.

            Returns:
                No value; this mapping rejects every lookup.

            Raises:
                TypeError: Always, to model a malformed adapter boundary.
            """
            del key
            raise TypeError(UNREADABLE_LOOKUP_ERROR)

        def __iter__(self) -> Iterator[str]:
            """Yield the advertised key for Mapping protocol compatibility.

            Returns:
                An iterator containing the advertised key.
            """
            return iter(("value",))

        def __len__(self) -> int:
            """Report one advertised mapping key.

            Returns:
                The number of advertised keys.
            """
            return 1

    unreadable = UnreadableMapping()
    assert Arr.get(unreadable, "value", "fallback") == "fallback"
    assert Arr.has(3, []) is False

    with pytest.raises(TypeError, match="Sequence paths"):
        Arr.set([], "name", 1)


@pytest.mark.unit
def test_collapse_reindexes_numeric_mapping_keys_and_later_sequences() -> None:
    """Reindex numeric keys while preserving string-keyed mapping entries.

    Returns:
        None.
    """
    assert Arr.collapse(
        [["first"], {0: "second", "label": "named"}, ["third"]],
    ) == {
        0: "first",
        1: "second",
        "label": "named",
        2: "third",
    }


@pytest.mark.unit
def test_pluck_supports_key_fields_and_missing_fields() -> None:
    """Extract values with field keys and represent absent fields as null.

    Returns:
        None.
    """
    records: list[dict[str, object]] = [
        {"id": "first", "value": 1},
        {"id": "second"},
    ]

    assert Arr.pluck(records, "value") == [1, None]
    assert Arr.pluck(records, "value", "id") == {
        "first": 1,
        "second": None,
    }
    assert Arr.pluck([[1], [2]], 0) == [1, 2]


@pytest.mark.unit
def test_array_conversion_and_sorting_report_invalid_inputs() -> None:
    """Raise typed errors when conversion or sort criteria are invalid.

    Returns:
        None.
    """
    with pytest.raises(ArrayConversionError):
        Arr.from_(object())

    with pytest.raises(InvalidSortCriterionError):
        Arr.sort([1], cast("Sequence[object]", 1))


@pytest.mark.unit
def test_recursive_sort_handles_nested_sequences_and_mixed_categories() -> None:
    """Sort nested positional values with deterministic type ordering.

    Returns:
        None.
    """
    result = Arr.sort_recursive([3, [2, 1], "a", None])

    assert result == [3, "a", [1, 2], None]

    def even(value: object, _: Hashable) -> bool:
        """Identify even integer values.

        Args:
            value: The value being inspected.
            _: The source position.

        Returns:
            Whether the value is even.
        """
        return isinstance(value, int) and value % 2 == 0

    assert Arr.last(iter((1, 2, 3, FOURTH_VALUE)), even) == FOURTH_VALUE


@pytest.mark.unit
def test_nested_presence_selection_and_iteration_helpers() -> None:
    """Cover Laravel key predicates and field projection helpers.

    Returns:
        None.
    """
    source = {"profile": {"name": "Ada"}, "active": True}

    assert Arr.has_all(source, ["profile.name", "active"])
    assert not Arr.has_all(source, [])
    assert Arr.has_any(source, ["missing", "active"])
    assert not Arr.has_any(source, None)
    assert Arr.only_values({"one": 1, "two": 2}, [2]) == {"two": 2}
    assert Arr.prepend_keys_with({"name": "Ada"}, "user_") == {
        "user_name": "Ada"
    }
    assert Arr.where_not_null({"present": 1, "missing": None}) == {"present": 1}


@pytest.mark.unit
def test_map_spread_appends_each_source_key() -> None:
    """Expand each tuple and preserve Laravel's appended-key callback.

    Returns:
        None.
    """

    def combine(first: object, second: object, key: object) -> str:
        """Combine spread values with their source key.

        Args:
            first: The first tuple value.
            second: The second tuple value.
            key: The input mapping key.

        Returns:
            A joined representation of the values.
        """
        return f"{first}-{second}-{key}"

    assert Arr.map_spread({"row": ("a", "b")}, combine) == {"row": "a-b-row"}


@pytest.mark.unit
def test_prepend_push_and_random_preserve_container_semantics() -> None:
    """Cover prepend behavior and in-place sequence appends.

    Returns:
        None.
    """
    assert Arr.prepend(["b", "c"], "a") == ["a", "b", "c"]
    assert Arr.prepend({"name": "Ada"}, "first") == {
        0: "first",
        "name": "Ada",
    }
    assert Arr.prepend({"b": 2}, 1, "a") == {"a": 1, "b": 2}

    values: dict[str, object] = {}
    assert Arr.push(values, "tags", "python", "async") is values
    assert values == {"tags": ["python", "async"]}
    root: list[object] = []
    assert Arr.push(root, None, "one", "two") is root
    assert root == ["one", "two"]

    assert Arr.random([]) is None
    sample = Arr.random({"a": 1, "b": 2}, 2, preserve_keys=True)
    assert sample == {"a": 1, "b": 2}
    assert Arr.shuffle({"a": 1, "b": 2}) in ([1, 2], [2, 1])


@pytest.mark.unit
def test_sole_and_sort_helpers_cover_success_and_failure_paths() -> None:
    """Select a unique value and sort common Python array values.

    Raises:
        LookupError: If no item matches.
        ValueError: If multiple values match.
    """
    assert Arr.sole({"only": SINGLE_VALUE}) == SINGLE_VALUE
    with pytest.raises(LookupError, match="No matching item"):
        Arr.sole([], lambda _value, _key: True)
    with pytest.raises(ValueError, match="Expected one item"):
        Arr.sole([7, 7])

    assert Arr.sort({"high": 3, "low": 1}) == {"low": 1, "high": 3}
    assert Arr.sort_desc({"low": 1, "high": 3}) == {
        "high": 3,
        "low": 1,
    }
    assert Arr.sort_recursive({"z": 1, "a": 2}) == {"a": 2, "z": 1}
    assert Arr.sort_recursive_desc({"a": 1, "z": 2}) == {"z": 2, "a": 1}
    assert Arr.sort_recursive({"values": [10, 2]}, Arr.SORT_NUMERIC) == {
        "values": [2, 10]
    }


@pytest.mark.unit
def test_sort_accepts_field_paths_and_multiple_criteria() -> None:
    """Sort record sequences with one or more Laravel-style selectors.

    Returns:
        None.
    """
    records: list[dict[str, object]] = [
        {"name": "John", "age": 8},
        {"name": "John", "age": 10},
        {"name": "Dave", "age": 10},
    ]

    assert Arr.sort(records, "name") == [records[2], records[0], records[1]]
    assert Arr.sort(records, ["name", ("age", "desc")]) == [
        records[2],
        records[1],
        records[0],
    ]
    assert Arr.sort_desc(records, "name") == [
        records[0],
        records[1],
        records[2],
    ]


@pytest.mark.unit
def test_from_converts_iterables_and_object_attributes() -> None:
    """Convert common Python data carriers into mapping or list values.

    Returns:
        None.
    """

    class Record:
        """Represent a simple record used by the conversion test.

        Attributes:
            name: The stored record name.
        """

        def __init__(self) -> None:
            """Initialize the record with its test value.

            The object intentionally uses a normal instance attribute so
            ``Arr.from_`` can demonstrate standard Python object conversion.
            """
            self.name = "Titanspan"

    assert Arr.from_(("a", "b")) == ["a", "b"]
    assert Arr.from_(Record()) == {"name": "Titanspan"}


@pytest.mark.unit
def test_css_compilers_and_wrapping_handle_mapping_and_iterable_inputs() -> (
    None
):
    """Compile conditional CSS data and wrap general iterables.

    Returns:
        None.
    """
    assert Arr.to_css_classes({"enabled": True, "disabled": False}) == (
        "enabled"
    )
    assert Arr.to_css_styles({"color: red": True, "display: none": False}) == (
        "color: red;"
    )
    assert Arr.wrap(iter((1, 2))) == [1, 2]


@pytest.mark.unit
def test_sequence_paths_mutation_and_missing_defaults() -> None:
    """Apply nested path operations to lists and distinguish invalid keys.

    Returns:
        None.
    """
    values: list[object] = ["zero"]

    assert Arr.get(values, None) is values
    assert Arr.get(values, 0) == "zero"
    assert Arr.get(values, "0") == "zero"
    assert Arr.get(values, True, "missing") == "missing"
    assert Arr.get(values, -1, "missing") == "missing"
    assert Arr.get(values, "no-index", "missing") == "missing"

    Arr.set(values, 2, "two")
    assert values == ["zero", None, "two"]
    Arr.forget(values, 0)
    assert values == [None, "two"]

    with pytest.raises(TypeError, match="non-negative integer"):
        Arr.set(values, "invalid", "value")

    with pytest.raises(ArrayMutationError):
        Arr.push({"tags": "immutable target"}, "tags", "python")


@pytest.mark.unit
def test_array_conversions_cover_iterables_models_and_invalid_values() -> None:
    """Convert standard iterables and model objects or reject scalars.

    Raises:
        ArrayConversionError: If an object cannot become mapping data.
    """

    class ModelDump:
        """Provide a Pydantic-style model conversion method.

        The small test object validates the model boundary without replacing
        the separate integration test against Pydantic itself.
        """

        def model_dump(self) -> dict[str, object]:
            """Return the model fields as a dictionary.

            Returns:
                A dictionary containing one model field.
            """
            return {"id": EXPECTED_COUNT}

    class ToDict:
        """Provide a compatibility object exposing ``to_dict``.

        The fixture confirms that Titanspan accepts plain Python model
        adapters without requiring a framework-specific base class.
        """

        def to_dict(self) -> dict[str, object]:
            """Return one named field as a dictionary.

            Returns:
                A dictionary containing one model field.
            """
            return {"name": "Ada"}

    assert Arr.from_(iter((1, 2))) == [1, 2]
    assert Arr.from_(ModelDump()) == {"id": EXPECTED_COUNT}
    assert Arr.from_(ToDict()) == {"name": "Ada"}

    with pytest.raises(ArrayConversionError):
        Arr.from_(object())

    with pytest.raises(ArrayConversionError):
        Arr.from_(None)


@pytest.mark.unit
def test_nested_query_sort_and_css_edges() -> None:
    """Handle nested query data, sort modes, and CSS input shapes.

    Returns:
        None.
    """
    assert Arr.query({"filters": {"active": True}, "values": [1, None]}) == (
        "filters%5Bactive%5D=1&values%5B0%5D=1"
    )
    assert Arr.query({"missing": None}) == ""

    natural = Arr.sort_recursive(
        ["file10", "file2"],
        Arr.SORT_NATURAL,
    )
    assert natural == ["file2", "file10"]
    folded = Arr.sort_recursive(
        ["b", "A", "a"],
        Arr.SORT_STRING | Arr.SORT_FLAG_CASE,
    )
    assert folded == ["A", "a", "b"]
    assert Arr.sort_recursive(["10", "2"], Arr.SORT_NUMERIC) == [
        "2",
        "10",
    ]

    mixed: list[object] = [b"byte", None, 4, "text", object()]
    assert len(Arr.sort(mixed)) == len(mixed)
    assert Arr.sort_desc(["b", 2, None]) == [None, "b", 2]

    assert Arr.to_css_classes("active") == "active"
    assert Arr.to_css_classes(["active", "rounded"]) == "active rounded"
    assert Arr.to_css_classes(3) == "3"
    assert Arr.to_css_styles("color:red") == "color:red;"
    assert Arr.to_css_styles(["color:red", "padding:0;"]) == (
        "color:red; padding:0;"
    )
    assert Arr.to_css_styles(3) == "3"

    assert Arr.wrap((1, 2)) == (1, 2)
    assert Arr.wrap([1, 2]) == [1, 2]


@pytest.mark.unit
def test_sort_rejects_unsupported_selectors_and_maps_object_fields() -> None:
    """Reject invalid sort criteria and read attributes from object records.

    Raises:
        InvalidSortCriterionError: If a selector uses an unsupported shape.
    """

    class Record:
        """Provide named fields for attribute-based selection.

        Attributes:
            name: The record's display name.
        """

        def __init__(self, name: str) -> None:
            """Initialize one record.

            Args:
                name: The value exposed as an object attribute.
            """
            self.name = name

    records = [Record("z"), Record("a")]
    assert Arr.pluck(records, "name") == ["z", "a"]
    assert Arr.sort(records, "name") == [records[1], records[0]]
    assert Arr.select(records, ["name"]) == [
        {"name": "z"},
        {"name": "a"},
    ]

    assert Arr.sort([{"age": 5}, {"age": 1}], ("age", "asc")) == [
        {"age": 1},
        {"age": 5},
    ]
    with pytest.raises(InvalidSortCriterionError):
        Arr.sort([1, 2], cast("Sequence[object]", object()))
    with pytest.raises(InvalidSortCriterionError):
        Arr.sort([1, 2], [("value", "sideways")])


@pytest.mark.unit
def test_mapping_defaults_types_and_mixed_collapse_cases() -> None:
    """Cover typed errors, keyed conversions, and mixed container merging.

    Raises:
        ArrayValueError: If a typed accessor receives an incompatible value.
    """
    assert Arr.array({"items": {"first": 1}}, "items") == {"first": 1}
    assert Arr.array({}, "items", []) == []
    assert Arr.collapse([[1], {"name": "Ada"}, [2]]) == {
        0: 1,
        "name": "Ada",
        1: 2,
    }
    assert Arr.collapse([[1], [2], {"name": "Ada"}]) == {
        0: 1,
        1: 2,
        "name": "Ada",
    }

    assert Arr.only({"one": 1, "two": 2}, "one") == {"one": 1}
    assert Arr.except_({"one": 1, "two": 2}, "one") == {"two": 2}
    assert Arr.only_values({"integer": 1, "boolean": True}, 1) == {
        "integer": 1,
        "boolean": True,
    }
    assert Arr.only_values(
        {"integer": 1, "boolean": True},
        1,
        strict=True,
    ) == {"integer": 1}

    with pytest.raises(ArrayValueError):
        Arr.array({}, "items")
    with pytest.raises(ArrayValueError):
        Arr.float({"ratio": 1}, "ratio")
    with pytest.raises(ArrayValueError):
        Arr.integer({"count": True}, "count")
    with pytest.raises(ArrayValueError):
        Arr.string({"name": None}, "name")


@pytest.mark.unit
def test_sort_key_by_reject_filters_and_lifecycle_helpers() -> None:
    """Exercise sorting callbacks and conditional keyed transformations.

    Returns:
        None.
    """
    assert Arr.sort(["aa", "b"], len) == ["b", "aa"]

    def invalid_key(item: object) -> Hashable:
        """Return an unhashable value through a typed test boundary.

        Args:
            item: The list-like item returned as an invalid key.

        Returns:
            A statically typed view used to exercise runtime validation.
        """
        return cast("Hashable", item)

    assert Arr.key_by([[1], [2]], invalid_key) == {}
    assert Arr.join([], ",") == ""
    assert Arr.join(["only"], ",", " and ") == "only"
    assert Arr.is_assoc(["first", "second"]) is False
    assert Arr.is_list({0: "first", 1: "second"})
    assert Arr.is_list({0: "first", 2: "second"}) is False

    assert Arr.take({"first": 1, "second": 2}, 1) == {"first": 1}
    assert Arr.take({"first": 1, "second": 2}, -1) == {"second": 2}
    assert Arr.random({"only": 1}, 1) == [1]
    assert Arr.shuffle([1, 2]) in ([1, 2], [2, 1])
    assert Arr.set({}, None, "replacement") == "replacement"
    assert Arr.wrap(5) == [5]


@pytest.mark.unit
def test_defaults_error_paths_and_empty_predicate_behaviour() -> None:
    """Resolve lazy defaults and distinguish empty or unmatched predicates.

    Returns:
        None.
    """
    calls = 0

    def fallback() -> str:
        """Count a requested fallback and return its value.

        Returns:
            A stable fallback string.
        """
        nonlocal calls
        calls += 1
        return "missing"

    assert Arr.get({}, "key", fallback) == "missing"
    assert calls == 1
    assert Arr.add({"key": "present"}, "key", "ignored") == {"key": "present"}
    assert Arr.has({}, "nested.path") is False
    assert Arr.has({}, None) is False
    assert Arr.every([], lambda _value, _key: True)
    assert Arr.some([], lambda _value, _key: True) is False
    assert (
        Arr.first(
            [1, SECOND_VALUE],
            lambda value, _key: value == SECOND_VALUE,
        )
        == SECOND_VALUE
    )
    assert Arr.first([1], lambda _value, _key: False, fallback) == "missing"
    assert (
        Arr.last([1, SECOND_VALUE], lambda _value, _key: False, fallback)
        == "missing"
    )
    assert (
        Arr.sole(
            [1, SECOND_VALUE],
            lambda value, _key: value == SECOND_VALUE,
        )
        == SECOND_VALUE
    )
    assert Arr.flatten([[1, [2]]]) == [1, 2]
    assert Arr.collapse([]) == []
    assert Arr.crossJoin() == [[]]
    assert Arr.crossJoin([], [1]) == []
    assert Arr.divide({}) == ([], [])
    assert Arr.to_css_classes([]) == ""
    assert Arr.to_css_styles("") == ""


@pytest.mark.unit
def test_prepend_mutation_and_sort_failures_are_explicit() -> None:
    """Preserve prepend keys and reject invalid nested mutation and sorting.

    Returns:
        None.
    """
    assert Arr.prepend({4: "four", "name": "Ada", 7: "seven"}, "first") == {
        0: "first",
        1: "four",
        "name": "Ada",
        2: "seven",
    }
    with pytest.raises(TypeError, match="hashable"):
        Arr.prepend({"name": "Ada"}, "first", [])

    source: dict[str, object] = {"user": None}
    Arr.forget(source, "user.name")
    assert source == {"user": None}

    with pytest.raises(InvalidSortCriterionError):
        Arr.sort([1, 2], [object()])


@pytest.mark.unit
def test_sort_modes_cover_locale_and_case_sensitive_ordering() -> None:
    """Use locale and natural comparison flags without changing global locale.

    Returns:
        None.
    """
    values = ["z", "a", "B"]
    expected = sorted(values, key=locale.strxfrm)
    assert Arr.sort_recursive(values, Arr.SORT_LOCALE_STRING) == expected
    assert Arr.sort_recursive(
        ["file10", "File2", "file1"],
        Arr.SORT_NATURAL | Arr.SORT_FLAG_CASE,
    ) == ["file1", "File2", "file10"]


@pytest.mark.unit
@given(
    strategies.dictionaries(
        strategies.text(min_size=1).filter(lambda key: "." not in key),
        strategies.integers(),
        max_size=12,
    )
)
def test_dot_and_undot_round_trip_generated_flat_mappings(
    values: dict[str, int],
) -> None:
    """Preserve flat mappings through generated dot and undot operations.

    Args:
        values: A mapping with keys that do not require nested paths.

    Returns:
        None.
    """
    assert Arr.undot(Arr.dot(values)) == values
