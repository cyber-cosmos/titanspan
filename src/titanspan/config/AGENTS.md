# Configuration module instructions

Follow root `AGENTS.md` and `src/titanspan/AGENTS.md`. This module owns the
native configuration repository, trusted source loading, typed settings,
safe cache lifecycle, and application integration.

- `Repository` is the canonical implementation of
  `titanspan.contracts.config.ConfigRepository`. Preserve that contract
  identity and keep the protocol dependency-independent.
- `ConfigServiceProvider` registers the selected repository under its base
  reader/writer contracts and only registers optional typed, scoped, macro,
  and diagnostic capabilities when they are supported. Keep the Config facade
  dependent on these protocols, never on `Repository` identity.
- `Arr` owns dot-path traversal and `Macroable` owns macro registration.
  Delegate to those canonical Support implementations.
- Pydantic Settings construction and export are isolated under `_backends/`;
  public methods and errors belong to Titanspan. `Settings` currently derives
  from a private backend base, so inherited backend methods may be visible but
  are not a supported Titanspan API. Keep all internal operations on native
  methods such as `to_dict`; the boundary audit records this remaining
  encapsulation limit. Do not expose backend validation exceptions.
- `ConfigManager` owns source precedence and cache lifecycle. `ConfigLoader`
  executes only trusted project configuration files and is not a sandbox.
- Cache only validated JSON-compatible values. Never use pickle or execute a
  generated cache file. Treat snapshots as sensitive because they may contain
  credentials.
- The active Config facade resolves `ConfigRepository` through the shared
  application context. Its explicit `use` helper is a temporary test override.
  Do not add process-global repositories or resolve async services from
  synchronous reads.

- Validate environment and file input at configuration boundaries.
- Preserve the distinction between missing values, explicit `None`, false,
  zero, empty strings, and empty containers.
- Keep reads synchronous and inexpensive. Configuration mutation is intended
  for startup; simultaneous base-repository mutation is not thread-safe.
- Restore context-local overrides on errors and cancellation. Child tasks
  inherit the context captured when they are created.
- Keep secrets out of defaults, logs, exceptions, and examples. Never commit
  real credentials.
- Prefer explicit, typed settings and documented precedence. Avoid hidden
  process-global mutation and import-time environment reads.
- Use test-driven changes; cover valid and invalid values, defaults,
  precedence, cache safety, override isolation, boundary inputs, and
  secret-safe errors. Exercise file loading and Dishka integration with real
  temporary files and the actual container.
- Annotate every declaration and use a multi-line Google-style docstring.
  Comments should explain validation or precedence decisions that are not
  evident from Pydantic's field declarations.
- Consult `ARCHITECTURE.md`, ADRs 0003, 0009, 0010, and 0013, and
  `docs/specifications/config.md`. Run focused config tests, then
  `make lint`, `make format-check`, `make types`, `make coverage`, and
  `make check` for applicable changes.
