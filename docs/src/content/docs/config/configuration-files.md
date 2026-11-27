---
title: "Configuration files"
---

<span id="configuration-files"></span>

`ConfigLoader` discovers files in `<application-root>/config`. A file's
identifier-safe filename stem becomes its configuration namespace. The
supported formats are Python (`.py`), JSON (`.json`), and TOML (`.toml`).
Files load in alphabetical order, and duplicate namespace stems are rejected.

Python files must export a mapping named `config`:

```python
from titanspan.support import env

config = {
    "name": env("APP_NAME", "Titanspan"),
    "debug": env("APP_DEBUG", False),
}
```

JSON and TOML files contain the namespace mapping directly. Nested mapping
values from framework defaults, package defaults, and application files are
recursively merged; non-mapping values, including lists, are replaced by
the higher-priority value.

```python
from pathlib import Path

from titanspan.config import ConfigManager

manager = ConfigManager(Path.cwd())
repository = manager.load()
```

Python configuration executes application code and is not a sandbox. Only
load trusted files that belong to the application. The loader checks path
containment and rejects symlinks that escape the trusted configuration
directory. It does not load uploaded or user-selected files.

See [source precedence](/framework/config/precedence/) for how package defaults, settings,
environment values, and bootstrap overrides interact.
