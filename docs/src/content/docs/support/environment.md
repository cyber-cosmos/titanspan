---
title: "Environment utilities"
---

<span id="environment-utilities"></span>

`Env` provides access to process values, fallback adapters, and explicit edits
to existing dotenv files. Application configuration still
belongs to Pydantic Settings in `titanspan.config`; this utility does not
replace typed settings or load `.env` files during import.

## Read values

```python
from titanspan.support import Env, env

debug = Env.get("TITANSPAN_DEBUG", False)

required_mode = Env.get_or_fail("TITANSPAN_MODE")
same_mode = env("TITANSPAN_MODE")
assert required_mode == same_mode
```

The normalizer supports dotenv tokens: `true` and `(true)` become `True`;
`false` and `(false)` become `False`; `empty` becomes an empty string; and
`null` becomes `None`. A matching pair of outer quotes is removed. A lazy
default callback runs only when the variable is missing or normalizes to
`None`.

`get_or_fail` raises `RuntimeError` when the value is absent or null. Empty
strings, zero-like strings, and false remain present values.

## Adapters

The default repository reads from Python's live `os.environ` mapping. Custom
adapter factories provide fallback mappings:

```python
from titanspan.support import Env

Env.extend(lambda: {"SERVICE_REGION": "local"}, name="deployment")
assert Env.get("SERVICE_REGION") == "local"
```

The repository is cached in the active context. Adapter mappings are copied
and made read-only when the repository is created; process environment values
remain live. Re-registering a named adapter or toggling
`enable_process_environment` / `disable_process_environment` invalidates the
cached repository. Python has one standard
process environment mapping, so the environment controls determine whether
`os.environ` is consulted. They do not mutate process variables.

## Update a dotenv file

```python
from pathlib import Path

from titanspan.support import Env

Env.write_variables(
    {"APP_MODE": "local", "APP_DEBUG": True},
    Path(".env"),
)
```

Writes update existing blank assignments, preserve populated assignments by
default, and group new names after the last variable with the same prefix.
Pass `overwrite=True` to replace populated values. Existing newline style and
file permissions are retained. The write methods reject invalid variable
names, non-scalar values, non-finite numbers, NUL bytes, and multiline values
so values cannot inject additional assignments.

The serializer uses explicit scalar conversion for booleans and null:
`True` becomes `1`, while `False` and `None` become empty assignments. Strings
with special characters are quoted and escaped. File edits are explicit and
should be treated as changes to configuration data that may contain secrets.

## Python differences

- `get_repository()` returns Titanspan's small read-only repository type, not
  `python-dotenv`'s repository protocol.
- `extend()` factories return mappings of string keys to string or null values.
- `enable_process_environment()` and `disable_process_environment()` only
  control reads from
  `os.environ`; Titanspan never writes environment variables through them.
- `write_variable()` and `write_variables()` require existing files and safe
  single-line scalar assignments.

Unit tests cover parsing, fallbacks, adapter replacement, and safe file
updates. Integration tests compare environment reads with Pydantic Settings.
