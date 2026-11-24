---
name: laravel-api-design
description: Design a Laravel-inspired Titanspan API that remains idiomatic, typed Python and delegates infrastructure to mature libraries.
---

# Laravel-inspired API design

## When to use

Use when proposing a public API, fluent interface, convention, facade, model
operation, command, or workflow syntax influenced by Laravel.

## References

- `AGENTS.md`
- `ARCHITECTURE.md` and the relevant ADRs
- `ROADMAP.md`
- Official Laravel documentation for the corresponding public concept
- Official documentation for the selected Python library

## Procedure

1. Identify the developer problem and the corresponding Laravel public
   behavior. Study Laravel documentation, not only a code snippet.
2. Identify the underlying architectural responsibility and the mature Python
   package that should own it.
3. Separate Titanspan-owned conventions and lifecycle from delegated package
   behavior.
4. Design a minimal typed Python API using Python naming, explicit `await`
   for asynchronous operations, generics or protocols only when useful, and
   native object interoperability.
5. Document important semantic differences, transaction/resource behavior,
   failure behavior, and compatibility.
6. Add tests for the public contract and relevant boundary behavior.

## Failure modes

- Translating PHP syntax or magic behavior literally into Python.
- Hiding async operations behind properties or synchronous-looking access.
- Creating a competing ORM, router, container, queue, or graph runtime.
- Using facade globals or implicit mutable state.
- Advertising parity that is not implemented and tested.

## Validation

Verify both Laravel and Python library references from official sources. Run
focused API tests and `make check`; build docs when public examples change.

## Completion criteria

The API solves a real use case, is idiomatic and typed, preserves native
interoperability, has tested semantics, and clearly states its scope.
