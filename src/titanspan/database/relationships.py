"""Offer typed Active Record relationship declarations over SQLAlchemy.

The helpers delegate relationship instrumentation and loading to SQLAlchemy.
Mapped annotations identify related types without duplicating class metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from sqlalchemy import String, Table, and_, bindparam, func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import aliased, declared_attr, foreign, relationship

from titanspan.database.exceptions import DatabaseConfigurationError
from titanspan.facades.database import DB

type _AggregateFunction = Literal["min", "max"]
_MAX_AGGREGATE: _AggregateFunction = "max"
_MIN_AGGREGATE: _AggregateFunction = "min"
_PIVOT_TIMESTAMP_INFO_KEY = "titanspan_pivot_timestamps"
_PIVOT_TIMESTAMP_COLUMN_COUNT = 2
_MORPH_PIVOT_COLUMN_COUNT = 3


@dataclass(frozen=True, slots=True)
class MorphPivot:
    """Name the mapped keys used by a polymorphic many-to-many pivot.

    Attributes:
        type_column: Pivot column that stores the trusted morph alias.
        morph_key: Pivot key paired with the polymorphic endpoint identifier.
        other_key: Pivot key paired with the other endpoint identifier.
        owner_key: Key attribute on the model declaring the relation.
        related_key: Key attribute on the model passed to the relation helper.
    """

    type_column: str
    morph_key: str
    other_key: str
    owner_key: str = "id"
    related_key: str = "id"

    def __post_init__(self) -> None:
        """Reject empty names and ambiguous pivot key columns.

        Raises:
            ValueError: If a name is empty or pivot columns are repeated.
        """
        names = cast(
            "tuple[object, ...]",
            (
                self.type_column,
                self.morph_key,
                self.other_key,
                self.owner_key,
                self.related_key,
            ),
        )
        if any(not isinstance(name, str) or not name.strip() for name in names):
            message = "Morph pivot column and key names must be non-empty."
            raise ValueError(message)
        if (
            len({self.type_column, self.morph_key, self.other_key})
            != _MORPH_PIVOT_COLUMN_COUNT
        ):
            message = "Morph pivot type and key columns must be distinct."
            raise ValueError(message)


if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from typing import Any

    from sqlalchemy import Column
    from sqlalchemy.orm import Mapped
    from sqlalchemy.sql.base import ReadOnlyColumnCollection
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.sql.selectable import FromClause


def has_one[RelatedT](
    related_model: type[RelatedT],
    *,
    back_populates: str | None = None,
) -> Mapped[RelatedT]:
    """Declare a one-to-one relationship using its Mapped annotation.

    Args:
        back_populates: Optional inverse relationship attribute name.
        related_model: Mapped related class.

    Returns:
        SQLAlchemy relationship instrumentation for one related object.
    """
    return cast(
        "Mapped[RelatedT]",
        relationship(
            related_model,
            back_populates=back_populates,
            uselist=False,
        ),
    )


def of_many[RelatedT](
    related_model: type[RelatedT],
    foreign_key: str,
    *,
    aggregates: Mapping[str, _AggregateFunction] | None = None,
    owner_key: str = "id",
) -> Mapped[RelatedT | None]:
    """Declare one related row selected by per-parent aggregates.

    SQLAlchemy owns the mapped relationship and loader. A row-number window
    selects the requested min/max values within each parent group, and the
    related model's primary key breaks ties. The relationship is read-only.

    Args:
        related_model: Mapped class to select from the one-to-many relation.
        foreign_key: Related-model attribute that references the parent.
        aggregates: Ordered attribute-to-aggregate mapping. Each function is
            ``"min"`` or ``"max"``. Missing primary-key attributes default
            to ``"max"`` as a deterministic tie-breaker.
        owner_key: Parent attribute referenced by ``foreign_key``.

    Returns:
        A nullable, scalar mapped relationship selected for each parent.

    Raises:
        ValueError: If an aggregate or mapped attribute is unsupported.
    """
    mapper = sa_inspect(related_model)
    column_properties = {
        property_.key: property_ for property_ in mapper.column_attrs
    }
    if foreign_key not in column_properties:
        message = "The one-of-many foreign key must be a mapped column."
        raise ValueError(message)
    if len(column_properties[foreign_key].columns) != 1:
        message = "The one-of-many foreign key must map one column."
        raise ValueError(message)

    primary_keys = tuple(
        mapper.get_property_by_column(column).key
        for column in mapper.primary_key
    )
    selected_aggregates = _validated_aggregates(
        aggregates,
        primary_keys,
        column_properties,
    )
    order_expressions = _order_expressions(
        related_model,
        selected_aggregates,
    )
    non_null_expressions = tuple(
        getattr(related_model, name).is_not(None)
        for name in selected_aggregates
    )
    rank_label = _unique_rank_label(column_properties)
    ranked_rows = (
        select(
            related_model,
            func.row_number()
            .over(
                partition_by=getattr(related_model, foreign_key),
                order_by=order_expressions,
            )
            .label(rank_label),
        )
        .where(*non_null_expressions)
        .subquery()
    )
    ranked_model = aliased(related_model, ranked_rows)

    def relationship_for_parent(
        parent_model: type[object],
    ) -> Mapped[RelatedT | None]:
        """Bind the row-limited target to its declaring model.

        Args:
            parent_model: Declarative class receiving this attribute.

        Returns:
            SQLAlchemy's read-only row-limited relationship declaration.
        """

        def primary_join() -> ColumnElement[bool]:
            """Join the ranked target row to its owning parent.

            Returns:
                A predicate for the selected foreign-key group and first row.
            """
            return and_(
                foreign(getattr(ranked_model, foreign_key))
                == getattr(parent_model, owner_key),
                ranked_rows.c[rank_label] == 1,
            )

        return cast(
            "Mapped[RelatedT | None]",
            relationship(
                ranked_model,
                primaryjoin=primary_join,
                uselist=False,
                viewonly=True,
            ),
        )

    return cast(
        "Mapped[RelatedT | None]",
        declared_attr(relationship_for_parent),
    )


def latest_of_many[RelatedT](
    related_model: type[RelatedT],
    foreign_key: str,
    *,
    column: str | Sequence[str] | None = None,
    owner_key: str = "id",
) -> Mapped[RelatedT | None]:
    """Declare the related row with greatest values per parent.

    If no column is given, mapped primary-key columns determine the latest
    row. Explicit columns are sorted descending and followed by primary-key
    values to produce stable results.

    Args:
        related_model: Mapped class to select from the one-to-many relation.
        foreign_key: Related-model attribute that references the parent.
        column: One or more mapped attributes to maximize, or ``None`` to use
            the related model's primary key.
        owner_key: Parent attribute referenced by ``foreign_key``.

    Returns:
        A nullable, scalar mapped relationship selected for each parent.
    """
    columns = _selected_column_names(related_model, column)
    aggregates: dict[str, _AggregateFunction] = {}
    for name in columns:
        aggregates[name] = _MAX_AGGREGATE
    return of_many(
        related_model,
        foreign_key,
        aggregates=aggregates,
        owner_key=owner_key,
    )


def oldest_of_many[RelatedT](
    related_model: type[RelatedT],
    foreign_key: str,
    *,
    column: str | Sequence[str] | None = None,
    owner_key: str = "id",
) -> Mapped[RelatedT | None]:
    """Declare the related row with least values per parent.

    If no column is given, mapped primary-key columns determine the oldest
    row. Explicit columns are sorted ascending and followed by primary-key
    values to produce stable results.

    Args:
        related_model: Mapped class to select from the one-to-many relation.
        foreign_key: Related-model attribute that references the parent.
        column: One or more mapped attributes to minimize, or ``None`` to use
            the related model's primary key.
        owner_key: Parent attribute referenced by ``foreign_key``.

    Returns:
        A nullable, scalar mapped relationship selected for each parent.
    """
    columns = _selected_column_names(related_model, column)
    aggregates: dict[str, _AggregateFunction] = {}
    for name in columns:
        aggregates[name] = _MIN_AGGREGATE
    return of_many(
        related_model,
        foreign_key,
        aggregates=aggregates,
        owner_key=owner_key,
    )


def _validated_aggregates(
    aggregates: Mapping[str, _AggregateFunction] | None,
    primary_keys: tuple[str, ...],
    column_properties: Mapping[str, object],
) -> dict[str, _AggregateFunction]:
    """Validate sort attributes and append deterministic primary-key ties.

    Args:
        aggregates: Requested sortable mapped attributes and functions.
        primary_keys: Related-model primary-key attribute names.
        column_properties: Mapped column properties on the related model.

    Returns:
        A validated aggregate mapping in caller-specified order.
    """
    if aggregates is None:
        selected: dict[str, _AggregateFunction] = {}
        for name in primary_keys:
            selected[name] = _MAX_AGGREGATE
    else:
        selected = dict(aggregates)
        if not selected:
            message = "One-of-many aggregates cannot be empty."
            raise ValueError(message)

    for name, aggregate in tuple(selected.items()):
        if aggregate not in ("min", "max"):
            message = "One-of-many aggregates must be 'min' or 'max'."
            raise ValueError(message)
        if name not in column_properties:
            message = "One-of-many sort attributes must be mapped columns."
            raise ValueError(message)
        property_ = column_properties[name]
        # ColumnProperty.columns is a SQLAlchemy list of mapped columns.
        columns = cast(
            "Sequence[object]",
            getattr(property_, "columns", ()),
        )
        if len(columns) != 1:
            message = "One-of-many sort attributes must map one column."
            raise ValueError(message)

    for name in primary_keys:
        selected.setdefault(name, "max")
    return selected


def _order_expressions[RelatedT](
    related_model: type[RelatedT],
    aggregates: Mapping[str, _AggregateFunction],
) -> tuple[ColumnElement[object], ...]:
    """Build portable null-aware ordering for each aggregate attribute.

    Args:
        related_model: Mapped target class for the relationship.
        aggregates: Validated mapped sort attributes and aggregate functions.

    Returns:
        SQLAlchemy ordering terms, with null values after non-null values.
    """
    expressions: list[ColumnElement[object]] = []
    for name, aggregate in aggregates.items():
        attribute = getattr(related_model, name)
        expressions.append(cast("ColumnElement[object]", attribute.is_(None)))
        ordered = attribute.asc() if aggregate == "min" else attribute.desc()
        expressions.append(cast("ColumnElement[object]", ordered))
    return tuple(expressions)


def _selected_column_names[RelatedT](
    related_model: type[RelatedT],
    column: str | Sequence[str] | None,
) -> tuple[str, ...]:
    """Return explicit sort names or the mapped primary-key attributes.

    Args:
        related_model: Mapped class whose key names supply the default order.
        column: Optional explicit sortable mapped attribute names.

    Returns:
        Sort attribute names in the requested order.
    """
    if column is None:
        mapper = sa_inspect(related_model)
        return tuple(
            mapper.get_property_by_column(key).key for key in mapper.primary_key
        )
    if isinstance(column, str):
        return (column,)
    return tuple(column)


def _unique_rank_label(column_properties: Mapping[str, object]) -> str:
    """Choose a private label not present among mapped column attributes.

    Args:
        column_properties: Related-model mapped column properties.

    Returns:
        A unique window-ranking label for the select subquery.
    """
    label = "_titanspan_one_of_many_rank"
    while label in column_properties:
        label += "_"
    return label


def has_many[RelatedT](
    related_model: type[RelatedT],
    *,
    back_populates: str | None = None,
) -> Mapped[list[RelatedT]]:
    """Declare a one-to-many relationship from its Mapped annotation.

    Args:
        back_populates: Optional inverse relationship attribute name.
        related_model: Mapped related class.

    Returns:
        SQLAlchemy relationship instrumentation for related objects.
    """
    return cast(
        "Mapped[list[RelatedT]]",
        relationship(
            related_model,
            back_populates=back_populates,
            uselist=True,
        ),
    )


def belongs_to[RelatedT](
    related_model: type[RelatedT],
    *,
    back_populates: str | None = None,
) -> Mapped[RelatedT]:
    """Declare a many-to-one relationship from its Mapped annotation.

    Args:
        back_populates: Optional inverse relationship attribute name.
        related_model: Mapped related class.

    Returns:
        SQLAlchemy relationship instrumentation for one related object.
    """
    return cast(
        "Mapped[RelatedT]",
        relationship(
            related_model,
            back_populates=back_populates,
            uselist=False,
        ),
    )


def belongs_to_many[RelatedT](
    related_model: type[RelatedT],
    secondary: FromClause,
    *,
    back_populates: str | None = None,
    timestamps: tuple[str, str] | None = None,
) -> Mapped[list[RelatedT]]:
    """Declare a many-to-many relationship with an explicit association.

    Args:
        secondary: Trusted SQLAlchemy association table or selectable.
        back_populates: Optional inverse relationship attribute name.
        timestamps: Optional created-at and updated-at pivot column names.
        related_model: Mapped related class.

    Returns:
        SQLAlchemy relationship instrumentation for related objects.

    Raises:
        TypeError: If timestamping uses a non-table association.
        ValueError: If timestamping does not name two distinct table columns.
    """
    if timestamps is not None:
        _validate_pivot_timestamps(secondary, timestamps)
    info = (
        {_PIVOT_TIMESTAMP_INFO_KEY: timestamps}
        if timestamps is not None
        else None
    )
    return cast(
        "Mapped[list[RelatedT]]",
        relationship(
            related_model,
            secondary=secondary,
            back_populates=back_populates,
            uselist=True,
            info=info,
        ),
    )


def _validate_pivot_timestamps(
    secondary: FromClause,
    timestamps: tuple[str, str],
) -> None:
    """Validate configured pivot timestamp columns before mapping.

    Args:
        secondary: Association object supplied to the relationship helper.
        timestamps: Created-at and updated-at column names.

    Raises:
        TypeError: If the association is not a SQLAlchemy table.
        ValueError: If the configuration does not identify two table columns.
    """
    timestamp_values = cast("tuple[object, ...]", timestamps)
    if (
        len(timestamp_values) != _PIVOT_TIMESTAMP_COLUMN_COUNT
        or any(
            not isinstance(name, str) or not name.strip()
            for name in timestamp_values
        )
        or timestamps[0] == timestamps[1]
    ):
        message = "Pivot timestamps require two distinct column names."
        raise ValueError(message)
    if not isinstance(secondary, Table):
        message = "Pivot timestamps must name columns on a SQLAlchemy Table."
        raise TypeError(message)
    table = cast(
        "Table[ReadOnlyColumnCollection[str, Column[Any]]]",
        secondary,
    )
    if any(name not in table.c for name in timestamps):
        message = "Pivot timestamps must name columns on a SQLAlchemy Table."
        raise ValueError(message)


def morph_to_many[RelatedT](
    related_model: type[RelatedT] | Callable[[], type[RelatedT]],
    secondary: FromClause,
    pivot: MorphPivot,
    *,
    back_populates: str | None = None,
) -> Mapped[list[RelatedT]]:
    """Map a parent-to-related polymorphic pivot relationship.

    The pivot stores the declaring model's trusted alias and identifier in
    ``type_column`` and ``morph_key``. ``other_key`` stores the related key.
    Alias values resolve from the active application's immutable morph map.

    Args:
        related_model: Mapped class or deferred provider for the related type.
        secondary: Trusted SQLAlchemy association table.
        pivot: Column names and model keys used by the association table.
        back_populates: Optional inverse ``morphed_by_many`` attribute.

    Returns:
        SQLAlchemy relationship instrumentation for related objects.
    """
    return _morph_many_to_many(
        "morph_to_many",
        related_model,
        secondary,
        pivot,
        back_populates=back_populates,
    )


def morphed_by_many[RelatedT](
    related_model: type[RelatedT] | Callable[[], type[RelatedT]],
    secondary: FromClause,
    pivot: MorphPivot,
    *,
    back_populates: str | None = None,
) -> Mapped[list[RelatedT]]:
    """Map the inverse related-to-polymorphic-parent pivot relationship.

    The pivot stores the related model's trusted alias and identifier in
    ``type_column`` and ``morph_key``. ``other_key`` stores this model's key.

    Args:
        related_model: Mapped class or deferred provider for the morph type.
        secondary: Trusted SQLAlchemy association table.
        pivot: Column names and model keys used by the association table.
        back_populates: Optional inverse ``morph_to_many`` attribute.

    Returns:
        SQLAlchemy relationship instrumentation for related objects.
    """
    return _morph_many_to_many(
        "morphed_by_many",
        related_model,
        secondary,
        pivot,
        back_populates=back_populates,
    )


def _morph_many_to_many[RelatedT](
    direction: Literal["morph_to_many", "morphed_by_many"],
    related_model: type[RelatedT] | Callable[[], type[RelatedT]],
    secondary: FromClause,
    pivot: MorphPivot,
    back_populates: str | None,
) -> Mapped[list[RelatedT]]:
    """Create a mapped many-to-many join with an app-scoped discriminator.

    Args:
        direction: Side of the relation whose class selects the morph alias.
        related_model: Mapped related class.
        secondary: SQLAlchemy association table or selectable.
        pivot: Column names and model keys used by the association table.
        back_populates: Optional inverse relationship attribute.

    Returns:
        A deferred SQLAlchemy relationship descriptor.
    """

    def mapped_relation(owner_model: type[object]) -> Mapped[list[RelatedT]]:
        """Build join conditions after Declarative knows the owner class.

        Args:
            owner_model: Model class declaring this relationship.

        Returns:
            SQLAlchemy relationship instrumentation for the owner class.
        """
        type_column_value = _pivot_column(secondary, pivot.type_column)
        morph_column = _pivot_column(secondary, pivot.morph_key)
        other_column = _pivot_column(secondary, pivot.other_key)
        owner_column = cast(
            "ColumnElement[object]",
            getattr(owner_model, pivot.owner_key),
        )
        alias_parameter = bindparam(
            None,
            callable_=_trusted_morph_alias_callable(
                owner_model
                if direction == "morph_to_many"
                else _related_model_callable(related_model),
            ),
            type_=String(),
        )
        if direction == "morph_to_many":
            primary_join = and_(
                owner_column == foreign(morph_column),
                type_column_value == alias_parameter,
            )
        else:
            primary_join = owner_column == foreign(other_column)

        def secondary_join() -> ColumnElement[bool]:
            """Build the deferred join after the target class is available.

            Returns:
                SQLAlchemy join criteria between the pivot and target model.
            """
            related_column = cast(
                "ColumnElement[object]",
                getattr(
                    _related_model_callable(related_model)(),
                    pivot.related_key,
                ),
            )
            if direction == "morph_to_many":
                return foreign(other_column) == related_column
            return and_(
                foreign(morph_column) == related_column,
                type_column_value == alias_parameter,
            )

        return cast(
            "Mapped[list[RelatedT]]",
            relationship(
                _related_model_callable(related_model),
                secondary=secondary,
                primaryjoin=primary_join,
                secondaryjoin=secondary_join,
                back_populates=back_populates,
                foreign_keys=[morph_column, other_column],
                uselist=True,
                # The active application's alias is not a mapper constant.
                # The relation manager writes that bound value explicitly.
                viewonly=True,
                info={
                    "titanspan_morph_many_to_many": (direction, pivot),
                },
            ),
        )

    return cast(
        "Mapped[list[RelatedT]]",
        declared_attr(mapped_relation),
    )


def _pivot_column(
    secondary: FromClause,
    name: str,
) -> ColumnElement[object]:
    """Resolve one configured association column without evaluating strings.

    Args:
        secondary: SQLAlchemy selectable used as the relationship pivot.
        name: Explicit column name from trusted application code.

    Returns:
        The matching SQL expression.

    Raises:
        ValueError: If the selectable does not expose the requested column.
    """
    try:
        return cast("ColumnElement[object]", secondary.c[name])
    except KeyError as error:
        message = f"The morph pivot has no {name!r} column."
        raise ValueError(message) from error


def _trusted_morph_alias_callable(
    model_type: type[object] | Callable[[], type[object]],
) -> Callable[[], str]:
    """Create a bind-parameter callback for the active application's alias.

    Args:
        model_type: Mapped class or deferred class provider whose alias scopes
            the pivot rows.

    Returns:
        A callback evaluated when SQLAlchemy executes the mapped query.
    """

    def resolve_alias() -> str:
        """Resolve the exact mapped class through the active service.

        Returns:
            The configured alias for the requested model class.

        Raises:
            DatabaseConfigurationError: If the active map has no alias.
        """
        selected_model = (
            model_type if isinstance(model_type, type) else model_type()
        )
        alias = DB.resolve_service().morph_alias_for(selected_model)
        if alias is None:
            message = "The active database morph map has no model alias."
            raise DatabaseConfigurationError(message)
        return alias

    return resolve_alias


def _related_model_callable[RelatedT](
    related_model: type[RelatedT] | Callable[[], type[RelatedT]],
) -> Callable[[], type[RelatedT]]:
    """Normalize a model class or a deferred class provider.

    Args:
        related_model: Mapped class or callable returning that class.

    Returns:
        A callable that resolves the selected mapped class.
    """
    if isinstance(related_model, type):
        selected_model = cast("type[RelatedT]", related_model)

        def provide_model() -> type[RelatedT]:
            """Return the class supplied directly to the relationship helper.

            Returns:
                The mapped related class.
            """
            return selected_model

        return provide_model
    return related_model


def has_one_through[RelatedT](
    related_model: type[RelatedT],
    through_model: type[object],
    *,
    back_populates: str | None = None,
    primaryjoin: ColumnElement[bool] | None = None,
    secondaryjoin: ColumnElement[bool] | None = None,
) -> Mapped[RelatedT]:
    """Declare a read-only one-to-one path through a mapped table.

    Foreign keys on the intermediate table infer both joins by default. Supply
    explicit joins when the schema has multiple possible foreign-key paths.

    Args:
        related_model: Final mapped class returned by the relationship.
        through_model: Mapped class whose table connects both relationship
            endpoints.
        back_populates: Optional inverse view-only relationship attribute.
        primaryjoin: Optional parent-to-intermediate SQLAlchemy predicate.
        secondaryjoin: Optional intermediate-to-related predicate.

    Returns:
        SQLAlchemy relationship instrumentation for one related model.
    """
    return cast(
        "Mapped[RelatedT]",
        relationship(
            related_model,
            secondary=_mapped_table(through_model),
            back_populates=back_populates,
            primaryjoin=primaryjoin,
            secondaryjoin=secondaryjoin,
            uselist=False,
            viewonly=True,
        ),
    )


def has_many_through[RelatedT](
    related_model: type[RelatedT],
    through_model: type[object],
    *,
    back_populates: str | None = None,
    primaryjoin: ColumnElement[bool] | None = None,
    secondaryjoin: ColumnElement[bool] | None = None,
) -> Mapped[list[RelatedT]]:
    """Declare a read-only one-to-many path through a mapped table.

    Foreign keys on the intermediate table infer both joins by default. Supply
    explicit joins when the schema has multiple possible foreign-key paths.

    Args:
        related_model: Final mapped class returned by the relationship.
        through_model: Mapped class whose table connects both relationship
            endpoints.
        back_populates: Optional inverse view-only relationship attribute.
        primaryjoin: Optional parent-to-intermediate SQLAlchemy predicate.
        secondaryjoin: Optional intermediate-to-related predicate.

    Returns:
        SQLAlchemy relationship instrumentation for related models.
    """
    return cast(
        "Mapped[list[RelatedT]]",
        relationship(
            related_model,
            secondary=_mapped_table(through_model),
            back_populates=back_populates,
            primaryjoin=primaryjoin,
            secondaryjoin=secondaryjoin,
            uselist=True,
            viewonly=True,
        ),
    )


def _mapped_table(model: type[object]) -> FromClause:
    """Read a mapped table through SQLAlchemy's supported inspection API.

    Args:
        model: Intermediate mapped class used as a secondary table.

    Returns:
        The intermediate table expression used by SQLAlchemy relationships.
    """
    return cast("FromClause", sa_inspect(model).local_table)


__all__ = [
    "belongs_to",
    "belongs_to_many",
    "has_many",
    "has_many_through",
    "has_one",
    "has_one_through",
    "latest_of_many",
    "of_many",
    "oldest_of_many",
]
