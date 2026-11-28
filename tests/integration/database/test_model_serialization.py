"""Verify bounded model graph serialization with real SQLite persistence.

The tests exercise loaded relationships, cycle handling, visibility rules, and
the guarantee that serialization does not issue database queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import JSON, ForeignKey, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titanspan.database import (
    DatabaseManager,
    DatabaseServiceProvider,
    Model,
    ModelCollection,
    Schema,
)
from titanspan.database.exceptions import ModelSerializationLimitError
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_MAX_TEST_DEPTH = 40
_OVERSIZED_COLLECTION_LENGTH = 300
_EXPECTED_SERIALIZED_MODEL_COUNT = 2
_STATEMENT_EVENT_ARGUMENT_INDEX = 2
_MINIMUM_STATEMENT_EVENT_ARGUMENTS = 3


class SerializationParent(Model):
    """Represent a parent with loaded children and derived attributes.

    The relationships are bidirectional so serialization must detect cycles.
    """

    table = "serialization_parents"
    fillable = ("name", "private_value", "payload")
    hidden = ("private_value",)
    visible = (
        "id",
        "name",
        "payload",
        "children",
        "label",
        "child_names",
    )
    appends = ("label", "child_names")

    name: Mapped[str]
    private_value: Mapped[str]
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    children: Mapped[list[SerializationChild]] = relationship(
        back_populates="parent",
    )

    @property
    def label(self) -> str:
        """Return a derived label from a loaded scalar attribute.
        """  # fmt: skip
        return f"Parent: {self.name}"

    @property
    def child_names(self) -> list[str]:
        """Return child names and record whether an append getter executed.

        The counter lets the async test verify an unloaded relation is never
        touched implicitly during serialization.
        """
        self._child_names_reads = getattr(self, "_child_names_reads", 0) + 1
        return [child.name for child in self.children]


class SerializationChild(Model):
    """Represent a child whose inverse relationship creates a graph cycle.

    The model has its own hidden value and visible-field policy.
    """

    table = "serialization_children"
    fillable = ("parent_id", "name", "private_value")
    hidden = ("private_value",)
    visible = ("id", "name", "parent", "display_name")
    appends = ("display_name",)

    parent_id: Mapped[int] = mapped_column(
        ForeignKey("serialization_parents.id"),
    )
    name: Mapped[str]
    private_value: Mapped[str]
    parent: Mapped[SerializationParent] = relationship(
        back_populates="children",
    )

    @property
    def display_name(self) -> str:
        """Return a derived label from a loaded scalar attribute.
        """  # fmt: skip
        return f"Child: {self.name}"


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with a temporary SQLite database.

    Args:
        tmp_path: Pytest-owned temporary application directory.

    Returns:
        An unopened application configured with Database services.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/model_serialization.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def _create_schema() -> None:
    """Create parent and child tables with a real SQLite foreign key.
    """  # fmt: skip
    async with Schema.create("serialization_parents") as table:
        table.id()
        table.string("name", length=120)
        table.string("private_value", length=120)
        table.json("payload")
        table.timestamps()

    async with Schema.create("serialization_children") as table:
        table.id()
        table.foreign_id("parent_id").references(
            "serialization_parents",
        )
        table.string("name", length=120)
        table.string("private_value", length=120)
        table.timestamps()


def _nested_payload(depth: int) -> dict[str, object]:
    """Build a JSON mapping nested beyond the safe serialization depth.

    Args:
        depth: Number of nested mapping levels to create.

    Returns:
        A JSON-compatible payload with the requested depth.
    """
    value: object = "leaf"
    for _ in range(depth):
        value = {"nested": value}
    return {"root": value}


async def test_model_graph_serialization_is_cycle_safe_and_redacted(
    application: Application,
) -> None:
    """Serialize loaded bidirectional relationships with nested visibility.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_schema()
        parent = await SerializationParent.create_async(
            {
                "name": "visible parent",
                "private_value": "parent private sample",
                "payload": {"status": "ready"},
            },
        )
        await SerializationChild.create_async(
            {
                "parent_id": parent.id,
                "name": "visible child",
                "private_value": "child private sample",
            },
        )
        loaded = await (
            SerializationParent.query()
            .with_("children.parent")
            .first_or_fail_async()
        )

        serialized = loaded.to_dict()
        children = serialized["children"]
        assert isinstance(children, list)
        child_value: object = cast("object", children[0])
        assert isinstance(child_value, dict)
        child = cast("dict[str, object]", child_value)
        assert child["display_name"] == "Child: visible child"
        assert "private_value" not in serialized
        assert "private_value" not in child
        assert "parent" not in child
        assert serialized["label"] == "Parent: visible parent"
        assert loaded.to_json().find("parent private sample") == -1

        collection = ModelCollection([loaded, loaded.children[0]])
        collection_data = collection.to_dicts()
        assert len(collection_data) == _EXPECTED_SERIALIZED_MODEL_COUNT
        assert "child private sample" not in collection.to_json()
        assert "visible parent" not in repr(loaded)
        assert "parent private sample" not in repr(loaded)
        assert "<redacted>" in repr(loaded)


async def test_collection_visibility_changes_are_instance_scoped(
    application: Application,
) -> None:
    """Apply visible and hidden attributes to collection members only.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_schema()
        await SerializationParent.create_async(
            {
                "name": "first",
                "private_value": "first private",
                "payload": {"status": "ready"},
            },
        )
        await SerializationParent.create_async(
            {
                "name": "second",
                "private_value": "second private",
                "payload": {"status": "ready"},
            },
        )
        outside = await SerializationParent.create_async(
            {
                "name": "outside",
                "private_value": "outside private",
                "payload": {"status": "ready"},
            },
        )
        parents = await SerializationParent.query().order_by("id").get_async()
        collection = ModelCollection(parents[:2])
        initial_values = collection.to_dicts()

        assert collection.merge_hidden(()) is collection
        assert collection.make_visible() is collection
        assert collection.merge_visible(()) is collection
        assert collection.to_dicts() == initial_values

        assert collection.make_visible("private_value") is collection
        assert [value["private_value"] for value in collection.to_dicts()] == [
            "first private",
            "second private",
        ]
        assert "private_value" not in outside.to_dict()
        assert SerializationParent.hidden == ("private_value",)
        assert "private_value" not in SerializationParent.visible

        assert collection.set_visible(("id", "name")) is collection
        assert [set(value) for value in collection.to_dicts()] == [
            {"id", "name"},
            {"id", "name"},
        ]
        assert collection.merge_visible(("private_value",)) is collection
        assert collection.to_dicts()[0]["private_value"] == "first private"
        assert collection.make_visible("private_value") is collection
        assert collection.merge_hidden(("name",)) is collection
        assert "name" not in collection.to_dicts()[0]
        assert collection.set_hidden(()) is collection
        assert collection.to_dicts()[0]["name"] == "first"
        assert collection.make_hidden("name") is collection
        assert "name" not in collection.to_dicts()[0]


async def test_instance_appends_are_mutable_and_collection_scoped(
    application: Application,
) -> None:
    """Change appended attributes on instances and collection members.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_schema()
        await SerializationParent.create_async(
            {
                "name": "first",
                "private_value": "first private",
                "payload": {"status": "ready"},
            },
        )
        await SerializationParent.create_async(
            {
                "name": "second",
                "private_value": "second private",
                "payload": {"status": "ready"},
            },
        )
        parents = await (
            SerializationParent.query()
            .with_("children")
            .order_by("id")
            .get_async()
        )
        first, second = parents

        assert first.get_appends() == ("label", "child_names")
        assert first.has_appended("label")
        assert not first.has_appended("missing")
        assert first.append() is first
        assert first.merge_appends(()) is first
        assert first.get_appends() == ("label", "child_names")
        assert first.set_appends(("label",)) is first
        assert first.append("private_value") is first
        first_values = first.to_dict()
        assert first_values["label"] == "Parent: first"
        assert "child_names" not in first_values
        assert "private_value" not in first_values
        assert "child_names" in second.to_dict()
        assert SerializationParent.appends == ("label", "child_names")

        assert first.append("child_names", "label") is first
        assert first.get_appends() == (
            "label",
            "private_value",
            "child_names",
        )
        assert first.merge_appends(("label",)) is first
        assert first.get_appends() == (
            "label",
            "private_value",
            "child_names",
        )
        assert first.without_appends() is first
        assert "label" not in first.to_dict()
        assert "child_names" not in first.to_dict()

        collection = ModelCollection(parents)
        assert collection.set_appends(("label",)) is collection
        assert [value["label"] for value in collection.to_dicts()] == [
            "Parent: first",
            "Parent: second",
        ]
        assert collection.append("child_names") is collection
        assert [value["child_names"] for value in collection.to_dicts()] == [
            [],
            [],
        ]
        assert collection.without_appends() is collection
        assert all(
            "label" not in value and "child_names" not in value
            for value in collection.to_dicts()
        )


async def test_serialization_skips_unloaded_appends_without_database_io(
    application: Application,
) -> None:
    """Avoid relationship and append I/O when the graph was not eager loaded.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_schema()
        await SerializationParent.create_async(
            {
                "name": "parent",
                "private_value": "private sample",
                "payload": {},
            },
        )
        manager = await application.container.make_async(DatabaseManager)
        engine = manager.async_engine("sqlite").sync_engine
        statements: list[str] = []

        def record_query(*arguments: object) -> None:
            """Capture statement text without retaining parameters.

            SQLAlchemy supplies the statement as the third event argument.
            """
            if len(arguments) >= _MINIMUM_STATEMENT_EVENT_ARGUMENTS:
                statement = arguments[_STATEMENT_EVENT_ARGUMENT_INDEX]
                if isinstance(statement, str):
                    statements.append(statement)

        event.listen(engine, "before_cursor_execute", record_query)
        try:
            loaded = await SerializationParent.query().first_or_fail_async()
            before_serialization = len(statements)
            serialized = loaded.to_dict()
            after_serialization = len(statements)
        finally:
            event.remove(engine, "before_cursor_execute", record_query)

        assert after_serialization == before_serialization
        assert "children" not in serialized
        assert "label" not in serialized
        assert "child_names" not in serialized
        assert getattr(loaded, "_child_names_reads", 0) == 0


async def test_serialization_rejects_graphs_beyond_depth_limit(
    application: Application,
) -> None:
    """Fail explicitly instead of returning an incomplete deep payload.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_schema()
        await SerializationParent.create_async(
            {
                "name": "deep graph",
                "private_value": "private sample",
                "payload": _nested_payload(_MAX_TEST_DEPTH),
            },
        )
        loaded = await SerializationParent.query().first_or_fail_async()

        with pytest.raises(ModelSerializationLimitError):
            loaded.to_dict()


async def test_serialization_rejects_graphs_beyond_node_limit(
    application: Application,
) -> None:
    """Fail explicitly when loaded containers exceed the finite node budget.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_schema()
        await SerializationParent.create_async(
            {
                "name": "wide graph",
                "private_value": "private sample",
                "payload": {"items": ["item"] * 1100},
            },
        )
        loaded = await SerializationParent.query().first_or_fail_async()

        with pytest.raises(ModelSerializationLimitError):
            loaded.to_dict()


async def test_model_collection_serialization_has_a_finite_item_limit(
    application: Application,
) -> None:
    """Reject oversized model collections before allocating serialized rows.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        await _create_schema()
        model = await SerializationParent.create_async(
            {
                "name": "parent",
                "private_value": "private sample",
                "payload": {},
            },
        )
        collection = ModelCollection(
            [model] * _OVERSIZED_COLLECTION_LENGTH,
        )

        with pytest.raises(ModelSerializationLimitError):
            collection.to_dicts()
