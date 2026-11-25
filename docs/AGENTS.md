# Documentation instructions

Follow root `AGENTS.md` and `docs/development/standards.md`. Keep claims tied
to implementation and verified tests.

- Clearly label planned capabilities; do not describe a roadmap item as
  available.
- Verify code examples against the current package and use no nonexistent
  public APIs.
- Preserve a clear distinction between Titanspan-owned conventions and
  behavior delegated to third-party libraries.
- Update `docs/.vitepress/config.mts` whenever a published page is added,
  renamed, or removed. Keep every published Markdown page in the sidebar,
  verify all navigation links, and avoid duplicate sidebar destinations.
- Run `npm --prefix docs run docs:check-navigation` when editing pages or
  navigation. `docs:build` runs this check before VitePress.
- Use official sources for version-sensitive library or harness behavior.
- Keep examples tested against existing APIs, and make Python examples meet
  strict typing, 80-column, multiline-docstring, and comment standards.
- Document a behavior as available only when implemented and tested. Never
  invent results, external API details, or performance evidence.
- Run `make docs-build` after documentation or VitePress configuration
  changes. Run `make agents-check` for instruction, adapter, or skill changes.
