# Contracts module instructions

Follow the repository root `AGENTS.md`, `ARCHITECTURE.md`, and the native
guides under `docs/src/content/docs/contracts/` before changing public interfaces.

- Keep this package dependency-independent and limited to contracts.
- Use structural `Protocol` types by default. Use `ABC` only for a
  documented nominal or shared-behavior requirement.
- Organize shared contracts by domain under this package: `config`,
  `container`, `logging`, and `support` are established namespaces. Component
  packages may re-export the same contract object; they must not define a
  second protocol with equivalent behavior.
- Keep optional capabilities separate. Do not add contracts for unimplemented
  roadmap items or solely to mirror an external name.
- Use precise generics and standard-library types. Do not expose backend
  classes, exceptions, or runtime dependencies through public signatures.
- Document behavior, missing values, errors, lifecycle, mutation, ordering,
  task safety, and cancellation when applicable.
- Use one canonical snake_case spelling for each operation.
- Test public imports, structural and static typing, observable behavior, and
  actual framework integrations. A runtime protocol check is not behavioral
  conformance evidence.
- Start meaningful behavior changes with a failing test. Run targeted tests,
  Ruff, formatting, Pyright, architecture checks, and `make check` when
  applicable. Never weaken repository quality policies.
- Update `docs/src/content/docs/specifications/contracts.md` when native interfaces, ownership,
  or implementation status changes. Never report pending work as complete.
