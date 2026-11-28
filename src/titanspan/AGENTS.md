# Titanspan runtime package

Apply root [`AGENTS.md`](../../AGENTS.md) and
[`ARCHITECTURE.md`](../../ARCHITECTURE.md), plus the instructions for the
nearest implemented module. This file governs runtime package code only.

- Follow the module responsibilities and dependency direction in
  `ARCHITECTURE.md`; do not import optional external integrations into core
  modules. Database is a built-in component, and Foundation wires its native
  provider through the application composition root.
- Keep public APIs typed and explicit. Use synchronous interfaces for pure
  construction and in-memory work; use explicit async interfaces where
  underlying I/O or resource initialization is asynchronous.
- Use Titanspan domain-oriented filenames for public modules (for example,
  `container/container.py`). Document the delegated package honestly.
- Use Red-Green-Refactor for behavior changes and add unit plus real
  integration coverage for each implemented boundary. Test failure, cleanup,
  cancellation, scope isolation, and concurrency where relevant.
- Keep all declarations strictly typed and physically multi-line documented.
  Add comments for non-obvious rationale and invariants, not line-by-line
  narration.
- Follow the root technical writing standard for docstrings and comments.
  Preserve exact identifiers and keep comments concise and factual.
- Preserve lifecycle, cancellation, failure cleanup, and concurrency safety.
- A component is complete only when it satisfies its canonical contracts,
  participates in the owning application lifecycle, and has real cross-module
  integration tests for implemented dependencies. Record unavailable
  dependencies as blockers; do not simulate them with disconnected types.
- Do not put skills, agent settings, development scripts, credentials, or
  non-runtime assets in this package. Scoped Markdown instructions are
  development guidance and must not appear in built wheels.
- Validate with `make lint`, `make format-check`, `make python-standards`,
  `make types`, `make architecture-check`, `make coverage`, and `make check`.
  Run `make build` for packaging changes.
