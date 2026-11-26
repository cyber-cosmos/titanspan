---
name: native-api-design
description: Design expressive, idiomatic Python APIs that follow Titanspan specifications and preserve clear implementation boundaries.
---

# Native Titanspan API design

## When to use

Use when proposing a public API, fluent interface, convention, facade,
configuration format, model operation, command, or workflow syntax.

## References

- `AGENTS.md`
- `ARCHITECTURE.md` and relevant architecture decisions
- `ROADMAP.md` for sequencing only
- The owning component's native specification and existing tests
- Official documentation for an implementation dependency when needed

## Procedure

1. Identify the developer problem and inspect the current implementation,
   public API, tests, and module ownership.
2. Find the native Titanspan behavior specification. Update it when the
   behavior is not established.
3. Design a Python API using `snake_case`, explicit async operations,
   standard Python protocols, and precise types.
4. Keep application-facing interfaces owned by Titanspan and delegate
   infrastructure to the selected maintained library.
5. Define defaults, failures, mutation, resource ownership, concurrency,
   cancellation, and lifecycle behavior.
6. Add focused failing tests before implementation and real integration
   coverage at implementation boundaries.
7. Update public documentation and the changelog for behavior changes.

External frameworks may inform architectural choices, but their public API
names, language semantics, and behavior are not compatibility requirements.

## Failure modes

- Translating another language's syntax or naming mechanically.
- Keeping duplicate aliases for one Titanspan operation.
- Hiding asynchronous work behind synchronous-looking APIs.
- Creating a competing ORM, router, container, queue, or workflow runtime.
- Exposing backend types or exceptions through ordinary public interfaces.
- Claiming behavior without implementation and tests.

## Validation

Run the focused API tests, Ruff, formatting, Pyright, and applicable
architecture checks. Run `make check` and `make docs-build` when applicable.

## Completion criteria

The API follows the native behavior specification, has one Python spelling,
preserves clear ownership boundaries, documents its lifecycle, and has
meaningful unit and integration coverage.
