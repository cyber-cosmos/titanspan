---
title: "ADR 0013: Native configuration repository and safe snapshots"
---

<span id="adr-0013-native-configuration-repository-and-safe-snapshots"></span>

- Status: Accepted
- Date: 2026-11-25

## Context

Applications need a cohesive way to discover configuration, validate typed
settings, read dotted paths, scope test overrides, and reuse precomputed
configuration in deployments. Titanspan needs an application-owned API that
does not expose third-party settings types. Python configuration files are
executable code, and cached settings may contain secrets.

## Decision

Titanspan owns a mutable `config.Repository` that implements the canonical
`contracts.ConfigRepository` protocol. It delegates nested paths to Support's
`Arr` and macro behavior to Support's `Macroable`. `ConfigManager` composes
framework and package defaults, trusted application files, declared Settings,
and final bootstrap overrides. File discovery supports trusted Python,
JSON, and TOML files under the application root.

Pydantic Settings validates declared environment-backed fields through a
private adapter. `python-dotenv` parses selected dotenv files. Process values
take precedence and loading never mutates `os.environ`. A context-bound
`Config` facade and the existing Dishka container refer to the same
application repository.

Configuration caches use a versioned JSON envelope with atomic replacement
and owner-only file permissions where supported. Unsupported Python objects
are rejected. Cache loading never executes source or deserializes arbitrary
objects. Cache files remain sensitive, unencrypted artifacts.

## Alternatives considered

- Expose Pydantic Settings types and source configuration: rejected because
  backend-specific settings APIs would become part of the Titanspan surface.
- Load arbitrary Python paths as a sandbox: rejected because Python modules
  execute with the application's permissions.
- Use pickle or generated Python for caching: rejected because loading would
  execute code or deserialize arbitrary objects.
- Maintain a process-global Config facade store: rejected because it would
  leak state across applications and concurrent execution contexts.
- Duplicate nested path and macro utilities: rejected in favor of the
  canonical Support implementations.

## Consequences

- Configuration reads remain synchronous and lightweight.
- `Settings` methods documented by Titanspan remain the supported API. Its
  current private validation base still makes inherited backend methods
  visible; the boundary and a possible composition-based follow-up are
  recorded in `docs/specifications/backend-boundaries.md`.
- Application files are trusted code; callers must keep the config root
  trusted.
- Source precedence is explicit and tested. Unmapped process variables do not
  silently change configuration.
- `Repository.collection()` remains deferred. A standalone Collections API is
  available, but the configuration repository does not provide implicit
  conversion.
- Runtime base-repository mutation is not guaranteed to be thread-safe;
  context-local overrides do not mutate the base repository.
- Cache changes require explicit rebuild or clear; source file changes are
  not watched.

## References

- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Python `contextvars`](https://docs.python.org/3/library/contextvars.html)
