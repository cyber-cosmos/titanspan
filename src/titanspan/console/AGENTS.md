# Console module instructions

Follow root `AGENTS.md` and `src/titanspan/AGENTS.md`. This module owns the
`titanspan` command-line interface using Typer and Rich.

- Keep commands explicit and provide useful help and failure messages.
- Define shared command and output contracts only under
  `titanspan.contracts.console`; import the same objects from that package.
  Do not define component-local protocol duplicates.
- Register application services through `ConsoleServiceProvider` and the
  canonical `ServiceRegistry`. Let Foundation own startup and shutdown.
- Keep Typer and Rich imports inside `_backends/`. Preserve Titanspan types
  in public signatures and test APIs.
- Use `CommandRegistrar` when another component registers a command. Do not
  add a second parser or a separate command registry.
- Treat installed entry points as trusted code. Do not scan arbitrary modules.
- Do not perform destructive actions, network access, package publication, or
  implicit project modifications without an explicit user command.
- Keep CLI startup lightweight and ensure runtime templates, if introduced,
  are included in the installed distribution intentionally.
- Use test-driven changes. Test help, output, exit codes, errors, version
  metadata, module entry points, and installed-wheel commands as applicable.
- Keep declarations strictly typed and multi-line documented. Explain
  non-obvious option callback or exit behavior with implementation comments.
- Consult `ARCHITECTURE.md`, `ROADMAP.md`, and `CONTRIBUTING.md`. Run
  `make unit-test`, `make types`, `make coverage`, and `make check` for
  applicable changes.
