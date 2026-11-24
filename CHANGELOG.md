# Changelog

Notable changes to Titanspan are recorded here. The project has not made a
public release.

## Unreleased

- Established the installable package, CLI, FastAPI application lifecycle,
  Dishka dependency integration, and typed settings.
- Added explicit synchronous and AnyIO-based asynchronous Support sleep
  builders with context-local fakes and upstream-compatible assertions.
- Added Laravel-compatible environment value parsing, scoped mapping adapters,
  and validated dotenv file updates.
- Added synchronous and AnyIO-based asynchronous retry helpers backed by
  Tenacity.
- Added locale-aware numeric formatting, parsing, spelling, summaries, and
  context-local locale and currency scopes through the optional `numbers`
  extra.
- Added UUID and ULID binary codecs with typed custom codec registration and
  Python byte interoperability.
- Added initial tests, architecture decisions, contributor documentation, and
  repository automation.
