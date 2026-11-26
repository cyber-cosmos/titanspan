---
title: "Temporary service overrides"
---

<span id="temporary-service-overrides"></span>

Use a synchronous override for sync-safe replacements and resource factories:

```python
with container.override({Repository: FakeRepository}):
    service = container.make(DocumentService)
    assert isinstance(service.repository, FakeRepository)
```

Use the asynchronous form when replacements need asynchronous initialization
or cleanup:

```python
async with container.override({Repository: FakeRepository}):
    service = container.make(DocumentService)
    assert isinstance(service.repository, FakeRepository)
```

The active override is stored in task-local context. Nested overrides compose
in order and restore the previous overlay on normal exit, exceptions, and
cancellation. The synchronous form composes sync backend graphs and finalizes
their resources before returning. The asynchronous form shields cleanup from
cancellation and awaits async finalizers. Replacement factories and instances
belong to the temporary graph.

Unaffected application singletons share the same canonical cache and
initialization locks as the application graph. Replacing an application
service uses an overlay-specific value and does not overwrite the application's
base binding or cache. Before borrowing a singleton, each overlay checks the
dependency graph composed by the singleton's immediate owner against
replacements introduced in that overlay. If a requested singleton
transitively depends on a service replaced by the child overlay, resolution
raises `ScopeError` instead of returning or creating an owner-cached instance
that hides the replacement. Nested overlays repeat this check at each owner
boundary, including when an outer overlay already replaced the singleton.
Replacing the singleton in the active overlay creates a value against that
overlay's own dependencies. Unaffected singletons keep their owner, identity,
and cleanup lifecycle. Use a separate container when a fresh graph must cross
multiple existing singleton boundaries.

The synchronous form rejects async-only dependencies before initializing them;
use `async with` for those replacements. Both forms reject entry while an
execution scope is active and prevent application shutdown while overrides
remain open. After application registration freezes, overrides are the
supported substitution mechanism; arbitrary live rebinding is not available.
