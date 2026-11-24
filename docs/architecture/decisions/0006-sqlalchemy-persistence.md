# ADR 0006: SQLAlchemy Persistence

- Status: Accepted for the planned database module
- Date: 2026-11-24

## Context

The database module needs async I/O, transactions, migrations, and an
Eloquent-inspired API without implementing SQL compilation or persistence.

## Decision

Use SQLAlchemy async engines, statements, sessions, ORM, and Unit of Work
primitives. Use Alembic for migrations. A future Titanspan model and query API
must keep native SQLAlchemy access, use explicit transactions, and avoid
sharing unsafe mutable async sessions across concurrent tasks.

Neither package is an initial runtime dependency. Recheck compatible versions
and advisories when the database vertical slice begins.

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
