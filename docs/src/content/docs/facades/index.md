---
title: "Application facades"
---

<span id="application-facades"></span>

Facades provide typed access to application services from application code.
They resolve the active application's canonical service through its Container.
Use dependency injection inside reusable services and controllers. Use facades
at application entry points where they improve clarity.

## Available facades

Titanspan provides `Config`, `Log`, `Http`, `Route`, and `Event`. Each facade
declares its native contract and exposes explicit methods. Facades do not
forward unknown attributes dynamically and do not keep service instances in
process-global caches.

```python
from titanspan import Application
from titanspan.facades import Config, Log

application = Application(config={"app": {"name": "Example"}})

with application.context():
    assert Config.string("app.name") == "Example"
    Log.info("Application ready")
```

Application execution establishes this context through Foundation. A facade
call outside an active application context raises a native context error.

## Temporary service replacement

Use `Facade.use()` to replace one facade contract for the current execution
context:

```python
from titanspan import Application
from titanspan.config import Repository
from titanspan.contracts.config import ConfigRepository
from titanspan.facades import Config

application = Application()
replacement = Repository({"app": {"name": "Test"}})

with application.context(), Config.use(replacement):
    assert application.make(ConfigRepository) is replacement
    assert Config.get("app.name") == "Test"
```

The replacement applies to direct resolution and facade calls. Nested scopes
restore their parent service. Exceptions and cancellation also restore the
prior Container graph. The caller owns the replacement instance.

Replacements follow Container safety rules. Enter them before execution
scopes. The Container rejects a replacement when a cached singleton already
captures the replaced dependency. Use the Container's documented override
behavior for additional replacement types.

## Component fakes

Component test helpers retain their component-specific behavior. `Log.fake()`
replaces the logging manager through the Container and records calls in a
bounded memory sink. A logger injected from the Container observes the same
fake manager. `Http.fake()` selects a local fake transport for outgoing
requests. `Event.fake()` uses the active application's dispatcher.

Use the relevant component guide for fake setup, assertions, and lifecycle.
Do not use facade replacement as a production service registry.

## API reference

See the [Facade behavioral specification](/titanspan/specifications/facades/)
for supported methods, ownership rules, failure behavior, and test evidence.
