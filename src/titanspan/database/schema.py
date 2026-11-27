"""Build database schemas through Alembic and SQLAlchemy public APIs.

Schema builders participate in the application's current Unit of Work and
use SQLAlchemy inspection for metadata queries.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    inspect,
    literal,
    text,
)
from sqlalchemy.exc import ArgumentError, CompileError

from titanspan.contracts.database import DatabaseService
from titanspan.database.exceptions import DatabaseSchemaError
from titanspan.facades.base import Facade

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy.engine import Connection as SQLConnection
    from sqlalchemy.engine.reflection import Inspector
    from sqlalchemy.sql.elements import TextClause
    from sqlalchemy.sql.schema import SchemaItem
    from sqlalchemy.sql.type_api import TypeEngine


class _Alteration(TypedDict):
    """Keep Alembic alteration arguments statically checked."""

    name: str
    existing_type: TypeEngine[Any]
    type_: TypeEngine[Any] | None
    nullable: bool | None
    server_default: str | TextClause | None

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_SCHEMA_PARTS = 2
_DEFAULT_INDEX_PREFIX = "ix"

type _Operation = Literal[
    "create",
    "create_if_missing",
    "alter",
    "drop",
    "drop_if_exists",
    "rename",
]


class Schema(Facade[DatabaseService]):
    """Expose schema definition and inspection through the active app.
    """  # fmt: skip

    service_contract = DatabaseService

    @classmethod
    def create(
        cls,
        table_name: str,
        *,
        connection: str | None = None,
    ) -> Blueprint:
        """Build a new table with typed column helpers.

        Args:
            table_name: Safe table name, optionally schema-qualified.
            connection: Optional named application connection.

        Returns:
            A context manager that applies DDL after successful declaration.
        """
        return Blueprint(
            cls.resolve_service(),
            table_name,
            "create",
            connection,
        )

    @classmethod
    def create_if_missing(
        cls,
        table_name: str,
        *,
        connection: str | None = None,
    ) -> Blueprint:
        """Create a table only when SQLAlchemy inspection finds no table.

        Args:
            table_name: Safe table name, optionally schema-qualified.
            connection: Optional named application connection.

        Returns:
            A context manager that conditionally creates the table.
        """
        return Blueprint(
            cls.resolve_service(),
            table_name,
            "create_if_missing",
            connection,
        )

    @classmethod
    def alter(
        cls,
        table_name: str,
        *,
        connection: str | None = None,
    ) -> Blueprint:
        """Collect supported table alteration operations.

        Args:
            table_name: Existing safe table name.
            connection: Optional named application connection.

        Returns:
            A context manager that applies declared alterations.
        """
        return Blueprint(
            cls.resolve_service(),
            table_name,
            "alter",
            connection,
        )

    @classmethod
    def drop(
        cls,
        table_name: str,
        *,
        connection: str | None = None,
    ) -> Blueprint:
        """Drop a table and fail when the selected table is missing.

        Args:
            table_name: Existing safe table name.
            connection: Optional named application connection.

        Returns:
            A context manager that drops the table.
        """
        return Blueprint(
            cls.resolve_service(),
            table_name,
            "drop",
            connection,
        )

    @classmethod
    def drop_if_exists(
        cls,
        table_name: str,
        *,
        connection: str | None = None,
    ) -> Blueprint:
        """Drop a table only when it exists on the selected connection.

        Args:
            table_name: Safe table name.
            connection: Optional named application connection.

        Returns:
            A context manager that conditionally drops the table.
        """
        return Blueprint(
            cls.resolve_service(),
            table_name,
            "drop_if_exists",
            connection,
        )

    @classmethod
    def rename(
        cls,
        old_name: str,
        new_name: str,
        *,
        connection: str | None = None,
    ) -> Blueprint:
        """Rename one table using Alembic's dialect-aware operation.

        Args:
            old_name: Existing safe table name.
            new_name: Safe replacement table name.
            connection: Optional named application connection.

        Returns:
            A context manager that renames the table.
        """
        return Blueprint(
            cls.resolve_service(),
            old_name,
            "rename",
            connection,
            new_name=new_name,
        )

    @classmethod
    def has_table(
        cls,
        table_name: str,
        *,
        connection: str | None = None,
    ) -> bool:
        """Check for a table through SQLAlchemy's public Inspector.

        Args:
            table_name: Safe table name, optionally schema-qualified.
            connection: Optional named application connection.

        Returns:
            Whether the selected database contains the table.
        """
        return _inspect_sync(
            cls.resolve_service(),
            connection,
            lambda inspector, schema, name: inspector.has_table(
                name,
                schema=schema,
            ),
            table_name,
        )

    @classmethod
    async def has_table_async(
        cls,
        table_name: str,
        *,
        connection: str | None = None,
    ) -> bool:
        """Asynchronously inspect whether a table exists.

        Args:
            table_name: Safe table name, optionally schema-qualified.
            connection: Optional named application connection.

        Returns:
            Whether the selected database contains the table.
        """
        return await _inspect_async(
            cls.resolve_service(),
            connection,
            lambda inspector, schema, name: inspector.has_table(
                name,
                schema=schema,
            ),
            table_name,
        )

    @classmethod
    def has_column(
        cls,
        table_name: str,
        column_name: str,
        *,
        connection: str | None = None,
    ) -> bool:
        """Check for a column through SQLAlchemy table reflection.

        Args:
            table_name: Safe table name, optionally schema-qualified.
            column_name: Safe column identifier.
            connection: Optional named application connection.

        Returns:
            Whether the table contains the selected column.
        """
        _validate_identifier(column_name)
        return _inspect_sync(
            cls.resolve_service(),
            connection,
            lambda inspector, schema, name: column_name in {
                item["name"]
                for item in inspector.get_columns(name, schema=schema)
            },
            table_name,
        )

    @classmethod
    async def has_column_async(
        cls,
        table_name: str,
        column_name: str,
        *,
        connection: str | None = None,
    ) -> bool:
        """Asynchronously inspect whether a table contains a column.

        Args:
            table_name: Safe table name, optionally schema-qualified.
            column_name: Safe column identifier.
            connection: Optional named application connection.

        Returns:
            Whether the table contains the selected column.
        """
        _validate_identifier(column_name)
        return await _inspect_async(
            cls.resolve_service(),
            connection,
            lambda inspector, schema, name: column_name in {
                item["name"]
                for item in inspector.get_columns(name, schema=schema)
            },
            table_name,
        )

    @classmethod
    def has_columns(
        cls,
        table_name: str,
        column_names: Sequence[str],
        *,
        connection: str | None = None,
    ) -> bool:
        """Check that every requested column exists in a table.

        Args:
            table_name: Safe table name, optionally schema-qualified.
            column_names: Safe column identifiers to check.
            connection: Optional named application connection.

        Returns:
            Whether the table contains every requested column.
        """
        for column_name in column_names:
            _validate_identifier(column_name)
        expected = frozenset(column_names)
        return _inspect_sync(
            cls.resolve_service(),
            connection,
            lambda inspector, schema, name: expected.issubset(
                item["name"]
                for item in inspector.get_columns(name, schema=schema)
            ),
            table_name,
        )

    @classmethod
    async def has_columns_async(
        cls,
        table_name: str,
        column_names: Sequence[str],
        *,
        connection: str | None = None,
    ) -> bool:
        """Asynchronously check that all requested columns exist.

        Args:
            table_name: Safe table name, optionally schema-qualified.
            column_names: Safe column identifiers to check.
            connection: Optional named application connection.

        Returns:
            Whether the table contains every requested column.
        """
        for column_name in column_names:
            _validate_identifier(column_name)
        expected = frozenset(column_names)
        return await _inspect_async(
            cls.resolve_service(),
            connection,
            lambda inspector, schema, name: expected.issubset(
                item["name"]
                for item in inspector.get_columns(name, schema=schema)
            ),
            table_name,
        )

    @classmethod
    def list_tables(
        cls,
        *,
        schema: str | None = None,
        connection: str | None = None,
    ) -> list[str]:
        """List table names through SQLAlchemy reflection.

        Args:
            schema: Optional safe database schema.
            connection: Optional named application connection.

        Returns:
            Names returned by the selected dialect's Inspector.
        """
        _validate_optional_identifier(schema)
        return _inspect_list_sync(
            cls.resolve_service(),
            connection,
            schema,
        )

    @classmethod
    async def list_tables_async(
        cls,
        *,
        schema: str | None = None,
        connection: str | None = None,
    ) -> list[str]:
        """Asynchronously list table names through SQLAlchemy reflection.

        Args:
            schema: Optional safe database schema.
            connection: Optional named application connection.

        Returns:
            Names returned by the selected dialect's Inspector.
        """
        _validate_optional_identifier(schema)
        return await _inspect_list_async(
            cls.resolve_service(),
            connection,
            schema,
        )


class Blueprint:
    """Collect a table definition and execute it as one Alembic operation.
    """  # fmt: skip

    def __init__(
        self,
        service: DatabaseService,
        table_name: str,
        operation: _Operation,
        connection: str | None,
        *,
        new_name: str | None = None,
    ) -> None:
        """Create a builder bound to one app service and logical connection.

        Args:
            service: Canonical application Database service.
            table_name: Safe selected table name.
            operation: Schema operation applied after declarations complete.
            connection: Optional named connection for this operation.
            new_name: Safe target table name for a rename operation.

        Raises:
            DatabaseSchemaError: If identifiers are unsafe.
        """
        self._service = service
        self._schema, self._table_name = _split_table_name(table_name)
        self._operation = operation
        self._connection = connection
        self._new_name = new_name
        if new_name is not None:
            _split_table_name(new_name)
        self._columns: list[ColumnDefinition] = []
        self._constraints: list[SchemaItem] = []
        self._indexes: list[tuple[str | None, tuple[str, ...], bool]] = []
        self._drop_columns: list[str] = []
        self._rename_columns: list[tuple[str, str]] = []
        self._alterations: list[_Alteration] = []

    def __enter__(self) -> Blueprint:
        """Return the builder for synchronous schema declarations.

        Returns:
            This blueprint.
        """
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object | None,
    ) -> bool:
        """Apply DDL only after a successful synchronous declaration.

        Args:
            exception_type: Exception type raised by the declaration body.
            exception: Exception raised by the declaration body.
            traceback: Traceback supplied by the context manager protocol.

        Returns:
            ``False`` so declaration exceptions continue to propagate.
        """
        if exception_type is None:
            self.apply()
        return False

    async def __aenter__(self) -> Blueprint:
        """Return the builder for asynchronous schema declarations.

        Returns:
            This blueprint.
        """
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object | None,
    ) -> bool:
        """Apply DDL asynchronously after successful declarations.

        Args:
            exception_type: Exception type raised by the declaration body.
            exception: Exception raised by the declaration body.
            traceback: Traceback supplied by the context manager protocol.

        Returns:
            ``False`` so declaration exceptions continue to propagate.
        """
        if exception_type is None:
            await self.apply_async()
        return False

    def id(self, name: str = "id") -> ColumnDefinition:
        """Add a generated integer primary key column.

        Args:
            name: Primary key column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(
            name,
            Integer(),
            primary_key=True,
            autoincrement=True,
        )

    def integer(self, name: str) -> ColumnDefinition:
        """Add an integer column.

        Args:
            name: Safe column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(name, Integer())

    def big_integer(self, name: str) -> ColumnDefinition:
        """Add a large integer column.

        Args:
            name: Safe column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(name, BigInteger())

    def small_integer(self, name: str) -> ColumnDefinition:
        """Add a small integer column.

        Args:
            name: Safe column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(name, SmallInteger())

    def foreign_id(self, name: str) -> ColumnDefinition:
        """Add an integer column intended to reference another model key.

        Args:
            name: Safe foreign key column name.

        Returns:
            The column definition, including ``references`` configuration.
        """
        return self._add_column(name, Integer())

    def boolean(self, name: str) -> ColumnDefinition:
        """Add a boolean column.

        Args:
            name: Safe column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(name, Boolean())

    def string(
        self,
        name: str,
        *,
        length: int = 255,
    ) -> ColumnDefinition:
        """Add a bounded text column.

        Args:
            name: Safe column name.
            length: Maximum character length required by the dialect.

        Returns:
            The column definition for additional modifiers.
        """
        if length <= 0:
            message = "String length must be positive."
            raise DatabaseSchemaError(message)
        return self._add_column(name, String(length))

    def text(self, name: str) -> ColumnDefinition:
        """Add an unbounded text column.

        Args:
            name: Safe column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(name, Text())

    def binary(self, name: str) -> ColumnDefinition:
        """Add a binary large-object column.

        Args:
            name: Safe column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(name, LargeBinary())

    def decimal(
        self,
        name: str,
        *,
        precision: int = 10,
        scale: int = 2,
    ) -> ColumnDefinition:
        """Add a fixed-precision decimal column.

        Args:
            name: Safe column name.
            precision: Total significant decimal digits.
            scale: Digits stored after the decimal point.

        Returns:
            The column definition for additional modifiers.
        """
        if precision <= 0 or scale < 0 or scale > precision:
            message = "Invalid decimal precision or scale."
            raise DatabaseSchemaError(message)
        return self._add_column(name, Numeric(precision, scale))

    def float(self, name: str) -> ColumnDefinition:
        """Add a floating-point column.

        Args:
            name: Safe column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(name, Float())

    def date(self, name: str) -> ColumnDefinition:
        """Add a date column.

        Args:
            name: Safe column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(name, Date())

    def time(self, name: str) -> ColumnDefinition:
        """Add a time column.

        Args:
            name: Safe column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(name, Time(timezone=True))

    def datetime(self, name: str) -> ColumnDefinition:
        """Add a timezone-aware datetime column where the dialect supports it.

        Args:
            name: Safe column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(name, DateTime(timezone=True))

    def timestamp(self, name: str) -> ColumnDefinition:
        """Add a timezone-aware timestamp column where supported.

        Args:
            name: Safe column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(name, DateTime(timezone=True))

    def uuid(self, name: str) -> ColumnDefinition:
        """Add a native UUID column where supported by the dialect.

        Args:
            name: Safe column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(name, Uuid(as_uuid=True))

    def json(self, name: str) -> ColumnDefinition:
        """Add a JSON column through SQLAlchemy's portable type.

        Args:
            name: Safe column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self._add_column(name, JSON())

    def enum(self, name: str, *values: str) -> ColumnDefinition:
        """Add an enumerated string column.

        Args:
            name: Safe column name.
            values: Trusted allowed string values.

        Returns:
            The column definition for additional modifiers.
        """
        if not values or len(set(values)) != len(values):
            message = "Enum values must be unique and nonempty."
            raise DatabaseSchemaError(message)
        return self._add_column(name, Enum(*values, name=f"{name}_enum"))

    def timestamps(self) -> Blueprint:
        """Add nullable timezone-aware creation and update timestamps.

        Returns:
            This blueprint for further declarations.
        """
        self.datetime("created_at").nullable()
        self.datetime("updated_at").nullable()
        return self

    def soft_deletes(self, name: str = "deleted_at") -> ColumnDefinition:
        """Add a nullable timestamp used by soft-delete model behavior.

        Args:
            name: Safe deletion timestamp column name.

        Returns:
            The column definition for additional modifiers.
        """
        return self.datetime(name).nullable()

    def unique(
        self,
        *column_names: str,
        name: str | None = None,
    ) -> Blueprint:
        """Add a table-level unique constraint.

        Args:
            column_names: One or more safe column identifiers.
            name: Optional explicit constraint name.

        Returns:
            This blueprint for further declarations.
        """
        _validate_columns(column_names)
        _validate_optional_identifier(name)
        self._constraints.append(UniqueConstraint(*column_names, name=name))
        return self

    def index(
        self,
        *column_names: str,
        name: str | None = None,
        unique: bool = False,
    ) -> Blueprint:
        """Add a single or composite index after creating the table.

        Args:
            column_names: One or more safe column identifiers.
            name: Optional explicit index name.
            unique: Whether the database must enforce unique values.

        Returns:
            This blueprint for further declarations.
        """
        _validate_columns(column_names)
        _validate_optional_identifier(name)
        self._indexes.append((name, tuple(column_names), unique))
        return self

    def drop_column(self, name: str) -> Blueprint:
        """Drop a column from an altered table.

        Args:
            name: Existing safe column identifier.

        Returns:
            This blueprint for further declarations.
        """
        self._require_operation("alter")
        _validate_identifier(name)
        self._drop_columns.append(name)
        return self

    def rename_column(self, old_name: str, new_name: str) -> Blueprint:
        """Rename one column through Alembic's dialect-aware operation.

        Args:
            old_name: Existing safe column name.
            new_name: Safe replacement column name.

        Returns:
            This blueprint for further declarations.
        """
        self._require_operation("alter")
        _validate_columns((old_name, new_name))
        self._rename_columns.append((old_name, new_name))
        return self

    def alter_column(
        self,
        name: str,
        *,
        existing_type: TypeEngine[Any],
        type_: TypeEngine[Any] | None = None,
        nullable: bool | None = None,
        server_default: str | TextClause | None = None,
    ) -> Blueprint:
        """Alter a column using Alembic's dialect-specific implementation.

        Args:
            name: Safe column name.
            existing_type: Current SQLAlchemy type for dialect correctness.
            type_: Optional replacement SQLAlchemy type.
            nullable: Optional replacement nullability.
            server_default: Trusted SQL default expression or ``None``.

        Returns:
            This blueprint for further declarations.
        """
        self._require_operation("alter")
        _validate_identifier(name)
        self._alterations.append(
            _Alteration(
                name=name,
                existing_type=existing_type,
                type_=type_,
                nullable=nullable,
                server_default=server_default,
            ),
        )
        return self

    def apply(self) -> None:
        """Apply the declared operation synchronously in the app Unit of Work.
        """  # fmt: skip
        with self._service.session(self._connection) as session:
            connection = session.connection()
            self._apply(Operations(MigrationContext.configure(connection)))

    async def apply_async(self) -> None:
        """Apply the declared operation through the async app Unit of Work.
        """  # fmt: skip
        async with self._service.session_async(
            self._connection,
        ) as session:
            connection = await session.connection()
            await connection.run_sync(
                lambda sync_connection: self._apply(
                    Operations(MigrationContext.configure(sync_connection)),
                ),
            )

    def _apply(self, operations: Operations) -> None:
        """Apply collected DDL through Alembic's public Operations API.

        Args:
            operations: Alembic operations bound to the owned SQL connection.
        """
        if self._operation in ("create", "create_if_missing"):
            self._apply_create(operations)
        elif self._operation == "alter":
            self._apply_alter(operations)
        elif self._operation in ("drop", "drop_if_exists"):
            self._apply_drop(operations)
        else:
            self._apply_rename(operations)

    def _apply_create(self, operations: Operations) -> None:
        """Create this table and its declared indexes.

        Args:
            operations: Alembic operations bound to the owned SQL connection.
        """
        exists = _table_exists(
            operations.get_bind(),
            self._schema,
            self._table_name,
        )
        if self._operation == "create_if_missing" and exists:
            return
        columns = [definition.build() for definition in self._columns]
        operations.create_table(
            self._table_name,
            *columns,
            *self._constraints,
            schema=self._schema,
        )
        for name, column_names, unique in self._indexes:
            index_name = name or _index_name(self._table_name, column_names)
            operations.create_index(
                index_name,
                self._table_name,
                list(column_names),
                unique=unique,
                schema=self._schema,
            )

    def _apply_alter(self, operations: Operations) -> None:
        """Apply declared column and index changes to an existing table.

        Args:
            operations: Alembic operations bound to the owned SQL connection.
        """
        for definition in self._columns:
            operations.add_column(
                self._table_name,
                definition.build(),
                schema=self._schema,
            )
        for old_name, new_name in self._rename_columns:
            operations.alter_column(
                self._table_name,
                old_name,
                new_column_name=new_name,
                schema=self._schema,
            )
        for alteration in self._alterations:
            operations.alter_column(
                self._table_name,
                alteration["name"],
                existing_type=alteration["existing_type"],
                type_=alteration["type_"],
                nullable=alteration["nullable"],
                server_default=alteration["server_default"],
                schema=self._schema,
            )
        for column_name in self._drop_columns:
            operations.drop_column(
                self._table_name,
                column_name,
                schema=self._schema,
            )
        for name, column_names, unique in self._indexes:
            index_name = name or _index_name(self._table_name, column_names)
            operations.create_index(
                index_name,
                self._table_name,
                list(column_names),
                unique=unique,
                schema=self._schema,
            )

    def _apply_drop(self, operations: Operations) -> None:
        """Drop the selected table, respecting conditional-drop semantics.

        Args:
            operations: Alembic operations bound to the owned SQL connection.
        """
        if self._operation == "drop_if_exists" and not _table_exists(
            operations.get_bind(),
            self._schema,
            self._table_name,
        ):
            return
        operations.drop_table(self._table_name, schema=self._schema)

    def _apply_rename(self, operations: Operations) -> None:
        """Rename the table without moving it between schemas.

        Args:
            operations: Alembic operations bound to the owned SQL connection.
        """
        if self._new_name is None:
            message = "A table rename requires a target name."
            raise DatabaseSchemaError(message)
        new_schema, target_name = _split_table_name(self._new_name)
        if self._schema != new_schema:
            message = "A table rename cannot move a table between schemas."
            raise DatabaseSchemaError(message)
        operations.rename_table(
            self._table_name,
            target_name,
            schema=self._schema,
        )

    def _add_column(
        self,
        name: str,
        type_: TypeEngine[Any],
        *,
        nullable: bool = False,
        primary_key: bool = False,
        autoincrement: bool = False,
    ) -> ColumnDefinition:
        """Append a typed column to this create or alter blueprint.

        Args:
            name: Safe new column name.
            type_: SQLAlchemy column type.
            nullable: Whether values may be SQL NULL.
            primary_key: Whether the column is a primary key.
            autoincrement: Whether the backend should generate integer keys.

        Returns:
            A mutable column declaration for fluent modifiers.
        """
        _validate_identifier(name)
        if self._operation not in ("create", "create_if_missing", "alter"):
            message = "The selected schema operation does not accept columns."
            raise DatabaseSchemaError(message)
        definition = ColumnDefinition(
            self,
            name,
            type_,
            nullable=nullable,
            primary_key=primary_key,
            autoincrement=autoincrement,
        )
        self._columns.append(definition)
        return definition

    def _require_operation(self, expected: _Operation) -> None:
        """Require the blueprint operation that owns a declaration.

        Args:
            expected: Required schema operation.

        Raises:
            DatabaseSchemaError: If the operation does not match.
        """
        if self._operation is not expected:
            message = f"This declaration requires a {expected} blueprint."
            raise DatabaseSchemaError(message)


class ColumnDefinition:
    """Collect safe SQLAlchemy column options before DDL is emitted.
    """  # fmt: skip

    def __init__(
        self,
        blueprint: Blueprint,
        name: str,
        type_: TypeEngine[Any],
        *,
        nullable: bool,
        primary_key: bool,
        autoincrement: bool,
    ) -> None:
        """Create a mutable definition owned by one blueprint.

        Args:
            blueprint: Builder that will apply the column.
            name: Safe column identifier.
            type_: SQLAlchemy database type.
            nullable: Initial SQL NULL policy.
            primary_key: Whether this is a primary key.
            autoincrement: Whether the database generates integer values.
        """
        self._blueprint = blueprint
        self._name = name
        self._type = type_
        self._nullable = nullable
        self._primary_key = primary_key
        self._autoincrement = autoincrement
        self._default: str | None = None
        self._server_default: str | TextClause | None = None
        self._unique = False
        self._index = False
        self._comment: str | None = None
        self._foreign_key: ForeignKey | None = None

    def nullable(self, enabled: bool = True) -> ColumnDefinition:
        """Set whether the column accepts SQL NULL values.

        Args:
            enabled: Whether null values are permitted.

        Returns:
            This column definition.
        """
        self._nullable = enabled
        return self

    def default(self, value: object) -> ColumnDefinition:
        """Set a portable server default from a safely compiled literal.

        Args:
            value: Scalar value supported by SQLAlchemy literal compilation.

        Returns:
            This column definition.

        Raises:
            DatabaseSchemaError: If SQLAlchemy cannot compile the value.
        """
        try:
            self._default = str(
                literal(value).compile(
                    compile_kwargs={"literal_binds": True},
                )
            )
        except (ArgumentError, CompileError, TypeError) as error:
            message = "The schema default must be a supported scalar value."
            raise DatabaseSchemaError(message) from error
        return self

    def server_default(
        self,
        expression: str | TextClause,
    ) -> ColumnDefinition:
        """Set an explicit trusted SQL server-default expression.

        Args:
            expression: Application-authored SQL expression.

        Returns:
            This column definition.
        """
        self._server_default = (
            text(expression) if isinstance(expression, str) else expression
        )
        return self

    def unique(self, enabled: bool = True) -> ColumnDefinition:
        """Add a column-level unique constraint.

        Args:
            enabled: Whether uniqueness is enforced by the database.

        Returns:
            This column definition.
        """
        self._unique = enabled
        return self

    def index(self, enabled: bool = True) -> ColumnDefinition:
        """Create a single-column database index.

        Args:
            enabled: Whether SQLAlchemy should create the index.

        Returns:
            This column definition.
        """
        self._index = enabled
        return self

    def comment(self, value: str) -> ColumnDefinition:
        """Set a database column comment where the dialect supports it.

        Args:
            value: Comment text authored by the application developer.

        Returns:
            This column definition.
        """
        self._comment = value
        return self

    def references(
        self,
        table_name: str,
        column_name: str = "id",
        *,
        on_delete: str | None = None,
        on_update: str | None = None,
    ) -> ColumnDefinition:
        """Add a foreign key to a safe table and column identifier.

        Args:
            table_name: Safe target table, optionally schema-qualified.
            column_name: Safe target column.
            on_delete: Optional supported database delete action.
            on_update: Optional supported database update action.

        Returns:
            This column definition.
        """
        schema, table = _split_table_name(table_name)
        _validate_identifier(column_name)
        target = f"{schema}.{table}" if schema is not None else table
        self._foreign_key = ForeignKey(
            f"{target}.{column_name}",
            ondelete=_validate_action(on_delete),
            onupdate=_validate_action(on_update),
        )
        return self

    def build(self) -> Column[Any]:
        """Construct a SQLAlchemy Column from the collected options.

        Returns:
            A column configured with this definition's options.
        """
        foreign_keys = (
            (self._foreign_key,) if self._foreign_key is not None else ()
        )
        return Column(
            self._name,
            self._type,
            *foreign_keys,
            nullable=self._nullable and not self._primary_key,
            primary_key=self._primary_key,
            autoincrement=self._autoincrement,
            unique=self._unique,
            index=self._index,
            comment=self._comment,
            server_default=(
                self._server_default
                if self._server_default is not None
                else self._default
            ),
        )


def _inspect_sync(
    service: DatabaseService,
    connection: str | None,
    inspect_value: Callable[[Inspector, str | None, str], bool],
    table_name: str,
) -> bool:
    """Run a typed schema inspection callback on a sync SQL connection.

    Args:
        service: Application Database service.
        connection: Optional selected logical connection.
        inspect_value: Typed callback that inspects the selected table.
        table_name: Safe table name or qualified name.

    Returns:
        The inspector callback result.
    """
    schema, name = _split_table_name(table_name)
    with service.session(connection) as session:
        inspector = inspect(session.connection())
        return inspect_value(inspector, schema, name)


async def _inspect_async(
    service: DatabaseService,
    connection: str | None,
    inspect_value: Callable[[Inspector, str | None, str], bool],
    table_name: str,
) -> bool:
    """Run schema inspection with SQLAlchemy's async run_sync bridge.

    Args:
        service: Application Database service.
        connection: Optional selected logical connection.
        inspect_value: Typed callback that inspects the selected table.
        table_name: Safe table name or qualified name.

    Returns:
        The inspector callback result.
    """
    schema, name = _split_table_name(table_name)
    async with service.session_async(connection) as session:
        async_connection = await session.connection()
        return await async_connection.run_sync(
            lambda sync_connection: bool(
                inspect_value(inspect(sync_connection), schema, name)
            ),
        )


def _inspect_list_sync(
    service: DatabaseService,
    connection: str | None,
    schema: str | None,
) -> list[str]:
    """List tables through one synchronous Inspector instance.

    Args:
        service: Application Database service.
        connection: Optional selected logical connection.
        schema: Optional safe schema name.

    Returns:
        Reflected table names.
    """
    with service.session(connection) as session:
        return inspect(session.connection()).get_table_names(schema=schema)


async def _inspect_list_async(
    service: DatabaseService,
    connection: str | None,
    schema: str | None,
) -> list[str]:
    """List tables through SQLAlchemy's async run_sync bridge.

    Args:
        service: Application Database service.
        connection: Optional selected logical connection.
        schema: Optional safe schema name.

    Returns:
        Reflected table names.
    """
    async with service.session_async(connection) as session:
        async_connection = await session.connection()
        return await async_connection.run_sync(
            lambda sync_connection: inspect(
                sync_connection,
            ).get_table_names(schema=schema),
        )


def _table_exists(
    connection: SQLConnection,
    schema: str | None,
    table_name: str,
) -> bool:
    """Check one table on the already-owned SQLAlchemy connection.

    Args:
        connection: Physical connection currently owned by the Unit of Work.
        schema: Optional validated schema name.
        table_name: Validated table name.

    Returns:
        Whether the selected table exists.
    """
    return inspect(connection).has_table(table_name, schema=schema)


def _split_table_name(table_name: str) -> tuple[str | None, str]:
    """Validate a table or schema-qualified identifier.

    Args:
        table_name: One table identifier or ``schema.table``.

    Returns:
        Optional schema and table name.
    """
    parts = table_name.split(".")
    if len(parts) == 1:
        _validate_identifier(parts[0])
        return None, parts[0]
    if len(parts) != _SCHEMA_PARTS:
        message = "A table may have one schema qualifier."
        raise DatabaseSchemaError(message)
    _validate_columns(parts)
    return parts[0], parts[1]


def _validate_columns(names: Sequence[str]) -> None:
    """Validate one or more SQL identifier names.

    Args:
        names: Identifiers supplied by application code.
    """
    if not names:
        message = "At least one column name is required."
        raise DatabaseSchemaError(message)
    for name in names:
        _validate_identifier(name)


def _validate_identifier(name: str) -> None:
    """Reject SQL identifiers outside the portable safe naming subset.

    Args:
        name: Identifier supplied by application code.

    Raises:
        DatabaseSchemaError: If the identifier is malformed or unsafe.
    """
    if not _IDENTIFIER.fullmatch(name):
        message = "The schema identifier is invalid."
        raise DatabaseSchemaError(message)


def _validate_optional_identifier(name: str | None) -> None:
    """Validate a present optional SQL identifier.

    Args:
        name: Optional identifier.
    """
    if name is not None:
        _validate_identifier(name)


def _validate_action(action: str | None) -> str | None:
    """Validate a foreign-key action from a narrow SQL keyword allowlist.

    Args:
        action: Optional ``ON DELETE`` or ``ON UPDATE`` action.

    Returns:
        The normalized supported SQL action.

    Raises:
        DatabaseSchemaError: If the action is not in the allowlist.
    """
    if action is None:
        return None
    normalized = action.strip().upper()
    allowed = {
        "CASCADE",
        "RESTRICT",
        "SET NULL",
        "SET DEFAULT",
        "NO ACTION",
    }
    if normalized not in allowed:
        message = "The foreign-key action is unsupported."
        raise DatabaseSchemaError(message)
    return normalized


def _index_name(table_name: str, columns: Sequence[str]) -> str:
    """Create a deterministic index identifier from safe names.

    Args:
        table_name: Table name without its schema qualifier.
        columns: Indexed column identifiers.

    Returns:
        A deterministic index name.
    """
    return "_".join((_DEFAULT_INDEX_PREFIX, table_name, *columns))


__all__ = ["Blueprint", "ColumnDefinition", "Schema"]
