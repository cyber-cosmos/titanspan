---
name: component-development
description: Implement a focused feature in an existing Titanspan module with typed APIs, tests, and lifecycle safety.
---

# Titanspan component development

## When to use

Use when implementing or extending a real module capability or public API.

## References

- `AGENTS.md` and the nearest scoped `AGENTS.md`
- `ARCHITECTURE.md` and relevant ADRs
- `docs/src/content/docs/development/standards.md`
- `docs/src/content/docs/development/writing-standards.md`
- `docs/src/content/docs/development/agent-workflow.md`

## Procedure

1. Inspect the working tree and module implementation. Confirm the requested
   behavior belongs to an implemented scope.
2. Define observable behavior, failure cases, public API impact, and
   acceptance criteria.
3. Write a focused failing test for meaningful behavior and verify the
   failure is relevant.
4. Implement the smallest cohesive change using existing conventions,
   explicit types, and narrow module dependencies.
5. Add complete annotations and physically multi-line Google-style docstrings
   for each declaration. Comment on non-obvious invariants and design choices.
6. Handle cleanup, cancellation, timeout, and concurrency behavior where
   relevant.
7. Update API docs, examples, changelog, or ADRs as needed.
8. Inspect the complete diff and run applicable checks.

## Failure modes

- Adding placeholder APIs or speculative framework layers.
- Implementing planned modules without an accepted scope.
- Using undeclared library behavior or hiding async I/O.
- Editing generated files or unrelated user changes.
- Ignoring tests for failure and resource cleanup paths.

## Validation

Run focused Pytest coverage, then `make check`. Run `make build` for packaging
changes and `make docs-build` for docs site changes.

## Completion criteria

Implement and test the behavior. Keep it typed and documented. Stay within the
requested module. Report only checks you ran.
