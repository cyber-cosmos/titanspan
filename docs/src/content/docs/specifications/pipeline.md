---
title: "Pipeline behavioral specification"
---

# Pipeline behavioral specification

This specification describes verified behavior in `titanspan.pipeline`.
The API uses ordinary Python callables and the native Container. Pipeline
does not implement a scheduler, workflow engine, stream engine, or concurrency
component.

## Capability inventory

| Capability | Public API | Evidence |
| --- | --- | --- |
| Ordered sync transforms | `Pipeline.pipe`, `through` | `tests/unit/pipeline/test_pipeline.py` |
| Async transforms | `pipe_async`, `then_return_async` | `tests/unit/pipeline/test_pipeline.py` |
| Callable, class, and method stages | `through`, `stage_method` | `tests/unit/pipeline/test_pipeline.py` |
| Container-resolved stages | Optional `container` | `tests/integration/pipeline/test_pipeline_application.py` |
| Continuations and short-circuiting | `middleware`, `middleware_async` | Pipeline unit tests |
| Conditional and immutable builders | `when`, `send`, `through` | Pipeline unit tests |
| Destinations and direct results | `then`, `then_async`, `then_return` | Pipeline unit tests |
| Cancellation and cleanup | Explicit async execution | Pipeline cancellation tests |

## Stage execution

Stages execute in insertion order. `pipe()` and `pipe_async()` each append
one typed transform. `through()` snapshots an iterable of heterogeneous
runtime stages; callers can declare `Pipeline[Input, Output]` when its list
changes the final type. The `pipeline(value)` helper starts a typed
value-preserving builder.

Functions, callable instances, classes exposing `handle(value)`, and
`StageMethod` selectors are supported. A supplied Container constructs class
stages through its native sync or async resolution APIs. Without a Container,
the stage class must support zero-argument construction. Resolved class
stages are not cached by Pipeline.

Continuation middleware receives the current value and a callback for later
stages. It may call the callback with a transformed value, return the
downstream result after inspecting it, or return early to short-circuit. Sync
and async continuation wrappers are explicit and cannot be mixed implicitly.

## Sync, async, and failure behavior

`then()`, `then_return()`, and `pipe()` are synchronous and do not create or
block an event loop. If a synchronous stage or destination returns an
awaitable, Pipeline closes coroutine results and raises
`PipelineExecutionError`. Use `pipe_async()`, `then_async()`, or
`then_return_async()` for explicit asynchronous work. The async path awaits
each stage sequentially and does not detach work.

Application exceptions propagate unchanged. Cancellation propagates through
the active async stage. Pipeline has no task group and cannot close resources
hidden inside caller callbacks; the stage or its Container owns those
resources. Container-resolved instances follow their registered Container
lifetime.

## Middleware and orchestration boundaries

HTTP and Routing middleware own ASGI request/response lifetime, dependency
scope, streaming delivery, and disconnect cleanup. Those middleware stacks do
not reuse Pipeline because their lifecycle contract is broader than one value
continuation. Route-specific middleware remains owned by Routing.

AI clients, workflow state, retries, and external side effects remain owned
by their respective application components. Pipeline can sequence ordinary
stages around those integrations without providing their execution engines.
