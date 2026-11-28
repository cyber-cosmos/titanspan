---
title: "ADR 0006: SQLAlchemy Persistence"
---

<span id="adr-0006-sqlalchemy-persistence"></span>

- Status: Accepted
- Date: 2026-11-24

## Context

The Database component needs asynchronous I/O, transactions, migrations,
and expressive native model and query APIs without implementing SQL
compilation or persistence.

## Decision

Use SQLAlchemy async engines, statements, sessions, ORM, and Unit of Work
primitives. Use Alembic for migrations. A future Titanspan model and query API
must keep native SQLAlchemy access, use explicit transactions, and avoid
sharing unsafe mutable async sessions across concurrent tasks.

Database is a built-in component. SQLAlchemy, Alembic, and aiosqlite are
mandatory runtime dependencies so native persistence and the default SQLite
backend work in a standard install. Backend-specific drivers remain optional
extras. Engine and connection acquisition stays lazy and application-owned.

## Alternatives considered

- A custom ORM and query compiler: rejected because they duplicate persistence
  infrastructure.
- A synchronous ORM behind async wrappers: rejected because hidden blocking
  I/O violates the async-first direction.
- SQLModel as the persistence core: not selected because direct SQLAlchemy
  access is required for the planned conventions.

## Consequences

Session ownership, relationship loading, streaming results, and transaction
boundaries need explicit APIs and tests.

## Risks

ORM ergonomics can hide transaction or loading behavior. Keep database I/O
explicit and test session isolation before public release.

## References

- [SQLAlchemy asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/en/20/orm/)
- [Alembic documentation](https://alembic.sqlalchemy.org/en/latest/)
