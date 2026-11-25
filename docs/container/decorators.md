# Class lifetime declarations

The container provides decorators for declaring a class's cache lifetime.
They preserve the original class object and attach metadata for a container to
read while composing a dependency graph. They do not register services in a
global registry.

```python
from titanspan.container import singleton


@singleton
class ApplicationRegistry:
    """Hold registry data for one application instance.
    """
```

`singleton` means one instance per `Container`. Separate application
containers resolve independent values. As with explicit registrations,
application-owned resources are closed when the owning container closes.

Use `scoped` for a value owned by an active execution scope:

```python
from titanspan.container import Scope, scoped


@scoped(Scope.NODE)
class NodeContext:
    """Hold mutable context for one workflow node execution.
    """
```

Resolution must occur while the declared scope is active. The selected scope
maps to the dependency engine's supported ordered lifecycle levels. Scope
names at the same level are equivalent and cannot be nested within one
another. See [execution scopes](scopes.md) for the current mapping.

Explicit container registrations override class declarations. This keeps a
class's preferred default separable from test, application, or integration
configuration. Calling `container.scoped(Service, scope=...)` is also
available when lifetime metadata should remain outside the service class.

These decorators only express lifetime metadata. They do not declare contract
implementations, application bindings, contextual dependencies, or factories.
