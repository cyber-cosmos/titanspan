---
title: "Environment values"
---

<span id="environment-values"></span>

Use `titanspan.support.env()` inside trusted Python configuration files or
the canonical `Env` utility for explicit environment access.

```python
from titanspan.support import env

config = {
    "name": env("APP_NAME", "Titanspan"),
    "debug": env("APP_DEBUG", False),
}
```

Process environment values take precedence over the selected dotenv mapping.
The loader parses dotenv data through `python-dotenv` without writing values
to `os.environ`. An arbitrary environment variable has no effect on
configuration unless a configuration file or typed settings field maps it.

The `env()` helper follows the Support environment normalization rules:

| Text value | Result |
| --- | --- |
| `true`, `(true)` | `True` |
| `false`, `(false)` | `False` |
| `empty`, `(empty)` | Empty string |
| `null`, `(null)` | `None`, which selects the supplied default |
| Other text | String, with balanced surrounding quotes removed |

Numeric-looking strings remain strings. Use a typed Settings field when
schema-driven conversion and validation are required.

`ConfigManager` and `ConfigLoader` accept an explicit `environment_file`
inside the application root. Only one file is selected; automatic
`.env.<environment>` discovery is not implemented. Symlink dotenv files and
paths outside the application root are rejected.

For direct settings construction, use
`Settings.from_environment(env_file=path)`. Process variables override
dotenv values. Neither API creates a hidden global environment repository.
