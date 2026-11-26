---
title: "Package defaults"
---

<span id="package-defaults"></span>

Framework packages can contribute defaults through the `package_defaults`
argument to `ConfigManager`. Each top-level key is a configuration namespace
and each value is a mapping:

```python
from pathlib import Path

from titanspan.config import ConfigManager

manager = ConfigManager(
    Path.cwd(),
    package_defaults={
        "queue": {"workers": 2, "timeout_seconds": 30},
    },
)
repository = manager.load()
```

The namespace and nested values are defaults, so trusted application files
can override them. Defaults registered for the same namespace merge in the
order supplied. Mapping values merge recursively; lists and scalars replace
the previous value.

The current application composition root does not yet expose a general
third-party package provider lifecycle for configuration defaults. Packages
that need to contribute settings can compose a `ConfigManager` explicitly.
There is no configuration publishing command, and Titanspan never writes
over application-authored config files.
