"""Verify hierarchical configuration reads, mutation, and mapping behavior.

The tests preserve Python's strict type and mapping conventions.
"""

import asyncio
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import cast

import pytest

from titanspan.config import ConfigValueError, Repository

pytestmark = pytest.mark.unit
CACHE_TTL = 30
WORKER_COUNT = 4
CHILD_TASK_COUNT = 2
_TYPED_ACCESSORS: Mapping[str, Callable[[Repository, str], object]] = {
    "string": lambda repository, key: repository.string(key),
    "integer": lambda repository, key: repository.integer(key),
    "float": lambda repository, key: repository.float(key),
    "boolean": lambda repository, key: repository.boolean(key),
    "array": lambda repository, key: repository.array(key),
}


def test_repository_distinguishes_missing_values_and_literal_dotted_keys() -> (
    None
):
    """Preserve explicit nulls and prefer literal dotted mapping keys.

    Returns:
        None.
    """
    repository = Repository(
        {
            "service.name": "literal",
            "service": {"name": "nested", "active": False},
            "empty": None,
        }
    )

    assert repository.get("service.name") == "literal"
    assert repository.get("service.active") is False
    assert repository.has("empty")
    assert repository.get("empty", "fallback") is None
    assert repository.get("missing", "fallback") == "fallback"


def test_repository_resolves_callable_defaults_only_when_missing() -> None:
    """Evaluate a lazy default once only when its path is absent.

    Returns:
        None.
    """
    repository = Repository({"present": 0})
    calls: list[str] = []

    def fallback() -> str:
        """Record evaluation and provide a fallback string.

        Returns:
            The fallback configuration value.
        """
        calls.append("called")
        return "default"

    default: Callable[[], str] = fallback

    assert repository.get("present", default) == 0
    assert calls == []
    assert repository.get("missing", default) == "default"
    assert calls == ["called"]


def test_repository_retrieves_many_paths_and_per_key_defaults() -> None:
    """Return requested paths and apply their individual fallback values.

    Returns:
        None.
    """
    repository = Repository({"app": {"name": "Titanspan", "debug": False}})

    assert repository.get(["app.name", "app.debug", "missing"]) == {
        "app.name": "Titanspan",
        "app.debug": False,
        "missing": None,
    }
    assert repository.get_many(
        {"app.name": "fallback", "queue.workers": 4}
    ) == {
        "app.name": "Titanspan",
        "queue.workers": 4,
    }
    assert repository.get_many(["app.name"]) == {
        "app.name": "Titanspan",
    }
    assert repository.get({"app.missing": "fallback"}) == {
        "app.missing": "fallback",
    }


@pytest.mark.parametrize(
    ("method_name", "key", "expected"),
    [
        ("string", "name", "Titanspan"),
        ("integer", "workers", WORKER_COUNT),
        ("float", "temperature", 0.25),
        ("boolean", "debug", False),
        ("array", "providers", ["native"]),
    ],
)
def test_typed_accessors_accept_values_of_the_declared_type(
    method_name: str,
    key: str,
    expected: object,
) -> None:
    """Return configured values after strict native type validation.

    Args:
        method_name: Accessor selected for this case.
        key: Configuration key holding the test value.
        expected: The expected typed value.

    Returns:
        None.
    """
    values: dict[str, object] = {
        "name": "Titanspan",
        "workers": WORKER_COUNT,
        "temperature": 0.25,
        "debug": False,
        "providers": ["native"],
    }
    repository = Repository(values)

    assert _TYPED_ACCESSORS[method_name](repository, key) == expected


@pytest.mark.parametrize(
    ("value", "accessor"),
    [
        (True, "integer"),
        (4, "float"),
        (0, "boolean"),
        ("do-not-leak", "integer"),
        (None, "string"),
        (7, "array"),
    ],
)
def test_typed_accessors_reject_coercion_and_wrong_shapes(
    value: object,
    accessor: str,
) -> None:
    """Reject values that do not have the requested concrete type.

    Args:
        value: Invalid value stored under the selected key.
        accessor: Typed accessor expected to reject the value.

    Returns:
        None.
    """
    repository = Repository({"secret.setting": value})

    with pytest.raises(ConfigValueError) as error:
        _TYPED_ACCESSORS[accessor](repository, "secret.setting")

    assert "secret.setting" in str(error.value)
    assert "do-not-leak" not in str(error.value)


def test_repository_mutates_nested_values_and_sequence_settings() -> None:
    """Apply dot-path writes, batches, and ordered sequence changes.

    Returns:
        None.
    """
    repository = Repository({"app": {"middleware": ["existing"]}})

    repository.set("app.debug", True)
    repository.set({"app.name": "Titanspan", "cache.ttl": CACHE_TTL})
    repository.prepend("app.middleware", "first")
    repository.push("app.middleware", "last")

    assert repository.all()["app"] == {
        "middleware": ["first", "existing", "last"],
        "debug": True,
        "name": "Titanspan",
    }
    assert repository.get("cache.ttl") == CACHE_TTL


def test_mutations_inside_overrides_do_not_escape_into_base_configuration() -> (
    None
):
    """Keep writes and deletions inside the active override layer.

    Nested scopes see outer scoped writes, while leaving either scope restores
    the previous view without changing the base repository.
    """
    repository = Repository(
        {
            "app": {"name": "base", "debug": False},
            "middleware": ["base"],
        }
    )

    with repository.override({"app.debug": True}):
        repository.set("app.name", "outer")
        repository.push("middleware", "outer")

        with repository.override({"app.name": "inner"}):
            repository.set("app.name", "inner-updated")
            assert repository.get("app.name") == "inner-updated"

        assert repository.get("app.name") == "outer"
        assert repository.get("app.debug") is True
        assert repository.get("middleware") == ["base", "outer"]
        del repository["app.debug"]
        assert not repository.has("app.debug")

    assert repository.get("app.name") == "base"
    assert repository.get("app.debug") is False
    assert repository.get("middleware") == ["base"]


def test_repository_owns_builtin_inputs_and_returned_mutable_values() -> None:
    """Prevent caller mutations from bypassing repository write semantics.

    Built-in mappings and lists are copied at construction, assignment, and
    retrieval boundaries. Opaque application objects retain their identity.
    """
    initial = {"app": {"flags": ["initial"]}}
    repository = Repository(initial)

    initial["app"]["flags"].append("external")
    loaded = repository.get("app")
    assert isinstance(loaded, dict)
    loaded_values = cast("dict[str, object]", loaded)
    loaded_flags = cast("list[object]", loaded_values["flags"])
    loaded_flags.append("returned")

    assigned = {"workers": [1]}
    repository.set("queue", assigned)
    assigned["workers"].append(2)
    retrieved = repository.get("queue")
    assert isinstance(retrieved, dict)
    retrieved_values = cast("dict[str, object]", retrieved)
    retrieved_workers = cast("list[object]", retrieved_values["workers"])
    retrieved_workers.append(3)

    assert repository.get("app.flags") == ["initial"]
    assert repository.get("queue.workers") == [1]


@pytest.mark.anyio
async def test_scoped_mutations_are_isolated_between_child_tasks() -> None:
    """Keep inherited override layers independent across concurrent tasks.

    Child tasks inherit the active override at creation, but their subsequent
    writes must remain local to each task and must not change the parent view.
    """
    repository = Repository({"worker": {"name": "base", "tags": []}})
    both_ready = asyncio.Event()
    ready_count = 0

    async def mutate(name: str) -> tuple[str, list[object]]:
        """Write and read one task-local view after both tasks are ready.

        Args:
            name: Value identifying this task's configuration mutation.

        Returns:
            The task's own name and tags after its local writes.
        """
        nonlocal ready_count
        repository.set("worker.name", name)
        repository.push("worker.tags", name)
        ready_count += 1
        if ready_count == CHILD_TASK_COUNT:
            both_ready.set()
        await both_ready.wait()
        tags = repository.get("worker.tags")
        assert isinstance(tags, list)
        return repository.string("worker.name"), cast("list[object]", tags)

    with repository.override({"worker.name": "scope", "worker.tags": []}):
        results = await asyncio.gather(mutate("first"), mutate("second"))
        assert repository.get("worker.name") == "scope"
        assert repository.get("worker.tags") == []

    assert sorted(results) == [
        ("first", ["first"]),
        ("second", ["second"]),
    ]
    assert repository.get("worker.name") == "base"
    assert repository.get("worker.tags") == []


def test_repository_mapping_access_uses_python_missing_key_semantics() -> None:
    """Raise for missing reads and remove deleted paths.

    Returns:
        None.
    """
    repository = Repository({"present": 1})

    assert repository["present"] == 1
    assert "present" in repository
    with pytest.raises(KeyError):
        _ = repository["missing"]

    del repository["present"]
    repository["nested.created"] = "assigned"

    assert not repository.has("present")
    with pytest.raises(KeyError):
        _ = repository["present"]
    with pytest.raises(KeyError):
        del repository["missing"]
    assert repository.get("nested.created") == "assigned"


def test_repository_rejects_non_string_root_keys() -> None:
    """Require text keys for path-addressable root configuration.

    Returns:
        None.
    """
    malformed: object = {1: "invalid"}

    with pytest.raises(TypeError, match="keys must be strings"):
        Repository(cast("Mapping[str, object]", malformed))

    with pytest.raises(TypeError, match="keys must be strings"):
        Repository().set(cast("Mapping[str, object]", malformed))


def test_repository_validates_batch_updates_and_sequence_types() -> None:
    """Reject invalid batches and non-list sequence mutation targets.

    Returns:
        None.
    """
    repository = Repository({"app": {"middleware": "invalid"}})

    with pytest.raises(TypeError, match="batch update"):
        repository.set({"app.name": "Titanspan"}, "unexpected")
    with pytest.raises(TypeError, match="must be a list"):
        repository.prepend("app.middleware", "auth")
    with pytest.raises(TypeError, match="must be a list"):
        repository.push("app.middleware", "logging")

    assert not repository.has("app.name")


def test_repository_copies_nested_builtin_structures_for_snapshots() -> None:
    """Copy supported containers without cloning opaque application values.

    Returns:
        None.
    """
    shared_list = ["initial"]
    repository = Repository(
        {
            "tuple": ("value",),
            "set": {"value"},
            "frozen": frozenset({"value"}),
            "shared": [shared_list, shared_list],
        }
    )

    snapshot = repository.all()

    assert snapshot["tuple"] == ("value",)
    assert snapshot["set"] == {"value"}
    assert snapshot["frozen"] == frozenset({"value"})
    copied_shared = snapshot["shared"]
    assert isinstance(copied_shared, list)
    copied_items = cast("list[object]", copied_shared)
    first_copy = copied_items[0]
    second_copy = copied_items[1]
    assert first_copy is second_copy
    assert first_copy is not shared_list


def test_repository_merges_nested_override_mappings_and_redacts_repr() -> None:
    """Preserve unrelated nested values while producing safe representations.

    Returns:
        None.
    """
    repository = Repository(
        {
            "app": {
                "debug": False,
                "name": "Titanspan",
            },
            "database": {
                "password": "secret-value",  # pragma: allowlist secret
            },
        }
    )

    with repository.override({"app": {"debug": True}}):
        assert repository.get("app") == {
            "debug": True,
            "name": "Titanspan",
        }

    assert "secret-value" not in repr(repository)
    assert "[REDACTED]" in repr(repository)


def test_repository_redaction_stops_at_the_configured_depth_limit() -> None:
    """Bound diagnostic traversal for deeply nested configuration values.

    Returns:
        None.
    """
    deeply_nested: object = "value"
    for _ in range(35):
        deeply_nested = {"nested": deeply_nested}

    diagnostic = Repository({"deep": deeply_nested}).redacted()
    sequences = Repository({"items": ["one"], "pair": ("two",)}).redacted()

    assert "<maximum depth>" in repr(diagnostic)
    assert sequences == {"items": ["one"], "pair": ["two"]}


def test_repository_contains_rejects_non_text_keys() -> None:
    """Return false for non-string candidates without path coercion.

    Returns:
        None.
    """
    repository = Repository({"app": {"name": "Titanspan"}})

    assert 1 not in repository


def test_repository_all_returns_a_read_only_top_level_snapshot() -> None:
    """Prevent top-level snapshot edits from mutating repository state.

    Returns:
        None.
    """
    repository = Repository({"app": {"name": "Titanspan"}})
    snapshot = repository.all()

    assert isinstance(snapshot, Mapping)
    assert isinstance(snapshot, MappingProxyType)

    assert repository.has("app")


def test_diagnostics_summarize_unknown_keys_and_nonfinite_values() -> None:
    """Avoid invoking arbitrary key formatting or emitting invalid JSON data.

    Returns:
        None.
    """

    class SecretMapKey:
        """Represent a key that contains sensitive data when stringified.

        Diagnostics must identify the key type without invoking this method.
        """

        def __str__(self) -> str:
            """Return a value that diagnostics must never request.

            Returns:
                A deliberately sensitive string.
            """
            return "private-map-key"

    repository = Repository(
        {
            "unsafe": {SecretMapKey(): "value"},
            "score": float("nan"),
            "opaque": object(),
        }
    )

    diagnostic = repository.redacted()

    assert diagnostic["unsafe"] == {
        "<SecretMapKey key>": "[REDACTED]",
    }
    assert diagnostic["score"] == "<non-finite float>"
    assert diagnostic["opaque"] == "<object>"
    assert "private-map-key" not in str(diagnostic)


def test_repository_overrides_are_nested_and_context_local() -> None:
    """Restore nested configuration after the override scope exits.

    Returns:
        None.
    """
    repository = Repository({"app": {"debug": False, "name": "Titanspan"}})

    with repository.override({"app.debug": True}):
        assert repository.boolean("app.debug")
        assert repository.get("app.name") == "Titanspan"

    assert repository.boolean("app.debug") is False


def test_repository_macro_methods_delegate_to_the_canonical_registry() -> None:
    """Use the shared Support macro lifecycle without a second registry.

    Returns:
        None.
    """

    def has_name(repository: Repository) -> bool:
        """Check for the application name on the bound repository.

        Args:
            repository: Repository supplied as the macro's bound receiver.

        Returns:
            Whether the application name setting is present.
        """
        return repository.has("app.name")

    Repository.flush_macros()
    Repository.macro("hasName", has_name)
    repository = Repository({"app": {"name": "Titanspan"}})

    try:
        assert Repository.has_macro("hasName")
        assert repository.call_macro("hasName") is True
    finally:
        Repository.flush_macros()
