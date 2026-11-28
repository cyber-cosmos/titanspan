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

The standard Titanspan distribution includes SQLAlchemy, Alembic, and
`aiosqlite`. SQLite works in synchronous and asynchronous applications
without an extra. PostgreSQL applications can install the tested Psycopg
driver with:

```shell
uv add "titanspan[postgresql]"
```

Foundation registers the Database provider with its built-in providers.
Provider registration constructs an application-owned lazy manager; it does
not open a connection during application construction.

```python
from pathlib import Path

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
)
```

Relative SQLite paths resolve beneath `Application.base_path`; the process
working directory is not changed.

## Connections and execution

Configure named connections under `database.connections` and select one with
`database.default`. A connection may use a SQLAlchemy URL or structured fields
such as `driver`, `host`, `port`, `database`, `username`, and `password`.
Provide `sync_url` and `async_url` when the two execution modes need different
drivers. Pooling and isolation settings belong under `options` and are
validated before engine construction.

```python
from collections.abc import Mapping

from titanspan.facades import DB


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
from titanspan.facades import DB


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
from titanspan.facades import DB


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
updates, deletes, and atomic single- or multi-column increments and decrements.
Raw SQL expressions require
explicit trusted application-authored strings and bound values.
`to_sql()` compiles placeholders using the configured SQLAlchemy dialect.
`get_bindings()` returns parameter names with values redacted by default.
Set `redact=False` only in trusted diagnostics; returned values may contain
sensitive application data and must not be written to ordinary logs.
`explain()` and `explain_async()` return database-specific plans on SQLite,
PostgreSQL, MySQL, and MariaDB without executing the selected query. Plan
formats vary by database; SQLite and PostgreSQL have live integration tests.

`insert_returning()`, `update_returning()`, and `delete_returning()` expose
database-produced rows on SQLite and PostgreSQL. Other dialects reject these
operations until their driver behavior is verified. Use `delete()` without
filters for a full-table row deletion; there is no generic `truncate()` because
SQLAlchemy Core has no portable truncate operation or identity-reset policy.

Use `upsert()` or `upsert_async()` for an atomic database-side conflict
operation. `unique_by` names the unique key and `update` optionally restricts
the inserted columns copied into a conflicting row:

```python
from titanspan.facades import DB


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
`max`, and `exists`. Subquery joins are available through `join_sub()`,
`left_join_sub()`, `right_join_sub()`,
`full_outer_join_sub()`, and `cross_join_sub()` compose fluent subqueries.
`right_join()` reverses the join sides and uses a left outer join on
PostgreSQL, MySQL, MariaDB, and SQLite.
`join_with()` accepts a typed callback for column comparisons, bound values,
and nested ON-condition groups. A left join can retain parent rows while
filtering joined rows inside its ON clause.
`join_lateral()` and `left_join_lateral()` support correlated subqueries on
PostgreSQL. `where_full_text()` and `or_where_full_text()` delegate to
PostgreSQL text search, SQLite FTS, or MySQL and MariaDB full-text indexes.
SQLite requires an FTS virtual table and one full-text column per predicate.
MySQL and MariaDB require the selected columns to match an available full-text
index. PostgreSQL and SQLite are integration-tested; MySQL and MariaDB
expressions are generated through SQLAlchemy but have not been tested against
live servers.
`full_outer_join()` is available on PostgreSQL and SQLite 3.39 or later; MySQL
and MariaDB do not support full outer joins. MySQL joins are not real
integration-tested here. `select_sub()` and `add_select_sub()` add named scalar
projections, and `where_in()` / `where_not_in()` accept a fluent single-column
subquery as well as bound sequences. Create a correlated builder with
`subquery(table_name)`; it shares the outer table expressions so SQLAlchemy
can correlate scalar and EXISTS subqueries. `in_random_order()` uses SQLAlchemy's
backend-native random function on SQLite, PostgreSQL, and MySQL. Randomly
ordered queries cannot use cursor pagination. `where_row_values()` and
`or_where_row_values()` compare bound tuples on SQLite 3.15 or later,
PostgreSQL, and MySQL. The current pagination API offers length-aware and
simple page results. Equivalent asynchronous terminal methods
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

JSON predicates accept dot-separated object paths containing identifier
characters only, and values remain bound query parameters. `where_json_value()`
compares a scalar; `where_json_contains_key()` tests key existence even when a
stored value is JSON null; and `where_json_length()` compares array lengths.
These key and length operations use SQLite JSON1, PostgreSQL JSONB, or MySQL
and MariaDB JSON functions. `where_json_contains()` and its negated form use
PostgreSQL JSONB containment or the MySQL and MariaDB JSON containment
function. PostgreSQL containment requires JSONB columns. SQLite containment is
rejected because SQLite has no equivalent JSON containment operator. SQLite
and PostgreSQL behavior is integration-tested; MySQL and MariaDB expressions
have no live-server verification. Arbitrary array indexing is not provided.
`update_json()` and `update_json_async()` set one nested value through native
JSON functions. PostgreSQL updates require JSONB columns. Missing intermediate
objects are not synthesized consistently across database engines.

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

Declare password fields as hashed casts to use the application-owned Hashing
service:

```python
from collections.abc import Mapping
from typing import ClassVar

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import Model


class Account(Model):
    """Store account passwords using the configured Hashing component."""

    table = "accounts"
    casts: ClassVar[Mapping[str, str]] = {"password": "hashed"}
    password: Mapped[str] = mapped_column(String(255))
```

The cast runs immediately before model persistence and on model upserts. Async
operations call the bounded asynchronous Hasher API. Recognized encoded hashes
are preserved to avoid double hashing. Direct Query Builder writes bypass model
casts. Declare other database conversions with SQLAlchemy types or
`TypeDecorator`, and use ordinary Python properties for model accessors.

Mass assignment accepts only declared `fillable` columns by default. Use
`force_fill()` only with trusted application values. Mass-assignment rules do
not replace authorization. `User.query()` supports typed retrieval,
conditions, ordering, eager loading, aggregates, pagination, and bulk
mutations. Simple, length-aware, and cursor pagination are implemented.

Cursor pagination uses the model's single-column primary key as its stable
tie-breaker and returns hydrated models in the selected order:

```python
page = await User.query().order_by("name").cursor_paginate_async(
    per_page=50,
)
if page.next_cursor is not None:
    following = await User.query().order_by("name").cursor_paginate_async(
        per_page=50,
        cursor=page.next_cursor,
    )
```

The cursor query selects identifiers first and hydrates the bounded page
through the ORM, preserving model scopes and eager-load options. Concurrent
deletion between these two reads can shorten a page; cursor pages do not
provide a snapshot across requests.

Apply a typed local transformation with `apply()`. Named global predicate
factories are applied to root queries, relationship existence checks, and
eager-loaded related models:

```python
from collections.abc import Callable, Mapping
from typing import ClassVar

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import ColumnElement

from titanspan.database import Model, ModelQueryBuilder
from sqlalchemy.orm import Mapped, mapped_column


class PublishedPost(Model):
    """Represent a post filtered to published rows by default."""

    table = "posts"
    title: Mapped[str] = mapped_column()
    published: Mapped[bool] = mapped_column()
    global_scopes: ClassVar[
        Mapping[str, Callable[[], ColumnElement[bool]]]
    ] = {"published": lambda: PublishedPost.published.is_(True)}


def _named_posts(
    query: ModelQueryBuilder[PublishedPost],
) -> ModelQueryBuilder[PublishedPost]:
    """Restrict posts to rows with a title."""
    return query.where_not_null("title")


posts = PublishedPost.query().apply(_named_posts).get()
all_posts = PublishedPost.query().without_global_scope("published").get()
```

Call `without_global_scopes()` to remove all named predicates from one query.
Each query owns its scope selection. Raw `DB.table()` queries intentionally
bypass model scopes. Scope factories are trusted application code and must
return SQLAlchemy boolean expressions.

Use model-level `upsert()` for bulk conflict handling while preserving the
model's assignment policy and timestamp conventions:

```python
await User.upsert_async(
    [
        {"name": "Ada", "email": "ada@example.test"},
    ],
    unique_by=("email",),
)
```

Conflict targets and update columns use mapped model attribute names. The
operation maps them through SQLAlchemy metadata and delegates atomic conflict
handling to the configured database. Default updates preserve `created_at`
and refresh `updated_at`. This bulk operation does not hydrate models or send
per-model lifecycle events. Use Query Builder directly for trusted bulk data
that intentionally bypasses model assignment rules. Bulk upserts also bypass
soft-delete visibility filters because a conflict target is resolved by the
database rather than through an ORM row query.

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
discards pending create callbacks. Faker is not a mandatory dependency.
Factory callbacks can use deterministic Python values or an application-
selected fake-data library.

Use `relationship()` to assign a related factory or recycle a persisted model
for a single-valued relation. The mapped relationship determines whether the
result is a single object or a collection. Supply `count` for collection
factories. Nested factory graphs remain transient until the root factory
persists them through SQLAlchemy's
Unit of Work and relationship cascade. Related `after_creating()` callbacks
run only after the owning transaction commits. Recycled models are reused and
are not copied or created again. Map association objects when pivot rows need
additional attributes.

```python
post = Post.factory().relationship("author", User.factory())
posts = Post.factory().relationship(
    "comments",
    Comment.factory(),
    count=3,
)
```

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

Declare a model's pruning query explicitly. Ordinary pruning processes
bounded keyset pages, invokes `pruning()` and model delete hooks, and hard
deletes matching `SoftDeletes` models. The pretend form only counts matches:

```python
from titanspan.database import Model, ModelQueryBuilder


class ExpiredUpload(Model):
    """Represent uploads retained only for a limited period."""

    table = "uploads"
    expired: Mapped[bool] = mapped_column(default=False)

    def prunable(self) -> ModelQueryBuilder[ExpiredUpload]:
        """Select expired uploads for permanent removal."""
        return ExpiredUpload.query().where("expired", True)


count = await ExpiredUpload.prune_all_async(chunk_size=500, pretend=True)
```

Use `mass_prune_all()` or `mass_prune_all_async()` when per-model hooks and
lifecycle events should be skipped. Both modes bound each page and include
soft-deleted candidates; matching soft-deletable rows are permanently
removed. The `model:prune --model package.module:Class` Console command
requires an explicit trusted model path. It prompts before destructive work
and requires `--force` in production. `--pretend` performs no deletion.

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
suppression is available through a model-scoped context:

```python
async with DB.transaction_async():
    with User.without_events():
        await user.save_async()
```

Suppression applies to the current task or thread and application execution
scope, and remains in effect for that operation's after-commit callbacks.
Child tasks do not inherit their parent's quiet persistence authority.
Soft-delete and restore operations dispatch cancellable pre-events and
after-commit events. Force deletion dispatches force-delete events around the
standard delete events. A listener failure after commit is reported to the
caller, but it cannot undo a database write that already committed.

## Relationships and loading

Relationship helpers delegate mapping and loading to SQLAlchemy. The current
native declaration helpers include `has_one`, `has_many`, `belongs_to`,
`belongs_to_many`, and read-only `has_one_through` and `has_many_through`.
`latest_of_many`, `oldest_of_many`, and `of_many` also declare read-only,
single-result relations selected by per-parent aggregate values. The related
classes and foreign-key metadata must form a valid SQLAlchemy mapping.

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
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"))
    posts: Mapped[list[Post]] = has_many(Post, back_populates="user")
```

Use a mapped intermediate table for through relationships. SQLAlchemy infers
the joins from foreign keys; provide `primaryjoin` and `secondaryjoin` when a
schema has multiple paths. Through relationships are read-only because they
use an intermediate table as a view-only secondary mapping:

```python
from sqlalchemy.orm import Mapped

from titanspan.database import has_many_through, has_one_through


class Country(Model):
    """Represent posts owned by users in one country."""

    table = "countries"
    posts: Mapped[list[Post]] = has_many_through(Post, User)
    first_post: Mapped[Post] = has_one_through(Post, User)
```

The intermediate `User` table must reference `Country`, and `Post` must
reference `User`. A one-through relation also requires data and constraints
that make its single-result semantics valid.

Use one-of-many helpers when a parent needs one row from a has-many relation.
SQLAlchemy loads the declared relation using a window function partitioned by
the related foreign key. The database dialect must support window functions.
The related model's primary key breaks ties so each parent receives a stable
single result:

```python
from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import Model, latest_of_many, oldest_of_many


class Post(Model):
    """Represent a post that belongs to one user."""

    table = "posts"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    score: Mapped[int]
    published_at: Mapped[datetime]


class User(Model):
    """Represent one user's newest and oldest posts."""

    table = "users"
    latest_post: Mapped[Post | None] = latest_of_many(Post, "user_id")
    oldest_post: Mapped[Post | None] = oldest_of_many(Post, "user_id")
    highest_scored_post: Mapped[Post | None] = latest_of_many(
        Post,
        "user_id",
        column=("score", "published_at"),
    )
```

The default latest and oldest helpers order by the related primary key.
Pass `column` to select by one or more mapped attributes instead. `of_many()`
accepts an ordered mapping of mapped attributes to `"min"` or `"max"`
aggregates when different attributes need different directions. Primary-key
columns are appended as tie breakers. For nullable selected attributes, rows
without an aggregate value do not qualify; a parent with no qualifying row
receives `None`. These relations are read-only; persist changes through a
normal model or writable relationship.

`belongs_to_many()` maps a writable SQLAlchemy secondary relationship.
Use `relation()` for transactional attachment changes by identifier or
persisted related model. Titanspan loads the current collection in its owning
session and refreshes the detached parent's collection after commit:

```python
relation = user.relation("tags")
await relation.attach_async(tag.id)

changes = await relation.sync_async([first_tag.id, second_tag.id])
assert changes.detached == (removed_tag_id,)
```

The manager provides sync and async `attach`, `detach`, `sync`,
`sync_without_detaching`, `toggle`, and `update_existing_pivot` operations.
`detach()` without IDs removes every association. `sync()` removes omitted
associations by default; pass `detaching=False` to retain them. These
operations use the application's Database session and transaction lifecycle.

`update_existing_pivot()` and its async form update non-key columns on one
existing association row and return the affected-row count. They support a
direct SQLAlchemy `Table` with one unambiguous foreign key to each model's
single primary key. Key columns and unknown column names are rejected. An
identifier with no matching association returns zero. For richer pivot
behavior, timestamps managed by the ORM, or custom pivot models, map an
association object and use its normal model persistence APIs.

```python
updated = await user.relation("tags").update_existing_pivot_async(
    tag.id,
    {"position": 2},
)
```

Use `with_()` to load relationships as part of the query:

```python
from titanspan.database import ModelCollection


async def users_with_posts() -> ModelCollection[User]:
    """Return users with their posts loaded."""
    return await User.query().with_("posts").get_async()
```

Constrain a loaded relationship through a typed related-model builder:

```python
from titanspan.database import ModelQueryBuilder


def titled_posts(
    query: ModelQueryBuilder[Post],
) -> ModelQueryBuilder[Post]:
    """Load posts with a non-null title."""
    return query.where_not_null("title")


async def users_with_titled_posts() -> ModelCollection[User]:
    """Return users with only titled posts loaded."""
    return await User.query().with_where("posts", titled_posts).get_async()
```

The callback mutates and returns its related query builder. Nested relationship
paths may be constrained with the same method.

Load a direct relationship count through a typed SQLAlchemy query expression:

```python
from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, query_expression

from titanspan.database import Model, has_many


class Post(Model):
    """Represent a post related to one user."""

    table = "posts"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class User(Model):
    """Represent users with a selected post count."""

    table = "users"
    posts: Mapped[list[Post]] = has_many(Post)
    posts_count: Mapped[int | None] = query_expression()


users = await User.query().with_count("posts").get_async()
```

Pass `attribute="published_posts_count"` to `with_count()` to select into a
different declared `query_expression()`. `with_exists()`, `with_sum()`,
`with_avg()`, `with_min()`, and `with_max()` select matching aggregates.
Declare each result using `query_expression()` and use the matching default
attribute name shown by the method. Aggregates apply the related model's
global and soft-delete scopes. Self-referential and nested aggregates are not
supported yet.

Load an aggregate after retrieving a collection with
`load_aggregate()` or `load_aggregate_async()`. This issues one query for the
collection and assigns results to its declared query-expression attributes:

```python
users = await User.query().get_async()
await users.load_aggregate_async("posts", "count")
await users.load_aggregate_async(
    "posts",
    "sum",
    column_name="views",
    attribute="published_views",
)
```

The aggregate kind is `count`, `exists`, `sum`, `avg`, `min`, or `max`. Numeric
aggregates require `column_name`. All returned values must target mapped
`query_expression()` attributes. Transient models without database identities
are skipped.

Stream large model results through a context that owns the Session and cursor:

```python
user_ids: list[int] = []
async with User.query().order_by("id").stream_async(batch_size=500) as users:
    async for user in users:
        user_ids.append(user.id)
```

Use `stream()` for synchronous consumers. The iterator is valid only inside
its context; early exit, errors, and cancellation close the result before the
Session is released.

Async model results are detached after the operation. Accessing an unloaded
relationship does not initiate hidden async I/O. Serialization includes only
already-loaded relationships and omits attributes listed in `hidden`; it does
not lazy-load related records.

The built-in cast declaration currently supports `"hashed"`. SQLAlchemy types
own other value conversion, while Python properties provide native accessors
and mutators. A separate dynamic cast registry is not provided.

`ModelCollection` extends the native Collections component for identity-aware
model operations, safe conversion, and batch relationship loading. Ordinary
collection behavior remains owned by `titanspan.collections`.

Polymorphic relationships and API resources are not implemented yet.

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
columns and constraints; and inspects tables, views, columns, indexes, and
foreign keys through SQLAlchemy. SQLite alterations use Alembic batch
operations.
Dialect-specific operations fail explicitly when the selected backend cannot
provide them.

Alembic owns the revision graph and version table. Native `Migration` classes
run through Alembic's operation context. `MigrationManager` provides revision
creation, status, install, upgrade, rollback, reset, and refresh operations.
The Console currently registers `migrate`, `migrate:fresh`,
`migrate:install`, `migrate:status`, `migrate:rollback`, `migrate:reset`,
`migrate:refresh`, `db:show`, `db:table`, `db:wipe`, `db:seed`, and
`make:migration`, `make:model`, `make:seeder`, `model:prune`, and
`model:show`. `db:show`
displays the selected connection's redacted target, dialect, tables, and
optional views. Use `--counts` to query each table's row count; this may be
slow on large tables. The command does not estimate database size or report
server-wide open connections. `db:table <name>` displays reflected columns,
SQL types, nullability, primary keys, indexes, and foreign keys for one table.
It accepts `--database` to select a configured connection. `db:wipe` drops
tables in the selected connection's default schema through SQLAlchemy's
dependency ordering. It prompts before dropping tables and requires `--force`
in production. Views remain intact. `migrate:fresh` applies the same table
cleanup, runs all pending migrations, and optionally executes a trusted
seeder with `--seed` and `--seeder`.
`model:show module:Class` displays mapped columns and relationships without
opening a database connection.
Destructive rollback, reset, and refresh commands confirm before operating
and refuse production execution unless the explicit force policy permits it.
The ordinary `migrate` command also requires `--force` in production and
identifies the selected database before applying changes. `--isolated`
requires a supported PostgreSQL or MySQL migration lock; SQLite does not
provide this cross-process guarantee. PostgreSQL locking has real-server
coverage. MySQL and MariaDB locking has orchestration tests but no live-server
integration test.

Schema-dump commands and `db:monitor` are not implemented. `make:model`
generates an importable model with the framework's conventional table name.
`make:migration` creates a native revision; `--autogenerate` delegates
metadata comparison to Alembic and still requires review before execution.
`db:show` provides a basic table and view overview. Autogenerated revisions
require review before execution. DDL
rollback guarantees follow the selected dialect; some databases commit
schema changes implicitly.

## Application tests

Use the existing `ApplicationTest` or `AsyncApplicationTest` from
`titanspan.testing`. The Database component participates in the standard
application lifecycle and does not create another one.
Current integration tests use temporary SQLite databases and a disposable
PostgreSQL database. PostgreSQL integration is mandatory in CI; it fails if
the job's required URL is missing.

Database assertions run real Query Builder and ORM queries through the active
application service. Import `assert_database_has`, `assert_database_count`,
`assert_model_exists`, and their `_async` variants from `titanspan.database`.
The helpers also include missing-row, empty-table, and soft-delete assertions.
They do not create, migrate, or reset a test database. Use query-count
assertions to check statements issued through the selected connection while
the context is active. SQLite's generated `BEGIN` transaction boundary is
excluded from the count.

```python
from titanspan.database import assert_query_count_async
from titanspan.facades import DB

async with assert_query_count_async(1):
    await DB.table("users").count_async()
```

Use `assert_query_count` with a regular `with` block for synchronous queries.
The context removes its SQLAlchemy event listener after success, mismatch, or
an exception from the test body. Query logging and monitoring remain
unimplemented.

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
binding, model-based URL generation, query monitoring, database test isolation
helpers, read replicas, query caching, or distributed migration coordination.
Soft-delete and restore lifecycle events are implemented. See
[ADR 0006](/framework/architecture/decisions/0006-sqlalchemy-persistence/) for
the accepted persistence boundary and
[the backend boundary specification](/framework/specifications/backend-boundaries/)
for current interoperability ownership.
