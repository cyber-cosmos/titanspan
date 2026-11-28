"""Verify trusted polymorphic map validation and immutable snapshots.

Polymorphic discriminators resolve only through explicitly configured models.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)

from titanspan.database import (
    DatabaseConfigurationError,
    Model,
    MorphMap,
    MorphToRelation,
    morph_to,
)

pytestmark = pytest.mark.unit

if TYPE_CHECKING:
    from collections.abc import Mapping


class _MorphMapModel(Model):
    """Represent the mapped class registered under a trusted alias.

    Its table is used only for SQLAlchemy mapper validation.
    """

    table = "unit_morph_map_models"
    title: Mapped[str]


class _UnmappedMorphTarget:
    """Represent a class that cannot be queried by Titanspan's ORM.

    This deliberately unmapped type supports configuration rejection tests.
    """


class _PlainSQLAlchemyBase(DeclarativeBase):
    """Map a dependency model without Titanspan's Active Record API.

    The base supplies metadata for target validation tests.
    """


class _PlainSQLAlchemyTarget(_PlainSQLAlchemyBase):
    """Represent a mapped class without Titanspan's query entry point.

    The relationship must reject this class before attempting to query it.
    """

    __tablename__ = "unit_plain_sqlalchemy_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column()


def test_morph_map_resolves_only_explicit_mapped_classes() -> None:
    """Preserve exact class identities for lookup in both directions.

    Returns:
        None.
    """
    morph_map = MorphMap.from_config({"article": _MorphMapModel})

    assert morph_map.model_for("article") is _MorphMapModel
    assert morph_map.alias_for(_MorphMapModel) == "article"
    assert morph_map.model_for("unknown") is None
    assert morph_map.alias_for(_UnmappedMorphTarget) is None


def test_morph_map_can_be_empty_without_shared_state() -> None:
    """Build an empty immutable map when configuration omits aliases.

    Returns:
        None.
    """
    first = MorphMap.from_config(None)
    second = MorphMap.from_config(None)

    assert first.mappings == {}
    assert second is not first


def test_morph_map_uses_an_immutable_configuration_snapshot() -> None:
    """Ignore later mutations to the input mapping.

    Returns:
        None.
    """
    values: dict[str, object] = {"article": _MorphMapModel}
    morph_map = MorphMap.from_config(values)
    values["changed"] = _UnmappedMorphTarget

    assert tuple(morph_map.mappings) == ("article",)


def test_morph_map_rejects_class_names_from_configuration() -> None:
    """Require actual imported classes rather than class-name strings.

    Raises:
        DatabaseConfigurationError: If a configured value is not a class.
    """
    with pytest.raises(
        DatabaseConfigurationError,
        match="mapped model classes",
    ):
        MorphMap.from_config({"article": "package.models.Article"})


def test_morph_map_rejects_non_mapping_configuration() -> None:
    """Require the application map to be a mapping value.

    Raises:
        DatabaseConfigurationError: If configuration is not a mapping.
    """
    with pytest.raises(
        DatabaseConfigurationError,
        match="string-keyed map",
    ):
        MorphMap.from_config("article: package.models.Article")


def test_morph_map_constructor_checks_untyped_aliases_and_values() -> None:
    """Validate direct construction even when callers bypass annotations.

    Raises:
        DatabaseConfigurationError: If a key or value is invalid.
    """
    with pytest.raises(DatabaseConfigurationError, match="non-empty"):
        MorphMap({" ": _MorphMapModel})

    # Runtime configuration can bypass static hints, so exercise that boundary.
    raw_mappings: Mapping[object, object] = {
        "article": "package.models.Article",
    }
    with pytest.raises(DatabaseConfigurationError, match="mapped model"):
        MorphMap(cast("Mapping[str, type[object]]", raw_mappings))


def test_morph_map_rejects_unmapped_target_classes() -> None:
    """Require every configured target to have SQLAlchemy instrumentation.

    Raises:
        DatabaseConfigurationError: If a target class is not mapped.
    """
    with pytest.raises(
        DatabaseConfigurationError,
        match="mapped model classes",
    ):
        MorphMap.from_config({"article": _UnmappedMorphTarget})


def test_morph_map_requires_titanspan_queryable_models() -> None:
    """Reject mapped classes that cannot use the native model builder.

    Raises:
        DatabaseConfigurationError: If a class lacks Titanspan's query API.
    """
    with pytest.raises(DatabaseConfigurationError, match="mapped model"):
        MorphMap.from_config({"plain": _PlainSQLAlchemyTarget})
    with pytest.raises(DatabaseConfigurationError, match="mapped model"):
        morph_to(
            _PlainSQLAlchemyTarget,
            type_column="subject_type",
            foreign_key="subject_id",
            owner_key="id",
        )


def test_morph_map_rejects_empty_aliases_and_duplicate_model_types() -> None:
    """Reject blank aliases and ambiguous reverse class lookups.

    Raises:
        DatabaseConfigurationError: If an alias or model registration repeats.
    """
    with pytest.raises(DatabaseConfigurationError, match="non-empty"):
        MorphMap.from_config({" ": _MorphMapModel})
    with pytest.raises(DatabaseConfigurationError, match="one morph alias"):
        MorphMap.from_config(
            {
                "article": _MorphMapModel,
                "post": _MorphMapModel,
            },
        )


def test_morph_to_requires_mapped_unique_targets_and_column_names() -> None:
    """Reject incomplete or ambiguous relationship declarations.

    Raises:
        DatabaseConfigurationError: If a target class is not mapped.
        ValueError: If targets or mapped attribute names are invalid.
    """
    with pytest.raises(ValueError, match="at least one target"):
        morph_to(type_column="subject_type", foreign_key="subject_id")
    with pytest.raises(DatabaseConfigurationError, match="mapped model"):
        morph_to(
            _MorphMapModel,
            _UnmappedMorphTarget,
            type_column="subject_type",
            foreign_key="subject_id",
        )
    with pytest.raises(ValueError, match="unique"):
        morph_to(
            _MorphMapModel,
            _MorphMapModel,
            type_column="subject_type",
            foreign_key="subject_id",
        )
    with pytest.raises(ValueError, match="must not be empty"):
        morph_to(
            _MorphMapModel,
            type_column=" ",
            foreign_key="subject_id",
        )
    with pytest.raises(DatabaseConfigurationError, match="owner key"):
        morph_to(
            _MorphMapModel,
            type_column="subject_type",
            foreign_key="subject_id",
            owner_key="missing_id",
        )


def test_morph_to_rejects_unmapped_source_columns() -> None:
    """Reject source discriminator fields absent from the parent mapper.

    Raises:
        DatabaseConfigurationError: If a source field is not mapped.
    """
    descriptor = morph_to(
        _MorphMapModel,
        type_column="subject_type",
        foreign_key="subject_id",
    )

    with pytest.raises(DatabaseConfigurationError, match="type attribute"):
        descriptor.__get__(_MorphMapModel(), _MorphMapModel)

    invalid_foreign_key = morph_to(
        _MorphMapModel,
        type_column="title",
        foreign_key="missing_id",
    )
    with pytest.raises(DatabaseConfigurationError, match="foreign key"):
        invalid_foreign_key.__get__(_MorphMapModel(), _MorphMapModel)


def test_morph_to_descriptor_requires_an_instance() -> None:
    """Reject class-level use that has no polymorphic key values.

    Raises:
        AttributeError: If the descriptor is accessed without an instance.
    """
    descriptor = morph_to(
        _MorphMapModel,
        type_column="title",
        foreign_key="id",
    )

    with pytest.raises(AttributeError, match="requires a model instance"):
        descriptor.__get__(None, _MorphMapModel)


def test_morph_to_relation_rejects_targets_outside_its_allowlist() -> None:
    """Reject association classes excluded from the relationship declaration.

    Raises:
        DatabaseConfigurationError: If the value is outside the allowlist.
    """
    relation = MorphToRelation[object](
        _MorphMapModel(),
        target_models=(_MorphMapModel,),
        type_column="title",
        foreign_key="id",
        owner_key="id",
    )

    with pytest.raises(DatabaseConfigurationError, match="not allowed"):
        relation.associate(_UnmappedMorphTarget())
