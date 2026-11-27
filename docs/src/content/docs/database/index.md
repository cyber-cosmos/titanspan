---
title: "Database"
---

<span id="database"></span>

Titanspan Database provides application-owned connections, synchronous and
asynchronous queries, Active Record models, schema operations, and Alembic
migrations. SQLAlchemy owns connections, SQL compilation, ORM mapping, session
identity, and Unit of Work behavior. Alembic owns migration revisions and
revision state.

The component is under active development. This guide describes the APIs that
are implemented and exercised by the current SQLite and PostgreSQL integration
tests. It does not imply support for every SQLAlchemy dialect or every feature
listed in the project roadmap.

## Install

Install the optional Database and migration dependencies:

```shell
uv add "titanspan[database]"
```

SQLite and PostgreSQL drivers have separate extras. PostgreSQL applications
can install the tested Psycopg driver with:

```shell
uv add "titanspan[database,postgresql]"
```

The base Titanspan installation does not import SQLAlchemy or Alembic. Add the
Database provider to the application that uses persistence:

```python
from pathlib import Path

from titanspan.database import DatabaseServiceProvider
from titanspan.foundation import Application

application = Application(
    base_path=Path.cwd(),
    config={
        "database": {
            "default": "sqlite",
            "connections": {
                "sqlite": {
                    "driver": "sqlite",
                    "database": "database/application.sqlite",
                },
            },
        },
    },
    service_providers=(DatabaseServiceProvider(),),
)
```

Provider registration creates a lazy, application-owned manager. It does not
open a connection during application construction. Relative SQLite paths are
resolved beneath `Application.base_path`; the process working directory is
not changed.

## Connections and execution

Configure named connections under `database.connections` and select one with
`database.default`. A connection may use a SQLAlchemy URL or structured fields
such as `driver`, `host`, `port`, `database`, `username`, and `password`.
Provide `sync_url` and `async_url` when the two execution modes need different
drivers. Pooling and isolation settings belong under `options` and are
validated before engine construction.

```python
from collections.abc import Mapping

from titanspan.facades.database import DB


def active_users() -> list[Mapping[str, object]]:
    """Return active user rows from the selected database."""
    return (
        DB.connection("sqlite")
        .table("users")
        .where("active", True)
        .get()
    )
```

`DB.connection()` selects a logical connection. SQLAlchemy creates the
underlying engine on first use. `Connection.engine` and
`Connection.async_engine` are explicit SQLAlchemy interoperability points.
`Connection.execute()` and `execute_async()` accept trusted SQL text with
separately bound values; they are escape hatches, not identifier sanitizers.

Synchronous calls use SQLAlchemy synchronous engines and thread-owned
sessions. Async calls use SQLAlchemy asynchronous engines and task-owned
sessions. Titanspan rejects an inherited transaction context when a different
thread or task tries to use its mutable session. Sync and async engines have
separate connection and transaction boundaries.

## Transactions

Use explicit transaction scopes when multiple statements must commit or roll
back together:

```python
from titanspan.facades.database import DB


async def add_user() -> None:
    """Insert a user within one asynchronous transaction."""
    async with DB.transaction_async():
        await DB.table("users").insert_async(
            {"name": "Ada", "active": True},
        )
```

The synchronous API is `DB.transaction()`. Nested scopes use SQLAlchemy
savepoints where supported. A model save flushes its Unit of Work; the
outermost transaction owns commit. Operations outside an explicit transaction
use and finish an operation-owned Unit of Work. `DB.after_commit()` callbacks
run only after a successful outer commit. Rollback callbacks follow their
owning transaction or savepoint. `await DB.after_commit_async()` registers an
awaited callback on the current task's transaction and preserves registration
order with synchronous commit callbacks.

Transaction scopes expose a receipt with a confirmed outcome. If an
after-commit callback fails, the receipt reports that the database already
committed. If commit acknowledgement fails, Titanspan reports an unknown
outcome and invalidates the physical connection; applications must decide
whether a retry is safe.

Retry policies, distributed transactions, and exactly-once side-effect
delivery are not provided. A callback registered for commit must not be used
to hide work that needs atomicity with an external service.

## Query Builder

`DB.table()` returns a mutable builder intended for one operation. Clone it
before composing independent queries. Values are bound through SQLAlchemy;
table and column identifiers are validated before expression construction.

```python
from titanspan.facades.database import DB


active_users = (
    DB.table("users")
    .select("id", "name", "email")
    .where("active", True)
    .where_not_null("email")
    .order_by("name")
    .get()
)
```

Implemented operations include selected columns and raw projections, nested
conditions, comparisons, `IN`, `BETWEEN`, null checks, existence predicates,
joins, grouping, `HAVING`, ordering, limits, offsets, aggregates, inserts,
multi-row inserts, insert-from-query, conflict-safe upserts, insert-or-ignore,
updates, deletes, increments, and decrements. Raw SQL expressions require
explicit trusted application-authored strings and bound values.

`insert_returning()`, `update_returning()`, and `delete_returning()` expose
database-produced rows on SQLite and PostgreSQL. Other dialects reject these
operations until their driver behavior is verified. Use `delete()` without
filters for a full-table row deletion; there is no generic `truncate()` because
SQLAlchemy Core has no portable truncate operation or identity-reset policy.

Use `upsert()` or `upsert_async()` for an atomic database-side conflict
operation. `unique_by` names the unique key and `update` optionally restricts
the inserted columns copied into a conflicting row:

```python
from titanspan.facades.database import DB


async def save_user(email: str, name: str) -> int:
    """Insert a user or update its name by the unique email key.

    Args:
        email: User's unique email address.
        name: Name value written on insert or conflict.

    Returns:
        Driver-reported number of affected rows.
    """
    return await DB.table("users").upsert_async(
        [{"email": email, "name": name}],
        unique_by=("email",),
    )
```

SQLite and PostgreSQL use native `ON CONFLICT` statements. The MySQL dialect
uses its native duplicate-key statement; it relies on actual unique indexes
and ignores `unique_by` when identifying conflicts. MySQL and MariaDB are not
real-integration-tested here. MySQL `INSERT IGNORE` may suppress additional
data errors as warnings, following that backend's behavior. Returned affected
row counts follow each driver's semantics. Other dialects reject these
operations explicitly.

Retrieval methods include `get`, `first`, `first_or_fail`, `sole`, `find`,
`find_many`, `value`, `sole_value`, `pluck`, `count`, `sum`, `avg`, `min`,
`max`, and `exists`. Inner and left subquery joins are available through
`join_sub()` and `left_join_sub()`. `right_join()` reverses the join sides and
uses a left outer join on PostgreSQL, MySQL, MariaDB, and SQLite.
`full_outer_join()` is available on PostgreSQL and SQLite 3.39 or later; MySQL
and MariaDB do not support full outer joins. MySQL joins are not real
integration-tested here. The current pagination API offers
length-aware and simple page results. Equivalent asynchronous terminal methods
use an `_async` suffix. Use a stream context when a result must remain bounded
in memory:

```python
async with DB.table("events").cursor_async(batch_size=500) as rows:
    async for row in rows:
        await process_event(row)
```

Synchronous applications can use `cursor()` and `chunks()`. Async applications
can use `cursor_async()` and `chunks_async()`. The context owns the SQLAlchemy
result and session; exit it when iteration ends, including on early exit.
SQLAlchemy applies the requested `yield_per` size. `union()` and
`union_all()` compose compatible projections through SQLAlchemy compound
queries. `with_cte()` attaches a named common table expression. PostgreSQL and
MySQL builders can request `lock_for_update()` or `shared_lock()` inside an
active transaction. Unsupported dialects reject row locks, and aggregate
terminals reject lock modifiers because they do not return lockable rows.
Cursor pagination is available through `cursor_paginate()` and
`cursor_paginate_async()`. The builder adds a unique key column as a stable
tie-breaker, supports mixed ascending and descending order columns, and returns
forward and reverse cursor tokens. Cursor ordering values must be non-null and
use supported scalar types. Grouped and distinct queries are rejected. Tokens
are bounded, validated base64 JSON containing data values; they are not signed
and do not provide authenticity or authorization.

```python
page = await DB.table("events").order_by("id").cursor_paginate_async(
    per_page=100,
)
if page.next_cursor is not None:
    following = await DB.table("events").order_by("id").cursor_paginate_async(
        per_page=100,
        cursor=page.next_cursor,
    )
```

Date, time, year, month, and day predicates use bound SQLAlchemy expressions.
Date and time predicates are integration-tested on SQLite and PostgreSQL.
Other dialects depend on their SQLAlchemy dialect implementation.

`where_json_value()` compares a scalar at a dot-separated object path. Path
segments accept identifier characters only, and values remain bound query
parameters. SQLite and PostgreSQL JSON or JSONB behavior is integration-tested.
MySQL expression construction exists but does not yet have live-server
verification. Array indexing and nested JSON containment are not provided.

For long-running processing that may update rows as it proceeds, use keyset
pages over a unique, non-null, orderable column:

```python
async for rows in DB.table("events").select("payload").chunks_by_id_async(
    500,
    key_column="id",
):
    await process_events(rows)
```

Keyset pages close their operation session before yielding each page and do not
provide one snapshot transaction across the entire iteration. The continuation
column is selected internally and removed from projected result mappings.

## Models

Models use SQLAlchemy's typed declarative mapping. Titanspan adds safe
mass-assignment rules, application-aware persistence methods, timestamps,
hidden-field serialization, and typed query builders.

```python
from typing import ClassVar

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import Model


class User(Model):
    """Represent one application user."""

    table = "users"
    fillable = ("name", "email")
    hidden = ("private_note",)
    factory_attributes: ClassVar[dict[str, object]] = {
        "name": lambda index: f"User {index}",
        "email": lambda index: f"user-{index}@example.test",
    }

    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    private_note: Mapped[str] = mapped_column(String(255))
```

Declare columns with SQLAlchemy `Mapped` and `mapped_column`; bare annotations
do not define arbitrary column types. The base `Model` supplies an integer
`id` and nullable `created_at` and `updated_at` columns. Override `table`, the
timestamp names, or `timestamps` when the convention does not fit.

```python
async def create_user() -> User:
    """Create and update a model through asynchronous persistence."""
    user = await User.create_async(
        {
            "name": "Ada",
            "email": "ada@example.test",
            "private_note": "not included in serialized output",
        },
    )
    user.name = "Ada Lovelace"
    await user.save_async()
    return user
```

Mass assignment accepts only declared `fillable` columns by default. Use
`force_fill()` only with trusted application values. Mass-assignment rules do
not replace authorization. `User.query()` supports typed retrieval,
conditions, ordering, eager loading, aggregates, pagination, and bulk
mutations. Simple and length-aware pagination are implemented; cursor
pagination is not.

### Factories

Declare trusted defaults on `factory_attributes`. Values may be constants or
callables that receive the zero-based index of each generated model. The
factory resolves its Database service only when a create operation runs:

```python
from titanspan.database import ModelCollection


async def create_users() -> ModelCollection[User]:
    """Create ten users in one task-owned transaction."""
    return await (
        User.factory()
        .state({"name": lambda index: f"Member {index}"})
        .count(10)
        .create_async()
    )
```

`make()` and `make_many()` return transient models without database I/O.
`create()` and `create_many()` use the synchronous transaction policy;
`create_async()` uses a task-owned transaction. Batch persistence is sequential
and returns the native `ModelCollection`. `sequence()` applies repeating
ordered overrides. `after_making()` runs after transient construction, while
`after_creating()` waits for the owning transaction to commit. A rollback
discards pending create callbacks. Applications can use Faker in their own
attribute callbacks; the Database extra does not install a fake-data engine.

Relationship factories and model recycling are not implemented.

### Seeders

Seeders are application classes resolved through the native Container. Their
default execution wraps each seeder in a transaction; `call()` and
`call_async()` resolve nested seeders and inherit the selected connection.
Implement `run()` for synchronous work or `run_async()` for asynchronous
work:

```python
from titanspan.database import Seeder


class UserSeeder(Seeder):
    """Create representative users for local development."""

    def run(self) -> None:
        """Insert ten users in the seeder transaction."""
        User.factory().count(10).create()
```

Call `UserSeeder().execute()` from an active application context. The async
equivalent is `await UserSeeder().execute_async()`. Set
`transactional = False` only when a seeder deliberately owns its transaction
policy. Seeders are application code and are not assumed to be idempotent.

`titanspan db:seed` accepts a class name from
`database.seeders.<snake_case_name>` or a trusted `module:Class` path.
Non-production execution asks for confirmation unless `--force` is supplied.
Production execution fails closed unless the operator supplies `--force`.
Use `--database` to select and pass a connection through the seeder tree.
Models used by the seeder must be configured for that same connection.

The `SoftDeletes` mixin adds a nullable deletion timestamp and filters deleted
rows from model queries by default. `with_trashed()`, `only_trashed()`,
`restore()`, and `force_delete()` provide explicit visibility and deletion
operations. Raw table queries intentionally bypass model scopes.

## Model lifecycle events

Register typed model events with the application-owned Events dispatcher.
Creating and updating events run before SQLAlchemy flushes the model. A
listener can call `event.cancel()` to stop that write. Created, updated, saved,
and deleted events run only after the owning transaction commits:

```python
from app.models import User
from titanspan.database import ModelCreated
from titanspan.facades.event import Event


def record_creation(event: ModelCreated[User]) -> None:
    """Observe a committed user insert."""
    print(event.model.id)


def register_database_listeners() -> None:
    """Register listeners from an application startup callback."""
    Event.listen(ModelCreated, record_creation)
```

Register observer classes on the model when their hooks belong to one model:

```python
from app.models import User


class UserObserver:
    """Handle User lifecycle hooks through the active Container.

    Observer methods may use dependencies constructed by the Container.
    """

    async def created(self, user: User) -> None:
        """Run after the user's insert commits.

        Args:
            user: User whose insert is durable.
        """
        print(user.id)


def register_user_observer() -> None:
    """Register observers while the application context is active.

    Observer handles can be retained for later cleanup.
    """
    User.observe(UserObserver)
```

The active Container resolves an observer for each matching hook, so scoped
dependencies follow the current execution scope. Keep returned registration
handles if the application must later unregister those hooks. Synchronous
model operations require synchronous hooks; asynchronous model operations
await both synchronous and asynchronous hooks. Events registered inside a
savepoint remain pending until the outer transaction commits; rollback
discards them. Bulk Query Builder mutations bypass per-model events. Event
suppression and dedicated soft-delete and restore events are not implemented.
A listener failure after commit is reported to the caller, but it cannot undo
a database write that already committed.

## Relationships and loading

Relationship helpers delegate mapping and loading to SQLAlchemy. The current
native declaration helpers are `has_one`, `has_many`, `belongs_to`, and
`belongs_to_many`. The related classes and foreign-key metadata must form a
valid SQLAlchemy mapping.

```python
from __future__ import annotations

from sqlalchemy import ForeignKey, mapped_column
from sqlalchemy.orm import Mapped, relationship

from titanspan.database import Model, has_many


class Post(Model):
    """Represent a post owned by one user."""

    table = "posts"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped[User] = relationship(back_populates="posts")


class User(Model):
    """Represent a user with related posts."""

    table = "users"
    posts: Mapped[list[Post]] = has_many(Post, back_populates="user")
```

Use `with_()` to load relationships as part of the query:

```python
from titanspan.database import ModelCollection


async def users_with_posts() -> ModelCollection[User]:
    """Return users with their posts loaded."""
    return await User.query().with_("posts").get_async()
```

Async model results are detached after the operation. Accessing an unloaded
relationship does not initiate hidden async I/O. Serialization includes only
already-loaded relationships and omits attributes listed in `hidden`; it does
not lazy-load related records.

`ModelCollection` extends the native Collections component for identity-aware
model operations, safe conversion, and batch relationship loading. Ordinary
collection behavior remains owned by `titanspan.collections`.

Through and polymorphic relationships, relationship persistence helpers,
relationship aggregates, global and local scopes, broad custom cast and
accessor APIs, and API resources are not implemented yet.

## Schema and migrations

`Schema` and `Blueprint` use SQLAlchemy metadata and Alembic operations for
schema work. A blueprint applies its operations when its context exits:

```python
from titanspan.database import Schema


async def create_user_schema() -> None:
    """Create the user table using the native schema builder."""
    async with Schema.create("users") as table:
        table.id()
        table.string("email", length=320).unique()
        table.boolean("active").default(True)
        table.timestamps()
```

The current schema API creates, alters, and drops tables; defines common
columns and constraints; and inspects tables, columns, indexes, and foreign
keys through SQLAlchemy. SQLite alterations use Alembic batch operations.
Dialect-specific operations fail explicitly when the selected backend cannot
provide them.

Alembic owns the revision graph and version table. Native `Migration` classes
run through Alembic's operation context. `MigrationManager` provides revision
creation, status, install, upgrade, rollback, reset, and refresh operations.
The Console currently registers `migrate`, `migrate:install`,
`migrate:status`, `migrate:rollback`, `migrate:reset`, `migrate:refresh`,
`db:seed`, and `make:seeder`.
Destructive rollback, reset, and refresh commands confirm before operating
and refuse production execution unless the explicit force policy permits it.
The ordinary `migrate` command also requires `--force` in production and
identifies the selected database before applying changes. `--isolated`
requires a supported PostgreSQL or MySQL migration lock; SQLite does not
provide this cross-process guarantee. PostgreSQL locking has real-server
coverage. MySQL and MariaDB locking has orchestration tests but no live-server
integration test.

Fresh-database, schema-dump, database-inspection, and model-generation
commands are not implemented. Autogenerated revisions require review before
execution. DDL rollback guarantees follow the selected dialect; some
databases commit schema changes implicitly.

## Application tests

Use the existing `ApplicationTest` or `AsyncApplicationTest` from
`titanspan.testing` and add `DatabaseServiceProvider` to the test application.
The Database component does not create another application lifecycle.
Current integration tests use temporary SQLite databases and a disposable
PostgreSQL database. PostgreSQL integration is mandatory in CI; it fails if
the job's required URL is missing.

Database assertions run real Query Builder and ORM queries through the active
application service. Import `assert_database_has`, `assert_database_count`,
`assert_model_exists`, and their `_async` variants from `titanspan.database`.
The helpers also include missing-row, empty-table, and soft-delete assertions.
They do not create, migrate, or reset a test database. Query-count assertions
remain unavailable until Database query monitoring is implemented.

## Database-backed Validation rules

Use asynchronous `unique_rule` and `exists_rule` values with the existing
Validation service. The rules accept a mapped model or trusted table name,
use model connections by default, and bind values through the Query Builder.

```python
from pydantic import BaseModel

from titanspan.database import unique_rule
from titanspan.facades import Validation


class CreateUserInput(BaseModel):
    email: str


email_rule = unique_rule(User, "email", field="email")
validated = await Validation.validate_async(
    {"email": "ada@example.test"},
    CreateUserInput,
    async_rules=(email_rule,),
)
```

Use `exists_rule` to require a matching record. Add trusted fixed query
constraints with `constraints={"active": True}`. For updates, pass a trusted
column and identifier with `ignore=("id", user.id)`. Never take the ignored
identifier from request data. A `None` field skips the lookup so optional
inputs remain nullable. Database uniqueness constraints remain necessary
because a concurrent write can race with validation.

## Explicit route model binding

Register a model against an existing Router path parameter with
`titanspan.database.routing.bind_model`. The callback uses the active async
Database service and the model's `route_key_name`, which defaults to `id`.
Missing rows follow Routing's not-found response path.

```python
from titanspan.database.routing import bind_model

bind_model(app.router, User, parameter="user")

async def show_user(user: User) -> dict[str, object]:
    return {"id": user.id, "name": user.name}
```

Scoped child binding, automatic annotation discovery, and model-based URL
generation are not implemented yet.

MySQL and MariaDB drivers can be installed through optional extras, but this
repository does not yet run real integration tests for those dialects. Other
SQLAlchemy dialects may interoperate through documented SQLAlchemy APIs, but
they are not claimed as Titanspan-tested backends.

## Interoperability and boundaries

Advanced applications can use the SQLAlchemy engine, sessions, mapped
attributes, and statement objects exposed by the Database service. Such code
must preserve the active session's task or thread ownership and transaction
boundary. Use SQLAlchemy and Alembic APIs directly for capabilities not yet
exposed by the native layer.

The Database component does not yet provide scoped or automatic Routing model
binding, model-based URL generation, soft-delete and restore events,
query-count assertions, database test isolation helpers, read replicas, query
caching, or distributed migration coordination. See
[ADR 0006](/titanspan/architecture/decisions/0006-sqlalchemy-persistence/) for
the accepted persistence boundary and
[the backend boundary specification](/titanspan/specifications/backend-boundaries/)
for current interoperability ownership.
