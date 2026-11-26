# Support module instructions

Follow the root `AGENTS.md`, `ARCHITECTURE.md`, and
`docs/development/standards.md`.

- Keep Support independent of optional database, queue, AI, and web
  integrations.
- Follow the native Support specification and established behavior tests.
- Use one idiomatic Python spelling per public operation. Do not add
  duplicate aliases or forwarding wrappers.
- Preserve Python mapping, sequence, missing-value, mutation, and cancellation
  semantics. Document intentional Titanspan-specific behavior.
- Delegate canonical collection, application lifecycle, container, config,
  facade, and testing behavior to their owning Titanspan modules.
- Do not add dynamic attribute dispatch to imitate another language's magic
  methods. Use typed explicit APIs and narrow adapters.
- Keep macros class-scoped, isolated, thread-safe, and test-resettable.
- Never run synchronous callbacks that return awaitables without an explicit
  asynchronous API.
- Test input boundaries, mutation, error behavior, and resource cleanup for
  each changed public API.
- Validate with `make lint`, `make format-check`, `make types`,
  `make python-standards`, and relevant unit and integration tests.
