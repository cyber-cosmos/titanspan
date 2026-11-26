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

Use `settings.to_dict()` to export values to framework code. It includes
declaration defaults by default; `to_dict(include_defaults=False)` exports
only fields supplied by the selected environment or explicit constructor.
This mapping contains actual values, including secrets, and must not be logged
or exposed in diagnostics. Use `redacted()` for diagnostic output.

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

Use `from_environment()` to select a dotenv file rather than configuring
backend-specific sources. Inherited validation-library methods may remain
visible because the current native settings base subclasses its validation
backend; those inherited methods are outside Titanspan's documented settings
API. See the [backend boundary audit](/specifications/backend-boundaries).
