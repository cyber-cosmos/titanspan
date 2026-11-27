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
    fillable = ("name", "secret", "payload")
    hidden = ("secret",)
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
    secret: Mapped[str]
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
    fillable = ("parent_id", "name", "secret")
    hidden = ("secret",)
    visible = ("id", "name", "parent", "display_name")
    appends = ("display_name",)

    parent_id: Mapped[int] = mapped_column(
        ForeignKey("serialization_parents.id"),
    )
    name: Mapped[str]
    secret: Mapped[str]
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
        table.string("secret", length=120)
        table.json("payload")
        table.timestamps()

    async with Schema.create("serialization_children") as table:
        table.id()
        table.foreign_id("parent_id").references(
            "serialization_parents",
        )
        table.string("name", length=120)
        table.string("secret", length=120)
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
                "secret": "parent credential",
                "payload": {"status": "ready"},
            },
        )
        await SerializationChild.create_async(
            {
                "parent_id": parent.id,
                "name": "visible child",
                "secret": "child credential",
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
        assert "secret" not in serialized
        assert "secret" not in child
        assert "parent" not in child
        assert serialized["label"] == "Parent: visible parent"
        assert loaded.to_json().find("parent credential") == -1

        collection = ModelCollection([loaded, loaded.children[0]])
        collection_data = collection.to_dicts()
        assert len(collection_data) == _EXPECTED_SERIALIZED_MODEL_COUNT
        assert "child credential" not in collection.to_json()
        assert "visible parent" not in repr(loaded)
        assert "parent credential" not in repr(loaded)
        assert "<redacted>" in repr(loaded)


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
                "secret": "secret",
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
                "secret": "secret",
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
                "secret": "secret",
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
                "secret": "secret",
                "payload": {},
            },
        )
        collection = ModelCollection(
            [model] * _OVERSIZED_COLLECTION_LENGTH,
        )

        with pytest.raises(ModelSerializationLimitError):
            collection.to_dicts()
