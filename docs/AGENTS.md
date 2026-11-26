# Documentation instructions

Follow root `AGENTS.md` and `docs/src/content/docs/development/standards.md`. Keep claims tied
to implementation and verified tests.

Follow the [writing standard](src/content/docs/development/writing-standards.md)
and use the [glossary](src/content/docs/development/glossary.md) for canonical
terms. Keep examples direct and preserve exact API names.

- Clearly label planned capabilities; do not describe a roadmap item as
  available.
- Verify code examples against the current package and use no nonexistent
  public APIs.
- Preserve a clear distinction between Titanspan-owned conventions and
  behavior delegated to third-party libraries.
- Store published pages under `docs/src/content/docs/`. Update
  `docs/navigation.mjs` when navigation changes. Keep every published page in
  the sidebar, verify all links, and avoid duplicate destinations.
- Run `npm --prefix docs run docs:check-navigation` when editing pages or
  navigation. `docs:build` runs this check before Starlight.
- Use official sources for version-sensitive library or harness behavior.
- Keep examples tested against existing APIs, and make Python examples meet
  strict typing, 80-column, multiline-docstring, and comment standards.
- Document a behavior as available only when implemented and tested. Never
  invent results, external API details, or performance evidence.
- Run `make docs-build` after documentation or Astro configuration changes.
  Run `make docs-test` to verify rendered pages in Playwright. Run
  `make agents-check` for instruction, adapter, or skill changes.
- Run `make prose-check`, `make terminology-check`, and `make prose-test`
  after changing documentation.
