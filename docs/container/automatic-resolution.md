# Automatic dependency resolution

The container can resolve an unregistered concrete class and recursively
discover annotated concrete constructor dependencies:

```python
service = container.make(DocumentService)
```

Graph discovery inspects constructor annotations without instantiating classes.
The dependency engine validates the composed graph and constructs services.
Synchronous factories and constructors resolve immediately. If any registered
factory or resource requires asynchronous initialization, `make` raises
`AsyncResolutionRequiredError` before invoking that async factory; use
`await container.make_async(DocumentService)` instead.
Abstract classes and protocols need explicit bindings. Required primitive or
unannotated arguments are not guessed and produce a native resolution error.

Each newly requested root receives a cached graph generation. Later graphs
reuse application instances and instances explicitly resolved in the active
scope. Scope-created graphs close with their owning scope. The default bound is
128 retained graph roots; configure `max_graph_generations` for applications
with a different verified workload.

Automatic resolution is currently limited to class-valued constructor
annotations that can be resolved by Python's type-hint introspection. Contextual
values, primitive injection, and `Annotated` injection attributes remain
pending. Callable injection is available through `Container.call`; see the
[callable injection guide](injection.md). Runtime rebinding remains pending.
See the [behavior inventory](../specifications/container.md) for exact
implementation status.
