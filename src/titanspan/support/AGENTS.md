# Support module instructions

Follow the root `AGENTS.md`, `ARCHITECTURE.md`, and
`docs/development/standards.md`.

- Keep Support independent of optional database, queue, AI, and web
  integrations.
- Use the pinned [Laravel Support compatibility inventory] for API status;
  do not infer parity from matching names.
- Keep Laravel camelCase aliases explicit and colocated with their Python
  snake_case implementations. Keep keyword-safe names such as `except_` and
  `from_` explicit.
- Preserve Python mapping, sequence, missing-value, mutation, and cancellation
  semantics. Document each intentional difference.
- Delegate canonical collection, application lifecycle, container, config,
  facade, and testing behavior to their owning Titanspan modules.
- Do not add dynamic attribute dispatch to imitate PHP magic methods. Use
  typed explicit APIs and narrow adapters.
- Keep macros class-scoped, isolated, thread-safe, and test-resettable.
- Never run synchronous callbacks that return awaitables without an explicit
  async API.
- Test input boundaries, mutation, error behavior, aliases, and resource
  cleanup for each changed public API.
- Validate with `make lint`, `make format-check`, `make types`,
  `make python-standards`, and relevant unit and integration tests.

[Laravel Support compatibility inventory]:
  ../../../docs/compatibility/laravel-support.md
