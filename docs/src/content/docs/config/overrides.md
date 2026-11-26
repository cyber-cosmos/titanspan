---
title: "Scoped configuration overrides"
---

<span id="scoped-configuration-overrides"></span>

Use `Repository.override()` or `Config.override()` for temporary execution
context values:

```python
from titanspan import Application
from titanspan.config import Repository
from titanspan.facades import Config

application = Application(config={"app": {"debug": False}})
repository = Repository({"app": {"debug": False}})

with application.context(), Config.use(repository):
    with Config.override({"app.debug": True}):
        assert Config.boolean("app.debug") is True
    assert Config.boolean("app.debug") is False
```

Overrides are stored in a `ContextVar` and restored after normal return,
exceptions, and asynchronous cancellation. Nested scopes apply in order.
Child tasks inherit the context captured when each task is created; changes
made later in one task do not mutate another task's context.

Built-in mappings and lists are copied when an override is registered and
when an effective snapshot is created. Custom leaf objects retain identity.
The base repository is not mutated. These scopes do not make simultaneous
mutation of the base repository thread-safe.

`Config.use()` temporarily substitutes the repository contract through the
application Container. The application context must be active. Normal
application work uses the registered repository without an extra binding.
Background and CLI execution must establish the application context or inject
the canonical `ConfigRepository` contract.
