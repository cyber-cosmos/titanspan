# Titanspan runtime package

Apply root [`AGENTS.md`](../../AGENTS.md) and
[`ARCHITECTURE.md`](../../ARCHITECTURE.md), plus the instructions for the
nearest implemented module. This file governs runtime package code only.

- Follow the module responsibilities and dependency direction in
  `ARCHITECTURE.md`; do not import optional integrations into core modules.
- Keep public APIs typed, async where underlying I/O is async, explicit, and
  interoperable with the selected mature library.
- Use Titanspan domain-oriented filenames for public modules (for example,
  `container/container.py`). Document the delegated package honestly.
- Use Red-Green-Refactor for behavior changes and add unit plus real
  integration coverage for each implemented boundary. Test failure, cleanup,
  cancellation, scope isolation, and concurrency where relevant.
- Keep all declarations strictly typed and physically multi-line documented.
  Add comments for non-obvious rationale and invariants, not line-by-line
  narration.
- Preserve lifecycle, cancellation, failure cleanup, and concurrency safety.
- Do not put skills, agent settings, development scripts, credentials, or
  non-runtime assets in this package. Scoped Markdown instructions are
  development guidance and must not appear in built wheels.
- Validate with `make lint`, `make format-check`, `make python-standards`,
  `make types`, `make architecture-check`, `make coverage`, and `make check`.
  Run `make build` for packaging changes.
