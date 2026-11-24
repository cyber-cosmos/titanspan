# Documentation instructions

Follow root `AGENTS.md` and `docs/development/standards.md`. Keep claims tied
to implementation and verified tests.

- Clearly label planned capabilities; do not describe a roadmap item as
  available.
- Verify code examples against the current package and use no nonexistent
  public APIs.
- Preserve a clear distinction between Titanspan-owned conventions and
  behavior delegated to third-party libraries.
- Update navigation in `docs/.vitepress/config.mts` when adding a guide.
- Use official sources for version-sensitive library or harness behavior.
- Run `make docs-build` after documentation or VitePress configuration
  changes. Run `make agents-check` for instruction, adapter, or skill changes.
