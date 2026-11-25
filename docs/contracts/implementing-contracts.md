# Implementing contracts

## Define a real boundary

Add a contract when it enables substitution, a meaningful test seam, or an
explicit resource lifecycle. First check existing module-owned contracts.
Logging contracts, for example, belong to `titanspan.logging.contracts`.
Do not define another protocol with a different identity for the same
behavior.

Use `Protocol` for structural behavior. Use an abstract base class only when
nominal inheritance, shared behavior, or runtime abstract-method enforcement
is required. Keep contracts small and separate optional capabilities from
required behavior.

## Type and document behavior

Use generics when input and output types are related. Prefer standard-library
types and Titanspan-owned domain values. Keep backend classes and exceptions
out of public signatures. Describe missing values, mutation, ordering,
cancellation, concurrency, errors, and resource ownership when they apply.

Use Python snake_case as the canonical spelling. If a Laravel-compatible
spelling is needed, define a distinct compatibility protocol or an explicit
adapter. Do not force implementers to duplicate methods just to offer both
spellings.

## Keep implementations separate

Contracts contain no container engine, application bootstrap, database
engine, logger, network client, queue worker, or workflow runtime. Concrete
implementations live with their owning component and depend inward on the
contract only when that boundary has been implemented and tested.

Avoid importing optional integrations from `titanspan.contracts`. Keep shared
types in narrow modules to prevent cycles. `TYPE_CHECKING` imports should not
be used to conceal runtime dependencies needed by the actual contract.

## Validate a change

Write a failing test first for behavioral changes. Verify structural typing
with strict Pyright and test real implementations at integration boundaries.
Runtime protocol checks confirm attribute presence only; they are not a
substitute for signature checks or behavioral tests.

Run `uv run --locked ruff check .`,
`uv run --locked ruff format --check .`, `uv run --locked pyright`,
`make architecture-check`, and the applicable unit and integration tests.
Update the compatibility inventory and public documentation when a contract
or its guarantees change.
