# Configuration cache and commands

The configuration cache is an explicit snapshot for deployment or startup.
The default location is `bootstrap/cache/config.json` under the application
root. The envelope includes a schema version and Titanspan package version.

```bash
titanspan config:validate
titanspan config:show app
titanspan config:cache
titanspan config:clear
```

`config:show` and `config:validate` load current sources. `config:cache`
validates fresh sources and writes a deterministic JSON snapshot atomically.
`config:clear` removes only the configured cache file. `ConfigManager.load()`
uses a valid cache by default; pass `use_cache=False` to force fresh sources.

The cache accepts only JSON-compatible primitives, string-keyed mappings,
lists, and tuples. Classes, callables, service references, custom objects,
non-finite numbers, recursive values, and unsupported depth are rejected
with a native error. Titanspan does not stringify or execute cached values.

Cache files can contain credentials. The default cache file uses owner-only
permissions on platforms that support them. Keep the cache outside version
control and public artifacts. The cache is not encrypted. Source changes do
not invalidate an existing snapshot automatically; rebuild or clear it
explicitly. A compatible package-version check is performed before loading.

The CLI redacts common secret-shaped keys by default. Redaction is
heuristic and cannot reliably find secrets embedded in free-form strings.
