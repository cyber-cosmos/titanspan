# Contracts module instructions

Follow the repository root `AGENTS.md`, `ARCHITECTURE.md`, and the Contracts
guides under `docs/contracts/` before changing public interfaces.

- Keep this package dependency-independent and limited to contracts.
- Use structural `Protocol` types by default. Use `ABC` only for a documented
  nominal or shared-behavior requirement.
- Preserve canonical contract identity. Logging protocols remain owned by
  `titanspan.logging.contracts`; Support protocols already defined in
  `titanspan.contracts` must be re-exported, not redeclared.
- Keep optional capabilities separate. Do not add a contract only to mirror
  an upstream name or an unimplemented roadmap item.
- Use precise generics and standard-library types. Do not expose backend
  classes, exceptions, or runtime dependencies through public signatures.
- Document behavior, missing values, errors, lifecycle, mutation, ordering,
  task safety, and cancellation when applicable.
- Keep Laravel camelCase compatibility in separate explicit protocols or
  adapters; Python spellings remain canonical.
- Test public imports, structural and static typing, protocol behavior, and
  actual framework integrations. A runtime protocol check is not behavioral
  conformance evidence.
- Start meaningful behavior changes with a failing test. Run targeted tests,
  Ruff, formatting, Pyright, architecture checks, and `make check` when
  applicable. Never weaken repository quality policies.
- Update `docs/compatibility/laravel-contracts.md` when upstream mapping or
  parity evidence changes. Never report pending or blocked work as complete.
