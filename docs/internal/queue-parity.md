# Queue and Bus capability comparison

This internal matrix uses Laravel framework revision
`321caf77d6c037577434e177c3bf280abb2b3513` as the reference snapshot. It
records behavior for review; it does not define Titanspan's public API.

Sources:

- Laravel 13 Queue guide: <https://laravel.com/docs/13.x/queues>
- Laravel 13 Queue API: <https://api.laravel.com/docs/13.x/Illuminate/Queue.html>
- Laravel 13 Bus API: <https://api.laravel.com/docs/13.x/Illuminate/Bus.html>
- Framework source: <https://github.com/laravel/framework/tree/321caf77d6c037577434e177c3bf280abb2b3513/src/Illuminate/Queue>
- Bus source: <https://github.com/laravel/framework/tree/321caf77d6c037577434e177c3bf280abb2b3513/src/Illuminate/Bus>
- Queue tests: <https://github.com/laravel/framework/tree/321caf77d6c037577434e177c3bf280abb2b3513/tests/Queue>
- Bus tests: <https://github.com/laravel/framework/tree/321caf77d6c037577434e177c3bf280abb2b3513/tests/Bus>

The selected revision is the exact upstream snapshot reviewed for this
implementation. The matrix summarizes behavior and does not reproduce source
or prose.

## Status meanings

- **Equivalent**: behavior is implemented and verified for the same purpose.
- **Equivalent with Python-native syntax**: behavior uses native Python APIs.
- **Enhanced for asynchronous execution**: Titanspan makes async boundaries,
  cancellation, or scopes explicit.
- **Backend-dependent**: support depends on a configured Taskiq backend.
- **Dependent on another unfinished Titanspan component**: required native
  persistence or transaction ownership is not yet available.
- **Intentionally different for correctness or security**: Titanspan rejects
  unsafe or ambiguous behavior.
- **Unsupported with a technical justification**: not implemented because a
  required backend or ownership guarantee is absent.

## Job declaration and serialization

| Reference capability | Titanspan status | Evidence and difference |
| --- | --- | --- |
| Class jobs with handler methods | Equivalent with Python-native syntax | Typed dataclass or Pydantic job with `handle()`. |
| Injected handler services | Enhanced for asynchronous execution | Existing Container resolves dependencies inside one `JOB` scope. |
| Stable job identifiers | Equivalent with Python-native syntax | Explicit `job_name` or trusted registered class name. |
| Queue and connection selection | Equivalent with Python-native syntax | Class attributes, dispatch arguments, and fluent pending builder. |
| Attempts and backoff | Backend-dependent | Taskiq retry middleware; delayed backoff needs a scheduler. |
| Timeouts | Intentionally different for correctness or security | Async handlers can time out. Arbitrary sync thread code cannot be safely interrupted. |
| Payload serialization | Intentionally different for correctness or security | Bounded, versioned JSON; no arbitrary object or executable deserialization. |
| Model payload serialization | Unsupported with a technical justification | Persistence and rehydration contracts are not available. Pass identifiers and rehydrate through application services. |
| Job discovery | Intentionally different for correctness or security | Explicit trusted classes prevent untrusted module imports. |

## Dispatch and job lifecycle

| Reference capability | Titanspan status | Evidence and difference |
| --- | --- | --- |
| Dispatch an object | Equivalent with Python-native syntax | `Queue.dispatch_async()` or explicit pending builder. |
| Synchronous dispatch | Intentionally different for correctness or security | `dispatch_sync()` rejects active event-loop and incompatible scopes. |
| Delayed dispatch | Backend-dependent | Redis Taskiq schedule source; sync rejects delays; RabbitMQ adapter has no source. |
| After-commit dispatch | Dependent on another unfinished Titanspan component | Requires canonical Database transaction outcomes and nested transaction semantics. |
| After-response dispatch | Unsupported with a technical justification | Queue does not own HTTP response completion or a safe detached-task lifecycle. |
| Bulk dispatch | Unsupported with a technical justification | No backend-independent atomic bulk publication contract is implemented. |
| Conditional dispatch | Equivalent with Python-native syntax | Application code can conditionally call the explicit dispatcher; fluent helpers are absent. |
| Retry after exceptions | Backend-dependent | Taskiq `SmartRetryMiddleware` owns retry accounting and rescheduling. |
| Release or delete during handling | Unsupported with a technical justification | No public attempt-control contract exists. Raising a failure is handled by Taskiq retry policy. |
| Failure callbacks | Unsupported with a technical justification | Durable callback identity and retry semantics are not implemented. |
| Failed-job records and replay | Dependent on another unfinished Titanspan component | Requires persistent repository and safe operator commands. |
| Unique jobs | Unsupported with a technical justification | A verified distributed lease contract is not available. |
| Exactly-once processing | Intentionally different for correctness or security | Queue makes no exactly-once claim; external side effects can repeat. |

## Middleware and worker behavior

| Reference capability | Titanspan status | Evidence and difference |
| --- | --- | --- |
| Custom job middleware | Equivalent with Python-native syntax | Typed sync/async middleware through native Pipeline and Container. |
| Built-in overlap, rate, and exception middleware | Unsupported with a technical justification | No verified distributed coordination semantics are attached to Queue. |
| Per-job execution context | Enhanced for asynchronous execution | New Container `JOB` scope and immutable `JobContext` per attempt. |
| Bounded worker concurrency | Backend-dependent | Taskiq concurrency and prefetch are configured; a real Redis test verifies overlapping jobs use isolated `JOB` dependencies. |
| Graceful worker cancellation | Enhanced for asynchronous execution | AnyIO cancellation and Foundation cleanup; sync thread work cannot be forcibly stopped. |
| Worker process supervision | Unsupported with a technical justification | Use an external process manager; Queue does not replace operating-system supervision. |
| Restart, stop-when-empty, memory limits | Unsupported with a technical justification | No worker supervisor or reliable cross-process control plane is included. |
| Worker and job events | Equivalent with Python-native syntax | Metadata lifecycle events include accepted retries; release events remain pending. Payloads and exception messages stay private. |
| Queued event listeners | Dependent on another unfinished Titanspan component | Needs registered listener identity and safe event payload serialization. |

## Bus chains and batches

| Reference capability | Titanspan status | Evidence and difference |
| --- | --- | --- |
| Ordered job chain | Backend-dependent | Inline and Redis continuation tested; publication after success is non-atomic. |
| Chain-wide queue/connection and per-job overrides | Equivalent with Python-native syntax | Builder values provide defaults; job declarations override them. Inline and Redis tests verify selected destinations. |
| Prepending and appending pending jobs | Equivalent with Python-native syntax | Chain builders validate registered jobs before dispatch. |
| Chain callbacks and dynamic edits | Unsupported with a technical justification | Durable callback registration and edit coordination are absent. |
| Batch identifier and counters | Equivalent with Python-native syntax | In-process `BatchSnapshot` for sync execution and fake recording. |
| Batch failure tolerance | Equivalent with Python-native syntax | Local inline batch can continue after failure. |
| Distributed batches | Dependent on another unfinished Titanspan component | Require persistent atomic counters and concurrent completion ownership. |
| Batch callbacks, cancellation, retry, pruning | Dependent on another unfinished Titanspan component | Require durable callback identities and repository lifecycle. |

## Drivers, operations, and tooling

| Reference capability | Titanspan status | Evidence and difference |
| --- | --- | --- |
| Inline synchronous driver | Equivalent | Implemented and exercised through Foundation. |
| Redis queue | Backend-dependent | Redis Streams adapter and mandatory real Redis test path. Crash redelivery still needs evidence. |
| RabbitMQ queue | Backend-dependent | Optional Taskiq adapter exists; live integration remains pending. |
| SQS queue | Unsupported with a technical justification | No supported, stable Taskiq integration is selected. |
| Null driver | Equivalent with Python-native syntax | Explicit `discarded` receipt. |
| Results | Backend-dependent | Redis exposes bounded JSON results with finite retention; other built-in drivers do not provide result handles. |
| Queue size, priority, monitoring | Backend-dependent | No stable cross-backend contract is exposed. |
| Failed and batch administration | Dependent on another unfinished Titanspan component | Requires persistent queue records and destructive-scope policy. |
| Console worker and generation commands | Equivalent with Python-native syntax | `queue:work`, `queue:listen`, `make:job`, `make:job-middleware`. |
| Queue fake and dispatch assertions | Equivalent with Python-native syntax | Execution-local fake records facade and manager calls, runs recorded jobs through native job scopes, and asserts failure types. |
| Database queue driver and queue tables | Dependent on another unfinished Titanspan component | Deferred to native Database persistence and migration contracts. |

## Review conclusion

The current implementation covers typed job declaration, safe dispatch,
Container-backed execution, sync and async middleware, Redis worker execution,
retry, chains, fakes, and a local batch subset. It does not yet match the
reference's durable failed-job, uniqueness, worker-control, callback, or
distributed-batch behavior. Those gaps are explicit and must not be described
as available capabilities.
