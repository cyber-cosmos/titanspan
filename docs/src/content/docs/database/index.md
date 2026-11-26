---
title: "Database"
---

<span id="database"></span>

Database integration is planned and is not included in the current package.
The selected direction is SQLAlchemy for async persistence and Alembic for
migrations, with explicit transactions and native SQLAlchemy interoperability.

No Titanspan ORM, model, query builder, or migration API is available yet.
See [ADR 0006](/titanspan/architecture/decisions/0006-sqlalchemy-persistence/) and the
[architecture guide](https://github.com/titanspan/titanspan/blob/main/ARCHITECTURE.md#database-and-transaction-semantics).
