---
name: titanspan-architecture
description: Assess module boundaries, dependency direction, and architecture decisions for non-trivial Titanspan changes.
---

# Titanspan architecture review

## When to use

Use when a change crosses modules, changes a lifecycle or contract, adds an
integration, changes package direction, or may require an ADR.

## References

- `AGENTS.md`
- `ARCHITECTURE.md`
- `ROADMAP.md`
- Relevant files in `docs/architecture/decisions/`
- `docs/development/standards.md`
- `docs/development/writing-standards.md`

## Procedure

1. Inspect the current code, tests, Git status, and existing public surface.
2. Describe the module ownership and dependency direction affected.
3. Check whether a selected mature library already provides the behavior.
4. Identify lifecycle, optional dependency, security, concurrency, and API
   compatibility effects.
5. Compare the smallest reasonable alternatives. Recommend a thin typed
   boundary only when it provides a real convention, lifecycle, contract, or
   test seam.
6. Identify tests, docs, and ADR updates required before implementation.

## Failure modes

- Treating roadmap descriptions as supported code.
- Adding abstractions that duplicate a mature package.
- Creating circular imports or optional dependencies in core modules.
- Claiming performance, support, or compatibility without evidence.
- Mechanically translating another language instead of designing idiomatic
  Python APIs.

## Validation

For code changes, use the relevant focused tests and `make check`. For an ADR,
verify the decision file has context, alternatives, consequences, risks, and
official references. Run `make docs-build` when VitePress pages change.

## Completion criteria

Return the affected modules, dependency direction, smallest viable design,
alternatives and tradeoffs, validation plan, and whether an ADR is needed.
