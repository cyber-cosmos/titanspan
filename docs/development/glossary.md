# Titanspan glossary

Use these terms consistently. Status describes the current framework; it does
not promote roadmap work to an available capability.

| Term | Definition and status |
| --- | --- |
| Adapter | Code that maps a Titanspan-owned contract to a library or external system. |
| Agent | An AI system that selects actions or tools. Titanspan's agent component is planned. |
| Application | The framework object that composes providers and owns startup and shutdown. Implemented in Foundation. |
| Awaitable | A Python object that can be used in an `await` expression. |
| Backpressure | A way to slow a producer when a consumer cannot keep up. Titanspan streaming support is planned. |
| Binding | A container registration that associates a service key with its provider and lifetime. Implemented in Container. |
| Cancellation | A request to stop asynchronous work before it finishes. APIs must propagate cancellation. |
| Checkpoint | Saved workflow state that can support later resumption. Workflow checkpointing is planned. |
| Collection | A value-oriented API for transforming and selecting items. The component is planned. |
| Container | The application service registry and dependency-resolution API. Titanspan delegates object construction to Dishka. |
| Contract | A typed boundary that defines behavior shared by a producer and its consumers. |
| Coroutine | A Python object created by calling an `async def` function. |
| Facade | A context-aware API for resolving an application-owned service. Config and Log facades are implemented. |
| Middleware | A component that wraps request processing. Titanspan HTTP middleware is planned. |
| Provider | An object that registers services or participates in application startup. Service providers are implemented. |
| Scope | A lifetime that controls where a resolved service can be reused. Container scopes are implemented with documented backend limits. |
| Singleton | A service lifetime whose instance belongs to one application container. |
| Task | A unit of asynchronous work managed by an execution runtime. |
| Tool | An operation an agent can invoke under application authorization. Titanspan's agent tool support is planned. |
| Workflow | A stateful sequence of work with transitions and possible checkpoints. Titanspan's LangGraph integration is planned. |

Use `snake_case` for Python functions, methods, and variables. Preserve the
spelling and capitalization of public identifiers exactly. Use *application*
and *container* for Titanspan components; use library names only when the
behavior belongs to that dependency.
