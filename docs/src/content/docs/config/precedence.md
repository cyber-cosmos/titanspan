---
title: "Configuration source precedence"
---

<span id="configuration-source-precedence"></span>

For a fresh `ConfigManager` load, effective values are composed in this
order, from lowest to highest:

1. Framework defaults (`app.name` and `app.debug`).
2. Package defaults supplied to `ConfigManager`.
3. Application files under `config/`.
4. Explicit fields declared by the selected `Settings` class.
5. Explicit bootstrap overrides passed to `load(overrides=...)` or
   `Application(config=...)`.

Package defaults and application file mappings merge recursively within a
namespace. `app_name` and `debug` settings map to `app.name` and `app.debug`.
Custom settings fields map to their declared paths; nested mapping fields
update their dotted leaves so unspecified sibling values remain. Unset
settings defaults do not override application files. Later scalar and list
values replace earlier values. Bootstrap overrides are path assignments; use
dotted keys to update individual nested values without replacing an entire
namespace.

Environment values are read only where a declared source asks for them. In
Python config files, `env()` consults process variables before the selected
dotenv mapping. Typed `Settings.from_environment()` uses process variables
before its selected dotenv file. No unrelated environment variable silently
overrides an arbitrary configuration key.

A valid cache is a snapshot of already composed configuration. By default,
`load()` reads that snapshot instead of current files and environment sources.
Explicit `Settings` and `overrides` passed to the manager still apply above a
cached snapshot. Fresh `validate()` and `config:show` load current sources.
See [caching](/framework/config/caching/) for invalidation details.
