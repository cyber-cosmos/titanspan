# Typed settings

`titanspan.config.Settings` is Titanspan's settings base. Application
subclasses declare their own fields while Pydantic Settings performs
validation behind a private adapter.

```python
from titanspan.config import Settings


class WorkerSettings(Settings):
    """Define validated settings for a background worker."""

    queue_workers: int = 4
    region: str = "local"
```

The default environment prefix is `TITANSPAN_`; for example,
`TITANSPAN_QUEUE_WORKERS=8` supplies `queue_workers`. Process values take
precedence over the optional dotenv source.

```python
settings = WorkerSettings.from_environment(env_file=".env")
assert settings.queue_workers == 8
```

Validation failures become `SettingsValidationError`. Diagnostics include
field paths only, not submitted values. `redacted()` and the model's string
representations mask common secret-shaped field names.

Typed settings and repository access serve related purposes: Settings
validates declared fields, while `Repository` offers synchronous runtime
lookup. `ConfigManager` projects explicitly supplied fields into the same
configuration paths. The built-in `app_name` and `debug` fields map to
`app.name` and `app.debug`; custom fields use their declared names. Nested
mapping fields are applied as dotted leaf updates, preserving unspecified
sibling values from configuration files. Unset model defaults do not replace
file values.

Use a nested field when settings belong to an application namespace:

```python
from titanspan.config import Settings


class ServiceSettings(Settings):
    """Define settings for one application service."""

    queue: dict[str, str | int] = {"workers": 4}
```

An explicit `queue={"workers": 8}` value updates `queue.workers` while
preserving other keys loaded from `config/queue.py`.

The public settings base does not expose third-party settings source
configuration. Use its `from_environment()` method to select a dotenv file.
