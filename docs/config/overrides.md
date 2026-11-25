# Scoped configuration overrides

Use `Repository.override()` or `Config.override()` for temporary execution
context values:

```python
from titanspan.config import Repository
from titanspan.facades import Config

repository = Repository({"app": {"debug": False}})

with Config.use(repository):
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

`Config.use()` binds a repository only to the current execution context. The
application binds it around HTTP request middleware. For background or CLI
code outside that scope, bind it explicitly or inject the canonical
`ConfigRepository` contract.
