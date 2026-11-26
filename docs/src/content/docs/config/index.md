---
title: "Configuration"
---

<span id="configuration"></span>

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

The current component is early-stage. `Repository.collection()` is not
available. The standalone Collections API does not define how a configuration
repository should convert stored values. Configuration mutation is intended
for bootstrap; simultaneous mutation of one repository is not guaranteed to
be thread-safe.

## Guides

- [Repository and retrieval](/titanspan/config/repository/)
- [Environment values](/titanspan/config/environment/)
- [Configuration files](/titanspan/config/configuration-files/)
- [Typed settings](/titanspan/config/typed-settings/)
- [Source precedence](/titanspan/config/precedence/)
- [Package defaults](/titanspan/config/package-defaults/)
- [Configuration cache and commands](/titanspan/config/caching/)
- [Scoped overrides](/titanspan/config/overrides/)
- [Testing](/titanspan/config/testing/)
- [Security](/titanspan/config/security/)
- [Native configuration specification](/titanspan/specifications/config/)
