---
title: "Testing configuration"
---

<span id="testing-configuration"></span>

Test the repository directly for isolated behavior, then use real temporary
files and the application container for integration behavior.

```python
from titanspan import Application
from titanspan.config import Repository
from titanspan.facades import Config

application = Application()
repository = Repository({"app": {"debug": False}})

with application.context():
    with Config.use(repository):
        assert Config.boolean("app.debug") is False
```

`Config.use()` replaces the repository through the active application's
Container. It requires an application context and follows Container override
rules. The replacement object remains caller-owned. Use `Config.override()`
for task-local values and verify restoration after exceptions.

Use `ConfigManager` with a temporary root for file discovery, dotenv
precedence, package defaults, and cache tests. Avoid the developer's real
environment files by supplying isolated paths and controlling process
environment variables with the test framework.

The real FastAPI and Dishka integration test verifies that dependency
injection, HTTP request facade access, and application state share one
repository instance. Run focused checks with:

```bash
uv run --locked pytest tests/unit/config -q
uv run --locked pytest tests/integration/config -q
```

The component does not provide a separate testing framework or config fake.
Use the native Repository instance as a deterministic test value.
