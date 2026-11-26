---
title: "Configuration component specification"
---

<span id="configuration-component-specification"></span>

Configuration is a synchronous, application-owned service. `Repository`
provides hierarchical reads and controlled mutation; `ConfigManager` loads
trusted sources and owns source precedence; `ConfigCache` stores only safe
validated snapshots. Public interfaces and exceptions belong to Titanspan.

## Implemented API

| API | Responsibility | Behavioral evidence |
| --- | --- | --- |
| `Repository` | Dotted-path access, typed retrieval, mutation, mapping operations, and local overrides | `tests/unit/config/test_repository.py` |
| `Settings` | Typed declaration, environment loading, native dictionary export, and secret-safe diagnostics | `tests/unit/config/test_settings.py` |
| `ConfigLoader` | Deterministic loading of trusted Python, JSON, and TOML files | `tests/unit/config/test_loader.py` |
| `ConfigManager` | Compose framework defaults, package defaults, application sources, and overrides | `tests/unit/config/test_manager.py` |
| `ConfigCache` | Versioned JSON snapshots with atomic replacement and safe loading | `tests/unit/config/test_cache.py` |
| `ConfigServiceProvider` | Register the application-owned repository with the existing container | `tests/integration/config/` |
| `Config` facade | Resolve the repository bound to the active application context | `tests/unit/config/test_facade.py` |

The existing Support environment helper remains the canonical `env` import.
Configuration code does not maintain a second environment parser.

## Behavioral guarantees

- Missing, explicit `None`, false, zero, empty strings, and empty containers
  remain distinguishable.
- Typed getters validate stored values rather than coercing arbitrary input.
- Settings export uses the Titanspan `to_dict` method; raw exports may contain
  secrets, while `redacted` provides a bounded safe diagnostic view.
- Dot-path lookup and mutation delegate to Support's canonical data helpers.
- Source precedence is deterministic and application-specific. Arbitrary
  process variables do not override configuration without an explicit map.
- Python configuration files execute trusted application code with the
  application's permissions; they are not a sandbox.
- Loading configuration does not implicitly mutate `os.environ`.
- Scoped overrides restore state after exceptions and cancellation. Base
  repository mutation is not guaranteed to be thread-safe.
- Caches reject unsupported values instead of stringifying them or using
  unsafe deserialization. Cache files may contain secrets.
- Diagnostics and CLI inspection redact sensitive values by default.

## Deferred behavior

`Repository.collection()` remains deferred. The standalone Collections API
does not add conversion behavior to the configuration repository. Do not add
duplicate engines or placeholder facade behavior.

## Verification

Unit tests live under `tests/unit/config/`; real loader, container, facade,
cache, and application behavior lives under `tests/integration/config/`.
Public examples are maintained in `docs/config/` and must match the
implemented API.
