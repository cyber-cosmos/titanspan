# Configuration

Titanspan's configuration component provides a mutable, typed repository,
trusted application file loading, validated settings, execution-local
overrides, and a safe JSON cache. It uses Pydantic Settings and
`python-dotenv` internally while keeping its application API native.

```python
from titanspan.config import Repository

config = Repository({"app": {"name": "Titanspan", "debug": False}})

assert config.string("app.name") == "Titanspan"
assert config.boolean("app.debug") is False
```

The current component is early-stage. `collection()` is not available because
the canonical Collections component has not been implemented. Configuration
mutation is intended for bootstrap; simultaneous mutation of one repository
is not guaranteed to be thread-safe.

## Guides

- [Repository and retrieval](./repository)
- [Environment values](./environment)
- [Configuration files](./configuration-files)
- [Typed settings](./typed-settings)
- [Source precedence](./precedence)
- [Package defaults](./package-defaults)
- [Configuration cache and commands](./caching)
- [Scoped overrides](./overrides)
- [Testing](./testing)
- [Security](./security)
- [Native configuration specification](/specifications/config)
