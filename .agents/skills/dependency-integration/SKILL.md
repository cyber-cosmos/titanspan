---
name: dependency-integration
description: Evaluate or integrate a third-party Python package without duplicating its infrastructure or adding unjustified dependencies.
---

# Dependency integration

## When to use

Use when selecting, adding, upgrading, or wrapping a third-party package.

## References

- `AGENTS.md` and `docs/src/content/docs/development/standards.md`
- `ARCHITECTURE.md` and ADR 0010
- Official package docs, source repository, changelog, license, and advisories
- `pyproject.toml` and `uv.lock`

## Procedure

1. Confirm the capability is in scope and is not already provided by the
   standard library or an existing dependency.
2. Verify maintenance activity, license, Python range, async support,
   security status, and current API for the installed version.
3. Identify exactly what Titanspan owns: API ergonomics, configuration,
   lifecycle, contracts, testing, or cross-component behavior.
4. Keep the wrapper narrow and retain direct access to native APIs.
5. Keep optional functionality in an optional dependency group or extra when
   it is not required for core application startup.
6. Add focused adapter tests. Update dependency metadata with `uv add` or
   `uv lock`, never hand-edit generated lock content.
7. Update the ADR or docs if the choice is consequential.

## Failure modes

- Choosing a package based only on remembered APIs or popularity.
- Adding packages that lack maintenance, duplicate existing tools, conflict
  with the stack, or use an unsuitable license.
- Reimplementing the dependency's engine or concealing its ownership.
- Importing an optional integration from core package initialization.
- Editing `uv.lock` manually or selecting model/provider credentials.

## Validation

Run adapter tests, `uv sync --locked`, `make check`, `make security`, and
`make build` as applicable. Inspect the built wheel for intended runtime
contents.

## Completion criteria

Document dependency evidence and the ownership boundary. Confirm that `uv.lock`
resolves reproducibly, optional packages remain optional, and tests cover the
Titanspan contract.
